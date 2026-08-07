import json
from pathlib import Path

from enterprise_rag.answering import (
    CitationConstrainedAnswerGenerator,
    EvidenceAnswerGenerator,
)
from enterprise_rag.components import (
    build_runtime_components,
    describe_runtime_components,
)
from enterprise_rag.config import Settings
from enterprise_rag.reranking import LlmReranker
from enterprise_rag.retrieval import InMemoryHybridStore


def settings_for(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "embedding_backend": "hashing",
        "vector_backend": "memory",
        "reranker_backend": "none",
        "llm_backend": "extractive",
        "RAG_LLM_BASE_URL": "",
        "RAG_LLM_API_KEY": "",
        "RAG_LLM_MODEL": "",
        "audit_path": tmp_path / "audit.jsonl",
        "demo_db_path": tmp_path / "demo.sqlite",
    }
    values.update(overrides)
    return Settings(**values)


def test_none_and_extractive_preserve_the_deterministic_runtime(tmp_path: Path) -> None:
    components = build_runtime_components(settings_for(tmp_path))

    assert isinstance(components.store, InMemoryHybridStore)
    assert components.reranker is None
    assert components.chat_model is None
    assert isinstance(components.answer_generator, EvidenceAnswerGenerator)
    assert not isinstance(
        components.answer_generator,
        CitationConstrainedAnswerGenerator,
    )


def test_llm_reranker_and_answer_generator_share_one_chat_model(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path,
        reranker_backend="llm",
        llm_backend="openai_compatible",
        RAG_LLM_BASE_URL="https://llm.internal.example/v1",
        RAG_LLM_API_KEY="test-secret",
        RAG_LLM_MODEL="test-model",
    )

    components = build_runtime_components(settings)

    assert isinstance(components.reranker, LlmReranker)
    assert isinstance(
        components.answer_generator,
        CitationConstrainedAnswerGenerator,
    )
    assert components.chat_model is not None
    assert components.reranker._model is components.chat_model
    assert components.answer_generator._model is components.chat_model


def test_runtime_description_excludes_credentials_and_endpoint(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path,
        llm_backend="openai_compatible",
        RAG_LLM_BASE_URL="https://sensitive-host.example/v1",
        RAG_LLM_API_KEY="do-not-report-this-key",
        RAG_LLM_MODEL="test-model",
        milvus_token="do-not-report-this-token",
    )
    components = build_runtime_components(settings)

    serialized = json.dumps(describe_runtime_components(settings, components))

    assert "do-not-report-this-key" not in serialized
    assert "do-not-report-this-token" not in serialized
    assert "sensitive-host" not in serialized
    assert "test-model" in serialized


def test_runtime_description_records_retrieval_and_rerank_strategies(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path,
        query_rewrite_enabled=True,
        milvus_search_mode="native_rrf",
        milvus_fielded_search_enabled=True,
        rerank_strategy="weighted_rrf",
        reranker_weight=0.4,
        rerank_rrf_k=42,
    )
    components = build_runtime_components(settings)

    description = describe_runtime_components(settings, components)

    assert description["vector_store"]["query_rewrite_enabled"] is True
    assert description["vector_store"]["search_mode"] == "native_rrf"
    assert description["vector_store"]["fielded_search_enabled"] is True
    assert description["chunking"] == {
        "strategy": "structured_parent_child",
        "version": "structured-parent-child-v1",
        "child_max_tokens": 384,
        "child_overlap_tokens": 64,
        "parent_max_tokens": 1200,
    }
    assert description["reranker"]["strategy"] == "weighted_rrf"
    assert description["reranker"]["weight"] == 0.4
    assert description["reranker"]["rrf_k"] == 42
