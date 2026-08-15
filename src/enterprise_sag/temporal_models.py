from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


SubjectId = Annotated[str, Field(min_length=1, max_length=160)]
Predicate = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")]


class TemporalRelationType(StrEnum):
    SUPERSEDES = "supersedes"
    CORRECTS = "corrects"
    CONTRADICTS = "contradicts"
    REINFORCES = "reinforces"
    RETRACTS = "retracts"


class AssertionLifecycle(StrEnum):
    ACTIVE = "active"
    FUTURE = "future"
    SUPERSEDED = "superseded"
    CORRECTED = "corrected"
    RETRACTED = "retracted"
    CONTESTED = "contested"


class TemporalQueryMode(StrEnum):
    LATEST_VALID = "latest_valid"
    HISTORICAL = "historical"


class UsageOutcome(StrEnum):
    SELECTED = "selected"
    SUCCESSFUL = "successful"
    REJECTED = "rejected"


class MemoryEventCreate(BaseModel):
    subject_id: SubjectId
    content: str = Field(min_length=1, max_length=100_000)
    occurred_at: AwareDatetime | None = None
    observed_at: AwareDatetime = Field(default_factory=utc_now)
    source_kind: str = Field(default="conversation", min_length=1, max_length=48)
    source_ref: str | None = Field(default=None, max_length=500)
    session_id: str | None = Field(default=None, max_length=160)
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryEvent(MemoryEventCreate):
    event_id: str = Field(default_factory=lambda: f"mev_{uuid.uuid4().hex}")
    content_hash: str
    recorded_at: AwareDatetime = Field(default_factory=utc_now)


class AssertionDraft(BaseModel):
    local_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    predicate: Predicate
    object_text: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default="global", min_length=1, max_length=160)
    valid_from: AwareDatetime | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class RelationDraft(BaseModel):
    source_local_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,47}$",
    )
    target_assertion_id: str = Field(min_length=1, max_length=80)
    relation_type: TemporalRelationType
    effective_at: AwareDatetime | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_source_for_assertion_relations(self) -> RelationDraft:
        if self.relation_type != TemporalRelationType.RETRACTS and not self.source_local_id:
            raise ValueError("source_local_id is required unless relation_type is retracts")
        return self


class ConsolidationProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: f"mcp_{uuid.uuid4().hex}")
    event_id: str = Field(min_length=1, max_length=80)
    subject_id: SubjectId
    candidate_assertion_ids: list[str] = Field(default_factory=list, max_length=40)
    assertions: list[AssertionDraft] = Field(default_factory=list, max_length=24)
    relations: list[RelationDraft] = Field(default_factory=list, max_length=40)
    planner: str = Field(min_length=1, max_length=120)
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_local_and_candidate_references(self) -> ConsolidationProposal:
        local_ids = [item.local_id for item in self.assertions]
        if len(local_ids) != len(set(local_ids)):
            raise ValueError("assertion local_id values must be unique")
        allowed_candidates = set(self.candidate_assertion_ids)
        for relation in self.relations:
            if relation.source_local_id and relation.source_local_id not in local_ids:
                raise ValueError("relation source_local_id must reference a proposal assertion")
            if relation.target_assertion_id not in allowed_candidates:
                raise ValueError("relation target must be one of the reviewed candidates")
        return self


class TemporalAssertion(BaseModel):
    assertion_id: str
    event_id: str
    subject_id: SubjectId
    predicate: Predicate
    object_text: str
    scope: str
    valid_from: AwareDatetime
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    extraction_method: str
    recorded_at: AwareDatetime = Field(default_factory=utc_now)


class AssertionRelation(BaseModel):
    relation_id: str
    source_assertion_id: str | None = None
    target_assertion_id: str
    source_event_id: str
    relation_type: TemporalRelationType
    effective_at: AwareDatetime
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    recorded_at: AwareDatetime = Field(default_factory=utc_now)


class AssertionState(BaseModel):
    assertion: TemporalAssertion
    lifecycle: AssertionLifecycle
    valid_to: AwareDatetime | None = None
    changed_by_assertion_id: str | None = None
    changed_by_relation_id: str | None = None
    contradiction_count: int = 0
    reinforcement_count: int = 0


class TemporalUsageEvent(BaseModel):
    usage_id: str = Field(default_factory=lambda: f"mus_{uuid.uuid4().hex}")
    assertion_id: str
    outcome: UsageOutcome
    query_ref: str | None = Field(default=None, max_length=160)
    context: str = Field(default="retrieval", max_length=80)
    occurred_at: AwareDatetime = Field(default_factory=utc_now)


class AssertionUsageStats(BaseModel):
    assertion_id: str
    use_count: int = 0
    successful_use_count: int = 0
    rejected_use_count: int = 0
    last_used_at: AwareDatetime | None = None


class TemporalSearchHit(BaseModel):
    assertion: TemporalAssertion
    lifecycle: AssertionLifecycle
    valid_to: AwareDatetime | None = None
    score: float
    semantic_score: float
    lexical_score: float
    confidence_score: float
    importance_score: float
    reinforcement_score: float
    relation_reinforcement_count: int
    recency_score: float
    usage: AssertionUsageStats


class TemporalQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    subject_id: SubjectId
    mode: TemporalQueryMode = TemporalQueryMode.LATEST_VALID
    valid_at: AwareDatetime = Field(default_factory=utc_now)
    known_at: AwareDatetime = Field(default_factory=utc_now)
    top_k: int = Field(default=10, ge=1, le=100)
    predicates: list[str] = Field(default_factory=list, max_length=24)
    scopes: list[str] = Field(default_factory=list, max_length=24)


class ConsolidationApplyResult(BaseModel):
    proposal_id: str
    event_id: str
    assertion_ids: list[str]
    relation_ids: list[str]
    applied: bool
    projection_rebuilt: bool
    agent_loop_integration: Literal[False] = False
    prompt_injection: Literal[False] = False
