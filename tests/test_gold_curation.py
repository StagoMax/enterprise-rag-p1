from __future__ import annotations

import pytest

from scripts.curate_p3_gold import CURATION_VERSION, curate


def gold_row(row_id: str) -> dict[str, object]:
    return {
        "id": row_id,
        "category": "rag",
        "expected_source_ids": ["original-doc"],
        "expected_answer": "original answer",
    }


def test_curate_retains_excluded_row_but_disables_scoring() -> None:
    rows = [gold_row("rag-019"), gold_row("unmodified")]

    curated = curate(rows, {"original-doc"})

    assert len(curated) == 2
    assert curated[0]["score_enabled"] is False
    assert curated[0]["gold_review_status"] == "excluded"
    assert curated[0]["expected_source_ids"] == ["original-doc"]
    assert curated[1]["score_enabled"] is True
    assert curated[1]["gold_review_status"] == "verified"
    assert all(row["gold_revision"] == CURATION_VERSION for row in curated)


def test_curate_rejects_corrected_source_missing_from_corpus() -> None:
    with pytest.raises(ValueError, match="references missing documents"):
        curate([gold_row("rag-052")], {"original-doc"})
