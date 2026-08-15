from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from enterprise_rag.embeddings import EmbeddingProvider
from enterprise_sag.temporal_consolidation import TemporalConsolidationPlanner
from enterprise_sag.temporal_models import (
    AssertionRelation,
    ConsolidationApplyResult,
    ConsolidationProposal,
    MemoryEvent,
    MemoryEventCreate,
    TemporalAssertion,
    TemporalQuery,
    TemporalQueryMode,
    TemporalSearchHit,
    TemporalUsageEvent,
)
from enterprise_sag.temporal_retrieval import TemporalMemoryRetriever
from enterprise_sag.temporal_store import TemporalMemoryStore


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


class TemporalMemoryService:
    """Application boundary for manual temporal memory maintenance, outside Agent Loop."""

    def __init__(
        self,
        store: TemporalMemoryStore,
        embeddings: EmbeddingProvider | None = None,
        *,
        embedding_backend: str | None = None,
    ) -> None:
        self.store = store
        self.embeddings = embeddings
        self.embedding_backend = embedding_backend or (
            type(embeddings).__name__ if embeddings is not None else "unconfigured"
        )
        self.retriever = (
            TemporalMemoryRetriever(store, embeddings) if embeddings is not None else None
        )

    def _require_retriever(self) -> TemporalMemoryRetriever:
        if self.retriever is None:
            raise RuntimeError("Temporal retrieval requires an embedding provider")
        return self.retriever

    def _require_embeddings(self) -> EmbeddingProvider:
        if self.embeddings is None:
            raise RuntimeError("Temporal consolidation requires an embedding provider")
        return self.embeddings

    def append_interaction(self, request: MemoryEventCreate) -> MemoryEvent:
        """Fast append-only path: no extraction, retrieval, or LLM call happens here."""

        if not request.content.strip():
            raise ValueError("Memory event content cannot be blank")
        event = MemoryEvent(
            **request.model_dump(exclude={"content"}),
            content=request.content,
            content_hash=hashlib.sha256(request.content.encode("utf-8")).hexdigest(),
        )
        self.store.append_event(event)
        return event

    def propose_consolidation(
        self,
        event_id: str,
        planner: TemporalConsolidationPlanner,
        *,
        candidate_limit: int = 20,
    ) -> ConsolidationProposal:
        event = self.store.get_event(event_id)
        candidates = self._require_retriever().search(
            TemporalQuery(
                query=event.content,
                subject_id=event.subject_id,
                mode=TemporalQueryMode.HISTORICAL,
                valid_at=event.observed_at,
                known_at=datetime.now(UTC),
                top_k=candidate_limit,
            )
        )
        return planner.propose(event, candidates)

    def apply_consolidation(
        self,
        proposal: ConsolidationProposal,
    ) -> ConsolidationApplyResult:
        event = self.store.get_event(proposal.event_id)
        if event.subject_id != proposal.subject_id:
            raise ValueError("Proposal subject does not match its source event")
        applied_at = datetime.now(UTC)
        assertion_by_local: dict[str, TemporalAssertion] = {}
        for draft in proposal.assertions:
            assertion_by_local[draft.local_id] = TemporalAssertion(
                assertion_id=_stable_id("ast", proposal.proposal_id, draft.local_id),
                event_id=proposal.event_id,
                subject_id=proposal.subject_id,
                predicate=draft.predicate,
                object_text=draft.object_text,
                scope=draft.scope,
                valid_from=draft.valid_from or event.occurred_at or event.observed_at,
                confidence=draft.confidence,
                importance=draft.importance,
                extraction_method=proposal.planner,
                recorded_at=applied_at,
            )
        assertions = list(assertion_by_local.values())
        relation_models: list[AssertionRelation] = []
        for index, draft in enumerate(proposal.relations):
            source = assertion_by_local[draft.source_local_id] if draft.source_local_id else None
            relation_models.append(
                AssertionRelation(
                    relation_id=_stable_id(
                        "rel",
                        proposal.proposal_id,
                        str(index),
                        draft.relation_type.value,
                        draft.target_assertion_id,
                    ),
                    source_assertion_id=source.assertion_id if source else None,
                    target_assertion_id=draft.target_assertion_id,
                    source_event_id=proposal.event_id,
                    relation_type=draft.relation_type,
                    effective_at=(
                        draft.effective_at
                        or (source.valid_from if source else None)
                        or event.occurred_at
                        or event.observed_at
                    ),
                    confidence=draft.confidence,
                    rationale=draft.rationale,
                    recorded_at=applied_at,
                )
            )
        documents = [f"{item.predicate} {item.scope} {item.object_text}" for item in assertions]
        embeddings = self._require_embeddings()
        matrix = embeddings.embed_documents(documents) if documents else []
        vectors = {
            assertion.assertion_id: matrix[index] for index, assertion in enumerate(assertions)
        }
        applied = self.store.apply_consolidation(
            proposal,
            assertions,
            relation_models,
            embedding_backend=self.embedding_backend,
            embeddings=vectors,
        )
        return ConsolidationApplyResult(
            proposal_id=proposal.proposal_id,
            event_id=proposal.event_id,
            assertion_ids=[item.assertion_id for item in assertions],
            relation_ids=[item.relation_id for item in relation_models],
            applied=applied,
            projection_rebuilt=applied,
        )

    def search(self, request: TemporalQuery) -> list[TemporalSearchHit]:
        return self._require_retriever().search(request)

    def record_usage(self, event: TemporalUsageEvent) -> None:
        self.store.append_usage(event)
