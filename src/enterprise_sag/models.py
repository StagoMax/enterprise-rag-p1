from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class PackStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class SourceDocument(BaseModel):
    source_id: str
    canonical_path: str
    aliases: list[str] = Field(default_factory=list)
    title: str
    doc_format: str
    content_hash: str
    modified_at: datetime | None = None


class EvidenceUnit(BaseModel):
    evidence_id: str
    source_id: str
    ordinal: int
    title: str
    section_path: list[str] = Field(default_factory=list)
    anchors: list[str] = Field(default_factory=list)
    content: str
    content_hash: str


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str = "topic"


class EventExtraction(BaseModel):
    evidence_id: str
    event_text: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    event_time: str | None = None
    extraction_method: str


class IndexBuildReport(BaseModel):
    source_root: str
    database_path: str
    discovered_files: int
    parsed_files: int
    failed_files: list[dict[str, str]] = Field(default_factory=list)
    unique_sources: int
    duplicate_aliases: int
    evidence_units: int
    events: int
    entities: int
    event_entity_links: int
    extractor: str
    embedding_backend: str
    embedding_dimensions: int
    llm_requests: int = 0
    index_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContextPackRequest(BaseModel):
    """Typed retrieval request; it is deliberately independent from an Agent prompt."""

    request_id: str = Field(default_factory=lambda: f"cpr_{uuid.uuid4().hex}")
    query: str = Field(min_length=1)
    purpose: str = "evidence_review"
    subject_refs: list[str] = Field(default_factory=list)
    allowed_namespaces: list[str] = Field(default_factory=list)
    time_anchor: datetime = Field(default_factory=lambda: datetime.now(UTC))
    maximum_tokens: int = Field(default=4000, ge=256)


class EvidenceNeed(BaseModel):
    """One source-agnostic information requirement in a retrieval plan."""

    need_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    description: str = Field(min_length=1, max_length=240)
    query: str = Field(min_length=1, max_length=500)
    facets: list[str] = Field(default_factory=list)
    subject_refs: list[str] = Field(default_factory=list)
    time_mode: Literal["any", "latest_valid", "historical"] = "any"
    required: bool = False
    weight: float = Field(default=1.0, ge=0.1, le=3.0)


class RetrievalPlan(BaseModel):
    request_id: str
    original_query: str
    purpose: str
    needs: list[EvidenceNeed] = Field(min_length=1, max_length=6)
    planner: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RetrievalTrace(BaseModel):
    direct_event_score: float = 0.0
    direct_evidence_score: float = 0.0
    entity_score: float = 0.0
    lexical_score: float = 0.0
    expansion_hop: int = 0
    shared_entities: list[str] = Field(default_factory=list)
    selection_reason: str


class NeedRouteTrace(BaseModel):
    need_id: str
    route_rank: int = Field(ge=1)
    route_score: float
    normalized_route_score: float
    fusion_contribution: float
    semantic_support_score: float = 1.0
    semantic_support_reason: str = "deterministic-route-calibration"
    retrieval_trace: RetrievalTrace


class EvidenceSupport(BaseModel):
    need_id: str
    event_id: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str


class SagSearchHit(BaseModel):
    event_id: str
    evidence_id: str
    source_id: str
    source_path: str
    title: str
    section_path: list[str] = Field(default_factory=list)
    anchors: list[str] = Field(default_factory=list)
    event_text: str
    evidence_content: str
    score: float
    trace: RetrievalTrace


class FusedSagSearchHit(BaseModel):
    event_id: str
    evidence_id: str
    source_id: str
    source_path: str
    title: str
    section_path: list[str] = Field(default_factory=list)
    anchors: list[str] = Field(default_factory=list)
    event_text: str
    evidence_content: str
    score: float
    matched_need_ids: list[str] = Field(default_factory=list)
    route_traces: list[NeedRouteTrace] = Field(default_factory=list)


class NeedCoverage(BaseModel):
    need_id: str
    required: bool
    status: Literal["covered", "uncovered"]
    selected_event_ids: list[str] = Field(default_factory=list)
    reason: str


class ContextPackItem(BaseModel):
    event_id: str
    evidence_id: str
    content: str
    event_summary: str
    source_path: str
    title: str
    section_path: list[str] = Field(default_factory=list)
    anchors: list[str] = Field(default_factory=list)
    score: float
    selection_reason: str
    matched_need_ids: list[str] = Field(default_factory=list)
    route_traces: list[NeedRouteTrace] = Field(default_factory=list)
    estimated_tokens: int


class DraftContextPack(BaseModel):
    """Review artifact only. It deliberately has no prompt/messages field."""

    pack_id: str
    status: PackStatus = PackStatus.DRAFT
    purpose: str = "preview"
    query: str
    request: ContextPackRequest
    plan: RetrievalPlan
    coverage: list[NeedCoverage] = Field(default_factory=list)
    index_version: str
    retrieval_engine: str = "sag-multi-route-query-time-dynamic-hyperedges"
    items: list[ContextPackItem] = Field(default_factory=list)
    excluded_items: list[dict[str, str]] = Field(default_factory=list)
    estimated_tokens: int = 0
    maximum_tokens: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    def save_markdown(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Draft Context Pack（仅供人工审阅）",
            "",
            "> 此文件未注入任何 Agent Prompt，也不会改变 Agent Loop。",
            "",
            f"- Pack ID：`{self.pack_id}`",
            f"- 状态：`{self.status.value}`",
            f"- 查询：{self.query}",
            f"- Request purpose：`{self.request.purpose}`",
            f"- 索引版本：`{self.index_version}`",
            f"- Token 预算：{self.estimated_tokens} / {self.maximum_tokens}",
            "",
            "## Evidence Needs",
            "",
        ]
        coverage_by_id = {item.need_id: item for item in self.coverage}
        for need in self.plan.needs:
            coverage = coverage_by_id[need.need_id]
            lines.append(
                f"- `{need.need_id}` [{coverage.status}] "
                f"required={need.required}, weight={need.weight:g}：{need.description}"
            )
        lines.extend(["", "## Selected Evidence", ""])
        for number, item in enumerate(self.items, start=1):
            lines.extend(
                [
                    f"## {number}. {item.title}",
                    "",
                    f"- Event：{item.event_summary}",
                    f"- Section：{' > '.join(item.section_path) or '(root)'}",
                    f"- Score：{item.score:.6f}",
                    f"- Reason：`{item.selection_reason}`",
                    f"- Matched needs：{', '.join(item.matched_need_ids)}",
                    f"- Source：`{item.source_path}`",
                    f"- Anchors：{', '.join(item.anchors) or '(none)'}",
                    f"- Estimated tokens：{item.estimated_tokens}",
                    "",
                    "### Route traces",
                    "",
                    *[
                        (
                            f"- `{trace.need_id}` rank={trace.route_rank}, "
                            f"route_score={trace.route_score:.6f}, "
                            f"support={trace.semantic_support_score:.2f}, "
                            f"hop={trace.retrieval_trace.expansion_hop}, "
                            "entities="
                            f"{', '.join(trace.retrieval_trace.shared_entities) or '(none)'}, "
                            f"reason={trace.semantic_support_reason}"
                        )
                        for trace in item.route_traces
                    ],
                    "",
                    "### 原始证据单元",
                    "",
                    *[f"> {line}" if line else ">" for line in item.content.splitlines()],
                    "",
                ]
            )
        if self.excluded_items:
            lines.extend(["## 未纳入项目", ""])
            for item in self.excluded_items:
                lines.append(f"- `{item['event_id']}`：{item['reason']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
