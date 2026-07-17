from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Route(StrEnum):
    RAG = "rag"
    EXACT_SEARCH = "exact_search"
    TOOL = "tool"
    HANDOFF_OR_REFUSE = "handoff_or_refuse"


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    DRAFT = "draft"
    EXPIRED = "expired"


class Principal(BaseModel):
    subject: str
    roles: frozenset[str]
    tenant_id: str = "demo"


class DocumentInput(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    owner: str = Field(min_length=1, max_length=128)
    business_class: str = Field(min_length=1, max_length=128)
    sensitivity: str = "internal"
    allowed_roles: set[str] = Field(min_length=1)
    version: str = "1.0"
    status: DocumentStatus = DocumentStatus.ACTIVE
    source_uri: str | None = None

    @field_validator("allowed_roles")
    @classmethod
    def clean_roles(cls, value: set[str]) -> set[str]:
        roles = {role.strip() for role in value if role.strip()}
        if not roles:
            raise ValueError("at least one allowed role is required")
        return roles


class DocumentRecord(DocumentInput):
    checksum: str
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    position: int
    anchor: str
    allowed_roles: frozenset[str]
    version: str
    status: DocumentStatus
    business_class: str


class SearchHit(BaseModel):
    chunk: Chunk
    score: float
    lexical_score: float
    dense_score: float


class RouteDecision(BaseModel):
    route: Route
    confidence: float = Field(ge=0, le=1)
    reason: str
    requires_citation: bool = True


class Citation(BaseModel):
    source_type: str
    source_id: str
    title: str
    version: str | None = None
    anchor: str | None = None
    score: float | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    conversation_id: str | None = None


class QueryResponse(BaseModel):
    answer: str
    route: Route
    route_reason: str
    citations: list[Citation] = Field(default_factory=list)
    trace_id: str
    refused: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenRequest(BaseModel):
    subject: str = "demo-user"
    roles: set[str] = Field(default_factory=lambda: {"engineering"})
    tenant_id: str = "demo"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuditEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trace_id: str
    subject: str
    roles: list[str]
    route: Route
    allowed: bool
    reason: str
    source_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    trace_id: str = Field(min_length=1, max_length=128)
    rating: str = Field(pattern=r"^(helpful|unhelpful|citation_error|permission_issue)$")
    note: str | None = Field(default=None, max_length=1000)


class FeedbackEvent(FeedbackRequest):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    subject: str
