from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_", extra="ignore")

    app_name: str = "Enterprise RAG P1"
    dev_mode: bool = True
    jwt_secret: str = "local-development-secret-change-me"
    jwt_issuer: str = "enterprise-rag-p1"
    jwt_audience: str = "enterprise-rag-api"
    jwt_ttl_minutes: int = 60

    embedding_backend: Literal["hashing", "nemotron", "bge_m3"] = "hashing"
    nemotron_model_id: str = "nvidia/Nemotron-3-Embed-1B-BF16"
    nemotron_dimensions: int = 1024
    nemotron_device: str = "cuda"
    bge_model_id: str = "BAAI/bge-m3"
    bge_device: str = "cuda"
    reranker_backend: Literal["none", "cross_encoder"] = "none"
    reranker_model_id: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    reranker_device: str = "cuda"
    hashing_dimensions: int = 384

    top_k: int = 5
    min_retrieval_score: float = 0.12
    dense_weight: float = 0.5
    audit_path: Path = Path("data/audit.jsonl")
    feedback_path: Path = Path("data/feedback.jsonl")
    demo_db_path: Path = Path("data/demo.sqlite")
    corpus_path: Path = Path("data/processed/techqa_websphere/documents.jsonl")
    gold_path: Path = Path("data/processed/techqa_websphere/golden_questions.jsonl")
    evaluation_report_path: Path = Path("reports/baseline-current.json")


@lru_cache
def get_settings() -> Settings:
    return Settings()
