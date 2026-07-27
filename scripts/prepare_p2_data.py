from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from prepare_p1_data import classify, title_from_context

from enterprise_rag.models import GraphEdge, GraphRelationType

REFERENCE_PATTERN = re.compile(r"\bswg[a-z0-9]+\b", flags=re.IGNORECASE)


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


def corpus_catalog(archive: Path) -> dict[str, str]:
    with zipfile.ZipFile(archive) as bundle:
        document_ids = [
            Path(name).stem
            for name in bundle.namelist()
            if name.startswith("corpus/") and name.endswith(".txt")
        ]
    return {document_id.lower(): document_id for document_id in document_ids}


def read_corpus_documents(archive: Path, document_ids: set[str]) -> dict[str, str]:
    texts: dict[str, str] = {}
    with zipfile.ZipFile(archive) as bundle:
        for document_id in sorted(document_ids):
            payload = bundle.read(f"corpus/{document_id}.txt")
            texts[document_id] = payload.decode("utf-8", errors="replace").strip()
    return texts


def referenced_ids(text: str, catalog: dict[str, str]) -> list[str]:
    return list(
        dict.fromkeys(
            catalog[match.group(0).lower()]
            for match in REFERENCE_PATTERN.finditer(text)
            if match.group(0).lower() in catalog
        )
    )


def select_document_ids(
    archive: Path,
    train: list[dict[str, Any]],
    p1_documents: list[dict[str, Any]],
    limit: int,
) -> tuple[set[str], dict[str, str]]:
    catalog = corpus_catalog(archive)
    selected = {catalog[document["document_id"].lower()] for document in p1_documents}
    for record in train:
        for context in record.get("contexts", []):
            filename = context.get("filename", "")
            canonical = catalog.get(filename.removesuffix(".txt").lower())
            if canonical:
                selected.add(canonical)

    core_texts = read_corpus_documents(archive, selected)
    referenced = {
        target
        for text in core_texts.values()
        for target in referenced_ids(text, catalog)
        if target not in selected
    }
    for document_id in sorted(referenced):
        if len(selected) >= limit:
            break
        selected.add(document_id)
    for document_id in sorted(catalog.values()):
        if len(selected) >= limit:
            break
        selected.add(document_id)
    if len(selected) != limit:
        raise RuntimeError(f"expected {limit} documents, selected {len(selected)}")
    return selected, catalog


def build_documents(
    texts: dict[str, str],
    p1_documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    p1_by_id = {document["document_id"].lower(): document for document in p1_documents}
    documents: list[dict[str, Any]] = []
    for document_id, text in sorted(texts.items()):
        if document_id.lower() in p1_by_id:
            documents.append(p1_by_id[document_id.lower()])
            continue
        business_class, roles = classify(text)
        documents.append(
            {
                "document_id": document_id,
                "title": title_from_context(text, document_id),
                "content": text,
                "owner": "techqa-proxy-owner",
                "business_class": business_class,
                "sensitivity": "restricted" if roles == ["restricted"] else "internal",
                "allowed_roles": roles,
                "version": "techqa-p2-2026-07-18",
                "status": "active",
                "source_uri": f"hf://nvidia/TechQA-RAG-Eval/corpus/{document_id}.txt",
            }
        )
    return documents


def evidence_anchor(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 110)
    end = min(len(text), match.end() + 110)
    return " ".join(text[start:end].split())[:500]


def build_relations(
    texts: dict[str, str],
    catalog: dict[str, str],
    selected_ids: set[str],
) -> list[dict[str, Any]]:
    relations: dict[tuple[str, str, GraphRelationType], GraphEdge] = {}
    for source_id, text in sorted(texts.items()):
        for match in REFERENCE_PATTERN.finditer(text):
            target_id = catalog.get(match.group(0).lower())
            if target_id is None or target_id not in selected_ids or target_id == source_id:
                continue
            edge = GraphEdge(
                source_id=source_id,
                target_id=target_id,
                relation=GraphRelationType.REFERENCES,
                confidence=1.0,
                evidence_anchor=evidence_anchor(text, match),
            )
            relations.setdefault((source_id, target_id, edge.relation), edge)
    return [
        edge.model_dump(mode="json")
        for edge in sorted(
            relations.values(),
            key=lambda item: (item.source_id, item.target_id, item.relation.value),
        )
    ]


def build_graph_gold(
    documents: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    documents_by_id = {document["document_id"]: document for document in documents}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        source = documents_by_id[relation["source_id"]]
        target = documents_by_id[relation["target_id"]]
        if set(source["allowed_roles"]) & set(target["allowed_roles"]):
            outgoing[relation["source_id"]].append(relation)

    candidates = [
        (source_id, sorted(edges, key=lambda edge: edge["target_id"]))
        for source_id, edges in outgoing.items()
        if 1 <= len(edges) <= 2
    ]
    rows: list[dict[str, Any]] = []
    for source_id, edges in sorted(candidates):
        source = documents_by_id[source_id]
        target_id = edges[0]["target_id"]
        target = documents_by_id[target_id]
        roles = sorted(set(source["allowed_roles"]) & set(target["allowed_roles"]))
        rows.append(
            {
                "id": f"graph-{len(rows) + 1:03d}",
                "category": "graph_rag",
                "question": (
                    f'From the document "{source["title"]}", follow its documented reference '
                    "and identify the related IBM document."
                ),
                "expected_route": "rag",
                "retrieval_mode": "graph",
                "roles": [roles[0]],
                "expected_source_ids": [source_id, target_id],
                "expected_graph_target_ids": [target_id],
                "expected_graph_path": [source_id, target_id],
                "expected_answer": target["title"],
                "should_refuse": False,
            }
        )
        if len(rows) == limit:
            break
    if len(rows) != limit:
        raise RuntimeError(f"need {limit} graph questions, found {len(rows)}")
    return rows


def build_graph_acl_gold(
    documents: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    documents_by_id = {document["document_id"]: document for document in documents}
    rows: list[dict[str, Any]] = []
    for relation in relations:
        source = documents_by_id[relation["source_id"]]
        target = documents_by_id[relation["target_id"]]
        source_roles = set(source["allowed_roles"])
        if source_roles & set(target["allowed_roles"]):
            continue
        visible_roles = sorted(source_roles - set(target["allowed_roles"]))
        if not visible_roles:
            continue
        rows.append(
            {
                "id": f"graph-acl-{len(rows) + 1:03d}",
                "category": "graph_unauthorized",
                "question": (
                    f'From the document "{source["title"]}", follow its documented reference '
                    "and identify the related IBM document."
                ),
                "expected_route": "rag",
                "retrieval_mode": "graph",
                "roles": [visible_roles[0]],
                "expected_source_ids": [source["document_id"]],
                "forbidden_source_ids": [target["document_id"]],
                "expected_answer": "",
                "should_refuse": False,
            }
        )
        if len(rows) == limit:
            break
    if len(rows) != limit:
        raise RuntimeError(f"need {limit} graph ACL questions, found {len(rows)}")
    return rows


def write_manifest(path: Path, documents: list[dict[str, Any]]) -> None:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for document in documents:
            writer.writerow(
                {
                    **{field: document.get(field, "") for field in fields},
                    "allowed_roles": "|".join(document["allowed_roles"]),
                    "dataset": "nvidia/TechQA-RAG-Eval",
                    "license": "Apache-2.0",
                    "sha256": hashlib.sha256(document["content"].encode("utf-8")).hexdigest(),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path("data/raw/techqa/corpus.zip"))
    parser.add_argument("--train", type=Path, default=Path("data/raw/techqa/train.json"))
    parser.add_argument(
        "--p1-data",
        type=Path,
        default=Path("data/processed/techqa_websphere"),
    )
    parser.add_argument("--output", type=Path, default=Path("data/processed/techqa_p2"))
    parser.add_argument("--documents", type=int, default=1000)
    parser.add_argument("--graph-questions", type=int, default=40)
    parser.add_argument("--graph-acl-questions", type=int, default=20)
    args = parser.parse_args()

    train = read_json(args.train)
    p1_documents = read_jsonl(args.p1_data / "documents.jsonl")
    selected_ids, catalog = select_document_ids(
        args.archive,
        train,
        p1_documents,
        args.documents,
    )
    texts = read_corpus_documents(args.archive, selected_ids)
    documents = build_documents(texts, p1_documents)
    relations = build_relations(texts, catalog, selected_ids)
    graph_gold = build_graph_gold(documents, relations, args.graph_questions)
    graph_acl_gold = build_graph_acl_gold(documents, relations, args.graph_acl_questions)
    p1_gold = read_jsonl(args.p1_data / "golden_questions.jsonl")
    gold = [*p1_gold, *graph_gold, *graph_acl_gold]

    write_jsonl(args.output / "documents.jsonl", documents)
    write_jsonl(args.output / "relations.jsonl", relations)
    write_jsonl(args.output / "golden_questions.jsonl", gold)
    write_manifest(args.output / "manifest.csv", documents)
    summary = {
        "source_dataset": "nvidia/TechQA-RAG-Eval",
        "selection": "P1 documents + train contexts + explicit reference targets + fillers",
        "documents": len(documents),
        "relations": len(relations),
        "relation_types": {"references": len(relations)},
        "gold_questions": len(gold),
        "gold_by_category": {
            category: sum(row["category"] == category for row in gold)
            for category in sorted({row["category"] for row in gold})
        },
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
