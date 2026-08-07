import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "export_hard_negatives", REPO_ROOT / "scripts" / "export_hard_negatives.py"
)
export_hard_negatives = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_hard_negatives)


def test_build_review_rows_excludes_gold_and_non_rag_candidates():
    review = {
        "audits": [
            {
                "id": "rag-1",
                "top3": [
                    {"document_id": "wrong", "title": "Wrong", "score": 0.9},
                    {"document_id": "gold", "title": "Gold", "score": 0.8},
                ],
            },
            {"id": "exact-1", "top3": [{"document_id": "wrong"}]},
        ]
    }
    gold = {
        "rag-1": {
            "id": "rag-1",
            "category": "rag",
            "question": "question",
            "expected_source_ids": ["gold"],
        },
        "exact-1": {
            "id": "exact-1",
            "category": "exact_search",
            "expected_source_ids": ["gold"],
        },
    }

    rows = export_hard_negatives.build_review_rows(review, gold)

    assert len(rows) == 1
    assert rows[0]["positive_source_ids"] == ["gold"]
    assert rows[0]["candidates"] == [
        {
            "document_id": "wrong",
            "title": "Wrong",
            "rank": 1,
            "score": 0.9,
            "dense_score": None,
            "lexical_score": None,
            "label": "unreviewed",
        }
    ]


def test_full_candidate_window_and_disabled_gold_are_supported(tmp_path):
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "rag-1",
                        "category": "rag",
                        "expected_source_ids": ["gold"],
                    }
                ),
                json.dumps(
                    {
                        "id": "rag-disabled",
                        "category": "rag",
                        "expected_source_ids": ["old"],
                        "score_enabled": False,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    review = {
        "audits": [
            {
                "id": "rag-1",
                "candidates": [{"document_id": "hard", "rank": 17}],
            },
            {
                "id": "rag-disabled",
                "candidates": [{"document_id": "not-exported"}],
            },
        ]
    }

    rows = export_hard_negatives.build_review_rows(
        review, export_hard_negatives.load_scored_gold(gold_path)
    )

    assert [row["id"] for row in rows] == ["rag-1"]
    assert rows[0]["candidates"][0]["rank"] == 17


def test_evaluation_candidate_diagnostics_can_be_exported():
    report = {
        "candidate_diagnostics": {
            "queries": [
                {
                    "id": "rag-1",
                    "candidates": [
                        {
                            "document_id": "candidate",
                            "final_rank": 2,
                            "base_score": 0.75,
                        }
                    ],
                }
            ]
        }
    }
    gold = {
        "rag-1": {
            "id": "rag-1",
            "category": "rag",
            "question": "question",
            "expected_source_ids": ["gold"],
        }
    }

    rows = export_hard_negatives.build_review_rows(
        report, gold, {"candidate": "Candidate title"}
    )

    assert rows[0]["candidates"][0]["document_id"] == "candidate"
    assert rows[0]["candidates"][0]["title"] == "Candidate title"
    assert rows[0]["candidates"][0]["label"] == "unreviewed"
