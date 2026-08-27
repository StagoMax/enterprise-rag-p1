"""Benchmark warmed local SAG and formal P3 Graph RAG retrieval latency.

The Graph RAG index is attached read-only.  This script never repoints the
``enterprise_chunks`` Milvus alias.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from enterprise_rag.bootstrap import load_gold_questions
from enterprise_rag.components import build_embedding_provider, build_vector_store
from enterprise_rag.config import Settings
from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.graph_retrieval import GraphRagRetriever
from enterprise_sag.models import ContextPackRequest
from enterprise_sag.multi_retrieval import CoverageFusion, MultiRouteSagRetriever
from enterprise_sag.planning import SingleNeedPlanner
from enterprise_sag.retrieval import SagRetriever
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import SagSqliteStore

P3_INDEX_VERSION = "p3-techqa-28481-nemotron-1024-v3"
SAG_QUERIES = (
    "我的长期目标和职业选择是什么？",
    "我在工作中重视哪些原则？",
    "我的主要经历有哪些？",
    "我有哪些技能和学习计划？",
    "我偏好的沟通与协作方式是什么？",
    "我最近关注的事项是什么？",
    "我的价值观和做事偏好是什么？",
    "我做过哪些重要项目或工作？",
    "我希望未来在哪些方向继续发展？",
    "有哪些信息能帮助理解我的个人背景？",
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "samples": len(values),
        "mean_seconds": round(statistics.fmean(values), 4),
        "median_seconds": round(statistics.median(values), 4),
        "p95_seconds": round(percentile(values, 0.95), 4),
        "min_seconds": round(min(values), 4),
        "max_seconds": round(max(values), 4),
    }


def attach_readonly_version(store: Any, version: str) -> None:
    """Load one immutable collection without altering the public Milvus alias."""

    target_collection = store._collection_name(version)
    store._active_version = version
    store._refresh_document_cache()
    store._alias = target_collection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.repeats < 1 or args.top_k < 1:
        raise ValueError("--repeats and --top-k must be positive")

    model_started = time.perf_counter()
    embedding_settings = Settings(
        embedding_backend="nemotron",
        nemotron_model_id="models/nemotron-3-embed-1b",
        nemotron_dimensions=1024,
        nemotron_device="cuda",
    )
    embeddings = build_embedding_provider(embedding_settings)
    model_load_seconds = time.perf_counter() - model_started

    sag_settings = SagSettings(
        database_path=Path("data/sag_memory/personal_memory.sqlite"),
        embedding_backend="nemotron",
        nemotron_model_id="models/nemotron-3-embed-1b",
        nemotron_dimensions=1024,
        nemotron_device="cuda",
    )
    sag_store = SagSqliteStore(sag_settings.database_path)
    sag_retriever = MultiRouteSagRetriever(
        SingleNeedPlanner(),
        SagRetriever(
            sag_store,
            embeddings,
            seed_entity_count=sag_settings.retrieval_seed_entities,
            seed_event_count=sag_settings.retrieval_seed_events,
            candidate_limit=sag_settings.retrieval_candidate_limit,
            expansion_hops=sag_settings.retrieval_expansion_hops,
        ),
        route_top_k=sag_settings.retrieval_route_top_k,
        fusion=CoverageFusion(rrf_k=sag_settings.retrieval_fusion_rrf_k),
    )

    graph_settings = Settings(
        embedding_backend="nemotron",
        nemotron_model_id="models/nemotron-3-embed-1b",
        nemotron_dimensions=1024,
        nemotron_device="cuda",
        vector_backend="milvus",
        milvus_uri="http://127.0.0.1:19530",
        milvus_collection="enterprise_chunks",
        index_version=P3_INDEX_VERSION,
        dense_weight=0.7,
        milvus_search_multiplier=30,
        reranker_backend="none",
        query_rewrite_enabled=False,
    )
    graph_store = build_vector_store(graph_settings, embeddings, None)
    attach_started = time.perf_counter()
    attach_readonly_version(graph_store, P3_INDEX_VERSION)
    attach_seconds = time.perf_counter() - attach_started
    graph_chunk_count = int(
        graph_store._client.get_collection_stats(graph_store._alias).get("row_count", 0)
    )
    graph = VersionedKnowledgeGraph(Path("data/p3-nemotron-graph-state.json"))
    graph_retriever = GraphRagRetriever(
        graph_store,
        graph,
        seed_count=graph_settings.graph_seed_count,
        max_hops=graph_settings.graph_max_hops,
        expansion_limit=graph_settings.graph_expansion_limit,
        score_decay=graph_settings.graph_score_decay,
    )
    graph_questions = [
        row
        for row in load_gold_questions(
            Path("data/processed/techqa_p3/golden_questions.curated.jsonl")
        )
        if row.get("category") == "graph_rag" and row.get("score_enabled", True)
    ][:10]
    if len(graph_questions) != 10:
        raise RuntimeError(f"expected 10 graph_rag questions, found {len(graph_questions)}")

    for query in SAG_QUERIES:
        sag_retriever.search(ContextPackRequest(query=query), top_k=args.top_k)
    for row in graph_questions:
        graph_retriever.search(
            str(row["question"]),
            frozenset(str(role) for role in row["roles"]),
            top_k=args.top_k,
            exact=False,
            min_score=graph_settings.min_retrieval_score,
            use_graph=True,
            tenant_id="demo",
        )

    sag_samples: list[float] = []
    graph_samples: list[float] = []
    graph_path_count = 0
    for _ in range(args.repeats):
        for query in SAG_QUERIES:
            started = time.perf_counter()
            sag_retriever.search(ContextPackRequest(query=query), top_k=args.top_k)
            sag_samples.append(time.perf_counter() - started)
        for row in graph_questions:
            started = time.perf_counter()
            result = graph_retriever.search(
                str(row["question"]),
                frozenset(str(role) for role in row["roles"]),
                top_k=args.top_k,
                exact=False,
                min_score=graph_settings.min_retrieval_score,
                use_graph=True,
                tenant_id="demo",
            )
            graph_samples.append(time.perf_counter() - started)
            graph_path_count += len(result.graph_paths)

    report = {
        "measurement": {
            "scope": (
                "query-to-retrieval-result only; excludes startup, indexing, HTTP, "
                "answer generation, and SAG remote LLM planning/judgement"
            ),
            "state": "warm; one warm-up per query excluded",
            "top_k": args.top_k,
            "repeats_per_query": args.repeats,
            "embedding": "Nemotron-3-Embed-1B, 1024 dimensions, CUDA",
            "graph_mode": "forced graph expansion",
        },
        "setup_seconds": {
            "embedding_model_load": round(model_load_seconds, 3),
            "graph_readonly_index_attach_and_metadata_cache": round(attach_seconds, 3),
        },
        "corpora": {
            "sag": sag_store.stats(),
            "graph_rag": {
                "index_version": P3_INDEX_VERSION,
                "documents": len(graph_store.document_ids()),
                "chunks": graph_chunk_count,
                "graph_edges": graph.edge_count(),
                "questions": len(graph_questions),
                "graph_paths_across_measured_runs": graph_path_count,
            },
        },
        "sag_seconds": summary(sag_samples),
        "graph_rag_seconds": summary(graph_samples),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
