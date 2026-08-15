from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

CURATION_VERSION = "p3-gold-v4-2026-08-09"

# Decisions are deliberately explicit. The original source/question mapping is
# retained on every changed row so the curation can be audited or reverted.
DECISIONS: dict[str, dict[str, Any]] = {
    "rag-005": {
        "status": "ambiguous",
        "source_ids": [
            "swg21998452",
            "swg22003256",
            "swg22009455",
            "swg21979065",
            "swg22007664",
        ],
        "reason": (
            "The security bulletin is published as several near-identical Red Hat Linux "
            "advisory records; all five are evidence-equivalent for this question."
        ),
    },
    "rag-006": {
        "status": "expanded",
        "source_ids": ["swg21469413", "swg21605502"],
        "reason": (
            "The original ulimit guidance is valid; a DASH/TIP-specific "
            "'Too many open files' technote is an additional equivalent source."
        ),
    },
    "rag-019": {
        "status": "excluded",
        "reason": (
            "The expected PI37248 document concerns PFBC parsing and contains no Portal "
            "8.5 INSTCONFFAILED installation evidence. No corpus document establishes "
            "the full question-to-answer mapping."
        ),
    },
    "rag-027": {
        "status": "excluded",
        "reason": (
            "The expected document is about SessionObjectSize NotSerializableException "
            "and does not contain the Decision Center IlrStorePolicy ClassCastException. "
            "No exact supporting document was found in the corpus."
        ),
    },
    "rag-030": {
        "status": "excluded",
        "reason": (
            "The expected document is an OMEGAMON MQ Configuration Agent withdrawal "
            "notice and does not explain the KCIJPALO ABEND S013. No exact supporting "
            "document was found in the corpus."
        ),
    },
    "rag-033": {
        "status": "verified",
        "source_ids": ["swg21308281"],
        "reason": (
            "The question describes Installation Manager on a mounted Linux server; "
            "the technote directly says not to install it on an NFS-mounted disk and "
            "to install it only on a local disk."
        ),
    },
    "rag-034": {
        "status": "expanded",
        "source_ids": ["swg21624731", "swg21608705"],
        "reason": (
            "Both technotes directly explain the three-second WLM/HA messaging-engine "
            "lookup delay and prescribe tuning sib.trm.linger in sib.properties; either "
            "document is evidence-equivalent for this question."
        ),
    },
    "rag-040": {
        "status": "excluded",
        "reason": (
            "The expected PI37248 document concerns PFBC parsing and does not contain "
            "the supplied Portal profile augmentation failure or portal01_create.log "
            "evidence. No exact supporting document was found in the corpus."
        ),
    },
    "rag-046": {
        "status": "corrected",
        "source_ids": ["swg21659259", "swg21244384"],
        "answer": (
            "Direct downgrading to a lower major DataPower firmware release is not "
            "supported. The supported major-release downgrade method is to reinitialize "
            "the appliance to factory settings; for certain fix-pack downgrades, disable "
            "feature licenses that do not exist in the earlier release."
        ),
        "reason": (
            "The original reinitialize technote is the referenced procedure, while the "
            "downgrade technote states the supported major-release rule and the required "
            "license precaution."
        ),
    },
    "rag-052": {
        "status": "corrected",
        "source_ids": ["swg24043474", "swg1PI73197"],
        "answer": (
            "Yes. APAR PI73197 enables Java 8 support for EJBDeploy on WebSphere "
            "Application Server 8.5.5.9 or later. After applying the fix, EJBDeploy can "
            "no longer be used with Java 6."
        ),
        "reason": (
            "The original answer predates the PI73197 fix. The corpus contains both the "
            "downloadable fix record and the APAR record that directly answer the "
            "8.5.5.9-or-later question."
        ),
    },
    "rag-054": {
        "status": "excluded",
        "reason": (
            "The expected document is a post-migration authoring-portlet issue, while "
            "the question asks about a blank/corrupted WCM syndicator 'Subscribe Now' "
            "popup. The corpus has a different syndicator error but no exact evidence "
            "for this symptom."
        ),
    },
    "rag-056": {
        "status": "corrected",
        "source_ids": ["swg21397335"],
        "answer": (
            "For WebSphere Application Server V8 and later, use WASServiceHelper.bat "
            "from the install_root\\bin directory to create the Windows service. It is "
            "the product-shipped front end for WASService.exe; select the deployment "
            "manager or application-server profile and supply the service settings."
        ),
        "reason": (
            "The source is directly relevant and even shows a Deployment Manager service "
            "example, but the original gold answer quoted the older downloadable "
            "WASServiceCmd.exe steps. The BPM 8.5 question requires the V8-and-later "
            "WASServiceHelper.bat instruction stated in the same technote."
        ),
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def curate(rows: list[dict[str, Any]], document_ids: set[str]) -> list[dict[str, Any]]:
    curated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for original in rows:
        row = dict(original)
        row_id = str(row["id"])
        if row_id in seen:
            raise ValueError(f"duplicate gold id: {row_id}")
        seen.add(row_id)
        original_sources = list(row.get("expected_source_ids", []))
        decision = DECISIONS.get(row_id)
        row["gold_revision"] = CURATION_VERSION
        row["score_enabled"] = True
        row["gold_review_status"] = row.get("expansion_review_status", "verified")
        if row.get("expansion_review_notes"):
            row["gold_review_notes"] = row["expansion_review_notes"]
        if row.get("gold_expansion_version"):
            row["gold_review_basis"] = "expansion_audit_question_answer_source_checked"
        elif row["category"] in {"rag", "exact_search"}:
            row["gold_review_basis"] = (
                "source_document_exists_active_authorized_and_question_answer_checked"
            )
        else:
            row["gold_review_basis"] = "evaluation_contract_checked"
        if decision:
            row["gold_review_status"] = decision["status"]
            row["gold_review_notes"] = decision["reason"]
            if decision["status"] == "excluded":
                row["score_enabled"] = False
            else:
                new_sources = list(decision["source_ids"])
                missing = [source_id for source_id in new_sources if source_id not in document_ids]
                if missing:
                    raise ValueError(f"{row_id} references missing documents: {missing}")
                if new_sources != original_sources:
                    row["original_expected_source_ids"] = original_sources
                    row["expected_source_ids"] = new_sources
                if "answer" in decision and decision["answer"] != row.get("expected_answer"):
                    row["original_expected_answer"] = row.get("expected_answer", "")
                    row["expected_answer"] = decision["answer"]
        curated.append(row)
    if len(curated) != len(rows):
        raise AssertionError("curation changed the number of rows")
    return curated


def write_report(rows: list[dict[str, Any]], output: Path) -> None:
    counts = Counter(row["gold_review_status"] for row in rows)
    base_rows = [row for row in rows if row["category"] in {"rag", "exact_search"}]
    base_counts = Counter(row["gold_review_status"] for row in base_rows)
    excluded = [row for row in rows if not row["score_enabled"]]
    changed = [
        row
        for row in rows
        if "original_expected_source_ids" in row or "original_expected_answer" in row
    ]
    report = {
        "curation_version": CURATION_VERSION,
        "rows_total": len(rows),
        "rows_scored": sum(bool(row["score_enabled"]) for row in rows),
        "rows_excluded": len(excluded),
        "status_counts": dict(sorted(counts.items())),
        "base_rows_total": len(base_rows),
        "base_rows_scored": sum(bool(row["score_enabled"]) for row in base_rows),
        "base_rows_excluded": sum(not row["score_enabled"] for row in base_rows),
        "base_status_counts": dict(sorted(base_counts.items())),
        "changed_rows": [row["id"] for row in changed],
        "excluded_rows": [
            {
                "id": row["id"],
                "source_question_id": row.get("source_question_id"),
                "original_expected_source_ids": row.get("expected_source_ids", []),
                "reason": row.get("gold_review_notes", ""),
            }
            for row in excluded
        ],
        "rows": [
            {
                "id": row["id"],
                "category": row["category"],
                "score_enabled": row["score_enabled"],
                "status": row["gold_review_status"],
                "source_question_id": row.get("source_question_id"),
                "expected_source_ids": row.get("expected_source_ids", []),
                "notes": row.get("gold_review_notes", ""),
            }
            for row in rows
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# P3 金标逐题复核报告",
        "",
        f"- 复核版本：`{CURATION_VERSION}`",
        f"- 基础检索金标：{report['base_rows_total']}",
        f"- 基础检索纳入计分：{report['base_rows_scored']}",
        f"- 基础检索排除计分：{report['base_rows_excluded']}",
        f"- 全部评测行（含图谱、权限、拒答和工具）：{report['rows_total']}",
        "",
        "## 复核结论",
        "",
        "逐条检查了题目、期望答案和期望文档正文。只有能在当前语料建立证据链的题目才纳入计分；排除项保留原始标注和原因，不会静默删除。",
        "",
        "| 状态 | 数量 |",
        "|---|---:|",
    ]
    for status, count in sorted(base_counts.items()):
        lines.append(f"| {status} | {count} |")
    lines.extend(
        [
            "",
            f"## 基础检索 {report['base_rows_total']} 道逐题记录",
            "",
            "| ID | 类别 | 计分 | 状态 | 期望文档 | 复核备注 |",
            "|---|---|---:|---|---|---|",
        ]
    )
    default_notes = {
        "rag": "题目、答案与来源正文一致，保留原标注。",
        "exact_search": "题目显式指定文档 ID；ID、标题、状态和权限范围一致。",
    }
    for row in base_rows:
        notes = row.get("gold_review_notes", default_notes[row["category"]]).replace(
            "|", "\\|"
        )
        sources = ", ".join(row.get("expected_source_ids", []))
        lines.append(
            f"| {row['id']} | {row['category']} | {'是' if row['score_enabled'] else '否'} | "
            f"{row['gold_review_status']} | `{sources}` | {notes} |"
        )
    markdown = "\n".join(lines) + "\n"
    output.with_suffix(".md").write_text(markdown, encoding="utf-8")
    output.with_name(output.stem + ".zh-CN.md").write_text(markdown, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, default=Path("data/processed/techqa_p3/golden_questions.jsonl")
    )
    parser.add_argument(
        "--documents", type=Path, default=Path("data/processed/techqa_p3/documents.jsonl")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/techqa_p3/golden_questions.curated.jsonl"),
    )
    parser.add_argument("--report", type=Path, default=Path("reports/p3-gold-curation.json"))
    args = parser.parse_args()
    documents = read_jsonl(args.documents)
    document_ids = {str(row["document_id"]) for row in documents}
    curated = curate(read_jsonl(args.input), document_ids)
    write_jsonl(args.output, curated)
    write_report(curated, args.report)
    print(
        json.dumps(
            {"output": str(args.output), "report": str(args.report), "rows": len(curated)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
