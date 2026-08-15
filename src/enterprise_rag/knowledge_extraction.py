from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from enterprise_rag.knowledge_graph import (
    EntityCandidate,
    EntityMention,
    EntityType,
    KnowledgeNode,
    KnowledgeRelation,
    KnowledgeRelationType,
    KnowledgeSection,
    RelationCandidate,
    SectionType,
    canonical_node_id,
    canonical_product_name,
    evidence_is_present,
    extract_json_object,
    mention_id,
    relation_id,
)
from enterprise_rag.llm import ChatModel

EXTRACTION_VERSION = "p3-knowledge-terra-v5-2026-08-10"

_SYSTEM_PROMPT = """You are an enterprise knowledge-graph extraction and validation engine.
You must intelligently review every supplied stage: document structure, node types, entity
extraction, canonicalization, deterministic relation-rule proposals, and final relation validity.
Use only facts supported by the supplied text. Return exactly one valid JSON object and no
markdown. Evidence must be copied verbatim from the supplied text. Never invent identifiers.

Allowed section types:
title, summary, question, problem, symptom, cause, environment, resolution, answer,
related_information, content, other.

Allowed entity types:
document, product, component, version, error_code, fix, vulnerability, configuration, command,
file, operating_system, protocol, runtime, symptom, cause, procedure, organization, technology.

Allowed relation types:
references, part_of, version_of, applies_to, fixes, affects, caused_by, resolves, supersedes,
supports, does_not_support, configures, requires, related_to.

Return this compact schema (a=accept, r=reject):
{
  "s": [["section_id","section_type",0.0]],
  "ea": ["accepted E id whose proposed type and canonical name need no change"],
  "ec": [["accepted E id needing correction","correct canonical name","correct type",0.0]],
  "er": [["rejected E id","short reason"]],
  "ne": [
    {"id":"N id","decision":"a","surface":"verbatim mention",
     "canonical_name":"normalized name","entity_type":"allowed type",
     "section_id":"...","evidence":"verbatim text","confidence":0.0}
  ],
  "ra": ["accepted R id unchanged"],
  "rr": [["rejected R id","short reason"]],
  "nr": [
    {
      "decision":"accept or reject", "relation":"allowed type",
      "source_ref":"DOC/E/N id", "target_ref":"DOC/E/N id", "section_id":"...",
      "evidence":"verbatim text", "confidence":0.0, "reason":"..."
    }
  ],
  "v": {"valid":true, "issues":["..."]}
}

Review every proposed entity and every proposed rule exactly once. You may add entities as N1,
N2, ... and add relations when the text directly supports them. DOC means the current document.
Every proposed E id must occur exactly once across ea/ec/er. Every proposed R id must occur
exactly once across ra/rr. For existing ids, never repeat supplied text. Add at most five missing
high-value entities and at most six direct high-confidence new relations per review unit.
When a proposed rule row has member_rule_ids, review the row once using its rule_id; that
intelligent decision applies to all exactly equivalent member rules.
Do not create MENTIONS edges; those are generated mechanically from accepted entity mentions.
Do not infer a positive relation from a negated statement. Prefer does_not_support when explicit.
Generic co-occurrence is not a factual relation. Keep symptom/cause/procedure canonical names
concise but faithful to the evidence."""


_RELATION_ENDPOINTS: dict[
    KnowledgeRelationType, tuple[set[EntityType] | None, set[EntityType] | None]
] = {
    KnowledgeRelationType.REFERENCES: ({EntityType.DOCUMENT}, {EntityType.DOCUMENT}),
    KnowledgeRelationType.PART_OF: (
        {EntityType.COMPONENT, EntityType.CONFIGURATION, EntityType.RUNTIME},
        {EntityType.PRODUCT, EntityType.COMPONENT},
    ),
    KnowledgeRelationType.VERSION_OF: (
        {EntityType.VERSION},
        {EntityType.PRODUCT, EntityType.COMPONENT},
    ),
    KnowledgeRelationType.APPLIES_TO: (
        {EntityType.DOCUMENT, EntityType.FIX, EntityType.PROCEDURE, EntityType.CONFIGURATION},
        {
            EntityType.PRODUCT,
            EntityType.COMPONENT,
            EntityType.VERSION,
            EntityType.OPERATING_SYSTEM,
            EntityType.RUNTIME,
        },
    ),
    KnowledgeRelationType.FIXES: (
        {EntityType.FIX, EntityType.PROCEDURE, EntityType.CONFIGURATION},
        {EntityType.ERROR_CODE, EntityType.SYMPTOM, EntityType.VULNERABILITY},
    ),
    KnowledgeRelationType.AFFECTS: (
        {EntityType.ERROR_CODE, EntityType.SYMPTOM, EntityType.VULNERABILITY, EntityType.CAUSE},
        {EntityType.PRODUCT, EntityType.COMPONENT, EntityType.VERSION, EntityType.RUNTIME},
    ),
    KnowledgeRelationType.CAUSED_BY: (
        {EntityType.ERROR_CODE, EntityType.SYMPTOM},
        {EntityType.CAUSE, EntityType.CONFIGURATION, EntityType.VERSION, EntityType.VULNERABILITY},
    ),
    KnowledgeRelationType.RESOLVES: (
        {EntityType.PROCEDURE, EntityType.FIX, EntityType.CONFIGURATION, EntityType.COMMAND},
        {EntityType.ERROR_CODE, EntityType.SYMPTOM, EntityType.CAUSE, EntityType.VULNERABILITY},
    ),
    KnowledgeRelationType.SUPERSEDES: (
        {EntityType.VERSION, EntityType.FIX, EntityType.DOCUMENT},
        {EntityType.VERSION, EntityType.FIX, EntityType.DOCUMENT},
    ),
    KnowledgeRelationType.SUPPORTS: (
        {EntityType.PRODUCT, EntityType.COMPONENT, EntityType.VERSION},
        {
            EntityType.PRODUCT,
            EntityType.COMPONENT,
            EntityType.VERSION,
            EntityType.OPERATING_SYSTEM,
            EntityType.RUNTIME,
            EntityType.PROTOCOL,
            EntityType.TECHNOLOGY,
        },
    ),
    KnowledgeRelationType.DOES_NOT_SUPPORT: (
        {EntityType.PRODUCT, EntityType.COMPONENT, EntityType.VERSION},
        {
            EntityType.PRODUCT,
            EntityType.COMPONENT,
            EntityType.VERSION,
            EntityType.OPERATING_SYSTEM,
            EntityType.RUNTIME,
            EntityType.PROTOCOL,
            EntityType.TECHNOLOGY,
        },
    ),
    KnowledgeRelationType.CONFIGURES: (
        {EntityType.CONFIGURATION, EntityType.COMMAND, EntityType.PROCEDURE},
        {EntityType.PRODUCT, EntityType.COMPONENT, EntityType.RUNTIME, EntityType.PROTOCOL},
    ),
    KnowledgeRelationType.REQUIRES: (None, None),
    KnowledgeRelationType.RELATED_TO: (None, None),
}


def _compact_entity(entity: EntityCandidate, member_ids: list[str]) -> dict[str, Any]:
    return {
        "id": entity.candidate_id,
        "member_ids": member_ids,
        "entity_type": entity.entity_type.value,
        "surface": entity.surface,
        "canonical_name": entity.canonical_name,
        "section_id": entity.section_id,
        "evidence": entity.evidence,
        "confidence": entity.confidence,
        "extraction_method": entity.extraction_method,
    }


def _prepare_unit(
    unit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    entities: list[EntityCandidate] = unit["entities"]
    groups: dict[tuple[EntityType, str], list[EntityCandidate]] = defaultdict(list)
    for entity in entities:
        groups[(entity.entity_type, entity.canonical_name.casefold())].append(entity)

    representative_by_member: dict[str, str] = {}
    compact_entities: list[dict[str, Any]] = []
    for rows in groups.values():
        representative = max(rows, key=lambda row: (row.confidence, -row.start))
        member_ids = [row.candidate_id for row in rows]
        for member_id in member_ids:
            representative_by_member[member_id] = representative.candidate_id
        compact_entities.append(_compact_entity(representative, member_ids))

    compact_relations: list[dict[str, Any]] = []
    relation_index: dict[tuple[str, str, KnowledgeRelationType], int] = {}
    representative_rule_by_member: dict[str, str] = {}
    for relation in unit["relations"]:
        source_ref = representative_by_member.get(relation.source_ref, relation.source_ref)
        target_ref = representative_by_member.get(relation.target_ref, relation.target_ref)
        key = (source_ref, target_ref, relation.relation)
        if source_ref == target_ref:
            continue
        previous_index = relation_index.get(key)
        if previous_index is not None:
            representative = compact_relations[previous_index]["rule_id"]
            compact_relations[previous_index]["member_rule_ids"].append(relation.rule_id)
            representative_rule_by_member[relation.rule_id] = representative
            continue
        relation_index[key] = len(compact_relations)
        representative_rule_by_member[relation.rule_id] = relation.rule_id
        compact_relations.append(
            {
                **relation.model_dump(mode="json"),
                "source_ref": source_ref,
                "target_ref": target_ref,
                "member_rule_ids": [relation.rule_id],
            }
        )

    payload = {
        "sections": [
            {
                "section_id": section.section_id,
                "proposed_type": section.section_type.value,
                "heading": section.heading,
                "text": section.content,
            }
            for section in unit["sections"]
        ],
        "proposed_entities": compact_entities,
        "proposed_rule_relations": compact_relations,
    }
    return payload, representative_by_member, representative_rule_by_member


def build_review_prompt(
    document_id: str,
    title: str,
    unit: dict[str, Any],
) -> tuple[str, dict[str, str], dict[str, str]]:
    payload, representative_by_member, representative_rule_by_member = _prepare_unit(unit)
    prompt = {
        "document_id": document_id,
        "document_title": title,
        "instruction": (
            "Review structure, entity types, extraction, normalization, every deterministic "
            "rule proposal, and final relation validity. Add missing supported entities and "
            "relations. Return only the required JSON object."
        ),
        **payload,
    }
    return (
        json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
        representative_by_member,
        representative_rule_by_member,
    )


def _safe_enum(enum_type: type[Any], value: Any) -> Any | None:
    try:
        return enum_type(str(value).strip().casefold())
    except (TypeError, ValueError):
        return None


def _confidence(value: Any, default: float) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return default


def _accepted(value: Any) -> bool:
    return str(value).strip().casefold() in {"a", "accept", "accepted", "valid", "true"}


def _expand_compact_result(result: dict[str, Any]) -> dict[str, Any]:
    """Translate the token-efficient wire schema to the internal verbose schema."""
    if not any(key in result for key in ("s", "ea", "ec", "er", "ra", "rr")):
        return result
    sections = []
    for row in result.get("s", []):
        if isinstance(row, list) and len(row) >= 2:
            sections.append(
                {
                    "section_id": row[0],
                    "section_type": row[1],
                    "confidence": row[2] if len(row) > 2 else 0.8,
                }
            )
    entities = [
        {"id": reference, "decision": "accept"}
        for reference in result.get("ea", [])
        if isinstance(reference, str)
    ]
    for row in result.get("ec", []):
        if not isinstance(row, list) or len(row) < 3:
            continue
        entities.append(
            {
                "id": row[0],
                "decision": "accept",
                "canonical_name": row[1],
                "entity_type": row[2],
                "confidence": row[3] if len(row) > 3 else 0.8,
            }
        )
    for row in result.get("er", []):
        if isinstance(row, list) and row:
            entities.append(
                {
                    "id": row[0],
                    "decision": "reject",
                    "reason": row[1] if len(row) > 1 else "model_rejected",
                }
            )
    entities.extend(row for row in result.get("ne", []) if isinstance(row, dict))
    rule_reviews = [
        {"rule_id": reference, "decision": "accept"}
        for reference in result.get("ra", [])
        if isinstance(reference, str)
    ]
    for row in result.get("rr", []):
        if isinstance(row, list) and row:
            rule_reviews.append(
                {
                    "rule_id": row[0],
                    "decision": "reject",
                    "reason": row[1] if len(row) > 1 else "model_rejected",
                }
            )
    return {
        "section_reviews": sections,
        "entities": entities,
        "rule_reviews": rule_reviews,
        "new_relations": result.get("nr", []),
        "document_validation": result.get("v"),
    }


def _document_node(document_id: str, title: str, model_name: str) -> KnowledgeNode:
    return KnowledgeNode(
        node_id=canonical_node_id(EntityType.DOCUMENT, document_id),
        node_type=EntityType.DOCUMENT,
        canonical_name=document_id,
        aliases=[title],
        confidence=1.0,
        normalization_method="document-id-v1",
        reviewed_by_model=model_name,
    )


def _merge_node(target: dict[str, KnowledgeNode], node: KnowledgeNode) -> None:
    previous = target.get(node.node_id)
    if previous is None:
        target[node.node_id] = node
        return
    aliases = list(dict.fromkeys([*previous.aliases, *node.aliases]))
    target[node.node_id] = previous.model_copy(
        update={"aliases": aliases, "confidence": max(previous.confidence, node.confidence)}
    )


def _validate_relation(
    relation: KnowledgeRelationType,
    source: KnowledgeNode,
    target: KnowledgeNode,
    evidence: str,
    document_text: str,
) -> list[str]:
    issues: list[str] = []
    if source.node_id == target.node_id:
        issues.append("self_relation")
    if not evidence_is_present(evidence, document_text):
        issues.append("evidence_not_verbatim_in_document")
    allowed_source, allowed_target = _RELATION_ENDPOINTS[relation]
    if allowed_source is not None and source.node_type not in allowed_source:
        issues.append(f"invalid_source_type:{source.node_type.value}")
    if allowed_target is not None and target.node_type not in allowed_target:
        issues.append(f"invalid_target_type:{target.node_type.value}")
    return issues


class TerraDocumentReviewer:
    def __init__(self, model: ChatModel, *, model_name: str = "gpt-5.6-terra") -> None:
        self._model = model
        self.model_name = model_name

    def review(
        self,
        *,
        document_id: str,
        title: str,
        document_text: str,
        sections: list[KnowledgeSection],
        entities: list[EntityCandidate],
        relations: list[RelationCandidate],
        units: list[dict[str, Any]],
    ) -> tuple[
        list[KnowledgeSection],
        list[KnowledgeNode],
        list[EntityMention],
        list[KnowledgeRelation],
        list[dict[str, Any]],
        int,
        dict[str, Any],
    ]:
        section_updates: dict[str, tuple[SectionType, float]] = {}
        nodes: dict[str, KnowledgeNode] = {}
        mentions: dict[str, EntityMention] = {}
        accepted_relations: dict[
            tuple[str, str, KnowledgeRelationType, str], KnowledgeRelation
        ] = {}
        rejections: list[dict[str, Any]] = []
        document_node = _document_node(document_id, title, self.model_name)
        nodes[document_node.node_id] = document_node
        candidates_by_id = {candidate.candidate_id: candidate for candidate in entities}
        rules_by_id = {relation.rule_id: relation for relation in relations}
        request_count = 0
        expected_section_ids = {section.section_id for section in sections}
        reviewed_section_ids: set[str] = set()
        expected_candidate_ids: set[str] = set()
        reviewed_candidate_ids: set[str] = set()
        reviewed_rule_ids: set[str] = set()
        validation_units_reviewed = 0
        model_added_entities = 0

        for unit in units:
            (
                prompt,
                representative_by_member,
                representative_rule_by_member,
            ) = build_review_prompt(document_id, title, unit)
            compact_ids = set(representative_by_member.values())
            unit_candidate_ids = {
                candidate.candidate_id
                for candidate in unit["entities"]
                if candidate.candidate_id in compact_ids
            }
            unit_rule_ids = {relation.rule_id for relation in unit["relations"]}
            expected_rule_references = set(representative_rule_by_member.values())
            expected_unit_sections = {
                section.section_id.split(":part:")[0] for section in unit["sections"]
            }
            section_results: dict[str, dict[str, Any]] = {}
            entity_results: dict[str, dict[str, Any]] = {}
            rule_results: dict[str, dict[str, Any]] = {}
            new_relations: list[dict[str, Any]] = []
            validations: list[dict[str, Any]] = []
            current_prompt = prompt
            for completion_attempt in range(3):
                raw = self._model.complete(_SYSTEM_PROMPT, current_prompt)
                request_count += 1
                partial = _expand_compact_result(extract_json_object(raw))
                for review in partial.get("section_reviews", []):
                    if isinstance(review, dict):
                        reference = str(review.get("section_id", "")).split(":part:")[0]
                        if reference:
                            section_results[reference] = review
                for review in partial.get("entities", []):
                    if isinstance(review, dict):
                        reference = str(review.get("id", "")).strip()
                        if reference:
                            entity_results[reference] = review
                for review in partial.get("rule_reviews", []):
                    if isinstance(review, dict):
                        reference = str(review.get("rule_id", "")).strip()
                        if reference:
                            rule_results[reference] = review
                new_relations.extend(
                    row
                    for row in partial.get("new_relations", [])
                    if isinstance(row, dict)
                )
                validation = partial.get("document_validation")
                if isinstance(validation, dict):
                    validations.append(validation)
                missing_sections = expected_unit_sections - set(section_results)
                missing_entities = unit_candidate_ids - set(entity_results)
                missing_rules = expected_rule_references - set(rule_results)
                if not (missing_sections or missing_entities or missing_rules):
                    break
                retry_payload = json.loads(prompt)
                retry_payload["completion_instruction"] = {
                    "attempt": completion_attempt + 2,
                    "return_only_missing_reviews": True,
                    "missing_section_ids": sorted(missing_sections),
                    "missing_entity_ids": sorted(missing_entities),
                    "missing_rule_ids": sorted(missing_rules),
                }
                current_prompt = json.dumps(
                    retry_payload, ensure_ascii=False, separators=(",", ":")
                )
            result = {
                "section_reviews": list(section_results.values()),
                "entities": list(entity_results.values()),
                "rule_reviews": list(rule_results.values()),
                "new_relations": new_relations,
                "document_validation": {
                    "valid": all(bool(row.get("valid", True)) for row in validations),
                    "issues": [
                        issue
                        for row in validations
                        for issue in row.get("issues", [])
                    ],
                }
                if validations
                else None,
            }
            expected_candidate_ids.update(unit_candidate_ids)
            reviewed_candidates: set[str] = set()
            ref_to_node: dict[str, str] = {"DOC": document_node.node_id}

            for review in result.get("section_reviews", []):
                if not isinstance(review, dict):
                    continue
                section_id = str(review.get("section_id", "")).split(":part:")[0]
                section_type = _safe_enum(SectionType, review.get("section_type"))
                if section_type is not None:
                    reviewed_section_ids.add(section_id)
                    section_updates[section_id] = (
                        section_type,
                        _confidence(review.get("confidence"), 0.8),
                    )

            for review in result.get("entities", []):
                if not isinstance(review, dict):
                    continue
                reference = str(review.get("id", "")).strip()
                if reference in unit_candidate_ids:
                    reviewed_candidates.add(reference)
                    reviewed_candidate_ids.add(reference)
                if not _accepted(review.get("decision")):
                    if reference:
                        rejections.append(
                            {
                                "stage": "entity_review",
                                "reference": reference,
                                "reason": review.get(
                                    "reason",
                                    review.get("normalization_reason", "model_rejected"),
                                ),
                            }
                        )
                    continue
                candidate = candidates_by_id.get(reference)
                entity_type = _safe_enum(
                    EntityType,
                    review.get("entity_type")
                    or (candidate.entity_type.value if candidate else None),
                )
                if entity_type is None:
                    rejections.append(
                        {"stage": "entity_review", "reference": reference, "reason": "invalid_type"}
                    )
                    continue
                surface = str(
                    review.get("surface") or (candidate.surface if candidate else "")
                ).strip()
                canonical_name = str(
                    review.get("canonical_name")
                    or (candidate.canonical_name if candidate else surface)
                ).strip()
                evidence = str(
                    review.get("evidence") or (candidate.evidence if candidate else "")
                ).strip()
                section_id = str(
                    review.get("section_id") or (candidate.section_id if candidate else "")
                ).split(":part:")[0]
                if (
                    not surface
                    or not canonical_name
                    or not evidence_is_present(evidence, document_text)
                ):
                    rejections.append(
                        {
                            "stage": "entity_review",
                            "reference": reference,
                            "reason": "missing_name_or_non_verbatim_evidence",
                        }
                    )
                    continue
                if entity_type == EntityType.PRODUCT:
                    canonical_name = canonical_product_name(canonical_name)
                if entity_type == EntityType.DOCUMENT:
                    canonical_name = canonical_name.casefold().removeprefix("document:")
                node = KnowledgeNode(
                    node_id=canonical_node_id(entity_type, canonical_name),
                    node_type=entity_type,
                    canonical_name=canonical_name,
                    aliases=list(dict.fromkeys([surface, canonical_name])),
                    confidence=_confidence(
                        review.get("confidence"),
                        candidate.confidence if candidate else 0.75,
                    ),
                    normalization_method="terra-canonicalization-v1",
                    reviewed_by_model=self.model_name,
                )
                _merge_node(nodes, node)
                ref_to_node[reference] = node.node_id
                if candidate is not None:
                    for member_id, representative in representative_by_member.items():
                        if representative == reference:
                            member = candidates_by_id.get(member_id)
                            if member is None:
                                continue
                            mention = EntityMention(
                                mention_id=mention_id(
                                    document_id,
                                    member.section_id,
                                    node.node_id,
                                    member.surface,
                                ),
                                document_id=document_id,
                                section_id=member.section_id,
                                node_id=node.node_id,
                                surface=member.surface,
                                evidence=member.evidence,
                                confidence=min(node.confidence, member.confidence),
                                extraction_method=f"{member.extraction_method}+terra-review",
                                reviewed_by_model=self.model_name,
                            )
                            mentions[mention.mention_id] = mention
                            ref_to_node[member_id] = node.node_id
                else:
                    model_added_entities += 1
                    mention = EntityMention(
                        mention_id=mention_id(document_id, section_id, node.node_id, surface),
                        document_id=document_id,
                        section_id=section_id,
                        node_id=node.node_id,
                        surface=surface,
                        evidence=evidence,
                        confidence=node.confidence,
                        extraction_method="terra-entity-extraction-v1",
                        reviewed_by_model=self.model_name,
                    )
                    mentions[mention.mention_id] = mention

            missing_reviews = unit_candidate_ids - reviewed_candidates
            for reference in sorted(missing_reviews):
                rejections.append(
                    {
                        "stage": "entity_review",
                        "reference": reference,
                        "reason": "model_omitted_required_review",
                    }
                )

            def accept_relation(
                review: dict[str, Any],
                *,
                is_rule: bool,
                ref_map: dict[str, str] = ref_to_node,
            ) -> None:
                if not _accepted(review.get("decision")):
                    if is_rule:
                        rejections.append(
                            {
                                "stage": "rule_review",
                                "reference": review.get("rule_id"),
                                "reason": review.get("reason", "model_rejected"),
                            }
                        )
                    return
                rule_id = str(review.get("rule_id", "")) or None
                candidate_rule = rules_by_id.get(rule_id or "")
                relation_type = _safe_enum(
                    KnowledgeRelationType,
                    review.get("relation")
                    or (candidate_rule.relation.value if candidate_rule else None),
                )
                if relation_type is None or relation_type == KnowledgeRelationType.MENTIONS:
                    rejections.append(
                        {"stage": "relation_validation", "reason": "invalid_relation_type"}
                    )
                    return
                source_ref = str(review.get("source_ref", ""))
                target_ref = str(review.get("target_ref", ""))
                source_id = ref_map.get(source_ref)
                target_id = ref_map.get(target_ref)
                if source_id is None and candidate_rule is not None:
                    source_id = ref_map.get(candidate_rule.source_ref)
                if target_id is None and candidate_rule is not None:
                    target_id = ref_map.get(candidate_rule.target_ref)
                evidence = str(
                    review.get("evidence")
                    or (candidate_rule.evidence if candidate_rule is not None else "")
                ).strip()
                section_id = str(
                    review.get("section_id")
                    or (candidate_rule.section_id if candidate_rule is not None else "")
                ).split(":part:")[0]
                if source_id is None or target_id is None:
                    rejections.append(
                        {
                            "stage": "relation_validation",
                            "reference": rule_id,
                            "reason": "unknown_endpoint",
                        }
                    )
                    return
                source = nodes[source_id]
                target = nodes[target_id]
                issues = _validate_relation(
                    relation_type,
                    source,
                    target,
                    evidence,
                    document_text,
                )
                if issues:
                    rejections.append(
                        {
                            "stage": "relation_validation",
                            "reference": rule_id,
                            "reason": issues,
                        }
                    )
                    return
                relation = KnowledgeRelation(
                    relation_id=relation_id(
                        source_id,
                        relation_type,
                        target_id,
                        document_id,
                        evidence,
                    ),
                    source_id=source_id,
                    target_id=target_id,
                    relation=relation_type,
                    document_id=document_id,
                    section_id=section_id,
                    evidence=evidence,
                    confidence=_confidence(
                        review.get("confidence"),
                        candidate_rule.confidence if candidate_rule else 0.75,
                    ),
                    extraction_method=(
                        f"{candidate_rule.rule_name}+terra-validation"
                        if candidate_rule
                        else "terra-relation-extraction-v1"
                    ),
                    rule_id=rule_id,
                    validation_notes=[str(review.get("reason", "terra accepted"))],
                    reviewed_by_model=self.model_name,
                )
                key = (source_id, target_id, relation_type, document_id)
                previous = accepted_relations.get(key)
                if previous is None or relation.confidence > previous.confidence:
                    accepted_relations[key] = relation

            reviewed_rules: set[str] = set()
            for review in result.get("rule_reviews", []):
                if not isinstance(review, dict):
                    continue
                rule_id = str(review.get("rule_id", ""))
                if rule_id:
                    representative = representative_rule_by_member.get(rule_id, rule_id)
                    member_rule_ids = {
                        member
                        for member, member_representative in (
                            representative_rule_by_member.items()
                        )
                        if member_representative == representative
                    }
                    reviewed_rules.update(member_rule_ids)
                    reviewed_rule_ids.update(member_rule_ids)
                    review = {**review, "rule_id": representative}
                accept_relation(review, is_rule=True)
            for review in result.get("new_relations", []):
                if isinstance(review, dict):
                    accept_relation(review, is_rule=False)

            for rule_id in sorted(unit_rule_ids - reviewed_rules):
                rejections.append(
                    {
                        "stage": "rule_review",
                        "reference": rule_id,
                        "reason": "model_omitted_required_review",
                    }
                )
            validation = result.get("document_validation")
            if isinstance(validation, dict):
                validation_units_reviewed += 1
                if not bool(validation.get("valid", True)):
                    rejections.append(
                        {
                            "stage": "document_validation",
                            "reason": validation.get("issues", []),
                        }
                    )
            else:
                rejections.append(
                    {
                        "stage": "document_validation",
                        "reason": "model_omitted_required_validation",
                    }
                )

        for section_id in sorted(expected_section_ids - reviewed_section_ids):
            rejections.append(
                {
                    "stage": "structure_review",
                    "reference": section_id,
                    "reason": "model_omitted_required_review",
                }
            )

        reviewed_sections = []
        for section in sections:
            update = section_updates.get(section.section_id)
            if update is None:
                reviewed_sections.append(section)
            else:
                reviewed_sections.append(
                    section.model_copy(
                        update={
                            "section_type": update[0],
                            "confidence": update[1],
                            "extraction_method": "deterministic-structure+terra-review-v1",
                        }
                    )
                )
        relation_validation_rejections = sum(
            rejection.get("stage") == "relation_validation" for rejection in rejections
        )
        intelligence_audit = {
            "model": self.model_name,
            "structure_parsing": {
                "proposed": len(expected_section_ids),
                "reviewed": len(reviewed_section_ids),
            },
            "node_typing": {
                "proposed": len(expected_candidate_ids),
                "reviewed": len(reviewed_candidate_ids),
            },
            "entity_extraction": {
                "proposed": len(expected_candidate_ids),
                "reviewed": len(reviewed_candidate_ids),
                "model_added": model_added_entities,
            },
            "entity_normalization": {
                "accepted_nodes": max(len(nodes) - 1, 0),
                "normalization_method": "terra-canonicalization-v1",
            },
            "deterministic_rule_review": {
                "proposed": len(rules_by_id),
                "reviewed": len(reviewed_rule_ids),
            },
            "relation_validation": {
                "accepted": len(accepted_relations),
                "rejected": relation_validation_rejections,
                "units": len(units),
                "units_reviewed": validation_units_reviewed,
            },
        }
        return (
            reviewed_sections,
            list(nodes.values()),
            list(mentions.values()),
            list(accepted_relations.values()),
            rejections,
            request_count,
            intelligence_audit,
        )


def document_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
