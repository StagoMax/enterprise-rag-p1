from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SagSettings(BaseSettings):
    """Configuration for the isolated SAG projection; no Agent-loop settings live here."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    source_root: Path = Field(
        default=Path("data/sag_sources"),
        validation_alias=AliasChoices("SAG_SOURCE_ROOT", "SOURCE_ROOT"),
    )
    database_path: Path = Path("data/sag_memory/personal_memory.sqlite")
    asset_store_path: Path = Path("data/sag_memory/assets")
    preview_dir: Path = Path("data/sag_memory/previews")
    temporal_database_path: Path = Path("data/sag_memory/temporal_memory.sqlite")
    temporal_proposal_dir: Path = Path("data/sag_memory/temporal_proposals")

    extractor: Literal["deepseek", "deterministic"] = "deepseek"
    extractor_batch_size: int = Field(default=6, ge=1, le=12)
    allow_extractor_fallback: bool = False
    chunk_target_tokens: int = Field(default=480, ge=64)
    chunk_max_tokens: int = Field(default=640, ge=96)

    embedding_backend: Literal["nemotron", "hashing"] = "nemotron"
    hashing_dimensions: int = Field(default=384, ge=64)
    nemotron_model_id: str = "models/nemotron-3-embed-1b"
    nemotron_dimensions: int = 1024
    nemotron_device: str = "cuda"
    embedding_batch_size: int = Field(default=8, ge=1)
    ingestion_max_file_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)

    llm_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("SAG_LLM_BASE_URL", "DEEPSEEK_BASE_URL"),
    )
    llm_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("SAG_LLM_API_KEY", "DEEPSEEK_API_KEY", "DEEPSEEK_KEY"),
    )
    llm_model: str = Field(
        default="",
        validation_alias=AliasChoices("SAG_LLM_MODEL", "DEEPSEEK_MODEL", "DEEPSEEKMODEL"),
    )
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_tokens: int = Field(default=3600, ge=256)
    llm_max_retries: int = Field(default=2, ge=0)

    retrieval_seed_entities: int = Field(default=8, ge=1)
    retrieval_seed_events: int = Field(default=24, ge=1)
    retrieval_expansion_hops: int = Field(default=1, ge=0, le=4)
    retrieval_candidate_limit: int = Field(default=80, ge=1)
    retrieval_max_needs: int = Field(default=5, ge=1, le=6)
    retrieval_route_top_k: int = Field(default=16, ge=1)
    retrieval_fusion_rrf_k: int = Field(default=10, ge=1)
    retrieval_judge_candidates_per_need: int = Field(default=10, ge=1)
    retrieval_minimum_semantic_support: float = Field(default=0.58, ge=0.0, le=1.0)
    context_pack_maximum_tokens: int = Field(default=4000, ge=256)

    def require_llm(self) -> tuple[str, str, str]:
        api_key = self.llm_api_key.get_secret_value()
        if not (self.llm_base_url and api_key and self.llm_model):
            raise RuntimeError(
                "DeepSeek extractor requires DEEPSEEK_BASE_URL, DEEPSEEK_KEY, "
                "and DEEPSEEKMODEL (or SAG_LLM_* equivalents)"
            )
        return self.llm_base_url, api_key, self.llm_model
