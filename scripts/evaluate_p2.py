from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from enterprise_rag.answering import EXCERPT_CHARS, EvidenceAnswerGenerator
from enterprise_rag.audit import JsonlAuditStore
from enterprise_rag.bootstrap import (
    initialize_demo_data,
    load_documents,
    load_gold_questions,
    load_graph_edges,
)
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.config import Settings
from enterprise_rag.embeddings import (
    BgeM3EmbeddingProvider,
    HashingEmbeddingProvider,
    NemotronEmbeddingProvider,
)
from enterprise_rag.evaluation import (
    content_recall,
    ndcg_at_k,
    reciprocal_rank,
    wilson_interval,
)
from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.graph_retrieval import GraphRagRetriever
from enterprise_rag.models import Principal, QueryRequest
from enterprise_rag.retrieval import InMemoryHybridStore
from enterprise_rag.router import RuleBasedRouter
from enterprise_rag.service import EnterpriseRagService
from enterprise_rag.sql_tool import ReadOnlySqlTool

# A gold span counts as surfaced once this share of its content tokens appears in
# the answer.
ANSWER_RECALL_THRESHOLD = 0.6

# Categories carrying a prose gold answer. The refusal slices and graph_unauthorized
# ship an empty expected_answer, and tool answers are exact values scored separately.
PROSE_ANSWER_CATEGORIES = frozenset({"rag", "exact_search", "graph_rag"})


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percent), len(ordered) - 1)
    return ordered[index]


def embedding_provider(settings: Settings):
    if settings.embedding_backend == "nemotron":
        return NemotronEmbeddingProvider(
            settings.nemotron_model_id,
            settings.nemotron_dimensions,
            settings.nemotron_device,
        )
    if settings.embedding_backend == "bge_m3":
        return BgeM3EmbeddingProvider(settings.bge_model_id, settings.bge_device)
    return HashingEmbeddingProvider(settings.hashing_dimensions)


def build_service(settings: Settings) -> EnterpriseRagService:
    initialize_demo_data(settings.demo_db_path)
    store = InMemoryHybridStore(
        embedding_provider(settings),
        dense_weight=settings.dense_weight,
    )
    items = []
    for document_input in load_documents(settings.corpus_path):
        document = build_document(document_input)
        items.append((document, chunk_document(document)))
    store.upsert_documents(items)
    store.commit(settings.index_version)

    graph = VersionedKnowledgeGraph()
    graph.publish(
        settings.index_version,
        load_graph_edges(settings.relations_path),
        store.document_ids(),
    )
    retriever = GraphRagRetriever(
        store,
        graph,
        seed_count=settings.graph_seed_count,
        max_hops=settings.graph_max_hops,
        expansion_limit=settings.graph_expansion_limit,
        score_decay=settings.graph_score_decay,
    )
    return EnterpriseRagService(
        settings=settings,
        router=RuleBasedRouter(),
        store=store,
        graph=graph,
        retriever=retriever,
        sql_tool=ReadOnlySqlTool(settings.demo_db_path),
        audit=JsonlAuditStore(settings.audit_path),
        answer_generator=EvidenceAnswerGenerator(),
    )


def rate(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(bool(row[key]) for row in rows) / max(len(rows), 1), 4)


def counts(rows: list[dict[str, Any]], key: str) -> tuple[int, int]:
    return sum(bool(row[key]) for row in rows), len(rows)


def isolation_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    successes = sum(
        row["forbidden_clear"] and row["response_forbidden_clear"] for row in rows
    )
    return successes, len(rows)


def evaluate(settings: Settings) -> dict[str, Any]:
    index_started = time.perf_counter()
    service = build_service(settings)
    index_seconds = time.perf_counter() - index_started
    gold = load_gold_questions(settings.gold_path)
    results: list[dict[str, Any]] = []

    for row in gold:
        principal = Principal(
            subject="p2-evaluation-runner",
            roles=frozenset(row["roles"]),
            tenant_id="demo",
        )
        query_started = time.perf_counter()
        response = service.query(
            QueryRequest(
                question=str(row["question"]),
                retrieval_mode=str(row.get("retrieval_mode", "auto")),
            ),
            principal,
        )
        latency_ms = (time.perf_counter() - query_started) * 1000
        citations = [citation.source_id for citation in response.citations]
        expected = set(row.get("expected_source_ids", []))
        forbidden = set(row.get("forbidden_source_ids", []))
        graph_targets = set(row.get("expected_graph_target_ids", []))
        graph_paths = response.metadata.get("graph_paths", [])
        serialized_paths = json.dumps(graph_paths, ensure_ascii=False)
        serialized_response = response.model_dump_json()
        expected_path = row.get("expected_graph_path")

        hybrid_target_recalled = False
        if row["category"] == "graph_rag":
            hybrid_response = service.query(
                QueryRequest(
                    question=str(row["question"]),
                    retrieval_mode="hybrid",
                ),
                principal,
            )
            hybrid_ids = {citation.source_id for citation in hybrid_response.citations}
            hybrid_target_recalled = bool(graph_targets & hybrid_ids)

        gold_answer = str(row.get("expected_answer", "") or "")
        answer_recall: float | None = None
        answer_span_hit: bool | None = None
        # A gold span longer than one excerpt cannot be reproduced in full no
        # matter how good retrieval is, so it is measured but not gated.
        answer_span_hit_fitting: bool | None = None
        if gold_answer and row["category"] in PROSE_ANSWER_CATEGORIES:
            answer_recall = round(content_recall(gold_answer, response.answer), 4)
            answer_span_hit = answer_recall >= ANSWER_RECALL_THRESHOLD
            if len(gold_answer) <= EXCERPT_CHARS:
                answer_span_hit_fitting = answer_span_hit

        tool_answer_correct: bool | None = None
        if row["category"] == "tool" and gold_answer:
            normalized_gold = gold_answer.lower().replace(",", "")
            tool_answer_correct = normalized_gold in response.answer.lower().replace(",", "")

        results.append(
            {
                "id": row["id"],
                "category": row["category"],
                "route_correct": response.route == row["expected_route"],
                "answer_recall": answer_recall,
                "answer_span_hit": answer_span_hit,
                "answer_span_hit_fitting": answer_span_hit_fitting,
                "gold_answer_chars": len(gold_answer) if gold_answer else None,
                "tool_answer_correct": tool_answer_correct,
                "reciprocal_rank": round(reciprocal_rank(citations, expected), 4)
                if expected
                else None,
                "ndcg_at_3": round(ndcg_at_k(citations, expected, 3), 4) if expected else None,
                "refusal_correct": response.refused is bool(row.get("should_refuse", False)),
                "evidence_recalled": not expected or bool(expected & set(citations)),
                "all_evidence_recalled": not expected or expected.issubset(citations),
                "top1_correct": not expected or bool(citations and citations[0] in expected),
                "graph_target_recalled": not graph_targets or bool(graph_targets & set(citations)),
                "graph_path_correct": expected_path is None
                or any(path.get("node_ids") == expected_path for path in graph_paths),
                "hybrid_target_recalled": hybrid_target_recalled,
                "forbidden_clear": not bool(forbidden & set(citations))
                and not any(source_id in serialized_paths for source_id in forbidden),
                "response_forbidden_clear": not any(
                    source_id.lower() in serialized_response.lower()
                    for source_id in forbidden
                ),
                "latency_ms": round(latency_ms, 3),
                "citation_ids": citations,
                "graph_used": bool(response.metadata.get("graph_used", False)),
                "graph_paths": graph_paths,
            }
        )

    p1_retrieval = [
        row for row in results if row["category"] in {"rag", "exact_search"}
    ]
    graph_rows = [row for row in results if row["category"] == "graph_rag"]
    graph_acl_rows = [
        row for row in results if row["category"] == "graph_unauthorized"
    ]
    refusal_rows = [
        row for row in results if row["category"] in {"unauthorized", "no_evidence"}
    ]
    tool_rows = [row for row in results if row["tool_answer_correct"] is not None]
    answer_rows = [row for row in results if row["answer_recall"] is not None]
    fitting_answer_rows = [
        row for row in results if row["answer_span_hit_fitting"] is not None
    ]
    ranked_rows = [row for row in results if row["reciprocal_rank"] is not None]
    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        category_rows[row["category"]].append(row)

    latencies = [row["latency_ms"] for row in results]
    graph_target_recall = rate(graph_rows, "graph_target_recalled")
    hybrid_target_recall = rate(graph_rows, "hybrid_target_recalled")
    metrics = {
        "route_accuracy": rate(results, "route_correct"),
        "p1_retrieval_recall_at_3": rate(p1_retrieval, "evidence_recalled"),
        "p1_top1_citation_accuracy": rate(p1_retrieval, "top1_correct"),
        "graph_joint_recall_at_3": rate(graph_rows, "all_evidence_recalled"),
        "graph_target_recall_at_3": graph_target_recall,
        "graph_path_accuracy": rate(graph_rows, "graph_path_correct"),
        "graph_hybrid_target_recall_at_3": hybrid_target_recall,
        "graph_recall_gain": round(graph_target_recall - hybrid_target_recall, 4),
        "graph_acl_isolation": round(
            sum(
                row["forbidden_clear"] and row["response_forbidden_clear"]
                for row in graph_acl_rows
            )
            / max(len(graph_acl_rows), 1),
            4,
        ),
        "permission_isolation": round(
            sum(
                row["forbidden_clear"] and row["response_forbidden_clear"]
                for row in results
            )
            / max(len(results), 1),
            4,
        ),
        "refusal_accuracy": rate(refusal_rows, "refusal_correct"),
        "tool_answer_accuracy": rate(tool_rows, "tool_answer_correct"),
        "answer_span_hit_rate": rate(answer_rows, "answer_span_hit"),
        "answer_span_hit_rate_fitting": rate(fitting_answer_rows, "answer_span_hit_fitting"),
        "answer_content_recall": round(
            sum(row["answer_recall"] for row in answer_rows) / max(len(answer_rows), 1),
            4,
        ),
        "mrr_at_3": round(
            sum(row["reciprocal_rank"] for row in ranked_rows) / max(len(ranked_rows), 1),
            4,
        ),
        "ndcg_at_3": round(
            sum(row["ndcg_at_3"] for row in ranked_rows) / max(len(ranked_rows), 1),
            4,
        ),
        "p50_latency_ms": round(percentile(latencies, 0.5), 2),
        "p95_latency_ms": round(percentile(latencies, 0.95), 2),
        "index_seconds": round(index_seconds, 2),
    }
    thresholds = {
        "route_accuracy": 0.90,
        "p1_retrieval_recall_at_3": 0.85,
        "p1_top1_citation_accuracy": 0.95,
        "graph_joint_recall_at_3": 0.80,
        "graph_target_recall_at_3": 0.85,
        "graph_path_accuracy": 0.95,
        "graph_recall_gain": 0.15,
        "graph_acl_isolation": 1.0,
        "permission_isolation": 1.0,
        "refusal_accuracy": 0.90,
        "tool_answer_accuracy": 0.85,
        # Gated on the length-controlled subset only. The unrestricted
        # answer_span_hit_rate is reported but not gated, because it falls
        # monotonically with gold-answer length regardless of retrieval quality.
        #
        # This is a regression floor, not a quality target. The metric is new and
        # there is no principled prior for a "good" value, so the floor sits below
        # the measured Nemotron baseline (0.619, 95% CI 0.524-0.706) far enough to
        # fire on real degradation rather than on sampling noise. Raising it is a
        # roadmap item, tracked with the excerpt-truncation fix it depends on.
        "answer_span_hit_rate_fitting": 0.55,
    }
    checks = {key: metrics[key] >= threshold for key, threshold in thresholds.items()}

    # Wilson bounds on every proportion. Several slices are n=20 and saturate at
    # 1.0, where a bare point estimate overstates what the sample can support.
    proportion_samples = {
        "route_accuracy": counts(results, "route_correct"),
        "p1_retrieval_recall_at_3": counts(p1_retrieval, "evidence_recalled"),
        "p1_top1_citation_accuracy": counts(p1_retrieval, "top1_correct"),
        "graph_joint_recall_at_3": counts(graph_rows, "all_evidence_recalled"),
        "graph_target_recall_at_3": counts(graph_rows, "graph_target_recalled"),
        "graph_path_accuracy": counts(graph_rows, "graph_path_correct"),
        "graph_hybrid_target_recall_at_3": counts(graph_rows, "hybrid_target_recalled"),
        "graph_acl_isolation": isolation_counts(graph_acl_rows),
        "permission_isolation": isolation_counts(results),
        "refusal_accuracy": counts(refusal_rows, "refusal_correct"),
        "tool_answer_accuracy": counts(tool_rows, "tool_answer_correct"),
        "answer_span_hit_rate": counts(answer_rows, "answer_span_hit"),
        "answer_span_hit_rate_fitting": counts(fitting_answer_rows, "answer_span_hit_fitting"),
    }
    confidence_intervals = {
        key: {
            "successes": successes,
            "n": total,
            "low": round(wilson_interval(successes, total)[0], 4),
            "high": round(wilson_interval(successes, total)[1], 4),
        }
        for key, (successes, total) in proportion_samples.items()
    }
    return {
        "stage": "p2-experimental",
        "backend": settings.embedding_backend,
        "model": (
            settings.nemotron_model_id
            if settings.embedding_backend == "nemotron"
            else settings.bge_model_id
            if settings.embedding_backend == "bge_m3"
            else f"hashing-{settings.hashing_dimensions}"
        ),
        "dimensions": (
            settings.nemotron_dimensions
            if settings.embedding_backend == "nemotron"
            else 1024
            if settings.embedding_backend == "bge_m3"
            else settings.hashing_dimensions
        ),
        "documents": service.document_count(),
        "relations": service.current_index_info().relations,
        "questions": len(results),
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "confidence_intervals": confidence_intervals,
        "passed": all(checks.values()),
        "by_category": {
            category: {
                "count": len(rows),
                "route_accuracy": rate(rows, "route_correct"),
                "evidence_recall": rate(rows, "evidence_recalled"),
                "permission_isolation": rate(rows, "forbidden_clear"),
            }
            for category, rows in sorted(category_rows.items())
        },
        "failures": [
            row
            for row in results
            if not (
                row["route_correct"]
                and row["refusal_correct"]
                and row["evidence_recalled"]
                and row["forbidden_clear"]
                and row["response_forbidden_clear"]
                and (row["category"] != "graph_rag" or row["all_evidence_recalled"])
                and row["graph_path_correct"]
                # None means no gold answer, or one too long to fit an excerpt;
                # neither is a failure the retriever can be held to.
                and row["answer_span_hit_fitting"] is not False
                and row["tool_answer_correct"] is not False
            )
        ],
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# P2 Graph RAG Baseline: {report['backend']}",
        "",
        f"- Documents: {report['documents']}",
        f"- Relations: {report['relations']}",
        f"- Questions: {report['questions']}",
        f"- Passed: {'yes' if report['passed'] else 'no'}",
        "",
        "| Metric | Result | 95% CI | n | Threshold | Passed |",
        "|---|---:|:--:|---:|---:|---|",
    ]
    intervals = report.get("confidence_intervals", {})
    for key, threshold in report["thresholds"].items():
        interval = intervals.get(key)
        span = f"{interval['low']:.4f}–{interval['high']:.4f}" if interval else "—"
        size = str(interval["n"]) if interval else "—"
        lines.append(
            f"| {key} | {report['metrics'][key]:.4f} | {span} | {size} | "
            f"{threshold:.4f} | {report['checks'][key]} |"
        )
    lines.extend(
        [
            "",
            "## Ranking and answer quality",
            "",
            f"- MRR@3: {report['metrics']['mrr_at_3']:.4f}",
            f"- nDCG@3: {report['metrics']['ndcg_at_3']:.4f}",
            f"- Mean answer content recall: {report['metrics']['answer_content_recall']:.4f}",
            f"- Answer span hit rate, all gold spans: "
            f"{report['metrics']['answer_span_hit_rate']:.4f} (not gated; falls with "
            f"gold length, since one excerpt holds {EXCERPT_CHARS} chars)",
            "",
            f"P50 latency: {report['metrics']['p50_latency_ms']} ms",
            f"P95 latency: {report['metrics']['p95_latency_ms']} ms",
            f"Index time: {report['metrics']['index_seconds']} s",
        ]
    )
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["hashing", "nemotron", "bge_m3"], default="hashing")
    parser.add_argument("--model")
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/processed/techqa_p2"),
    )
    args = parser.parse_args()

    overrides: dict[str, str] = {}
    if args.model and args.backend == "nemotron":
        overrides["nemotron_model_id"] = args.model
    if args.model and args.backend == "bge_m3":
        overrides["bge_model_id"] = args.model
    settings = Settings(
        embedding_backend=args.backend,
        nemotron_dimensions=args.dimensions,
        nemotron_device=args.device,
        bge_device=args.device,
        corpus_path=args.data / "documents.jsonl",
        relations_path=args.data / "relations.jsonl",
        gold_path=args.data / "golden_questions.jsonl",
        graph_enabled=True,
        index_version="p2-evaluation-v1",
        graph_state_path=Path("data/p2-evaluation-graph-state.json"),
        audit_path=Path(f"data/p2-evaluation-{args.backend}-audit.jsonl"),
        demo_db_path=Path(f"data/p2-evaluation-{args.backend}.sqlite"),
        min_retrieval_score=0.08,
        **overrides,
    )
    report = evaluate(settings)
    output = args.output or Path(f"reports/p2-baseline-{args.backend}.json")
    write_report(report, output)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("backend", "passed", "documents", "relations", "metrics")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
