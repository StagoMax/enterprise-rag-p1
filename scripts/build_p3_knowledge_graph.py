from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from enterprise_rag.knowledge_extraction import (
    EXTRACTION_VERSION,
    TerraDocumentReviewer,
    document_checksum,
)
from enterprise_rag.knowledge_graph import (
    DocumentKnowledge,
    EntityType,
    KnowledgeNode,
    KnowledgeRelationType,
    extract_rule_entities,
    parse_sections,
    propose_rule_relations,
    review_units,
)
from enterprise_rag.llm import OpenAiCompatibleChatModel, OpenAiResponsesChatModel

DEFAULT_MODEL = "gpt-5.6-terra"
_thread_state = threading.local()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def load_env(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def nowcoding_credentials(env_path: Path) -> tuple[str, str]:
    env = load_env(env_path)
    base_url = env.get("NOWCODING_BASE_URL", "").strip()
    api_key = env.get("NOWCODING_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("NOWCODING_BASE_URL and NOWCODING_KEY are required")
    return base_url, api_key


def local_responses_base_url(env_path: Path) -> str | None:
    env = load_env(env_path)
    configured = env.get("NOWCODING_RESPONSES_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    try:
        with socket.create_connection(("127.0.0.1", 15723), timeout=0.3):
            return "http://127.0.0.1:15723/v1"
    except OSError:
        return None


def thread_reviewer(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: float,
    max_tokens: int,
    max_retries: int,
    responses_base_url: str | None,
) -> TerraDocumentReviewer:
    reviewer = getattr(_thread_state, "reviewer", None)
    if reviewer is None:
        if responses_base_url:
            model = OpenAiResponsesChatModel(
                responses_base_url,
                api_key,
                model_name,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                max_retries=max_retries,
            )
        else:
            model = OpenAiCompatibleChatModel(
                base_url,
                api_key,
                model_name,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                temperature=0.0,
                max_retries=max_retries,
            )
        reviewer = TerraDocumentReviewer(model, model_name=model_name)
        _thread_state.reviewer = reviewer
    return reviewer


def process_document(
    row: dict[str, Any],
    *,
    corpus_document_ids: set[str],
    base_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: float,
    max_tokens: int,
    max_retries: int,
    review_unit_characters: int,
    responses_base_url: str | None,
) -> DocumentKnowledge:
    document_id = str(row["document_id"])
    title = str(row["title"])
    content = str(row["content"])
    sections = parse_sections(document_id, content)
    entities = extract_rule_entities(sections)
    relations = propose_rule_relations(
        document_id,
        sections,
        entities,
        corpus_document_ids,
    )
    units = review_units(
        sections,
        entities,
        relations,
        max_characters=review_unit_characters,
    )
    reviewer = thread_reviewer(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        max_retries=max_retries,
        responses_base_url=responses_base_url,
    )
    (
        reviewed_sections,
        nodes,
        mentions,
        accepted_relations,
        rejections,
        request_count,
        intelligence_audit,
    ) = reviewer.review(
        document_id=document_id,
        title=title,
        document_text=content,
        sections=sections,
        entities=entities,
        relations=relations,
        units=units,
    )
    return DocumentKnowledge(
        document_id=document_id,
        checksum=document_checksum(content),
        extraction_version=EXTRACTION_VERSION,
        model=model_name,
        sections=reviewed_sections,
        nodes=nodes,
        mentions=mentions,
        relations=accepted_relations,
        deterministic_entity_count=len(entities),
        deterministic_relation_count=len(relations),
        llm_request_count=request_count,
        validation_rejections=rejections,
        intelligence_audit=intelligence_audit,
    )


def load_cache(
    path: Path,
    documents_by_id: dict[str, dict[str, Any]],
) -> dict[str, DocumentKnowledge]:
    cached: dict[str, DocumentKnowledge] = {}
    if not path.exists():
        return cached
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = DocumentKnowledge.model_validate_json(line)
            document = documents_by_id.get(row.document_id)
            if document is None:
                continue
            if row.extraction_version != EXTRACTION_VERSION:
                continue
            if row.checksum != document_checksum(str(document["content"])):
                continue
            previous = cached.get(row.document_id)
            if previous is not None and previous != row:
                raise RuntimeError(
                    "conflicting knowledge cache entries for "
                    f"{row.document_id} at line {line_number}"
                )
            cached[row.document_id] = row
    return cached


def _merge_node(nodes: dict[str, KnowledgeNode], node: KnowledgeNode) -> None:
    previous = nodes.get(node.node_id)
    if previous is None:
        nodes[node.node_id] = node
        return
    aliases = list(dict.fromkeys([*previous.aliases, *node.aliases]))
    nodes[node.node_id] = previous.model_copy(
        update={"aliases": aliases, "confidence": max(previous.confidence, node.confidence)}
    )


def project_document_relations(
    documents: list[dict[str, Any]],
    results: list[DocumentKnowledge],
    baseline_relations: list[dict[str, Any]],
    *,
    max_entity_documents: int,
    neighbors_per_document: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    document_ids = {str(row["document_id"]) for row in documents}
    projected: dict[tuple[str, str, str], dict[str, Any]] = {}
    provenance_counts: Counter[str] = Counter()

    def add(
        source_id: str,
        target_id: str,
        relation: str,
        confidence: float,
        evidence: str,
        provenance: str,
    ) -> None:
        if source_id == target_id or source_id not in document_ids or target_id not in document_ids:
            return
        key = (source_id, target_id, relation)
        row = {
            "source_id": source_id,
            "target_id": target_id,
            "relation": relation,
            "confidence": round(min(max(confidence, 0.0), 1.0), 6),
            "evidence_anchor": " ".join(evidence.split())[:500],
        }
        previous = projected.get(key)
        if previous is None or row["confidence"] > previous["confidence"]:
            projected[key] = row
        provenance_counts[provenance] += 1

    for row in baseline_relations:
        add(
            str(row["source_id"]),
            str(row["target_id"]),
            str(row.get("relation", "references")),
            float(row.get("confidence", 1.0)),
            str(row.get("evidence_anchor", "explicit document reference")),
            "baseline_explicit_reference",
        )

    document_node_to_id = {
        f"document:{document_id.casefold()}": document_id for document_id in document_ids
    }
    entity_documents: dict[str, dict[str, tuple[float, str, EntityType]]] = defaultdict(dict)
    for result in results:
        node_types = {node.node_id: node.node_type for node in result.nodes}
        for relation in result.relations:
            if relation.relation == KnowledgeRelationType.REFERENCES:
                source_id = document_node_to_id.get(relation.source_id)
                target_id = document_node_to_id.get(relation.target_id)
                if source_id and target_id:
                    add(
                        source_id,
                        target_id,
                        "references",
                        relation.confidence,
                        relation.evidence,
                        "terra_validated_reference",
                    )
        for mention in result.mentions:
            entity_type = node_types.get(mention.node_id)
            if entity_type is None or entity_type in {
                EntityType.DOCUMENT,
                EntityType.PRODUCT,
                EntityType.VERSION,
                EntityType.PROTOCOL,
                EntityType.FILE,
                EntityType.ORGANIZATION,
                EntityType.TECHNOLOGY,
            }:
                continue
            previous = entity_documents[mention.node_id].get(result.document_id)
            value = (mention.confidence, mention.evidence, entity_type)
            if previous is None or value[0] > previous[0]:
                entity_documents[mention.node_id][result.document_id] = value

    type_confidence = {
        EntityType.VULNERABILITY: 0.94,
        EntityType.FIX: 0.92,
        EntityType.ERROR_CODE: 0.9,
        EntityType.CONFIGURATION: 0.82,
        EntityType.COMMAND: 0.8,
        EntityType.COMPONENT: 0.76,
        EntityType.OPERATING_SYSTEM: 0.74,
        EntityType.RUNTIME: 0.74,
        EntityType.SYMPTOM: 0.7,
        EntityType.CAUSE: 0.7,
        EntityType.PROCEDURE: 0.68,
    }
    for node_id, per_document in entity_documents.items():
        if not 2 <= len(per_document) <= max_entity_documents:
            continue
        ranked = sorted(
            per_document.items(),
            key=lambda item: (-item[1][0], item[0]),
        )
        for source_id, (source_confidence, source_evidence, entity_type) in ranked:
            neighbors = [item for item in ranked if item[0] != source_id][:neighbors_per_document]
            for target_id, (target_confidence, _, _) in neighbors:
                confidence = min(source_confidence, target_confidence, type_confidence[entity_type])
                add(
                    source_id,
                    target_id,
                    "related_to",
                    confidence,
                    f"Shared reviewed {entity_type.value} {node_id}. {source_evidence}",
                    f"shared_{entity_type.value}",
                )
    rows = [projected[key] for key in sorted(projected)]
    return rows, dict(sorted(provenance_counts.items()))


def finalize(
    *,
    documents: list[dict[str, Any]],
    results: list[DocumentKnowledge],
    output: Path,
    baseline_relations: list[dict[str, Any]],
    report_path: Path,
    model_name: str,
    elapsed_seconds: float,
    max_entity_documents: int,
    neighbors_per_document: int,
    source_document_count: int,
    cached_only: bool,
) -> dict[str, Any]:
    nodes: dict[str, KnowledgeNode] = {}
    mentions: dict[str, dict[str, Any]] = {}
    relations: dict[str, dict[str, Any]] = {}
    section_rows: list[dict[str, Any]] = []
    validation_rejections: list[dict[str, Any]] = []
    for result in results:
        for section in result.sections:
            section_rows.append(section.model_dump(mode="json"))
        for node in result.nodes:
            _merge_node(nodes, node)
        for mention in result.mentions:
            mentions[mention.mention_id] = mention.model_dump(mode="json")
        for relation in result.relations:
            relations[relation.relation_id] = relation.model_dump(mode="json")
        validation_rejections.extend(
            {"document_id": result.document_id, **row}
            for row in result.validation_rejections
        )

    document_relations, projection_counts = project_document_relations(
        documents,
        results,
        baseline_relations,
        max_entity_documents=max_entity_documents,
        neighbors_per_document=neighbors_per_document,
    )
    write_jsonl_atomic(
        output / "sections.jsonl",
        sorted(section_rows, key=lambda row: (row["document_id"], row["start"])),
    )
    write_jsonl_atomic(
        output / "nodes.jsonl",
        [nodes[key].model_dump(mode="json") for key in sorted(nodes)],
    )
    write_jsonl_atomic(
        output / "mentions.jsonl",
        [mentions[key] for key in sorted(mentions)],
    )
    write_jsonl_atomic(
        output / "relations.jsonl",
        [relations[key] for key in sorted(relations)],
    )
    write_jsonl_atomic(output / "document_relations.jsonl", document_relations)
    write_jsonl_atomic(output / "validation_rejections.jsonl", validation_rejections)

    node_counts = Counter(node.node_type.value for node in nodes.values())
    relation_counts = Counter(row["relation"] for row in relations.values())
    section_counts = Counter(row["section_type"] for row in section_rows)
    audit_totals: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        for stage, values in result.intelligence_audit.items():
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if isinstance(value, int):
                    audit_totals[stage][key] += value
    intelligence_coverage: dict[str, dict[str, Any]] = {}
    for stage, counts in sorted(audit_totals.items()):
        payload: dict[str, Any] = dict(sorted(counts.items()))
        proposed = counts.get("proposed")
        reviewed = counts.get("reviewed")
        if proposed is not None and reviewed is not None:
            payload["coverage"] = round(reviewed / proposed, 6) if proposed else 1.0
        units = counts.get("units")
        units_reviewed = counts.get("units_reviewed")
        if units is not None and units_reviewed is not None:
            payload["unit_coverage"] = round(units_reviewed / units, 6) if units else 1.0
        intelligence_coverage[stage] = payload
    report = {
        "extraction_version": EXTRACTION_VERSION,
        "model": model_name,
        "documents": len(results),
        "source_documents": source_document_count,
        "complete_corpus": len(results) == source_document_count,
        "cached_only": cached_only,
        "llm_requests": sum(result.llm_request_count for result in results),
        "sections": len(section_rows),
        "section_type_counts": dict(sorted(section_counts.items())),
        "nodes": len(nodes),
        "node_type_counts": dict(sorted(node_counts.items())),
        "mentions": len(mentions),
        "relations": len(relations),
        "relation_type_counts": dict(sorted(relation_counts.items())),
        "validation_rejections": len(validation_rejections),
        "document_relations": len(document_relations),
        "document_relation_projection_counts": projection_counts,
        "intelligence_stage_coverage": intelligence_coverage,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "output": str(output),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown = [
        "# P3 智能知识图谱构建报告",
        "",
        f"- 抽取版本：`{EXTRACTION_VERSION}`",
        f"- 智能模型：`{model_name}`",
        f"- 完成文档：{report['documents']}",
        f"- LLM 请求：{report['llm_requests']}",
        f"- 结构章节：{report['sections']}",
        f"- 规范节点：{report['nodes']}",
        f"- 实体提及：{report['mentions']}",
        f"- 知识关系：{report['relations']}",
        f"- 关系验证拒绝：{report['validation_rejections']}",
        f"- 投影文档边：{report['document_relations']}",
        f"- 总耗时：{report['elapsed_seconds']} 秒",
        "",
        "## 节点类型",
        "",
        "| 类型 | 数量 |",
        "|---|---:|",
    ]
    markdown.extend(f"| {key} | {value} |" for key, value in sorted(node_counts.items()))
    markdown.extend(["", "## 关系类型", "", "| 类型 | 数量 |", "|---|---:|"])
    markdown.extend(f"| {key} | {value} |" for key, value in sorted(relation_counts.items()))
    report_path.with_suffix(".md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--documents", type=Path, default=Path("data/processed/techqa_p3/documents.jsonl")
    )
    parser.add_argument(
        "--baseline-relations",
        type=Path,
        default=Path("data/processed/techqa_p3/relations.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/techqa_p3/knowledge_graph"),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("artifacts/p3-knowledge-terra-v5.jsonl"),
    )
    parser.add_argument(
        "--report", type=Path, default=Path("reports/p3-knowledge-graph-build.json")
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--cached-only",
        action="store_true",
        help="Finalize valid cached documents without making API requests.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--document-retries", type=int, default=2)
    parser.add_argument("--review-unit-characters", type=int, default=8000)
    parser.add_argument("--max-entity-documents", type=int, default=20)
    parser.add_argument("--neighbors-per-document", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 1 or args.document_retries < 0:
        raise SystemExit("workers must be positive and retries non-negative")

    started = time.perf_counter()
    documents = read_jsonl(args.documents)
    if args.limit is not None:
        documents = documents[: args.limit]
    source_document_count = len(documents)
    documents_by_id = {str(row["document_id"]): row for row in documents}
    if len(documents_by_id) != len(documents):
        raise RuntimeError("documents contain duplicate IDs")
    corpus_document_ids = {document_id.casefold() for document_id in documents_by_id}
    base_url, api_key = nowcoding_credentials(args.env_file)
    responses_base_url = local_responses_base_url(args.env_file)
    cached = load_cache(args.cache, documents_by_id)
    if args.cached_only:
        documents = [
            row for row in documents if str(row["document_id"]) in cached
        ]
        documents_by_id = {str(row["document_id"]): row for row in documents}
    pending = [row for row in documents if str(row["document_id"]) not in cached]
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    completed = len(cached)
    llm_requests = sum(row.llm_request_count for row in cached.values())
    failures: dict[str, str] = {}
    print(
        json.dumps(
            {
                "documents": len(documents),
                "cached": len(cached),
                "pending": len(pending),
                "workers": args.workers,
                "model": args.model,
                "extraction_version": EXTRACTION_VERSION,
                "transport": "responses" if responses_base_url else "chat_completions",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    def task(row: dict[str, Any]) -> DocumentKnowledge:
        last_error: Exception | None = None
        for attempt in range(args.document_retries + 1):
            try:
                return process_document(
                    row,
                    corpus_document_ids=corpus_document_ids,
                    base_url=base_url,
                    api_key=api_key,
                    model_name=args.model,
                    timeout_seconds=args.timeout_seconds,
                    max_tokens=args.max_tokens,
                    max_retries=args.max_retries,
                    review_unit_characters=args.review_unit_characters,
                    responses_base_url=responses_base_url,
                )
            except Exception as error:  # noqa: BLE001 - preserve document-level recovery
                last_error = error
                if attempt < args.document_retries:
                    time.sleep(1.5 * (2**attempt))
        assert last_error is not None
        raise last_error

    with (
        args.cache.open("a", encoding="utf-8", newline="\n") as cache_handle,
        ThreadPoolExecutor(max_workers=args.workers) as executor,
    ):
        futures: dict[Future[DocumentKnowledge], str] = {
            executor.submit(task, row): str(row["document_id"]) for row in pending
        }
        for future in as_completed(futures):
            document_id = futures[future]
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001 - report all failed documents
                failures[document_id] = f"{type(error).__name__}: {error}"
            else:
                payload = result.model_dump_json()
                with lock:
                    cache_handle.write(payload + "\n")
                    cache_handle.flush()
                cached[document_id] = result
                completed += 1
                llm_requests += result.llm_request_count
            if completed > 0 and completed % 25 == 0:
                elapsed = time.perf_counter() - started
                rate = max((completed - (len(documents) - len(pending))) / elapsed, 0.0)
                remaining = (len(documents) - completed) / rate if rate else 0.0
                print(
                    json.dumps(
                        {
                            "completed": completed,
                            "total": len(documents),
                            "failed": len(failures),
                            "llm_requests": llm_requests,
                            "documents_per_second": round(rate, 3),
                            "eta_minutes": round(remaining / 60, 1),
                        }
                    ),
                    flush=True,
                )

    if failures:
        failure_path = args.report.with_name(args.report.stem + "-failures.json")
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(
            json.dumps(failures, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise SystemExit(
            f"{len(failures)} documents failed; rerun to resume. Details: {failure_path}"
        )
    results = [cached[str(row["document_id"])] for row in documents]
    baseline_relations = read_jsonl(args.baseline_relations)
    report = finalize(
        documents=documents,
        results=results,
        output=args.output,
        baseline_relations=baseline_relations,
        report_path=args.report,
        model_name=args.model,
        elapsed_seconds=time.perf_counter() - started,
        max_entity_documents=args.max_entity_documents,
        neighbors_per_document=args.neighbors_per_document,
        source_document_count=source_document_count,
        cached_only=args.cached_only,
    )
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
