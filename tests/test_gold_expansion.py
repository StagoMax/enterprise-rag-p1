from __future__ import annotations

import pytest

from scripts.expand_p3_gold import build_expansion, merge_expansion, update_summary


def raw_record(question_id: str = "Q-1", answer: str = "Use the supported setting.") -> dict:
    return {
        "id": question_id,
        "question": "How do I fix the product configuration?",
        "answer": answer,
        "is_impossible": False,
        "contexts": [
            {
                "filename": "doc-1.txt",
                "text": f"ANSWER\n{answer}",
            }
        ],
    }


def document(answer: str = "Use the supported setting.") -> dict:
    return {
        "document_id": "doc-1",
        "content": f"Title: Example\n\nANSWER\n{answer}",
        "allowed_roles": ["engineering"],
    }


def test_build_expansion_creates_audited_rag_row() -> None:
    additions, audit = build_expansion(
        [raw_record()],
        [document()],
        [{"id": "rag-060", "category": "rag", "source_question_id": "OLD"}],
        approved_ids=("Q-1",),
        answer_overrides={},
    )

    assert additions[0]["id"] == "rag-061"
    assert additions[0]["roles"] == ["engineering"]
    assert additions[0]["expected_source_ids"] == ["doc-1"]
    assert additions[0]["expansion_review_status"] == "verified"
    assert audit[0]["answer_present_in_source"] is True
    assert audit[0]["support_section"] == "ANSWER"


def test_build_expansion_rejects_answer_not_present_in_source() -> None:
    with pytest.raises(ValueError, match="answer is not present in source"):
        build_expansion(
            [raw_record(answer="A different answer")],
            [document()],
            [],
            approved_ids=("Q-1",),
            answer_overrides={},
        )


def test_merge_and_summary_include_added_rag_rows() -> None:
    baseline = [
        {"id": "rag-001", "category": "rag"},
        {"id": "exact-001", "category": "exact_search"},
    ]
    additions = [{"id": "rag-002", "category": "rag"}]

    merged = merge_expansion(baseline, additions)
    summary = update_summary({}, merged)

    assert [row["id"] for row in merged] == ["rag-001", "rag-002", "exact-001"]
    assert summary["gold_questions"] == 3
    assert summary["gold_by_category"] == {"exact_search": 1, "rag": 2}
