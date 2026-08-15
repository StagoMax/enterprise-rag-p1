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


def test_curate_expands_equivalent_rag_034_sources() -> None:
    curated = curate(
        [gold_row("rag-034")],
        {"original-doc", "swg21624731", "swg21608705"},
    )

    assert curated[0]["score_enabled"] is True
    assert curated[0]["gold_review_status"] == "expanded"
    assert curated[0]["expected_source_ids"] == ["swg21624731", "swg21608705"]


def test_curate_corrects_rag_056_for_was_v8_and_later() -> None:
    curated = curate(
        [gold_row("rag-056")],
        {"original-doc", "swg21397335"},
    )

    assert curated[0]["score_enabled"] is True
    assert curated[0]["gold_review_status"] == "corrected"
    assert curated[0]["expected_source_ids"] == ["swg21397335"]
    assert "WASServiceHelper.bat" in str(curated[0]["expected_answer"])
    assert curated[0]["original_expected_answer"] == "original answer"


def test_curate_preserves_expansion_review_status() -> None:
    row = gold_row("rag-061")
    row.update(
        {
            "gold_expansion_version": "test-expansion",
            "expansion_review_status": "corrected",
            "expansion_review_notes": "Corrected during expansion audit.",
        }
    )

    curated = curate([row], {"original-doc"})

    assert curated[0]["gold_review_status"] == "corrected"
    assert curated[0]["gold_review_notes"] == "Corrected during expansion audit."
    assert curated[0]["gold_review_basis"] == (
        "expansion_audit_question_answer_source_checked"
    )
