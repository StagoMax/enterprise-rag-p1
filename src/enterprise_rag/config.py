from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from enterprise_rag.chunking import ChunkingConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_", extra="ignore")

    app_name: str = "Enterprise Graph RAG"
    dev_mode: bool = True
    jwt_secret: str = "local-development-secret-change-me"
    jwt_issuer: str = "enterprise-graph-rag"
    jwt_audience: str = "enterprise-rag-api"
    jwt_ttl_minutes: int = 60

    embedding_backend: Literal["hashing", "nemotron", "bge_m3"] = "hashing"
    nemotron_model_id: str = "nvidia/Nemotron-3-Embed-1B-BF16"
    nemotron_dimensions: int = 1024
    nemotron_device: str = "cuda"
    bge_model_id: str = "BAAI/bge-m3"
    bge_device: str = "cuda"
    # llm 重排走 llm_* 配置的生成后端；cross_encoder 在 P1 实测是负增益，默认仍不启用。
    reranker_backend: Literal["none", "cross_encoder", "llm"] = "none"
    reranker_model_id: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    reranker_device: str = "cuda"
    rerank_candidates: int = 20
    rerank_strategy: Literal["replace", "weighted_rrf"] = "replace"
    reranker_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    rerank_rrf_k: int = Field(default=60, ge=1)
    reranker_cache_mode: Literal["off", "record", "replay"] = "off"
    reranker_cache_path: Path | None = None
    query_rewrite_enabled: bool = False
    hashing_dimensions: int = 384

    # Structure-aware child chunks are embedded/retrieved; bounded parent sections
    # are retained only for evidence expansion after a hit is selected.
    chunking_strategy: Literal["legacy", "structured_parent_child"] = (
        "structured_parent_child"
    )
    chunk_max_tokens: int = Field(default=384, ge=16)
    chunk_overlap_tokens: int = Field(default=64, ge=0)
    chunk_parent_max_tokens: int = Field(default=1200, ge=16)
    chunking_version: str = "structured-parent-child-v1"

    # 生成模型。显式 RAG_* 配置优先；其次使用项目 .env 里的 DeepSeek、
    # NowCoding 命名；最后兼容旧的 OPENTOPIA_* 命名。validation_alias
    # 会绕过 env_prefix，因此每种名字都要显式列出。
    llm_backend: Literal["extractive", "openai_compatible"] = "openai_compatible"
    # 刻意不接受通用的 OPENAI_* 名字：环境变量优先级高于 .env，
    # 机器上一个无关的 OPENAI_API_KEY 会静默顶掉本项目的凭据（已踩过，表现为 401）。
    llm_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "RAG_LLM_BASE_URL",
            "DEEPSEEK_BASE_URL",
            "NOWCODING_BASE_URL",
            "OPENTOPIA_OPENAI_BASE_URL",
        ),
    )
    llm_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "RAG_LLM_API_KEY",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_KEY",
            "NOWCODING_KEY",
            "OPENTOPIA_MODEL_KEY",
        ),
    )
    llm_model: str = Field(
        default="",
        validation_alias=AliasChoices(
            "RAG_LLM_MODEL",
            "DEEPSEEK_MODEL",
            "DEEPSEEKMODEL",
            "NOWCODING_MODEL",
            "NOWCODINGMODEL",
            "OPENTOPIA_MODEL",
        ),
    )
    llm_timeout_seconds: float = 90.0
    llm_max_tokens: int = 1200
    llm_temperature: float = 0.0
    llm_max_retries: int = 2

    # 向量存储。memory 保留 P1/P2 的进程内实现供离线测试使用；
    # milvus 走 MilvusClient，URI 是本地文件即嵌入式 Milvus Lite，换成 grpc 地址即独立部署。
    vector_backend: Literal["memory", "milvus"] = "milvus"
    milvus_uri: str = "data/milvus/enterprise-rag.db"
    milvus_token: SecretStr = SecretStr("")
    milvus_collection: str = "enterprise_chunks"
    milvus_search_mode: Literal["separate", "native_rrf"] = "separate"
    milvus_fielded_search_enabled: bool = False
    milvus_rrf_k: int = Field(default=60, ge=1)
    # 候选池宽度 = top_k * 该值。精排在池内进行，池太窄会丢召回：
    # 1,000 文档实测 x4/x12/x30 对应 Top-1 0.575/0.613/0.650，p50 121/150/217 ms。
    milvus_search_multiplier: int = 12
    # Optional experiment guard: expand the chunk-level recall pool until enough
    # distinct documents are available for a document-level comparison/rerank.
    milvus_adaptive_recall_enabled: bool = False
    milvus_adaptive_recall_max_chunks: int = Field(default=4096, ge=1)

    # Product and evaluation contracts expose the three best distinct documents.
    top_k: int = 3
    min_retrieval_score: float = 0.12
    dense_weight: float = 0.5
    graph_enabled: bool = True
    graph_seed_count: int = 2
    graph_max_hops: int = 2
    graph_expansion_limit: int = 12
    graph_score_decay: float = 0.82
    index_version: str = "p3-techqa-28481-v1"
    audit_path: Path = Path("data/audit.jsonl")
    feedback_path: Path = Path("data/feedback.jsonl")
    demo_db_path: Path = Path("data/demo.sqlite")
    corpus_path: Path = Path("data/processed/techqa_p3/documents.jsonl")
    relations_path: Path = Path("data/processed/techqa_p3/relations.jsonl")
    graph_state_path: Path = Path("data/p3-milvus-graph-state.json")
    gold_path: Path = Path("data/processed/techqa_p3/golden_questions.curated.jsonl")
    evaluation_report_path: Path = Path("reports/p3-milvus-hashing.json")
    library_default_roles: str = "engineering,operations,finance,knowledge_admin"

    def chunking_config(self) -> "ChunkingConfig":
        from enterprise_rag.chunking import ChunkingConfig

        return ChunkingConfig(
            strategy=self.chunking_strategy,
            child_max_tokens=self.chunk_max_tokens,
            child_overlap_tokens=self.chunk_overlap_tokens,
            parent_max_tokens=self.chunk_parent_max_tokens,
            version=self.chunking_version,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
