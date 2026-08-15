from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class IngestionOptions(BaseModel):
    """Transport-independent metadata for one source ingestion request."""

    asset_id: str | None = Field(default=None, pattern=r"^ast_[a-f0-9]{24,32}$")
    source_key: str | None = Field(default=None, min_length=1, max_length=300)
    namespace: str = Field(default="enterprise_knowledge", min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_metadata(self) -> IngestionOptions:
        if len(self.metadata) > 64:
            raise ValueError("metadata may contain at most 64 keys")
        return self


class TextIngestionRequest(IngestionOptions):
    content: str = Field(min_length=1, max_length=5_000_000)
    filename: str = Field(default="imported.md", min_length=1, max_length=255)


class IngestionResult(BaseModel):
    job_id: str
    status: Literal["published", "unchanged"]
    asset_id: str
    version_id: str
    previous_version_id: str | None = None
    version_number: int = Field(ge=1)
    source_id: str
    content_hash: str
    namespace: str
    title: str
    stored_path: str
    index_version: str
    pipeline_signature: str
    reused_projection: bool = False
    evidence_units: int = Field(default=0, ge=0)
    events: int = Field(default=0, ge=0)
    entities: int = Field(default=0, ge=0)
    llm_requests: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SourceAssetView(BaseModel):
    asset_id: str
    source_key: str
    namespace: str
    origin: str
    version_id: str
    version_number: int
    source_id: str
    title: str
    original_filename: str
    content_hash: str
    stored_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_units: int = 0
    events: int = 0
    created_at: datetime

