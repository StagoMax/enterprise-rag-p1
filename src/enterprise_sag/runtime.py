from __future__ import annotations

from enterprise_rag.embeddings import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    NemotronEmbeddingProvider,
)
from enterprise_rag.llm import OpenAiCompatibleChatModel
from enterprise_sag.extraction import QueryEntityAnalyzer
from enterprise_sag.judgement import (
    DeepSeekEvidenceCoverageJudge,
    RelativeScoreCoverageJudge,
)
from enterprise_sag.multi_retrieval import CoverageFusion, MultiRouteSagRetriever
from enterprise_sag.planning import DeepSeekEvidenceNeedPlanner, SingleNeedPlanner
from enterprise_sag.retrieval import SagRetriever
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import SagSqliteStore


def create_embedding_provider(settings: SagSettings) -> EmbeddingProvider:
    if settings.embedding_backend == "nemotron":
        return NemotronEmbeddingProvider(
            model_id=settings.nemotron_model_id,
            dimensions=settings.nemotron_dimensions,
            device=settings.nemotron_device,
            batch_size=settings.embedding_batch_size,
        )
    return HashingEmbeddingProvider(settings.hashing_dimensions)


def create_chat_model(settings: SagSettings) -> OpenAiCompatibleChatModel:
    base_url, api_key, model = settings.require_llm()
    return OpenAiCompatibleChatModel(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
        temperature=0.0,
        max_retries=settings.llm_max_retries,
    )


def create_multi_route_retriever(
    settings: SagSettings,
    store: SagSqliteStore,
    embeddings: EmbeddingProvider,
    chat_model: OpenAiCompatibleChatModel | None,
) -> MultiRouteSagRetriever:
    planner = (
        SingleNeedPlanner()
        if chat_model is None
        else DeepSeekEvidenceNeedPlanner(
            chat_model,
            max_needs=settings.retrieval_max_needs,
        )
    )
    route_retriever = SagRetriever(
        store,
        embeddings,
        query_analyzer=QueryEntityAnalyzer(),
        seed_entity_count=settings.retrieval_seed_entities,
        seed_event_count=settings.retrieval_seed_events,
        candidate_limit=settings.retrieval_candidate_limit,
        expansion_hops=settings.retrieval_expansion_hops,
    )
    coverage_judge = (
        RelativeScoreCoverageJudge()
        if chat_model is None
        else DeepSeekEvidenceCoverageJudge(
            chat_model,
            candidates_per_need=settings.retrieval_judge_candidates_per_need,
            minimum_support=settings.retrieval_minimum_semantic_support,
        )
    )
    return MultiRouteSagRetriever(
        planner,
        route_retriever,
        route_top_k=settings.retrieval_route_top_k,
        fusion=CoverageFusion(rrf_k=settings.retrieval_fusion_rrf_k),
        coverage_judge=coverage_judge,
    )
