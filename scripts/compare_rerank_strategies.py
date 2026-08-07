from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

QUALITY_METRICS = frozenset(
    {
        "semantic_rag_recall_at_3",
        "semantic_rag_top1_citation_accuracy",
        "mrr_at_3",
        "ndcg_at_3",
        "answer_span_hit_rate_fitting",
        "answer_content_recall",
    }
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _invariant_configuration(report: dict[str, Any]) -> dict[str, Any]:
    configuration = json.loads(json.dumps(report.get("configuration", {})))
    reranker = configuration.get("reranker", {})
    for key in ("strategy", "cache_mode"):
        reranker.pop(key, None)
    return {
        "index_version": report.get("index_version"),
        "backend": report.get("backend"),
        "model": report.get("model"),
        "dimensions": report.get("dimensions"),
        "dense_weight": report.get("dense_weight"),
        "top_k": report.get("top_k"),
        "min_retrieval_score": report.get("min_retrieval_score"),
        "milvus_search_multiplier": report.get("milvus_search_multiplier"),
        "evaluation_categories": report.get("evaluation_categories"),
        "questions": report.get("questions"),
        "gold_sha256": report.get("gold_sha256"),
        "configuration": configuration,
    }


def paired_counts(
    left: dict[str, dict[str, Any]],
    right: dict[str, dict[str, Any]],
    key: str,
) -> dict[str, int]:
    counts = {"both": 0, "left_only": 0, "right_only": 0, "neither": 0}
    for row_id in sorted(left):
        left_value = bool(left[row_id].get(key))
        right_value = bool(right[row_id].get(key))
        bucket = (
            "both"
            if left_value and right_value
            else "left_only"
            if left_value
            else "right_only"
            if right_value
            else "neither"
        )
        counts[bucket] += 1
    return counts


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if {left.get("rerank_strategy"), right.get("rerank_strategy")} != {
        "replace",
        "weighted_rrf",
    }:
        raise ValueError("reports must compare replace with weighted_rrf")
    if _invariant_configuration(left) != _invariant_configuration(right):
        raise ValueError("reports are not a controlled rerank-strategy comparison")
    left_rows = {str(row["id"]): row for row in left.get("results", [])}
    right_rows = {str(row["id"]): row for row in right.get("results", [])}
    if left_rows.keys() != right_rows.keys():
        raise ValueError("reports contain different evaluated question IDs")
    record = left if left.get("rerank_strategy") == "replace" else right
    replay = right if record is left else left
    if record.get("configuration", {}).get("reranker", {}).get("cache_mode") != "record":
        raise ValueError("replace report must use reranker record mode")
    if replay.get("configuration", {}).get("reranker", {}).get("cache_mode") != "replay":
        raise ValueError("weighted_rrf report must use reranker replay mode")
    record_stats = record.get("reranker_stats", {})
    replay_stats = replay.get("reranker_stats", {})
    if record_stats.get("degraded_calls") != 0 or replay_stats.get("degraded_calls") != 0:
        raise ValueError("reranker degraded during the controlled comparison")
    if record_stats.get("calls") != replay_stats.get("calls"):
        raise ValueError("record and replay runs used different reranker call sequences")
    if not record_stats.get("judgement_digest") or (
        record_stats.get("judgement_digest") != replay_stats.get("judgement_digest")
    ):
        raise ValueError("record and replay runs used different reranker judgements")
    record_accounted_calls = sum(
        int(record_stats.get(key) or 0)
        for key in ("external_calls", "cache_hits", "deterministic_calls")
    )
    if record_accounted_calls != record_stats.get("calls"):
        raise ValueError("record run has unaccounted reranker calls")
    if replay_stats.get("external_calls") != 0:
        raise ValueError("replay run unexpectedly called the external reranker")
    if replay_stats.get("cache_hits") != replay_stats.get("calls"):
        raise ValueError("replay run did not reuse every recorded rerank judgement")
    if replay_stats.get("http_attempts") not in (0, None):
        raise ValueError("replay run unexpectedly sent external HTTP requests")
    record_http_attempts = record_stats.get("http_attempts")
    if not isinstance(record_http_attempts, int) or (
        record_http_attempts < int(record_stats.get("external_calls") or 0)
    ):
        raise ValueError("record run has invalid external HTTP request accounting")
    return {
        "left_strategy": left.get("rerank_strategy"),
        "right_strategy": right.get("rerank_strategy"),
        "questions": len(left_rows),
        "recall_at_3": paired_counts(left_rows, right_rows, "evidence_recalled"),
        "top1": paired_counts(left_rows, right_rows, "top1_correct"),
        "metric_delta_right_minus_left": {
            key: round(float(right["metrics"][key]) - float(value), 4)
            for key, value in left.get("metrics", {}).items()
            if key in QUALITY_METRICS
            and key in right.get("metrics", {})
            and isinstance(value, int | float)
        },
        "latency_comparable": False,
        "latency_note": (
            "replace records external judgements while weighted_rrf replays them locally; "
            "run a separate uncached latency benchmark for deployment sizing"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = compare(load(args.left), load(args.right))
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
