from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from enterprise_rag.models import Route
from enterprise_rag.router import RuleBasedRouter

EXPANSION_VERSION = "p3-gold-expansion-v1-2026-08-09"

# These questions were individually checked against the cited corpus document.
# Keeping the selection explicit makes the expansion reproducible and reviewable.
APPROVED_QUESTION_IDS = (
    "TRAIN_Q000",
    "TRAIN_Q001",
    "DEV_Q008",
    "TRAIN_Q009",
    "DEV_Q021",
    "TRAIN_Q033",
    "DEV_Q034",
    "TRAIN_Q037",
    "DEV_Q038",
    "TRAIN_Q042",
    "TRAIN_Q091",
    "DEV_Q102",
    "DEV_Q140",
    "TRAIN_Q152",
    "TRAIN_Q172",
    "TRAIN_Q195",
    "DEV_Q195",
    "TRAIN_Q208",
    "TRAIN_Q227",
    "DEV_Q234",
    "TRAIN_Q235",
    "DEV_Q245",
    "TRAIN_Q250",
    "DEV_Q254",
    "TRAIN_Q259",
    "DEV_Q275",
    "DEV_Q296",
    "DEV_Q299",
    "DEV_Q305",
    "DEV_Q306",
    "TRAIN_Q310",
    "TRAIN_Q314",
    "TRAIN_Q330",
    "TRAIN_Q334",
    "TRAIN_Q339",
    "TRAIN_Q350",
    "TRAIN_Q388",
    "TRAIN_Q415",
    "TRAIN_Q421",
    "TRAIN_Q439",
    "TRAIN_Q450",
    "TRAIN_Q458",
    "TRAIN_Q501",
    "TRAIN_Q512",
    "TRAIN_Q523",
    "TRAIN_Q535",
    "TRAIN_Q540",
    "TRAIN_Q552",
    "TRAIN_Q587",
    # Replacements for weak or incomplete raw labels found during review.
    "TRAIN_Q013",
    "TRAIN_Q098",
    "TRAIN_Q189",
    "DEV_Q155",
    "DEV_Q216",
    "TRAIN_Q226",
    "TRAIN_Q466",
    "TRAIN_Q467",
    "DEV_Q302",
    "TRAIN_Q070",
    "TRAIN_Q219",
)

ANSWER_OVERRIDES = {
    "DEV_Q254": (
        "Code the appropriate security definitions for FEK.CMD.SEND and "
        "FEK.CMD.SEND.CLEAR."
    )
}

# Rejected candidates remain in the audit trail instead of silently disappearing.
REJECTED_CANDIDATES = {
    "DEV_Q055": (
        "The question is about table mapping with special characters in column comments, "
        "but the cited answer only gives a generic code-page reinsertion remedy."
    ),
    "TRAIN_Q087": (
        "The question says current GTK libraries are already installed, while the answer "
        "only repeats an RPM installation instruction and does not resolve that conflict."
    ),
    "DEV_Q123": (
        "The question asks for configuration and a source-not-found failure, but the answer "
        "only states a Rational Reporting support limitation."
    ),
    "DEV_Q193": (
        "The question asks for the supported releases of two Nokia products; the answer "
        "only names one release of one product."
    ),
    "TRAIN_Q261": (
        "The cited text does not establish that the ObjectServer repository change caused "
        "the reported administrative-security failure."
    ),
    "TRAIN_Q389": (
        "The question asks for the supported operating-system matrix, but the answer is "
        "only an introductory sentence and omits the matrix."
    ),
    "TRAIN_Q423": (
        "The stale-report question is not sufficiently tied to the cited credentials/content-"
        "store-corruption symptom, so the proposed NC-table remedy is not a safe gold answer."
    ),
    "TRAIN_Q488": (
        "The question asks specifically about digital signatures; the answer only states "
        "that DB2 uses FIPS-certified encryption modules."
    ),
    "TRAIN_Q500": (
        "The answer ends with an introduction to a link list and omits the actual releases "
        "and links requested by the question."
    ),
    "TRAIN_Q549": (
        "The answer refers to commands shown below, but those commands are missing from the "
        "gold answer."
    ),
    "TRAIN_Q565": (
        "Generic MQ client/queue-manager interoperability does not prove that ODM 8.5.1 "
        "supports MQ 9.0."
    ),
}

SUPPORT_HEADINGS = (
    "RESOLVING THE PROBLEM",
    "ANSWER",
    "CAUSE",
    "SOLUTION",
    "WORKAROUND",
    "CONTENT",
)


def read_json(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _document_id(context: dict[str, Any]) -> str:
    return Path(str(context.get("filename", ""))).stem


def _next_rag_number(rows: list[dict[str, Any]]) -> int:
    numbers = [
        int(match.group(1))
        for row in rows
        if (match := re.fullmatch(r"rag-(\d+)", str(row.get("id", ""))))
    ]
    return max(numbers, default=0) + 1


def _answer_span(text: str, answer: str) -> tuple[int, int] | None:
    tokens = answer.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.span() if match else None


def _support_section(text: str, answer: str) -> str:
    span = _answer_span(text, answer)
    if span is None:
        return "UNKNOWN"
    answer_at = span[0]
    candidates: list[tuple[int, str]] = []
    for heading in SUPPORT_HEADINGS:
        for match in re.finditer(rf"(?im)^\s*{re.escape(heading)}\s*$", text[:answer_at]):
            candidates.append((match.start(), heading))
    return max(candidates, default=(-1, "DOCUMENT BODY"))[1]


def _evidence_excerpt(text: str, answer: str) -> str:
    span = _answer_span(text, answer)
    if span is None:
        return ""
    start = max(0, span[0] - 220)
    end = min(len(text), span[1] + 320)
    return " ".join(text[start:end].split())


def _without_current_expansion(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    approved = set(APPROVED_QUESTION_IDS)
    return [
        row
        for row in rows
        if row.get("gold_expansion_version") != EXPANSION_VERSION
        and not (
            row.get("source_question_id") in approved
            and str(row.get("id", "")).startswith("rag-")
            and int(str(row["id"]).removeprefix("rag-")) > 60
        )
    ]


def build_expansion(
    records: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    approved_ids: tuple[str, ...] = APPROVED_QUESTION_IDS,
    answer_overrides: dict[str, str] = ANSWER_OVERRIDES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(approved_ids) != len(set(approved_ids)):
        raise ValueError("approved question IDs must be unique")

    records_by_id = {str(record["id"]): record for record in records}
    documents_by_id = {str(document["document_id"]): document for document in documents}
    existing_source_ids = {
        str(row["source_question_id"])
        for row in existing_rows
        if row.get("source_question_id")
    }
    duplicate_sources = sorted(set(approved_ids) & existing_source_ids)
    if duplicate_sources:
        raise ValueError(f"questions already present in baseline gold: {duplicate_sources}")

    router = RuleBasedRouter()
    next_number = _next_rag_number(existing_rows)
    additions: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for question_id in approved_ids:
        record = records_by_id.get(question_id)
        if record is None:
            raise ValueError(f"approved question is missing from raw data: {question_id}")
        if record.get("is_impossible"):
            raise ValueError(f"approved question is marked impossible: {question_id}")
        contexts = record.get("contexts", [])
        if len(contexts) != 1:
            raise ValueError(f"approved question must have exactly one context: {question_id}")
        if router.route(str(record["question"])).route != Route.RAG:
            raise ValueError(f"approved question does not route to RAG: {question_id}")

        source_id = _document_id(contexts[0])
        document = documents_by_id.get(source_id)
        if document is None:
            raise ValueError(f"source document is missing for {question_id}: {source_id}")
        answer = answer_overrides.get(question_id, str(record.get("answer", "")).strip())
        if not answer:
            raise ValueError(f"approved question has an empty answer: {question_id}")
        content = str(document.get("content", ""))
        if _answer_span(content, answer) is None:
            raise ValueError(f"answer is not present in source for {question_id}: {source_id}")

        row_id = f"rag-{next_number:03d}"
        next_number += 1
        status = "corrected" if question_id in answer_overrides else "verified"
        row = {
            "id": row_id,
            "category": "rag",
            "question": str(record["question"]).strip(),
            "expected_route": "rag",
            "roles": list(document["allowed_roles"]),
            "expected_source_ids": [source_id],
            "expected_answer": answer,
            "should_refuse": False,
            "source_question_id": question_id,
            "route_taxonomy_version": "p1-rules-1",
            "gold_expansion_version": EXPANSION_VERSION,
            "expansion_review_status": status,
            "source_document_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        if status == "corrected":
            row["original_source_answer"] = str(record.get("answer", "")).strip()
            row["expansion_review_notes"] = (
                "The raw answer was a malformed cause fragment. The corrected gold answer "
                "uses the direct instruction in RESOLVING THE PROBLEM."
            )
        additions.append(row)
        audit_rows.append(
            {
                "id": row_id,
                "source_question_id": question_id,
                "role": document["allowed_roles"][0],
                "expected_source_id": source_id,
                "review_status": status,
                "question": row["question"],
                "expected_answer": answer,
                "support_section": _support_section(content, answer),
                "answer_present_in_source": True,
                "evidence_excerpt": _evidence_excerpt(content, answer),
                "review_conclusion": row.get(
                    "expansion_review_notes",
                    "Question, answer, and cited source were manually checked as a direct match.",
                ),
            }
        )
    return additions, audit_rows


def merge_expansion(
    baseline_rows: list[dict[str, Any]], additions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    insert_at = next(
        (
            index
            for index, row in enumerate(baseline_rows)
            if row.get("category") != "rag"
        ),
        len(baseline_rows),
    )
    return [*baseline_rows[:insert_at], *additions, *baseline_rows[insert_at:]]


def update_summary(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = dict(summary)
    result["gold_questions"] = len(rows)
    result["gold_by_category"] = {
        category: sum(row.get("category") == category for row in rows)
        for category in sorted({str(row.get("category")) for row in rows})
    }
    result["gold_expansion_version"] = EXPANSION_VERSION
    return result


def write_audit_report(
    audit_rows: list[dict[str, Any]],
    baseline_count: int,
    output: Path,
) -> None:
    role_counts = Counter(str(row["role"]) for row in audit_rows)
    status_counts = Counter(str(row["review_status"]) for row in audit_rows)
    report = {
        "expansion_version": EXPANSION_VERSION,
        "baseline_questions": baseline_count,
        "questions_added": len(audit_rows),
        "questions_after_expansion": baseline_count + len(audit_rows),
        "role_counts": dict(sorted(role_counts.items())),
        "review_status_counts": dict(sorted(status_counts.items())),
        "rejected_candidate_count": len(REJECTED_CANDIDATES),
        "rejected_candidates": [
            {"source_question_id": question_id, "reason": reason}
            for question_id, reason in REJECTED_CANDIDATES.items()
        ],
        "rows": audit_rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# P3 评测集扩充与逐题审计",
        "",
        f"- 扩充版本：`{EXPANSION_VERSION}`",
        f"- 原评测题数：{baseline_count}",
        f"- 新增题数：{len(audit_rows)}",
        f"- 扩充后题数：{baseline_count + len(audit_rows)}",
        "- 新增角色分布："
        + "、".join(f"{role} {count}" for role, count in sorted(role_counts.items())),
        f"- 候选审查淘汰：{len(REJECTED_CANDIDATES)} 道",
        "",
        "## 审查标准",
        "",
        "每道新增题均核对问题、期望答案和唯一来源文档。答案必须出现在当前语料正文中，"
        "且语义上直接回答问题；仅有关键词重合、答案残缺或只能间接推断的候选不纳入。",
        "",
        "## 淘汰的弱金标候选",
        "",
        "| 原始题目 ID | 淘汰原因 |",
        "|---|---|",
    ]
    for question_id, reason in REJECTED_CANDIDATES.items():
        lines.append(f"| `{question_id}` | {reason} |")
    lines.extend(
        [
            "",
            "## 纳入的 60 道题",
            "",
            "| 新 ID | 原始题目 ID | 角色 | 来源 | 结论 | 支撑段落 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in audit_rows:
        lines.append(
            f"| `{row['id']}` | `{row['source_question_id']}` | {row['role']} | "
            f"`{row['expected_source_id']}` | {row['review_status']} | "
            f"{row['support_section']} |"
        )
    lines.extend(["", "## 逐题证据", ""])
    for row in audit_rows:
        lines.extend(
            [
                f"### {row['id']} / {row['source_question_id']}",
                "",
                f"- 角色：{row['role']}",
                f"- 来源：`{row['expected_source_id']}`",
                f"- 复核结论：{row['review_status']}；{row['review_conclusion']}",
                f"- 问题：{row['question']}",
                f"- 期望答案：{row['expected_answer']}",
                f"- 来源证据：{row['evidence_excerpt']}",
                "",
            ]
        )
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/raw/techqa/train.json"))
    parser.add_argument(
        "--documents",
        type=Path,
        default=Path("data/processed/techqa_p3/documents.jsonl"),
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path("data/processed/techqa_p3/golden_questions.jsonl"),
    )
    parser.add_argument(
        "--summary", type=Path, default=Path("data/processed/techqa_p3/summary.json")
    )
    parser.add_argument(
        "--audit-report", type=Path, default=Path("reports/p3-gold-expansion-audit.json")
    )
    args = parser.parse_args()

    current_rows = read_jsonl(args.gold)
    baseline_rows = _without_current_expansion(current_rows)
    additions, audit_rows = build_expansion(
        read_json(args.train),
        read_jsonl(args.documents),
        baseline_rows,
    )
    expanded_rows = merge_expansion(baseline_rows, additions)
    write_jsonl(args.gold, expanded_rows)

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    args.summary.write_text(
        json.dumps(update_summary(summary, expanded_rows), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_audit_report(audit_rows, len(baseline_rows), args.audit_report)
    print(
        json.dumps(
            {
                "gold": str(args.gold),
                "baseline": len(baseline_rows),
                "added": len(additions),
                "total": len(expanded_rows),
                "roles": dict(sorted(Counter(row["role"] for row in audit_rows).items())),
                "audit_report": str(args.audit_report),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
