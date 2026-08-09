from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from enterprise_rag.answering import EXCERPT_CHARS
from enterprise_rag.audit import JsonlAuditStore
from enterprise_rag.bootstrap import (
    initialize_demo_data,
    load_documents,
    load_gold_questions,
    load_graph_edges,
)
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.components import (
    RuntimeComponents,
    build_runtime_components,
    describe_runtime_components,
)
from enterprise_rag.config import Settings
from enterprise_rag.evaluation import (
    content_recall,
    ndcg_at_k,
    reciprocal_rank,
    wilson_interval,
)
from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.graph_retrieval import GraphRagRetriever
from enterprise_rag.models import Principal, QueryRequest
from enterprise_rag.router import RuleBasedRouter
from enterprise_rag.service import EnterpriseRagService
from enterprise_rag.sql_tool import ReadOnlySqlTool

# A gold span counts as surfaced once this share of its content tokens appears in
# the answer.
ANSWER_RECALL_THRESHOLD = 0.6

# Categories carrying a prose gold answer. The refusal slices and graph_unauthorized
# ship an empty expected_answer, and tool answers are exact values scored separately.
PROSE_ANSWER_CATEGORIES = frozenset({"rag", "exact_search", "graph_rag"})
EVALUATION_CATEGORIES = frozenset(
    {
        "rag",
        "exact_search",
        "tool",
        "unauthorized",
        "no_evidence",
        "graph_rag",
        "graph_unauthorized",
    }
)
CONFIDENCE_GATED_METRICS = frozenset(
    {
        "route_accuracy",
        "semantic_rag_recall_at_3",
        "semantic_rag_top1_citation_accuracy",
        "graph_joint_recall_at_3",
        "graph_target_recall_at_3",
        "graph_path_accuracy",
        "refusal_accuracy",
        "tool_answer_accuracy",
        "answer_span_hit_rate_fitting",
    }
)
METRIC_LABELS = {
    "route_accuracy": "Route accuracy",
    "p1_retrieval_recall_at_3": "Base retrieval Recall@3",
    "p1_top1_citation_accuracy": "Base retrieval Top-1 citation accuracy",
    "semantic_rag_recall_at_3": "Semantic RAG Recall@3",
    "semantic_rag_top1_citation_accuracy": "Semantic RAG Top-1 citation accuracy",
    "graph_joint_recall_at_3": "Graph joint Recall@3",
    "graph_target_recall_at_3": "Graph target Recall@3",
    "graph_path_accuracy": "Graph path accuracy",
    "graph_recall_gain": "Graph recall gain",
    "graph_acl_isolation": "Graph ACL isolation",
    "permission_isolation": "Permission isolation",
    "refusal_accuracy": "Refusal accuracy",
    "tool_answer_accuracy": "Tool answer accuracy",
    "answer_span_hit_rate_fitting": "Fitting answer-span hit rate",
}


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percent), len(ordered) - 1)
    return ordered[index]


def _build_service_and_components(
    settings: Settings,
) -> tuple[EnterpriseRagService, RuntimeComponents]:
    initialize_demo_data(settings.demo_db_path)
    components = build_runtime_components(settings)
    store = components.store
    if settings.vector_backend == "milvus":
        if not store.has_version(settings.index_version):
            available = ", ".join(store.versions()) or "none"
            raise RuntimeError(
                f"Milvus index version {settings.index_version!r} is unavailable "
                f"(available: {available})"
            )
        # Attach the immutable published snapshot. Evaluation must not rebuild it.
        store.rollback(settings.index_version)
    else:
        items = []
        chunking_config = settings.chunking_config()
        for document_input in load_documents(settings.corpus_path):
            document = build_document(document_input)
            items.append((document, chunk_document(document, config=chunking_config)))
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
    service = EnterpriseRagService(
        settings=settings,
        router=RuleBasedRouter(),
        store=store,
        graph=graph,
        retriever=retriever,
        sql_tool=ReadOnlySqlTool(settings.demo_db_path),
        audit=JsonlAuditStore(settings.audit_path),
        answer_generator=components.answer_generator,
    )
    return service, components


def build_service(settings: Settings) -> EnterpriseRagService:
    service, _ = _build_service_and_components(settings)
    return service


def rate(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(bool(row[key]) for row in rows) / max(len(rows), 1), 4)


def counts(rows: list[dict[str, Any]], key: str) -> tuple[int, int]:
    return sum(bool(row[key]) for row in rows), len(rows)


def isolation_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    successes = sum(row["forbidden_clear"] and row["response_forbidden_clear"] for row in rows)
    return successes, len(rows)


def _retrieval_slice_metrics(
    rows: list[dict[str, Any]],
) -> dict[str, float]:
    return {
        "recall_at_3": rate(rows, "evidence_recalled"),
        "top1_citation_accuracy": rate(rows, "top1_correct"),
    }


def _confidence_checks(
    thresholds: dict[str, float],
    confidence_intervals: dict[str, dict[str, float | int]],
) -> dict[str, bool]:
    """Gate quality proportions on their Wilson lower bound.

    Zero-tolerance isolation checks remain point-estimate gates: a confidence
    lower bound can never equal 1.0 for a finite sample. Their intervals are
    still reported so sample uncertainty remains visible.
    """
    return {
        key: float(confidence_intervals[key]["low"]) >= thresholds[key]
        for key in sorted(CONFIDENCE_GATED_METRICS)
        if key in thresholds and key in confidence_intervals
    }


def _quality_thresholds(
    categories: set[str],
    *,
    has_fitting_answers: bool,
) -> dict[str, float]:
    thresholds = {
        "route_accuracy": 0.90,
        "permission_isolation": 1.0,
    }
    if categories & {"rag", "exact_search"}:
        thresholds.update(
            {
                "p1_retrieval_recall_at_3": 0.85,
                "p1_top1_citation_accuracy": 0.95,
            }
        )
    if "rag" in categories:
        thresholds.update(
            {
                "semantic_rag_recall_at_3": 0.85,
                "semantic_rag_top1_citation_accuracy": 0.95,
            }
        )
    if "graph_rag" in categories:
        thresholds.update(
            {
                "graph_joint_recall_at_3": 0.80,
                "graph_target_recall_at_3": 0.85,
                "graph_path_accuracy": 0.95,
                "graph_recall_gain": 0.15,
            }
        )
    if "graph_unauthorized" in categories:
        thresholds["graph_acl_isolation"] = 1.0
    if categories & {"unauthorized", "no_evidence"}:
        thresholds["refusal_accuracy"] = 0.90
    if "tool" in categories:
        thresholds["tool_answer_accuracy"] = 0.85
    if has_fitting_answers:
        # This remains a regression floor rather than a quality target. It is
        # gated only on gold spans short enough to fit in one excerpt.
        thresholds["answer_span_hit_rate_fitting"] = 0.55
    return thresholds


def _candidate_trace(
    settings: Settings,
    components: RuntimeComponents,
    question: str,
    principal: Principal,
    expected: set[str],
    limit: int,
    *,
    require_full: bool = False,
) -> list[dict[str, Any]]:
    hits = components.store.search(
        question,
        principal.roles,
        top_k=limit,
        exact=False,
        min_score=settings.min_retrieval_score,
    )
    document_ids = [hit.chunk.document_id for hit in hits]
    if len(document_ids) != len(set(document_ids)):
        raise RuntimeError("candidate diagnostics returned duplicate documents")
    if require_full and len(hits) != limit:
        raise RuntimeError(
            "candidate diagnostics require exactly distinct documents: "
            f"required={limit}, returned={len(hits)}, unique={len(set(document_ids))}"
        )
    base_order = sorted(
        enumerate(hits),
        key=lambda item: (-item[1].score, item[0]),
    )
    base_rank_by_id = {
        hit.chunk.document_id: rank for rank, (_, hit) in enumerate(base_order, start=1)
    }
    return [
        {
            "document_id": hit.chunk.document_id,
            "title": hit.chunk.title,
            "business_class": hit.chunk.business_class,
            "anchor": hit.chunk.anchor,
            "base_rank": base_rank_by_id[hit.chunk.document_id],
            "final_rank": final_rank,
            "base_score": hit.score,
            "lexical_score": hit.lexical_score,
            "dense_score": hit.dense_score,
            "is_gold": hit.chunk.document_id in expected,
            "requires_relevance_review": (bool(expected) and hit.chunk.document_id not in expected),
        }
        for final_rank, hit in enumerate(hits, start=1)
    ]


def _candidate_funnel(
    candidate_traces: list[dict[str, Any]],
    semantic_rag_rows: list[dict[str, Any]],
    *,
    candidate_limit: int,
    output_limit: int,
    reranked: bool,
) -> dict[str, Any]:
    """Split end-to-end misses into candidate-recall and downstream-ranking stages."""
    if not candidate_traces:
        return {
            "enabled": False,
            "candidate_limit": candidate_limit,
            "output_limit": output_limit,
            "reranked": reranked,
            "queries": 0,
            "candidate_hit_count": 0,
            "candidate_miss_count": 0,
            "candidate_miss_ids": [],
            "candidate_hit_but_top3_miss_ids": [],
            "candidate_hit_but_top1_miss_ids": [],
            "base_top3_hit_ids": [],
            "base_top1_hit_ids": [],
            "rerank_rescue_ids": [],
            "rerank_regression_ids": [],
            "rerank_top1_rescue_ids": [],
            "rerank_top1_regression_ids": [],
            "candidate_hit_not_promoted_ids": [],
            "final_top3_hit_outside_candidate_ids": [],
            "set_relationship_valid": None,
        }

    result_by_id = {str(row["id"]): row for row in semantic_rag_rows}
    trace_by_id = {str(trace["id"]): trace for trace in candidate_traces}
    if trace_by_id.keys() != result_by_id.keys():
        missing_traces = sorted(result_by_id.keys() - trace_by_id.keys())
        missing_results = sorted(trace_by_id.keys() - result_by_id.keys())
        raise RuntimeError(
            "candidate diagnostics and semantic results cover different queries: "
            f"missing_traces={missing_traces}, missing_results={missing_results}"
        )

    candidate_hit_ids = {
        row_id for row_id, trace in trace_by_id.items() if trace["gold_in_candidates"]
    }
    all_ids = set(trace_by_id)
    base_top3_hit_ids = {
        row_id
        for row_id, trace in trace_by_id.items()
        if any(
            candidate["is_gold"] and candidate["base_rank"] <= output_limit
            for candidate in trace["candidates"]
        )
    }
    base_top1_hit_ids = {
        row_id
        for row_id, trace in trace_by_id.items()
        if any(
            candidate["is_gold"] and candidate["base_rank"] == 1
            for candidate in trace["candidates"]
        )
    }
    final_top3_hit_ids = {
        row_id for row_id, row in result_by_id.items() if row["evidence_recalled"]
    }
    final_top1_hit_ids = {
        row_id for row_id, row in result_by_id.items() if row["top1_correct"]
    }
    eligible_final_top3_ids = final_top3_hit_ids & candidate_hit_ids
    eligible_final_top1_ids = final_top1_hit_ids & candidate_hit_ids
    final_top3_outside_candidate_ids = final_top3_hit_ids - candidate_hit_ids

    return {
        "enabled": True,
        "candidate_limit": candidate_limit,
        "output_limit": output_limit,
        "reranked": reranked,
        "queries": len(all_ids),
        "candidate_hit_count": len(candidate_hit_ids),
        "candidate_miss_count": len(all_ids - candidate_hit_ids),
        "candidate_miss_ids": sorted(all_ids - candidate_hit_ids),
        "candidate_recall": round(len(candidate_hit_ids) / max(len(all_ids), 1), 4),
        "base_top3_hit_count": len(base_top3_hit_ids),
        "base_top3_hit_ids": sorted(base_top3_hit_ids),
        "base_top1_hit_count": len(base_top1_hit_ids),
        "base_top1_hit_ids": sorted(base_top1_hit_ids),
        "base_conditional_recall_at_3": round(
            len(base_top3_hit_ids) / max(len(candidate_hit_ids), 1), 4
        ),
        "base_conditional_top1_accuracy": round(
            len(base_top1_hit_ids) / max(len(candidate_hit_ids), 1), 4
        ),
        "final_top3_hit_count": len(final_top3_hit_ids),
        "final_top1_hit_count": len(final_top1_hit_ids),
        "eligible_final_top3_hit_count": len(eligible_final_top3_ids),
        "eligible_final_top1_hit_count": len(eligible_final_top1_ids),
        "conditional_recall_at_3": round(
            len(eligible_final_top3_ids) / max(len(candidate_hit_ids), 1), 4
        ),
        "conditional_top1_accuracy": round(
            len(eligible_final_top1_ids) / max(len(candidate_hit_ids), 1), 4
        ),
        "candidate_hit_but_top3_miss_ids": sorted(candidate_hit_ids - final_top3_hit_ids),
        "candidate_hit_but_top1_miss_ids": sorted(candidate_hit_ids - final_top1_hit_ids),
        "rerank_rescue_ids": sorted(eligible_final_top3_ids - base_top3_hit_ids),
        "rerank_regression_ids": sorted(base_top3_hit_ids - final_top3_hit_ids),
        "rerank_top1_rescue_ids": sorted(eligible_final_top1_ids - base_top1_hit_ids),
        "rerank_top1_regression_ids": sorted(base_top1_hit_ids - final_top1_hit_ids),
        "candidate_hit_not_promoted_ids": sorted(
            candidate_hit_ids - base_top3_hit_ids - final_top3_hit_ids
        ),
        "final_top3_hit_outside_candidate_ids": sorted(final_top3_outside_candidate_ids),
        "set_relationship_valid": not final_top3_outside_candidate_ids,
    }


def evaluate(
    settings: Settings,
    *,
    candidate_diagnostics: bool = False,
    candidate_limit: int = 20,
    categories: frozenset[str] | None = None,
) -> dict[str, Any]:
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    index_started = time.perf_counter()
    service, components = _build_service_and_components(settings)
    index_seconds = time.perf_counter() - index_started
    if categories is not None:
        unknown_categories = categories - EVALUATION_CATEGORIES
        if unknown_categories:
            unknown = ", ".join(sorted(unknown_categories))
            raise ValueError(f"unknown evaluation categories: {unknown}")
        if not categories:
            raise ValueError("categories must not be empty")
    all_gold = load_gold_questions(settings.gold_path)
    eligible_gold = [row for row in all_gold if row.get("score_enabled", True)]
    gold = [row for row in eligible_gold if categories is None or row["category"] in categories]
    excluded_gold = [row for row in all_gold if not row.get("score_enabled", True)]
    if categories is not None and not gold:
        raise ValueError("no scored gold rows match the selected categories")
    results: list[dict[str, Any]] = []
    candidate_traces: list[dict[str, Any]] = []

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
        citations = [citation.source_id for citation in response.citations[: settings.top_k]]
        expected = set(row.get("expected_source_ids", []))
        forbidden = set(row.get("forbidden_source_ids", []))
        graph_targets = set(row.get("expected_graph_target_ids", []))
        graph_paths = response.metadata.get("graph_paths", [])
        serialized_paths = json.dumps(graph_paths, ensure_ascii=False)
        serialized_response = response.model_dump_json()
        expected_path = row.get("expected_graph_path")

        if candidate_diagnostics and row["category"] == "rag":
            candidates = _candidate_trace(
                settings,
                components,
                str(row["question"]),
                principal,
                expected,
                candidate_limit,
                require_full=True,
            )
            candidate_traces.append(
                {
                    "id": row["id"],
                    "question": row["question"],
                    "expected_source_ids": sorted(expected),
                    "gold_in_candidates": any(candidate["is_gold"] for candidate in candidates),
                    "candidates": candidates,
                }
            )

        hybrid_target_recalled = False
        if row["category"] == "graph_rag":
            hybrid_response = service.query(
                QueryRequest(
                    question=str(row["question"]),
                    retrieval_mode="hybrid",
                ),
                principal,
            )
            hybrid_ids = {
                citation.source_id for citation in hybrid_response.citations[: settings.top_k]
            }
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
                    source_id.lower() in serialized_response.lower() for source_id in forbidden
                ),
                "latency_ms": round(latency_ms, 3),
                "citation_ids": citations,
                "graph_used": bool(response.metadata.get("graph_used", False)),
                "graph_paths": graph_paths,
            }
        )

    p1_retrieval = [row for row in results if row["category"] in {"rag", "exact_search"}]
    semantic_rag_rows = [row for row in results if row["category"] == "rag"]
    exact_search_rows = [row for row in results if row["category"] == "exact_search"]
    graph_rows = [row for row in results if row["category"] == "graph_rag"]
    graph_acl_rows = [row for row in results if row["category"] == "graph_unauthorized"]
    refusal_rows = [row for row in results if row["category"] in {"unauthorized", "no_evidence"}]
    tool_rows = [row for row in results if row["tool_answer_correct"] is not None]
    answer_rows = [row for row in results if row["answer_recall"] is not None]
    fitting_answer_rows = [row for row in results if row["answer_span_hit_fitting"] is not None]
    ranked_rows = [row for row in results if row["reciprocal_rank"] is not None]
    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        category_rows[row["category"]].append(row)

    latencies = [row["latency_ms"] for row in results]
    graph_target_recall = rate(graph_rows, "graph_target_recalled")
    hybrid_target_recall = rate(graph_rows, "hybrid_target_recalled")
    semantic_metrics = _retrieval_slice_metrics(semantic_rag_rows)
    exact_search_metrics = _retrieval_slice_metrics(exact_search_rows)
    retrieval_funnel = _candidate_funnel(
        candidate_traces,
        semantic_rag_rows,
        candidate_limit=candidate_limit,
        output_limit=settings.top_k,
        reranked=settings.reranker_backend != "none",
    )
    metrics = {
        "route_accuracy": rate(results, "route_correct"),
        "p1_retrieval_recall_at_3": rate(p1_retrieval, "evidence_recalled"),
        "p1_top1_citation_accuracy": rate(p1_retrieval, "top1_correct"),
        "semantic_rag_recall_at_3": semantic_metrics["recall_at_3"],
        "semantic_rag_top1_citation_accuracy": semantic_metrics["top1_citation_accuracy"],
        "exact_search_recall_at_3": exact_search_metrics["recall_at_3"],
        "exact_search_top1_citation_accuracy": exact_search_metrics["top1_citation_accuracy"],
        "graph_joint_recall_at_3": rate(graph_rows, "all_evidence_recalled"),
        "graph_target_recall_at_3": graph_target_recall,
        "graph_path_accuracy": rate(graph_rows, "graph_path_correct"),
        "graph_hybrid_target_recall_at_3": hybrid_target_recall,
        "graph_recall_gain": round(graph_target_recall - hybrid_target_recall, 4),
        "graph_acl_isolation": round(
            sum(
                row["forbidden_clear"] and row["response_forbidden_clear"] for row in graph_acl_rows
            )
            / max(len(graph_acl_rows), 1),
            4,
        ),
        "permission_isolation": round(
            sum(row["forbidden_clear"] and row["response_forbidden_clear"] for row in results)
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
    if candidate_diagnostics:
        metrics[f"semantic_rag_recall_at_{candidate_limit}"] = retrieval_funnel[
            "candidate_recall"
        ]
        metrics["semantic_rag_base_conditional_recall_at_3"] = retrieval_funnel[
            "base_conditional_recall_at_3"
        ]
        metrics["semantic_rag_base_conditional_top1_accuracy"] = retrieval_funnel[
            "base_conditional_top1_accuracy"
        ]
        metrics["semantic_rag_conditional_recall_at_3"] = retrieval_funnel[
            "conditional_recall_at_3"
        ]
        metrics["semantic_rag_conditional_top1_accuracy"] = retrieval_funnel[
            "conditional_top1_accuracy"
        ]
    evaluated_categories = set(category_rows)
    thresholds = _quality_thresholds(
        evaluated_categories,
        has_fitting_answers=bool(fitting_answer_rows),
    )
    checks = {key: metrics[key] >= threshold for key, threshold in thresholds.items()}

    # Wilson bounds on every proportion. Several slices are n=20 and saturate at
    # 1.0, where a bare point estimate overstates what the sample can support.
    proportion_samples = {
        "route_accuracy": counts(results, "route_correct"),
        "p1_retrieval_recall_at_3": counts(p1_retrieval, "evidence_recalled"),
        "p1_top1_citation_accuracy": counts(p1_retrieval, "top1_correct"),
        "semantic_rag_recall_at_3": counts(semantic_rag_rows, "evidence_recalled"),
        "semantic_rag_top1_citation_accuracy": counts(semantic_rag_rows, "top1_correct"),
        "exact_search_recall_at_3": counts(exact_search_rows, "evidence_recalled"),
        "exact_search_top1_citation_accuracy": counts(exact_search_rows, "top1_correct"),
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
    if candidate_diagnostics:
        proportion_samples.update(
            {
                f"semantic_rag_recall_at_{candidate_limit}": (
                    retrieval_funnel["candidate_hit_count"],
                    retrieval_funnel["queries"],
                ),
                "semantic_rag_base_conditional_recall_at_3": (
                    retrieval_funnel["base_top3_hit_count"],
                    retrieval_funnel["candidate_hit_count"],
                ),
                "semantic_rag_base_conditional_top1_accuracy": (
                    retrieval_funnel["base_top1_hit_count"],
                    retrieval_funnel["candidate_hit_count"],
                ),
                "semantic_rag_conditional_recall_at_3": (
                    retrieval_funnel["eligible_final_top3_hit_count"],
                    retrieval_funnel["candidate_hit_count"],
                ),
                "semantic_rag_conditional_top1_accuracy": (
                    retrieval_funnel["eligible_final_top1_hit_count"],
                    retrieval_funnel["candidate_hit_count"],
                ),
            }
        )
    confidence_intervals = {
        key: {
            "successes": successes,
            "n": total,
            "low": round(wilson_interval(successes, total)[0], 4),
            "high": round(wilson_interval(successes, total)[1], 4),
        }
        for key, (successes, total) in proportion_samples.items()
    }
    confidence_checks = _confidence_checks(thresholds, confidence_intervals)
    runtime_configuration = describe_runtime_components(settings, components)
    reranker_calls = getattr(components.reranker, "call_count", None)
    reranker_degraded_calls = getattr(components.reranker, "degraded_count", None)
    reranker_external_calls = getattr(components.reranker, "external_call_count", None)
    reranker_cache_hits = getattr(components.reranker, "cache_hit_count", None)
    reranker_deterministic_calls = getattr(
        components.reranker, "deterministic_call_count", None
    )
    reranker_http_attempts = getattr(components.reranker, "http_attempt_count", None)
    reranker_judgement_digest = getattr(components.reranker, "judgement_digest", None)
    return {
        "stage": f"{settings.corpus_path.parent.name.removeprefix('techqa_')}-experimental",
        "vector_backend": settings.vector_backend,
        "index_version": settings.index_version,
        "dense_weight": settings.dense_weight,
        "top_k": settings.top_k,
        "min_retrieval_score": settings.min_retrieval_score,
        "milvus_search_multiplier": settings.milvus_search_multiplier,
        "milvus_search_mode": settings.milvus_search_mode,
        "milvus_fielded_search_enabled": settings.milvus_fielded_search_enabled,
        "query_rewrite_enabled": settings.query_rewrite_enabled,
        "rerank_strategy": settings.rerank_strategy,
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
        "reranker_backend": settings.reranker_backend,
        "reranker": runtime_configuration["reranker"]["model"],
        "answer_generator_backend": settings.llm_backend,
        "answer_generator": runtime_configuration["answer_generator"]["effective_class"],
        "configuration": runtime_configuration,
        "reranker_stats": {
            "calls": reranker_calls,
            "degraded_calls": reranker_degraded_calls,
            "external_calls": reranker_external_calls,
            "cache_hits": reranker_cache_hits,
            "deterministic_calls": reranker_deterministic_calls,
            "http_attempts": reranker_http_attempts,
            "judgement_digest": reranker_judgement_digest,
            "degraded_rate": round(
                reranker_degraded_calls / reranker_calls,
                4,
            )
            if reranker_calls
            else 0.0
            if reranker_calls == 0
            else None,
        },
        "documents": service.document_count(),
        "relations": service.current_index_info().relations,
        "questions": len(results),
        "questions_total": len(all_gold),
        "questions_eligible": len(eligible_gold),
        "evaluation_categories": sorted(evaluated_categories),
        "questions_excluded": len(excluded_gold),
        "excluded_gold_ids": [row["id"] for row in excluded_gold],
        "gold_path": str(settings.gold_path),
        "gold_sha256": (
            sha256(settings.gold_path.read_bytes()).hexdigest()
            if settings.gold_path.exists()
            else None
        ),
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "confidence_checks": confidence_checks,
        "confidence_intervals": confidence_intervals,
        "candidate_diagnostics": {
            "enabled": candidate_diagnostics,
            "limit": candidate_limit,
            "reranked": settings.reranker_backend != "none",
            "all_queries_full": (
                all(len(trace["candidates"]) == candidate_limit for trace in candidate_traces)
                if candidate_diagnostics
                else None
            ),
            "minimum_unique_documents": (
                min((len(trace["candidates"]) for trace in candidate_traces), default=0)
                if candidate_diagnostics
                else None
            ),
            "queries": candidate_traces,
        },
        "retrieval_funnel": retrieval_funnel,
        "passed_point_estimates": all(checks.values()),
        "passed": all(checks.values()) and all(confidence_checks.values()),
        "by_category": {
            category: {
                "count": len(rows),
                "route_accuracy": rate(rows, "route_correct"),
                "evidence_recall": rate(rows, "evidence_recalled"),
                "top1_citation_accuracy": rate(rows, "top1_correct"),
                "permission_isolation": rate(rows, "forbidden_clear"),
            }
            for category, rows in sorted(category_rows.items())
        },
        "results": results,
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
        f"# {report['stage'].removesuffix('-experimental').upper()} Graph RAG Evaluation: "
        f"{report['backend']} on {report['vector_backend']}",
        "",
        f"- Index version: {report['index_version']}",
        f"- Dense weight: {report['dense_weight']}",
        f"- Milvus search multiplier: {report['milvus_search_multiplier']}",
        f"- Milvus search mode: {report.get('milvus_search_mode', 'separate')}",
        f"- Fielded search: {report.get('milvus_fielded_search_enabled', False)}",
        f"- Query rewrite: {report.get('query_rewrite_enabled', False)}",
        f"- Reranker: {report['reranker_backend']} ({report['reranker'] or 'none'})",
        f"- Rerank strategy: {report.get('rerank_strategy', 'replace')}",
        f"- Reranker cache mode: "
        f"{report.get('configuration', {}).get('reranker', {}).get('cache_mode', 'off')}",
        f"- Answer generator: {report['answer_generator_backend']} ({report['answer_generator']})",
        f"- Reranker calls: {report.get('reranker_stats', {}).get('calls')}",
        f"- Reranker degraded calls: {report.get('reranker_stats', {}).get('degraded_calls')}",
        f"- Reranker external calls: {report.get('reranker_stats', {}).get('external_calls')}",
        f"- Reranker cache hits: {report.get('reranker_stats', {}).get('cache_hits')}",
        f"- Reranker deterministic calls: "
        f"{report.get('reranker_stats', {}).get('deterministic_calls')}",
        f"- Reranker HTTP attempts: "
        f"{report.get('reranker_stats', {}).get('http_attempts')}",
        f"- Reranker judgement digest: "
        f"{report.get('reranker_stats', {}).get('judgement_digest')}",
        f"- Documents: {report['documents']}",
        f"- Relations: {report['relations']}",
        f"- Gold rows total: {report.get('questions_total', report['questions'])}",
        f"- Evaluation categories: {', '.join(report.get('evaluation_categories', [])) or 'all'}",
        f"- Questions scored: {report['questions']}",
        f"- Questions excluded from scoring: {report.get('questions_excluded', 0)}",
        f"- Point-estimate checks passed: "
        f"{'yes' if report.get('passed_point_estimates', report['passed']) else 'no'}",
        f"- Passed: {'yes' if report['passed'] else 'no'}",
        "",
        "| Metric | Result | 95% CI | n | Threshold | Point | CI lower |",
        "|---|---:|:--:|---:|---:|---|---|",
    ]
    intervals = report.get("confidence_intervals", {})
    for key, threshold in report["thresholds"].items():
        interval = intervals.get(key)
        span = f"{interval['low']:.4f}–{interval['high']:.4f}" if interval else "—"
        size = str(interval["n"]) if interval else "—"
        lines.append(
            f"| {METRIC_LABELS.get(key, key)} | {report['metrics'][key]:.4f} | {span} | {size} | "
            f"{threshold:.4f} | {report['checks'][key]} | "
            f"{report.get('confidence_checks', {}).get(key, 'n/a')} |"
        )
    lines.extend(
        [
            "",
            "## Retrieval slices",
            "",
            "| Slice | Recall@3 | Top-1 citation | n |",
            "|---|---:|---:|---:|",
            "| Semantic RAG | "
            f"{report['metrics']['semantic_rag_recall_at_3']:.4f} | "
            f"{report['metrics']['semantic_rag_top1_citation_accuracy']:.4f} | "
            f"{report['confidence_intervals']['semantic_rag_recall_at_3']['n']} |",
            "| Exact search | "
            f"{report['metrics']['exact_search_recall_at_3']:.4f} | "
            f"{report['metrics']['exact_search_top1_citation_accuracy']:.4f} | "
            f"{report['confidence_intervals']['exact_search_recall_at_3']['n']} |",
            "",
            f"Candidate diagnostics: "
            f"{'enabled' if report['candidate_diagnostics']['enabled'] else 'disabled'} "
            f"(limit {report['candidate_diagnostics']['limit']}).",
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
            "Latency note: replay mode uses local cached judgements and is not a deployment "
            "latency measurement."
            if report.get("configuration", {}).get("reranker", {}).get("cache_mode")
            == "replay"
            else "Latency note: includes live reranker latency when reranking is enabled.",
            f"Index time: {report['metrics']['index_seconds']} s",
        ]
    )
    funnel = report.get("retrieval_funnel", {})
    if funnel.get("enabled"):
        ranking_index = lines.index("## Ranking and answer quality")
        funnel_lines = [
            "## Candidate-to-ranking funnel",
            "",
            "| Stage | Hits | Denominator | Conditional rate |",
            "|---|---:|---:|---:|",
            f"| Candidate Recall@{funnel['candidate_limit']} | "
            f"{funnel['candidate_hit_count']} | {funnel['queries']} | "
            f"{funnel['candidate_recall']:.4f} |",
            f"| Candidate base Recall@{funnel['output_limit']} | "
            f"{funnel['base_top3_hit_count']} | "
            f"{funnel['candidate_hit_count']} | "
            f"{funnel['base_conditional_recall_at_3']:.4f} |",
            f"| Final Recall@{funnel['output_limit']} given candidate hit | "
            f"{funnel['eligible_final_top3_hit_count']} | "
            f"{funnel['candidate_hit_count']} | "
            f"{funnel['conditional_recall_at_3']:.4f} |",
            "| Candidate base Top-1 | "
            f"{funnel['base_top1_hit_count']} | "
            f"{funnel['candidate_hit_count']} | "
            f"{funnel['base_conditional_top1_accuracy']:.4f} |",
            "| Final Top-1 given candidate hit | "
            f"{funnel['eligible_final_top1_hit_count']} | "
            f"{funnel['candidate_hit_count']} | "
            f"{funnel['conditional_top1_accuracy']:.4f} |",
            "",
            "- Upstream candidate misses: "
            + (", ".join(funnel["candidate_miss_ids"]) or "none"),
            "- Candidate hits dropped before final Top-3: "
            + (", ".join(funnel["candidate_hit_but_top3_miss_ids"]) or "none"),
            "- Rerank rescues versus candidate base Top-3: "
            + (", ".join(funnel["rerank_rescue_ids"]) or "none"),
            "- Rerank regressions versus candidate base Top-3: "
            + (", ".join(funnel["rerank_regression_ids"]) or "none"),
            f"- Final Top-3 is a subset of the candidate pool: "
            f"{funnel['set_relationship_valid']}",
            "",
        ]
        lines[ranking_index:ranking_index] = funnel_lines
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the same component configuration used by the API. CLI values override "
            "RAG_* environment settings; API keys are accepted only through "
            "RAG_LLM_API_KEY or OPENTOPIA_MODEL_KEY."
        )
    )
    parser.add_argument("--backend", choices=["hashing", "nemotron", "bge_m3"])
    parser.add_argument("--model")
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--device")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--vector-backend", choices=["memory", "milvus"])
    parser.add_argument("--index-version")
    parser.add_argument("--milvus-uri")
    parser.add_argument("--milvus-collection")
    parser.add_argument("--dense-weight", type=float)
    parser.add_argument("--search-multiplier", type=int)
    parser.add_argument(
        "--adaptive-recall",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Expand chunk recall until the requested number of distinct documents is found.",
    )
    parser.add_argument("--adaptive-recall-max-chunks", type=int)
    parser.add_argument("--milvus-search-mode", choices=["separate", "native_rrf"])
    parser.add_argument(
        "--fielded-search",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--query-rewrite",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--hybrid-rrf-k", type=int)
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--min-retrieval-score", type=float)
    parser.add_argument("--chunk-max-tokens", type=int)
    parser.add_argument("--chunk-overlap-tokens", type=int)
    parser.add_argument("--chunk-parent-max-tokens", type=int)
    parser.add_argument("--chunking-version")
    parser.add_argument("--reranker", choices=["none", "cross_encoder", "llm"])
    parser.add_argument("--reranker-model")
    parser.add_argument("--reranker-device")
    parser.add_argument("--rerank-candidates", type=int)
    parser.add_argument("--rerank-strategy", choices=["replace", "weighted_rrf"])
    parser.add_argument("--reranker-weight", type=float)
    parser.add_argument("--rerank-rrf-k", type=int)
    parser.add_argument("--reranker-cache-mode", choices=["off", "record", "replay"])
    parser.add_argument("--reranker-cache-path", type=Path)
    parser.add_argument(
        "--answer-generator",
        choices=["extractive", "openai_compatible"],
        help="Answer backend; openai_compatible requires LLM settings and an environment key.",
    )
    parser.add_argument("--llm-base-url")
    parser.add_argument("--llm-model")
    parser.add_argument(
        "--candidate-diagnostics",
        action="store_true",
        help="Record ranked semantic-RAG candidates for hard-negative analysis.",
    )
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument(
        "--category",
        action="append",
        choices=sorted(EVALUATION_CATEGORIES),
        help="Evaluate only this category; repeat to select multiple categories.",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/processed/techqa_p2"),
    )
    parser.add_argument(
        "--gold-path",
        type=Path,
        help="Override the gold JSONL path; rows with score_enabled=false are excluded.",
    )
    args = parser.parse_args()
    if args.top_k is not None and args.top_k < 1:
        parser.error("--top-k must be positive")
    if args.candidate_limit < 1:
        parser.error("--candidate-limit must be positive")
    if args.rerank_candidates is not None and args.rerank_candidates < 1:
        parser.error("--rerank-candidates must be positive")
    if args.reranker_weight is not None and not 0 <= args.reranker_weight <= 1:
        parser.error("--reranker-weight must be between 0 and 1")
    if args.rerank_rrf_k is not None and args.rerank_rrf_k < 1:
        parser.error("--rerank-rrf-k must be positive")
    if args.hybrid_rrf_k is not None and args.hybrid_rrf_k < 1:
        parser.error("--hybrid-rrf-k must be positive")
    if args.adaptive_recall_max_chunks is not None and args.adaptive_recall_max_chunks < 1:
        parser.error("--adaptive-recall-max-chunks must be positive")

    base_settings = Settings()
    embedding_backend = args.backend or base_settings.embedding_backend
    vector_backend = args.vector_backend or base_settings.vector_backend
    index_version = args.index_version or (
        base_settings.index_version if vector_backend == "milvus" else "p2-evaluation-v1"
    )
    evaluation_prefix = (
        f"{args.data.name}-milvus-{embedding_backend}"
        if vector_backend == "milvus"
        else f"p2-evaluation-{embedding_backend}"
    )
    dense_weight = (
        args.dense_weight if args.dense_weight is not None else base_settings.dense_weight
    )
    search_multiplier = (
        args.search_multiplier
        if args.search_multiplier is not None
        else base_settings.milvus_search_multiplier
    )
    overrides: dict[str, str] = {}
    if args.model and embedding_backend == "nemotron":
        overrides["nemotron_model_id"] = args.model
    if args.model and embedding_backend == "bge_m3":
        overrides["bge_model_id"] = args.model
    settings = Settings(
        embedding_backend=embedding_backend,
        nemotron_dimensions=args.dimensions or base_settings.nemotron_dimensions,
        nemotron_device=args.device or base_settings.nemotron_device,
        bge_device=args.device or base_settings.bge_device,
        corpus_path=args.data / "documents.jsonl",
        relations_path=args.data / "relations.jsonl",
        gold_path=args.gold_path or args.data / "golden_questions.jsonl",
        graph_enabled=True,
        vector_backend=vector_backend,
        milvus_uri=args.milvus_uri or base_settings.milvus_uri,
        milvus_collection=args.milvus_collection or base_settings.milvus_collection,
        dense_weight=dense_weight,
        milvus_search_multiplier=search_multiplier,
        milvus_adaptive_recall_enabled=(
            args.adaptive_recall
            if args.adaptive_recall is not None
            else base_settings.milvus_adaptive_recall_enabled
        ),
        milvus_adaptive_recall_max_chunks=(
            args.adaptive_recall_max_chunks
            or base_settings.milvus_adaptive_recall_max_chunks
        ),
        milvus_search_mode=args.milvus_search_mode or base_settings.milvus_search_mode,
        milvus_fielded_search_enabled=(
            args.fielded_search
            if args.fielded_search is not None
            else base_settings.milvus_fielded_search_enabled
        ),
        query_rewrite_enabled=(
            args.query_rewrite
            if args.query_rewrite is not None
            else base_settings.query_rewrite_enabled
        ),
        milvus_rrf_k=args.hybrid_rrf_k or base_settings.milvus_rrf_k,
        top_k=args.top_k or base_settings.top_k,
        chunk_max_tokens=args.chunk_max_tokens or base_settings.chunk_max_tokens,
        chunk_overlap_tokens=(
            args.chunk_overlap_tokens
            if args.chunk_overlap_tokens is not None
            else base_settings.chunk_overlap_tokens
        ),
        chunk_parent_max_tokens=(
            args.chunk_parent_max_tokens or base_settings.chunk_parent_max_tokens
        ),
        chunking_version=args.chunking_version or base_settings.chunking_version,
        reranker_backend=args.reranker or base_settings.reranker_backend,
        reranker_model_id=args.reranker_model or base_settings.reranker_model_id,
        reranker_device=(args.reranker_device or args.device or base_settings.reranker_device),
        rerank_candidates=args.rerank_candidates or base_settings.rerank_candidates,
        rerank_strategy=args.rerank_strategy or base_settings.rerank_strategy,
        reranker_weight=(
            args.reranker_weight
            if args.reranker_weight is not None
            else base_settings.reranker_weight
        ),
        rerank_rrf_k=args.rerank_rrf_k or base_settings.rerank_rrf_k,
        reranker_cache_mode=(
            args.reranker_cache_mode or base_settings.reranker_cache_mode
        ),
        reranker_cache_path=(
            args.reranker_cache_path or base_settings.reranker_cache_path
        ),
        llm_backend=args.answer_generator or base_settings.llm_backend,
        RAG_LLM_BASE_URL=args.llm_base_url or base_settings.llm_base_url,
        RAG_LLM_MODEL=args.llm_model or base_settings.llm_model,
        index_version=index_version,
        graph_state_path=Path(f"data/{evaluation_prefix}-graph-state.json"),
        audit_path=Path(f"data/{evaluation_prefix}-audit.jsonl"),
        demo_db_path=Path(f"data/{evaluation_prefix}.sqlite"),
        min_retrieval_score=(
            args.min_retrieval_score
            if args.min_retrieval_score is not None
            else 0.08
        ),
        **overrides,
    )
    report = evaluate(
        settings,
        candidate_diagnostics=args.candidate_diagnostics,
        candidate_limit=args.candidate_limit,
        categories=frozenset(args.category) if args.category else None,
    )
    output = args.output or Path(f"reports/p2-baseline-{embedding_backend}.json")
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
