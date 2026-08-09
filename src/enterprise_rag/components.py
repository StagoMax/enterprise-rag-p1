from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from enterprise_rag.answering import (
    CitationConstrainedAnswerGenerator,
    EvidenceAnswerGenerator,
)
from enterprise_rag.config import Settings
from enterprise_rag.embeddings import (
    BgeM3EmbeddingProvider,
    CrossEncoderReranker,
    EmbeddingProvider,
    HashingEmbeddingProvider,
    NemotronEmbeddingProvider,
    Reranker,
)
from enterprise_rag.llm import OpenAiCompatibleChatModel
from enterprise_rag.reranking import LlmReranker
from enterprise_rag.retrieval import InMemoryHybridStore
from enterprise_rag.vector_store import HybridStore, MilvusHybridStore


@dataclass(frozen=True, slots=True)
class RuntimeComponents:
    """Model and retrieval components shared by serving and evaluation."""

    embeddings: EmbeddingProvider
    chat_model: OpenAiCompatibleChatModel | None
    reranker: Reranker | None
    store: HybridStore
    answer_generator: EvidenceAnswerGenerator


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_backend == "nemotron":
        return NemotronEmbeddingProvider(
            model_id=settings.nemotron_model_id,
            dimensions=settings.nemotron_dimensions,
            device=settings.nemotron_device,
        )
    if settings.embedding_backend == "bge_m3":
        return BgeM3EmbeddingProvider(
            model_id=settings.bge_model_id,
            device=settings.bge_device,
        )
    return HashingEmbeddingProvider(settings.hashing_dimensions)


def build_chat_model(settings: Settings) -> OpenAiCompatibleChatModel | None:
    api_key = settings.llm_api_key.get_secret_value()
    if not (settings.llm_base_url and settings.llm_model and api_key):
        return None
    return OpenAiCompatibleChatModel(
        base_url=settings.llm_base_url,
        api_key=api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        max_retries=settings.llm_max_retries,
    )


def build_reranker(
    settings: Settings,
    chat_model: OpenAiCompatibleChatModel | None,
) -> Reranker | None:
    if settings.reranker_backend == "cross_encoder":
        return CrossEncoderReranker(
            settings.reranker_model_id,
            device=settings.reranker_device,
        )
    if settings.reranker_backend == "llm":
        if chat_model is None:
            raise RuntimeError(
                "reranker_backend=llm requires llm_base_url, llm_model, and llm_api_key"
            )
        return LlmReranker(
            chat_model,
            max_candidates=settings.rerank_candidates,
            cache_mode=settings.reranker_cache_mode,
            cache_path=settings.reranker_cache_path,
            cache_namespace=(
                f"{settings.llm_model}|temperature={settings.llm_temperature}|reranker-v1"
            ),
        )
    return None


def build_vector_store(
    settings: Settings,
    embeddings: EmbeddingProvider,
    reranker: Reranker | None,
) -> HybridStore:
    if settings.vector_backend == "milvus":
        return MilvusHybridStore(
            embeddings,
            uri=settings.milvus_uri,
            token=settings.milvus_token.get_secret_value(),
            collection=settings.milvus_collection,
            dense_weight=settings.dense_weight,
            reranker=reranker,
            search_multiplier=settings.milvus_search_multiplier,
            adaptive_recall_enabled=settings.milvus_adaptive_recall_enabled,
            adaptive_recall_max_chunks=settings.milvus_adaptive_recall_max_chunks,
            rerank_candidates=settings.rerank_candidates,
            query_rewrite_enabled=settings.query_rewrite_enabled,
            fielded_search_enabled=settings.milvus_fielded_search_enabled,
            search_mode=settings.milvus_search_mode,
            hybrid_rrf_k=settings.milvus_rrf_k,
            rerank_strategy=settings.rerank_strategy,
            reranker_weight=settings.reranker_weight,
            rerank_rrf_k=settings.rerank_rrf_k,
        )
    return InMemoryHybridStore(
        embeddings,
        dense_weight=settings.dense_weight,
        reranker=reranker,
        query_rewrite_enabled=settings.query_rewrite_enabled,
        rerank_strategy=settings.rerank_strategy,
        reranker_weight=settings.reranker_weight,
        rerank_rrf_k=settings.rerank_rrf_k,
    )


def build_answer_generator(
    settings: Settings,
    chat_model: OpenAiCompatibleChatModel | None,
) -> EvidenceAnswerGenerator:
    if settings.llm_backend != "openai_compatible" or chat_model is None:
        return EvidenceAnswerGenerator()
    return CitationConstrainedAnswerGenerator(chat_model, evidence_limit=settings.top_k)


def build_runtime_components(settings: Settings) -> RuntimeComponents:
    embeddings = build_embedding_provider(settings)
    chat_model = build_chat_model(settings)
    reranker = build_reranker(settings, chat_model)
    return RuntimeComponents(
        embeddings=embeddings,
        chat_model=chat_model,
        reranker=reranker,
        store=build_vector_store(settings, embeddings, reranker),
        answer_generator=build_answer_generator(settings, chat_model),
    )


def describe_runtime_components(
    settings: Settings,
    components: RuntimeComponents,
) -> dict[str, Any]:
    """Return reproducibility metadata without credentials or endpoint URLs."""

    embedding_model = (
        settings.nemotron_model_id
        if settings.embedding_backend == "nemotron"
        else settings.bge_model_id
        if settings.embedding_backend == "bge_m3"
        else f"hashing-{settings.hashing_dimensions}"
    )
    reranker_model = (
        settings.reranker_model_id
        if settings.reranker_backend == "cross_encoder"
        else settings.llm_model or None
        if settings.reranker_backend == "llm"
        else None
    )
    return {
        "embedding": {
            "backend": settings.embedding_backend,
            "model": embedding_model,
            "dimensions": components.embeddings.dimensions,
        },
        "chunking": {
            "strategy": settings.chunking_strategy,
            "version": settings.chunking_version,
            "child_max_tokens": settings.chunk_max_tokens,
            "child_overlap_tokens": settings.chunk_overlap_tokens,
            "parent_max_tokens": settings.chunk_parent_max_tokens,
        },
        "reranker": {
            "backend": settings.reranker_backend,
            "model": reranker_model,
            "effective_class": type(components.reranker).__name__
            if components.reranker is not None
            else None,
            "candidates": settings.rerank_candidates,
            "strategy": settings.rerank_strategy,
            "weight": settings.reranker_weight,
            "rrf_k": settings.rerank_rrf_k,
            "cache_mode": settings.reranker_cache_mode,
            "cache_path": str(settings.reranker_cache_path)
            if settings.reranker_cache_path
            else None,
        },
        "vector_store": {
            "backend": settings.vector_backend,
            "collection": settings.milvus_collection
            if settings.vector_backend == "milvus"
            else None,
            "dense_weight": settings.dense_weight,
            "search_multiplier": settings.milvus_search_multiplier,
            "adaptive_recall_enabled": settings.milvus_adaptive_recall_enabled,
            "adaptive_recall_max_chunks": settings.milvus_adaptive_recall_max_chunks,
            "search_mode": settings.milvus_search_mode,
            "fielded_search_enabled": settings.milvus_fielded_search_enabled,
            "hybrid_rrf_k": settings.milvus_rrf_k,
            "query_rewrite_enabled": settings.query_rewrite_enabled,
            "index_version": settings.index_version,
        },
        "answer_generator": {
            "backend": settings.llm_backend,
            "effective_class": type(components.answer_generator).__name__,
            "model": settings.llm_model
            if isinstance(
                components.answer_generator,
                CitationConstrainedAnswerGenerator,
            )
            else None,
            "evidence_limit": settings.top_k,
        },
        "llm": {
            "configured": components.chat_model is not None,
            "model": settings.llm_model or None,
            "timeout_seconds": settings.llm_timeout_seconds,
            "max_tokens": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,
            "max_retries": settings.llm_max_retries,
        },
    }
