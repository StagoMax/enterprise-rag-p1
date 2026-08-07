import pytest

from scripts.compare_rerank_strategies import compare


def report(strategy: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "index_version": "v1",
        "backend": "nemotron",
        "model": "model",
        "dimensions": 1024,
        "dense_weight": 0.7,
        "milvus_search_multiplier": 30,
        "evaluation_categories": ["rag"],
        "questions": 2,
        "rerank_strategy": strategy,
        "configuration": {
            "embedding": {"model": "model"},
            "reranker": {
                "backend": "llm",
                "strategy": strategy,
                "weight": 0.5,
                "rrf_k": 60,
                "cache_mode": "record" if strategy == "replace" else "replay",
                "cache_path": "artifacts/cache.jsonl",
            },
            "vector_store": {"search_mode": "native_rrf"},
        },
        "metrics": {"semantic_rag_recall_at_3": 0.5},
        "reranker_stats": {
            "calls": 2,
            "degraded_calls": 0,
            "external_calls": 2 if strategy == "replace" else 0,
            "cache_hits": 0 if strategy == "replace" else 2,
            "deterministic_calls": 0,
            "http_attempts": 2 if strategy == "replace" else 0,
            "judgement_digest": "same-sequence-digest",
        },
        "results": rows,
    }


def test_compare_reports_paired_rerank_wins_and_losses() -> None:
    left = report(
        "replace",
        [
            {"id": "q1", "evidence_recalled": True, "top1_correct": False},
            {"id": "q2", "evidence_recalled": False, "top1_correct": True},
        ],
    )
    right = report(
        "weighted_rrf",
        [
            {"id": "q1", "evidence_recalled": True, "top1_correct": True},
            {"id": "q2", "evidence_recalled": True, "top1_correct": False},
        ],
    )

    result = compare(left, right)

    assert result["recall_at_3"] == {
        "both": 1,
        "left_only": 0,
        "right_only": 1,
        "neither": 0,
    }
    assert result["top1"] == {
        "both": 0,
        "left_only": 1,
        "right_only": 1,
        "neither": 0,
    }


def test_compare_rejects_non_strategy_configuration_drift() -> None:
    left = report("replace", [])
    right = report("weighted_rrf", [])
    right["dense_weight"] = 0.5

    with pytest.raises(ValueError, match="controlled"):
        compare(left, right)


@pytest.mark.parametrize("field", ["calls", "judgement_digest"])
def test_compare_rejects_reranker_sequence_drift(field: str) -> None:
    left = report("replace", [])
    right = report("weighted_rrf", [])
    right["reranker_stats"][field] = (
        1 if field == "calls" else "different-sequence-digest"
    )

    with pytest.raises(ValueError, match="different reranker"):
        compare(left, right)


def test_compare_accepts_deterministic_recorded_calls() -> None:
    left = report("replace", [])
    right = report("weighted_rrf", [])
    left["reranker_stats"].update(
        {"external_calls": 1, "deterministic_calls": 1}
    )

    compare(left, right)


def test_compare_requires_record_then_replay_cache_modes() -> None:
    left = report("replace", [])
    right = report("weighted_rrf", [])
    right["configuration"]["reranker"]["cache_mode"] = "off"

    with pytest.raises(ValueError, match="replay mode"):
        compare(left, right)
