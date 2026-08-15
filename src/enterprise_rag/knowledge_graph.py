from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SectionType(StrEnum):
    TITLE = "title"
    SUMMARY = "summary"
    QUESTION = "question"
    PROBLEM = "problem"
    SYMPTOM = "symptom"
    CAUSE = "cause"
    ENVIRONMENT = "environment"
    RESOLUTION = "resolution"
    ANSWER = "answer"
    RELATED_INFORMATION = "related_information"
    CONTENT = "content"
    OTHER = "other"


class EntityType(StrEnum):
    DOCUMENT = "document"
    PRODUCT = "product"
    COMPONENT = "component"
    VERSION = "version"
    ERROR_CODE = "error_code"
    FIX = "fix"
    VULNERABILITY = "vulnerability"
    CONFIGURATION = "configuration"
    COMMAND = "command"
    FILE = "file"
    OPERATING_SYSTEM = "operating_system"
    PROTOCOL = "protocol"
    RUNTIME = "runtime"
    SYMPTOM = "symptom"
    CAUSE = "cause"
    PROCEDURE = "procedure"
    ORGANIZATION = "organization"
    TECHNOLOGY = "technology"


class KnowledgeRelationType(StrEnum):
    REFERENCES = "references"
    MENTIONS = "mentions"
    PART_OF = "part_of"
    VERSION_OF = "version_of"
    APPLIES_TO = "applies_to"
    FIXES = "fixes"
    AFFECTS = "affects"
    CAUSED_BY = "caused_by"
    RESOLVES = "resolves"
    SUPERSEDES = "supersedes"
    SUPPORTS = "supports"
    DOES_NOT_SUPPORT = "does_not_support"
    CONFIGURES = "configures"
    REQUIRES = "requires"
    RELATED_TO = "related_to"


class KnowledgeSection(BaseModel):
    section_id: str
    document_id: str
    heading: str
    section_type: SectionType
    content: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0, le=1)
    extraction_method: str = "deterministic-structure-v1"

    @model_validator(mode="after")
    def valid_offsets(self) -> KnowledgeSection:
        if self.end < self.start:
            raise ValueError("section end must not precede start")
        return self


class EntityCandidate(BaseModel):
    candidate_id: str
    entity_type: EntityType
    surface: str
    canonical_name: str
    section_id: str
    evidence: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0, le=1)
    extraction_method: str


class RelationCandidate(BaseModel):
    rule_id: str
    source_ref: str
    target_ref: str
    relation: KnowledgeRelationType
    section_id: str
    evidence: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    rule_name: str


class KnowledgeNode(BaseModel):
    node_id: str
    node_type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    normalization_method: str
    reviewed_by_model: str


class EntityMention(BaseModel):
    mention_id: str
    document_id: str
    section_id: str
    node_id: str
    surface: str
    evidence: str
    confidence: float = Field(ge=0, le=1)
    extraction_method: str
    reviewed_by_model: str


class KnowledgeRelation(BaseModel):
    relation_id: str
    source_id: str
    target_id: str
    relation: KnowledgeRelationType
    document_id: str
    section_id: str
    evidence: str
    confidence: float = Field(ge=0, le=1)
    extraction_method: str
    rule_id: str | None = None
    validation_status: str = "accepted"
    validation_notes: list[str] = Field(default_factory=list)
    reviewed_by_model: str

    @model_validator(mode="after")
    def reject_self_relation(self) -> KnowledgeRelation:
        if self.source_id == self.target_id:
            raise ValueError("knowledge relations cannot be self-references")
        return self


class DocumentKnowledge(BaseModel):
    document_id: str
    checksum: str
    extraction_version: str
    model: str
    sections: list[KnowledgeSection]
    nodes: list[KnowledgeNode]
    mentions: list[EntityMention]
    relations: list[KnowledgeRelation]
    deterministic_entity_count: int
    deterministic_relation_count: int
    llm_request_count: int
    validation_rejections: list[dict[str, Any]] = Field(default_factory=list)
    intelligence_audit: dict[str, Any] = Field(default_factory=dict)


_HEADING_TYPES = {
    "ABSTRACT": SectionType.SUMMARY,
    "SUMMARY": SectionType.SUMMARY,
    "QUESTION": SectionType.QUESTION,
    "PROBLEM": SectionType.PROBLEM,
    "PROBLEM(ABSTRACT)": SectionType.PROBLEM,
    "SYMPTOM": SectionType.SYMPTOM,
    "SYMPTOMS": SectionType.SYMPTOM,
    "CAUSE": SectionType.CAUSE,
    "ENVIRONMENT": SectionType.ENVIRONMENT,
    "RESOLVING THE PROBLEM": SectionType.RESOLUTION,
    "RESOLUTION": SectionType.RESOLUTION,
    "SOLUTION": SectionType.RESOLUTION,
    "WORKAROUND": SectionType.RESOLUTION,
    "ANSWER": SectionType.ANSWER,
    "CONTENT": SectionType.CONTENT,
    "RELATED INFORMATION": SectionType.RELATED_INFORMATION,
    "CROSS REFERENCE INFORMATION": SectionType.RELATED_INFORMATION,
}
_HEADING_PATTERN = re.compile(
    r"(?im)^\s*(" + "|".join(re.escape(value) for value in _HEADING_TYPES) + r")\s*$"
)

PRODUCT_ALIASES: dict[str, tuple[str, ...]] = {
    "IBM MQ": ("IBM MQ", "WebSphere MQ", "WMQ"),
    "IBM Db2": ("IBM Db2", "IBM DB2", "DB2 UDB", "DB2"),
    "WebSphere Application Server": (
        "WebSphere Application Server",
        "IBM WebSphere Application Server",
        "WAS",
    ),
    "IBM HTTP Server": ("IBM HTTP Server", "IHS"),
    "IBM DataPower Gateway": ("IBM DataPower Gateway", "WebSphere DataPower", "DataPower"),
    "IBM Operational Decision Manager": (
        "IBM Operational Decision Manager",
        "Operational Decision Manager",
        "ODM",
    ),
    "IBM Business Process Manager": (
        "IBM Business Process Manager",
        "WebSphere Business Process Manager",
        "IBM BPM",
        "BPM",
    ),
    "IBM Content Navigator": ("IBM Content Navigator", "ICN"),
    "IBM FileNet": ("IBM FileNet", "FileNet P8", "FileNet"),
    "IBM Cognos Analytics": ("IBM Cognos Analytics", "Cognos Analytics", "Cognos"),
    "IBM Tivoli Monitoring": ("IBM Tivoli Monitoring", "ITM"),
    "Tivoli Integrated Portal": ("Tivoli Integrated Portal", "TIP"),
    "Jazz for Service Management": ("Jazz for Service Management", "JazzSM"),
    "IBM Netcool/OMNIbus": ("IBM Netcool/OMNIbus", "Netcool OMNIbus", "OMNIbus"),
    "IBM SPSS Statistics": ("IBM SPSS Statistics", "SPSS Statistics", "SPSS"),
    "IBM Datacap": ("IBM Datacap", "Datacap"),
    "IBM Installation Manager": ("IBM Installation Manager", "Installation Manager"),
    "WebSphere Portal": ("IBM WebSphere Portal", "WebSphere Portal"),
}

_REFERENCE = re.compile(r"\bswg[a-z0-9]+\b", flags=re.IGNORECASE)
_CVE = re.compile(r"\bCVE-\d{4}-\d{4,8}\b", flags=re.IGNORECASE)
_APAR = re.compile(r"\b(?:APAR\s+)?(?:PI|PH|IJ|IT|JR|PK|PM)\d{5,8}\b", flags=re.IGNORECASE)
_ERROR_CODE = re.compile(
    r"\b(?:MQRC_[A-Z0-9_]+|SQL\d{4}[A-Z]?|[A-Z]{3,12}\d{3,8}[A-Z]?)\b"
)
_VERSION = re.compile(
    r"(?<![A-Za-z0-9])(?:v(?:ersion)?\s*)?\d+\.\d+(?:\.\d+){0,4}(?![A-Za-z0-9])",
    re.I,
)
_FILE = re.compile(
    r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]+\.(?:bat|sh|cmd|xml|conf|properties|ini|jar|ear|war|sql)(?![A-Za-z0-9_.-])",
    re.I,
)
_CONFIG = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*\.){1,5}[A-Za-z][A-Za-z0-9]*\b|\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+){1,5}\b"
)
_PROTOCOLS = re.compile(
    r"\b(?:SSLv?\d?(?:\.\d)?|TLSv?\d(?:\.\d)?|HTTP|HTTPS|JDBC|JMS|LDAP)\b",
    re.I,
)


def _clean_heading(value: str) -> str:
    return " ".join(value.split()).upper()


def parse_sections(document_id: str, text: str) -> list[KnowledgeSection]:
    matches = list(_HEADING_PATTERN.finditer(text))
    sections: list[KnowledgeSection] = []
    title_match = re.match(r"(?im)^Title:\s*(.+)$", text)
    if title_match:
        sections.append(
            KnowledgeSection(
                section_id=f"{document_id}:section:0",
                document_id=document_id,
                heading="TITLE",
                section_type=SectionType.TITLE,
                content=title_match.group(1).strip(),
                start=title_match.start(1),
                end=title_match.end(1),
            )
        )

    boundaries: list[tuple[int, int, str, SectionType]] = []
    for match in matches:
        heading = _clean_heading(match.group(1))
        boundaries.append((match.start(), match.end(), heading, _HEADING_TYPES[heading]))

    first_body_start = title_match.end() if title_match else 0
    if boundaries and boundaries[0][0] > first_body_start:
        body = text[first_body_start : boundaries[0][0]].strip()
        if body:
            start = text.find(body, first_body_start, boundaries[0][0])
            sections.append(
                KnowledgeSection(
                    section_id=f"{document_id}:section:{len(sections)}",
                    document_id=document_id,
                    heading="DOCUMENT BODY",
                    section_type=SectionType.CONTENT,
                    content=body,
                    start=start,
                    end=start + len(body),
                )
            )
    elif not boundaries:
        body = text[first_body_start:].strip()
        if body:
            start = text.find(body, first_body_start)
            sections.append(
                KnowledgeSection(
                    section_id=f"{document_id}:section:{len(sections)}",
                    document_id=document_id,
                    heading="DOCUMENT BODY",
                    section_type=SectionType.CONTENT,
                    content=body,
                    start=start,
                    end=start + len(body),
                )
            )

    for index, (_, heading_end, heading, section_type) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        content = text[heading_end:end].strip()
        if not content:
            continue
        start = text.find(content, heading_end, end)
        sections.append(
            KnowledgeSection(
                section_id=f"{document_id}:section:{len(sections)}",
                document_id=document_id,
                heading=heading,
                section_type=section_type,
                content=content,
                start=start,
                end=start + len(content),
            )
        )
    return sections


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def evidence_is_present(evidence: str, text: str) -> bool:
    evidence_normalized = _normalized_text(evidence)
    return bool(evidence_normalized) and evidence_normalized in _normalized_text(text)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if slug:
        return slug[:80]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def canonical_node_id(entity_type: EntityType, canonical_name: str) -> str:
    if entity_type == EntityType.DOCUMENT:
        return f"document:{canonical_name.casefold()}"
    return f"entity:{entity_type.value}:{_slug(canonical_name)}"


def canonical_product_name(value: str) -> str:
    normalized = _normalized_text(value)
    for canonical, aliases in PRODUCT_ALIASES.items():
        if any(normalized == _normalized_text(alias) for alias in aliases):
            return canonical
    return " ".join(value.split())


def _candidate(
    candidates: list[EntityCandidate],
    *,
    entity_type: EntityType,
    surface: str,
    canonical_name: str,
    section: KnowledgeSection,
    local_start: int,
    local_end: int,
    method: str,
    confidence: float = 1.0,
) -> None:
    absolute_start = section.start + local_start
    absolute_end = section.start + local_end
    evidence_start = max(0, local_start - 90)
    evidence_end = min(len(section.content), local_end + 120)
    candidates.append(
        EntityCandidate(
            candidate_id=f"E{len(candidates) + 1}",
            entity_type=entity_type,
            surface=surface,
            canonical_name=canonical_name,
            section_id=section.section_id,
            evidence=" ".join(section.content[evidence_start:evidence_end].split()),
            start=absolute_start,
            end=absolute_end,
            confidence=confidence,
            extraction_method=method,
        )
    )


def extract_rule_entities(sections: list[KnowledgeSection]) -> list[EntityCandidate]:
    candidates: list[EntityCandidate] = []
    seen: set[tuple[str, str, int]] = set()

    def add_match(
        section: KnowledgeSection,
        match: re.Match[str],
        entity_type: EntityType,
        canonical: str,
        method: str,
        confidence: float = 1.0,
    ) -> None:
        key = (entity_type.value, _normalized_text(canonical), section.start + match.start())
        if key in seen:
            return
        seen.add(key)
        _candidate(
            candidates,
            entity_type=entity_type,
            surface=match.group(0),
            canonical_name=canonical,
            section=section,
            local_start=match.start(),
            local_end=match.end(),
            method=method,
            confidence=confidence,
        )

    for section in sections:
        text = section.content
        for match in _REFERENCE.finditer(text):
            add_match(
                section,
                match,
                EntityType.DOCUMENT,
                match.group(0).lower(),
                "regex-document-reference-v1",
            )
        for match in _CVE.finditer(text):
            add_match(
                section,
                match,
                EntityType.VULNERABILITY,
                match.group(0).upper(),
                "regex-cve-v1",
            )
        for match in _APAR.finditer(text):
            canonical = re.sub(r"(?i)^APAR\s+", "", match.group(0)).upper()
            add_match(section, match, EntityType.FIX, canonical, "regex-apar-v1")
        for match in _ERROR_CODE.finditer(text):
            value = match.group(0)
            if _APAR.fullmatch(value) or _CVE.fullmatch(value):
                continue
            add_match(
                section,
                match,
                EntityType.ERROR_CODE,
                value.upper(),
                "regex-error-code-v1",
                0.96,
            )
        for match in _VERSION.finditer(text):
            canonical = re.sub(r"(?i)^v(?:ersion)?\s*", "", match.group(0)).strip()
            add_match(
                section,
                match,
                EntityType.VERSION,
                canonical,
                "regex-version-v1",
                0.9,
            )
        for canonical, aliases in PRODUCT_ALIASES.items():
            for alias in aliases:
                pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.I)
                for match in pattern.finditer(text):
                    add_match(
                        section,
                        match,
                        EntityType.PRODUCT,
                        canonical,
                        "product-alias-v1",
                        0.98 if len(alias) > 3 else 0.82,
                    )
        for match in _FILE.finditer(text):
            add_match(
                section,
                match,
                EntityType.FILE,
                match.group(0),
                "regex-file-v1",
                0.94,
            )
        for match in _PROTOCOLS.finditer(text):
            add_match(
                section,
                match,
                EntityType.PROTOCOL,
                match.group(0).upper(),
                "regex-protocol-v1",
                0.9,
            )
        for match in _CONFIG.finditer(text):
            value = match.group(0)
            if _CVE.fullmatch(value) or _ERROR_CODE.fullmatch(value):
                continue
            add_match(
                section,
                match,
                EntityType.CONFIGURATION,
                value,
                "regex-configuration-v1",
                0.78,
            )
    return candidates


def _sentence_for(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start), 0)
    right_candidates = [
        position
        for position in (text.find(".", end), text.find("\n", end))
        if position >= 0
    ]
    right = min(right_candidates, default=min(len(text), end + 240)) + 1
    return " ".join(text[left:right].split())[:500]


def propose_rule_relations(
    document_id: str,
    sections: list[KnowledgeSection],
    entities: list[EntityCandidate],
    corpus_document_ids: set[str],
) -> list[RelationCandidate]:
    relations: list[RelationCandidate] = []
    by_section: dict[str, list[EntityCandidate]] = defaultdict(list)
    for entity in entities:
        by_section[entity.section_id].append(entity)

    def append(
        source_ref: str,
        target_ref: str,
        relation: KnowledgeRelationType,
        section_id: str,
        evidence: str,
        confidence: float,
        rule_name: str,
    ) -> None:
        if source_ref == target_ref:
            return
        key = (source_ref, target_ref, relation)
        if any((row.source_ref, row.target_ref, row.relation) == key for row in relations):
            return
        relations.append(
            RelationCandidate(
                rule_id=f"R{len(relations) + 1}",
                source_ref=source_ref,
                target_ref=target_ref,
                relation=relation,
                section_id=section_id,
                evidence=evidence,
                confidence=confidence,
                rule_name=rule_name,
            )
        )

    sections_by_id = {section.section_id: section for section in sections}
    for entity in entities:
        if entity.entity_type == EntityType.DOCUMENT:
            target = entity.canonical_name.lower()
            if target in corpus_document_ids and target != document_id.lower():
                append(
                    "DOC",
                    entity.candidate_id,
                    KnowledgeRelationType.REFERENCES,
                    entity.section_id,
                    entity.evidence,
                    1.0,
                    "explicit-document-reference-v1",
                )

    for section_id, rows in by_section.items():
        section = sections_by_id[section_id]
        products = [row for row in rows if row.entity_type == EntityType.PRODUCT]
        versions = [row for row in rows if row.entity_type == EntityType.VERSION]
        fixes = [row for row in rows if row.entity_type == EntityType.FIX]
        errors = [row for row in rows if row.entity_type == EntityType.ERROR_CODE]
        for version in versions:
            nearby = sorted(products, key=lambda product: abs(product.start - version.start))
            if nearby and abs(nearby[0].start - version.start) <= 220:
                evidence = _sentence_for(
                    section.content,
                    max(0, min(version.start, nearby[0].start) - section.start),
                    max(version.end, nearby[0].end) - section.start,
                )
                append(
                    version.candidate_id,
                    nearby[0].candidate_id,
                    KnowledgeRelationType.VERSION_OF,
                    section_id,
                    evidence,
                    0.88,
                    "nearby-product-version-v1",
                )
        lowered = section.content.casefold()
        has_fix_trigger = any(word in lowered for word in (" fix", "resolve", "address", "correct"))
        if has_fix_trigger:
            for fix in fixes:
                for error in errors:
                    if abs(fix.start - error.start) <= 420:
                        append(
                            fix.candidate_id,
                            error.candidate_id,
                            KnowledgeRelationType.FIXES,
                            section_id,
                            _sentence_for(
                                section.content,
                                min(fix.start, error.start) - section.start,
                                max(fix.end, error.end) - section.start,
                            ),
                            0.86,
                            "fix-trigger-v1",
                        )
        if section.section_type == SectionType.ENVIRONMENT:
            for entity in [*products, *versions]:
                append(
                    "DOC",
                    entity.candidate_id,
                    KnowledgeRelationType.APPLIES_TO,
                    section_id,
                    entity.evidence,
                    0.9,
                    "environment-section-v1",
                )
    return relations


def review_units(
    sections: list[KnowledgeSection],
    entities: list[EntityCandidate],
    relations: list[RelationCandidate],
    *,
    max_characters: int = 14000,
) -> list[dict[str, Any]]:
    units: list[list[KnowledgeSection]] = []
    current: list[KnowledgeSection] = []
    current_size = 0
    for section in sections:
        if len(section.content) > max_characters:
            if current:
                units.append(current)
                current = []
                current_size = 0
            start = 0
            part = 1
            while start < len(section.content):
                end = min(start + max_characters, len(section.content))
                units.append(
                    [
                        section.model_copy(
                            update={
                                "section_id": f"{section.section_id}:part:{part}",
                                "content": section.content[start:end],
                                "start": section.start + start,
                                "end": section.start + end,
                            }
                        )
                    ]
                )
                if end == len(section.content):
                    break
                start = max(end - 500, start + 1)
                part += 1
            continue
        if current and current_size + len(section.content) > max_characters:
            units.append(current)
            current = []
            current_size = 0
        current.append(section)
        current_size += len(section.content)
    if current:
        units.append(current)

    result: list[dict[str, Any]] = []
    assigned_entity_ids: set[str] = set()
    for unit_sections in units:
        base_ids = {section.section_id.split(":part:")[0] for section in unit_sections}
        unit_entities = [
            entity
            for entity in entities
            if entity.section_id in base_ids
            and entity.candidate_id not in assigned_entity_ids
            and any(
                entity.section_id == section.section_id.split(":part:")[0]
                and entity.start < section.end
                and entity.end > section.start
                for section in unit_sections
            )
        ]
        assigned_entity_ids.update(entity.candidate_id for entity in unit_entities)
        entity_ids = {entity.candidate_id for entity in unit_entities}
        unit_relations = [
            relation
            for relation in relations
            if relation.section_id in base_ids
            and relation.source_ref in entity_ids | {"DOC"}
            and relation.target_ref in entity_ids | {"DOC"}
        ]
        result.append(
            {
                "sections": unit_sections,
                "entities": unit_entities,
                "relations": unit_relations,
            }
        )
    return result


def extract_json_object(raw: str) -> dict[str, Any]:
    first = raw.find("{")
    last = raw.rfind("}")
    if first < 0 or last <= first:
        raise ValueError("LLM output does not contain a JSON object")
    value = json.loads(raw[first : last + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM output root must be an object")
    return value


def relation_id(
    source_id: str,
    relation: KnowledgeRelationType,
    target_id: str,
    document_id: str,
    evidence: str,
) -> str:
    payload = "\0".join((source_id, relation.value, target_id, document_id, evidence))
    return "relation:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def mention_id(document_id: str, section_id: str, node_id: str, surface: str) -> str:
    payload = "\0".join((document_id, section_id, node_id, surface))
    return "mention:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
