from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from enterprise_rag.models import Route
from enterprise_rag.router import RuleBasedRouter


def read_json(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def title_from_context(text: str, fallback: str) -> str:
    match = re.search(r"^Title:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def classify(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()
    security_terms = ("security", "ssl", "certificate", "authentication", "encrypt", "cve")
    engineering_terms = ("install", "upgrade", "configure", "configuration", "deploy", "sdk")
    if any(term in lowered for term in security_terms):
        return "security-support", ["restricted"]
    if any(term in lowered for term in engineering_terms):
        return "engineering-support", ["engineering"]
    return "operations-support", ["operations"]


def build_documents(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    answerable_first = sorted(records, key=lambda row: bool(row.get("is_impossible")))
    selected: dict[str, dict[str, Any]] = {}
    for row in answerable_first:
        blob = f"{row.get('question', '')} " + " ".join(
            context.get("text", "") for context in row.get("contexts", [])
        )
        if "websphere" not in blob.lower():
            continue
        for context in row.get("contexts", []):
            filename = context.get("filename")
            text = context.get("text", "").strip()
            if not filename or not text or filename in selected:
                continue
            business_class, roles = classify(text)
            selected[filename] = {
                "document_id": filename.removesuffix(".txt"),
                "title": title_from_context(text, filename),
                "content": text,
                "owner": "techqa-proxy-owner",
                "business_class": business_class,
                "sensitivity": "restricted" if roles == ["restricted"] else "internal",
                "allowed_roles": roles,
                "version": "techqa-2025-05-05",
                "status": "active",
                "source_uri": f"hf://nvidia/TechQA-RAG-Eval/corpus/{filename}",
                "dataset": "nvidia/TechQA-RAG-Eval",
                "license": "Apache-2.0",
            }
            if len(selected) >= limit:
                return list(selected.values())
    return list(selected.values())


def build_rag_gold(
    records: list[dict[str, Any]], documents: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    by_filename = {f"{document['document_id']}.txt": document for document in documents}
    router = RuleBasedRouter()
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.get("is_impossible"):
            continue
        if router.route(record["question"]).route != Route.RAG:
            continue
        sources = [
            by_filename[context["filename"]]
            for context in record.get("contexts", [])
            if context.get("filename") in by_filename
        ]
        if not sources:
            continue
        source = sources[0]
        rows.append(
            {
                "id": f"rag-{len(rows) + 1:03d}",
                "category": "rag",
                "question": record["question"].strip(),
                "expected_route": "rag",
                "roles": source["allowed_roles"],
                "expected_source_ids": [item["document_id"] for item in sources],
                "expected_answer": record.get("answer", "").strip(),
                "should_refuse": False,
                "source_question_id": record.get("id"),
                "route_taxonomy_version": "p1-rules-1",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def build_exact_gold(documents: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in documents[:limit]:
        rows.append(
            {
                "id": f"exact-{len(rows) + 1:03d}",
                "category": "exact_search",
                "question": f"Find document ID {document['document_id']}.",
                "expected_route": "exact_search",
                "roles": document["allowed_roles"],
                "expected_source_ids": [document["document_id"]],
                "expected_answer": document["title"],
                "should_refuse": False,
            }
        )
    return rows


def build_tool_gold() -> list[dict[str, Any]]:
    cases = [
        ("What is total sales?", "405000"),
        ("How many sales orders are there?", "4"),
        ("What is average sales?", "101250"),
        ("What is total east sales?", "310000"),
        ("How many east sales orders are there?", "3"),
        ("What is average east sales?", "103333.33"),
        ("What is total sales in 2026Q1?", "295000"),
        ("How many sales orders are in 2026Q1?", "3"),
        ("What is average sales in 2026Q1?", "98333.33"),
        ("What is total east sales in 2026Q1?", "200000"),
        ("How many east sales orders are in 2026Q1?", "2"),
        ("What is average east sales in 2026Q1?", "100000"),
        ("What is total south sales in 2026Q1?", "95000"),
        ("How many south sales orders are in 2026Q1?", "1"),
        ("What is average south sales in 2026Q1?", "95000"),
        ("What is total east sales in 2026Q2?", "110000"),
        ("How many east sales orders are in 2026Q2?", "1"),
        ("What is average east sales in 2026Q2?", "110000"),
        ("What is total south sales?", "95000"),
        ("How many south sales orders are there?", "1"),
    ]
    return [
        {
            "id": f"tool-{index:03d}",
            "category": "tool",
            "question": question,
            "expected_route": "tool",
            "roles": ["operations"],
            "expected_source_ids": ["demo-sales-db"],
            "expected_answer": expected,
            "should_refuse": False,
        }
        for index, (question, expected) in enumerate(cases, start=1)
    ]


def build_unauthorized_gold(documents: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    restricted = [document for document in documents if document["allowed_roles"] == ["restricted"]]
    if len(restricted) < limit:
        raise RuntimeError(f"need {limit} restricted documents, found {len(restricted)}")
    return [
        {
            "id": f"acl-{index:03d}",
            "category": "unauthorized",
            "question": f"Find document ID {document['document_id']}.",
            "expected_route": "exact_search",
            "roles": ["engineering"],
            "forbidden_source_ids": [document["document_id"]],
            "expected_source_ids": [],
            "expected_answer": "",
            "should_refuse": True,
        }
        for index, document in enumerate(restricted[:limit], start=1)
    ]


def build_no_evidence_gold(limit: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"no-evidence-{index:03d}",
            "category": "no_evidence",
            "question": f"What does internal error code ORION-{9000 + index} mean?",
            "expected_route": "exact_search",
            "roles": ["engineering"],
            "expected_source_ids": [],
            "expected_answer": "",
            "should_refuse": True,
        }
        for index in range(1, limit + 1)
    ]


def write_manifest(path: Path, documents: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "document_id",
        "title",
        "business_class",
        "sensitivity",
        "allowed_roles",
        "owner",
        "version",
        "source_uri",
        "dataset",
        "license",
        "sha256",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for document in documents:
            row = {field: document.get(field, "") for field in fields}
            row["allowed_roles"] = "|".join(document["allowed_roles"])
            row["sha256"] = hashlib.sha256(document["content"].encode("utf-8")).hexdigest()
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/raw/techqa/train.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/techqa_websphere"))
    args = parser.parse_args()

    records = read_json(args.input)
    documents = build_documents(records, 200)
    if len(documents) != 200:
        raise RuntimeError(f"expected 200 documents, found {len(documents)}")

    gold = [
        *build_rag_gold(records, documents, 60),
        *build_exact_gold(documents, 20),
        *build_tool_gold(),
        *build_unauthorized_gold(documents, 10),
        *build_no_evidence_gold(10),
    ]
    if len(gold) != 120:
        raise RuntimeError(f"expected 120 gold questions, found {len(gold)}")

    document_rows = [
        {key: value for key, value in document.items() if key not in {"dataset", "license"}}
        for document in documents
    ]
    write_jsonl(args.output / "documents.jsonl", document_rows)
    write_jsonl(args.output / "golden_questions.jsonl", gold)
    write_manifest(args.output / "manifest.csv", documents)

    summary = {
        "source_dataset": "nvidia/TechQA-RAG-Eval",
        "selection": "WebSphere contexts; answerable records first; 200 unique documents",
        "documents": len(documents),
        "gold_questions": len(gold),
        "gold_by_category": {
            category: sum(row["category"] == category for row in gold)
            for category in sorted({row["category"] for row in gold})
        },
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
