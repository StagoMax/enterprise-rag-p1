from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from enterprise_rag.embeddings import EmbeddingProvider
from enterprise_sag.temporal_models import (
    AssertionLifecycle,
    TemporalQuery,
    TemporalQueryMode,
    TemporalSearchHit,
)
from enterprise_sag.temporal_store import TemporalMemoryStore


def _cosine(query: np.ndarray, document: np.ndarray) -> float:
    query_vector = np.asarray(query, dtype=np.float32).reshape(-1)
    document_vector = np.asarray(document, dtype=np.float32).reshape(-1)
    denominator = max(
        float(np.linalg.norm(query_vector)) * float(np.linalg.norm(document_vector)),
        1e-12,
    )
    return float(np.dot(query_vector, document_vector) / denominator)


class TemporalMemoryRetriever:
    """Validity-gated temporal retrieval; salience never resurrects inactive facts."""

    def __init__(
        self,
        store: TemporalMemoryStore,
        embeddings: EmbeddingProvider,
    ) -> None:
        self._store = store
        self._embeddings = embeddings

    def search(self, request: TemporalQuery) -> list[TemporalSearchHit]:
        states = self._store.resolve_states(
            request.subject_id,
            valid_at=request.valid_at,
            known_at=request.known_at,
        )
        if request.mode == TemporalQueryMode.LATEST_VALID:
            states = [
                state
                for state in states
                if state.lifecycle in {AssertionLifecycle.ACTIVE, AssertionLifecycle.CONTESTED}
            ]
        else:
            states = [state for state in states if state.lifecycle != AssertionLifecycle.FUTURE]
        if request.predicates:
            allowed_predicates = set(request.predicates)
            states = [state for state in states if state.assertion.predicate in allowed_predicates]
        if request.scopes:
            allowed_scopes = set(request.scopes)
            states = [state for state in states if state.assertion.scope in allowed_scopes]
        if not states:
            return []

        assertion_ids = [state.assertion.assertion_id for state in states]
        vector_by_id = self._store.load_embeddings(
            assertion_ids,
            dimensions=self._embeddings.dimensions,
        )
        query_vector = self._embeddings.embed_queries([request.query])[0]
        lexical_ids = self._store.search_fts(request.query, limit=max(request.top_k * 8, 40))
        lexical_rank = {assertion_id: rank for rank, assertion_id in enumerate(lexical_ids)}
        usage_by_id = self._store.usage_stats(assertion_ids)

        hits: list[TemporalSearchHit] = []
        for state in states:
            assertion = state.assertion
            semantic = (
                max(
                    _cosine(query_vector, vector_by_id[assertion.assertion_id]),
                    0.0,
                )
                if assertion.assertion_id in vector_by_id
                else 0.0
            )
            lexical = (
                1.0 / (1.0 + lexical_rank[assertion.assertion_id])
                if assertion.assertion_id in lexical_rank
                else 0.0
            )
            usage = usage_by_id[assertion.assertion_id]
            reinforcement = self._reinforcement_score(
                usage.use_count,
                usage.successful_use_count,
                usage.rejected_use_count,
                state.reinforcement_count,
            )
            recency = self._recency_score(assertion.valid_from, request.valid_at)
            lifecycle_multiplier = 0.82 if state.lifecycle == AssertionLifecycle.CONTESTED else 1.0
            if request.mode == TemporalQueryMode.HISTORICAL and state.lifecycle not in {
                AssertionLifecycle.ACTIVE,
                AssertionLifecycle.CONTESTED,
            }:
                lifecycle_multiplier = 0.94
            score = lifecycle_multiplier * (
                0.60 * semantic
                + 0.15 * lexical
                + 0.10 * assertion.confidence
                + 0.08 * assertion.importance
                + 0.05 * reinforcement
                + 0.02 * recency
            )
            hits.append(
                TemporalSearchHit(
                    assertion=assertion,
                    lifecycle=state.lifecycle,
                    valid_to=state.valid_to,
                    score=round(score, 6),
                    semantic_score=round(semantic, 6),
                    lexical_score=round(lexical, 6),
                    confidence_score=assertion.confidence,
                    importance_score=assertion.importance,
                    reinforcement_score=round(reinforcement, 6),
                    relation_reinforcement_count=state.reinforcement_count,
                    recency_score=round(recency, 6),
                    usage=usage,
                )
            )
        hits.sort(
            key=lambda item: (
                -item.score,
                -item.assertion.valid_from.timestamp(),
                item.assertion.assertion_id,
            )
        )
        return hits[: request.top_k]

    @staticmethod
    def _reinforcement_score(
        use_count: int,
        successful: int,
        rejected: int,
        relation_reinforcements: int,
    ) -> float:
        positive = (
            successful + max(use_count - successful - rejected, 0) * 0.25 + relation_reinforcements
        )
        total_signals = use_count + relation_reinforcements
        raw = positive / max(total_signals, 1)
        frequency = min(math.log1p(total_signals) / math.log(11), 1.0)
        return min(max(raw * frequency, 0.0), 1.0)

    @staticmethod
    def _recency_score(valid_from: datetime, valid_at: datetime) -> float:
        age_days = max((valid_at - valid_from).total_seconds() / 86_400, 0.0)
        return 1.0 / (1.0 + age_days / 365.0)
