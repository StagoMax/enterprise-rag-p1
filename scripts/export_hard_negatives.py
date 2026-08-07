"""Export retrieved non-gold documents for human hard-negative review.

The output is deliberately marked ``unreviewed``. A high-ranked document that is
absent from the gold IDs can still be an equivalent source, so treating every
retrieval miss as a training negative would teach the ranker the wrong lesson.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_scored_gold(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("score_enabled", True):
            rows[str(row["id"])] = row
    return rows


def load_document_titles(path: Path) -> dict[str, str]:
    titles: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        document_id = str(row.get("document_id", ""))
        if document_id:
            titles[document_id] = str(row.get("title", ""))
    return titles


def _audit_candidates(audit: dict[str, Any]) -> list[dict[str, Any]]:
    # New diagnostics should expose the full rerank window. Existing P3 review
    # artifacts only contain top3, which is still useful for bootstrapping.
    candidates = audit.get("candidates") or audit.get("top_candidates") or audit.get("top3")
    return [candidate for candidate in candidates or [] if isinstance(candidate, dict)]


def build_review_rows(
    review: dict[str, Any],
    gold: dict[str, dict[str, Any]],
    document_titles: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    document_titles = document_titles or {}
    rows: list[dict[str, Any]] = []
    audits = review.get("audits") or review.get("candidate_diagnostics", {}).get(
        "queries", []
    )
    for audit in audits:
        question_id = str(audit.get("id", ""))
        gold_row = gold.get(question_id)
        if gold_row is None or gold_row.get("category") != "rag":
            continue

        positive_ids = set(map(str, gold_row.get("expected_source_ids", [])))
        negatives = []
        for rank, candidate in enumerate(_audit_candidates(audit), start=1):
            document_id = str(candidate.get("document_id", ""))
            if not document_id or document_id in positive_ids:
                continue
            negatives.append(
                {
                    "document_id": document_id,
                    "title": str(
                        candidate.get("title") or document_titles.get(document_id, "")
                    ),
                    "rank": int(candidate.get("rank", candidate.get("final_rank", rank))),
                    "score": candidate.get("score", candidate.get("base_score")),
                    "dense_score": candidate.get("dense_score"),
                    "lexical_score": candidate.get("lexical_score"),
                    "label": "unreviewed",
                }
            )
        if not negatives:
            continue

        rows.append(
            {
                "id": question_id,
                "question": str(gold_row.get("question", audit.get("question", ""))),
                "positive_source_ids": sorted(positive_ids),
                "candidates": negatives,
                "review_instruction": (
                    "Mark each candidate relevant, equivalent, or hard_negative before training."
                ),
            }
        )
    return rows


def write_jsonl(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path, help="candidate audit JSON")
    parser.add_argument("gold", type=Path, help="curated golden questions JSONL")
    parser.add_argument("output", type=Path, help="review queue JSONL")
    parser.add_argument(
        "--documents",
        type=Path,
        help="optional documents JSONL used to backfill candidate titles",
    )
    args = parser.parse_args()

    review = json.loads(args.review.read_text(encoding="utf-8"))
    document_titles = load_document_titles(args.documents) if args.documents else None
    rows = build_review_rows(review, load_scored_gold(args.gold), document_titles)
    write_jsonl(rows, args.output)
    print(f"exported {len(rows)} query rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
