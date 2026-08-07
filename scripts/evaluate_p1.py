from __future__ import annotations

import argparse
import json
import shutil
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from enterprise_rag.answering import EvidenceAnswerGenerator
from enterprise_rag.audit import JsonlAuditStore
from enterprise_rag.bootstrap import initialize_demo_data, load_documents, load_gold_questions
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.config import Settings
from enterprise_rag.embeddings import (
    BgeM3EmbeddingProvider,
    CrossEncoderReranker,
    HashingEmbeddingProvider,
    NemotronEmbeddingProvider,
)
from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.graph_retrieval import GraphRagRetriever
from enterprise_rag.models import Principal, QueryRequest
from enterprise_rag.retrieval import InMemoryHybridStore
from enterprise_rag.router import RuleBasedRouter
from enterprise_rag.service import EnterpriseRagService
from enterprise_rag.sql_tool import ReadOnlySqlTool


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percent), len(ordered) - 1)
    return ordered[index]


def provider(settings: Settings):
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
    reranker = None
    if settings.reranker_backend == "cross_encoder":
        reranker = CrossEncoderReranker(
            settings.reranker_model_id,
            settings.reranker_device,
        )
    store = InMemoryHybridStore(
        provider(settings),
        dense_weight=settings.dense_weight,
        reranker=reranker,
    )
    items = []
    chunking_config = settings.chunking_config()
    for document_input in load_documents(settings.corpus_path):
        document = build_document(document_input)
        items.append((document, chunk_document(document, config=chunking_config)))
    store.upsert_documents(items)
    store.commit("p1-evaluation")
    graph = VersionedKnowledgeGraph()
    graph.publish("p1-evaluation", [], store.document_ids())
    retriever = GraphRagRetriever(store, graph)
    service = EnterpriseRagService(
        settings=settings,
        router=RuleBasedRouter(),
        store=store,
        graph=graph,
        retriever=retriever,
        sql_tool=ReadOnlySqlTool(settings.demo_db_path),
        audit=JsonlAuditStore(settings.audit_path),
        answer_generator=EvidenceAnswerGenerator(),
    )
    return service


def evaluate(settings: Settings) -> dict[str, Any]:
    started = time.perf_counter()
    service = build_service(settings)
    index_seconds = time.perf_counter() - started
    gold = load_gold_questions(settings.gold_path)
    results: list[dict[str, Any]] = []

    for row in gold:
        principal = Principal(
            subject="evaluation-runner",
            roles=frozenset(row["roles"]),
            tenant_id="demo",
        )
        query_started = time.perf_counter()
        response = service.query(QueryRequest(question=str(row["question"])), principal)
        latency_ms = (time.perf_counter() - query_started) * 1000
        citation_ids = [citation.source_id for citation in response.citations]
        expected_sources = set(row.get("expected_source_ids", []))
        forbidden_sources = set(row.get("forbidden_source_ids", []))

        route_correct = response.route == row["expected_route"]
        refusal_correct = response.refused is bool(row.get("should_refuse", False))
        evidence_recalled = not expected_sources or bool(expected_sources & set(citation_ids))
        forbidden_clear = not bool(forbidden_sources & set(citation_ids))
        if expected_sources and citation_ids:
            citation_accuracy = float(citation_ids[0] in expected_sources)
        elif not citation_ids:
            citation_accuracy = 1.0
        else:
            citation_accuracy = 0.0

        expected_answer = str(row.get("expected_answer", "")).lower().replace(",", "")
        normalized_answer = response.answer.lower().replace(",", "")
        answer_match = True
        if row["category"] == "tool" and expected_answer:
            answer_match = expected_answer in normalized_answer

        results.append(
            {
                "id": row["id"],
                "category": row["category"],
                "route_correct": route_correct,
                "refusal_correct": refusal_correct,
                "evidence_recalled": evidence_recalled,
                "citation_accuracy": round(citation_accuracy, 4),
                "forbidden_clear": forbidden_clear,
                "answer_match": answer_match,
                "latency_ms": round(latency_ms, 3),
                "actual_route": response.route,
                "refused": response.refused,
                "citation_ids": citation_ids,
            }
        )

    latencies = [row["latency_ms"] for row in results]
    retrieval_rows = [row for row in results if row["category"] in {"rag", "exact_search"}]
    refusal_rows = [row for row in results if row["category"] in {"unauthorized", "no_evidence"}]
    tool_rows = [row for row in results if row["category"] == "tool"]
    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        category_rows[row["category"]].append(row)

    def rate(rows: list[dict[str, Any]], key: str) -> float:
        return round(sum(bool(row[key]) for row in rows) / max(len(rows), 1), 4)

    metrics = {
        "route_accuracy": rate(results, "route_correct"),
        "retrieval_recall_at_3": rate(retrieval_rows, "evidence_recalled"),
        "citation_accuracy": round(
            statistics.fmean(row["citation_accuracy"] for row in retrieval_rows), 4
        ),
        "refusal_accuracy": rate(refusal_rows, "refusal_correct"),
        "permission_isolation": rate(results, "forbidden_clear"),
        "tool_answer_accuracy": rate(tool_rows, "answer_match"),
        "p50_latency_ms": round(percentile(latencies, 0.5), 2),
        "p95_latency_ms": round(percentile(latencies, 0.95), 2),
        "index_seconds": round(index_seconds, 2),
    }
    thresholds = {
        "route_accuracy": 0.90,
        "retrieval_recall_at_3": 0.85,
        "citation_accuracy": 0.95,
        "refusal_accuracy": 0.90,
        "permission_isolation": 1.0,
        "tool_answer_accuracy": 0.85,
    }
    checks = {key: metrics[key] >= threshold for key, threshold in thresholds.items()}
    return {
        "backend": settings.embedding_backend,
        "dense_weight": settings.dense_weight,
        "reranker": settings.reranker_model_id if settings.reranker_backend != "none" else None,
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
        "questions": len(results),
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "passed": all(checks.values()),
        "by_category": {
            category: {
                "count": len(rows),
                "route_accuracy": rate(rows, "route_correct"),
                "evidence_recall": rate(rows, "evidence_recalled"),
                "refusal_accuracy": rate(rows, "refusal_correct"),
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
                and row["citation_accuracy"] == 1.0
                and row["forbidden_clear"]
                and row["answer_match"]
            )
        ],
    }


def write_report(report: dict[str, Any], output: Path, promote: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = [
        f"# P1 Baseline: {report['backend']}",
        "",
        f"- Model: `{report['model']}`",
        f"- Documents: {report['documents']}",
        f"- Questions: {report['questions']}",
        f"- Passed: {'yes' if report['passed'] else 'no'}",
        "",
        "| Metric | Result | Threshold | Passed |",
        "|---|---:|---:|---|",
    ]
    for key, threshold in report["thresholds"].items():
        value = report["metrics"][key]
        markdown.append(f"| {key} | {value:.4f} | {threshold:.4f} | {report['checks'][key]} |")
    markdown.extend(
        [
            "",
            f"P50 latency: {report['metrics']['p50_latency_ms']} ms",
            f"P95 latency: {report['metrics']['p95_latency_ms']} ms",
            f"Index time: {report['metrics']['index_seconds']} s",
        ]
    )
    markdown_output = output.with_suffix(".md")
    markdown_output.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    if promote:
        shutil.copyfile(output, output.parent / "baseline-current.json")
        shutil.copyfile(markdown_output, output.parent / "baseline-current.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["hashing", "nemotron", "bge_m3"], default="hashing")
    parser.add_argument("--model")
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dense-weight", type=float, default=0.75)
    parser.add_argument("--reranker", choices=["none", "cross_encoder"], default="none")
    parser.add_argument("--reranker-model", default="cross-encoder/ms-marco-MiniLM-L6-v2")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()

    output = args.output or Path(f"reports/baseline-{args.backend}.json")
    model_overrides: dict[str, str] = {}
    if args.model and args.backend == "nemotron":
        model_overrides["nemotron_model_id"] = args.model
    if args.model and args.backend == "bge_m3":
        model_overrides["bge_model_id"] = args.model
    settings = Settings(
        embedding_backend=args.backend,
        nemotron_dimensions=args.dimensions,
        nemotron_device=args.device,
        bge_device=args.device,
        graph_enabled=False,
        dense_weight=args.dense_weight,
        reranker_backend=args.reranker,
        reranker_model_id=args.reranker_model,
        reranker_device=args.device,
        audit_path=Path(f"data/evaluation-{args.backend}-audit.jsonl"),
        demo_db_path=Path(f"data/evaluation-{args.backend}.sqlite"),
        min_retrieval_score=0.08,
        **model_overrides,
    )
    report = evaluate(settings)
    write_report(report, output, args.promote)
    print(json.dumps({key: report[key] for key in ("backend", "passed", "metrics")}, indent=2))


if __name__ == "__main__":
    main()
