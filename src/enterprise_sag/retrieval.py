from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from enterprise_rag.embeddings import EmbeddingProvider
from enterprise_sag.extraction import CandidateSelector, QueryEntityAnalyzer
from enterprise_sag.models import RetrievalTrace, SagSearchHit
from enterprise_sag.store import SagSqliteStore


def _cosine_scores(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.empty(0, dtype=np.float32)
    query_vector = np.asarray(query, dtype=np.float32).reshape(-1)
    query_norm = max(float(np.linalg.norm(query_vector)), 1e-12)
    row_norms = np.maximum(np.linalg.norm(matrix, axis=1), 1e-12)
    return (matrix @ query_vector) / (row_norms * query_norm)


class SagRetriever:
    """SAG retrieval with vector seeds and query-time SQL hyperedge expansion."""

    def __init__(
        self,
        store: SagSqliteStore,
        embeddings: EmbeddingProvider,
        *,
        query_analyzer: QueryEntityAnalyzer | None = None,
        candidate_selector: CandidateSelector | None = None,
        seed_entity_count: int = 8,
        seed_event_count: int = 24,
        candidate_limit: int = 80,
        expansion_hops: int = 1,
    ) -> None:
        self._store = store
        self._embeddings = embeddings
        self._query_analyzer = query_analyzer or QueryEntityAnalyzer()
        self._candidate_selector = candidate_selector or CandidateSelector()
        self._seed_entity_count = seed_entity_count
        self._seed_event_count = seed_event_count
        self._candidate_limit = candidate_limit
        self._expansion_hops = expansion_hops

    def _validate_dimensions(self) -> None:
        metadata = self._store.metadata()
        indexed_dimensions = int(metadata.get("embedding_dimensions", 0))
        if indexed_dimensions != self._embeddings.dimensions:
            raise ValueError(
                "Embedding dimensions do not match the SAG index: "
                f"query={self._embeddings.dimensions}, index={indexed_dimensions}"
            )

    def search(self, query: str, *, top_k: int = 10) -> list[SagSearchHit]:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            return []
        self._validate_dimensions()
        events = self._store.load_events()
        entities = self._store.load_entities()
        if not events:
            return []

        event_by_id = {str(item["event_id"]): item for item in events}
        query_vector = self._embeddings.embed_queries([normalized_query])[0]
        event_matrix = np.stack([item["event_vector"] for item in events])
        evidence_matrix = np.stack([item["evidence_vector"] for item in events])
        direct_event = _cosine_scores(query_vector, event_matrix)
        direct_evidence = _cosine_scores(query_vector, evidence_matrix)
        event_score = {
            str(item["event_id"]): max(float(direct_event[index]), 0.0)
            for index, item in enumerate(events)
        }
        evidence_score = {
            str(item["event_id"]): max(float(direct_evidence[index]), 0.0)
            for index, item in enumerate(events)
        }

        analyzed_entities = self._query_analyzer.analyze(normalized_query)
        entity_seed_scores: dict[str, float] = {}
        entity_display: dict[str, str] = {}
        if entities:
            query_entity_vectors = self._embeddings.embed_queries(analyzed_entities)
            entity_matrix = np.stack([item["vector"] for item in entities])
            score_matrix = np.stack(
                [_cosine_scores(vector, entity_matrix) for vector in query_entity_vectors]
            )
            maximum_scores = score_matrix.max(axis=0)
            ranked_entities = np.argsort(-maximum_scores)[: self._seed_entity_count]
            for index in ranked_entities:
                entity_id = str(entities[int(index)]["entity_id"])
                entity_seed_scores[entity_id] = max(float(maximum_scores[int(index)]), 0.0)
                entity_display[entity_id] = str(entities[int(index)]["display_name"])

        linked_events = self._store.event_ids_for_entities(list(entity_seed_scores))
        event_entity_score: dict[str, float] = {}
        event_shared_entities: dict[str, list[str]] = {}
        for event_id, entity_ids in linked_events.items():
            event_entity_score[event_id] = max(
                (entity_seed_scores[entity_id] for entity_id in entity_ids), default=0.0
            )
            event_shared_entities[event_id] = [
                entity_display[entity_id] for entity_id in entity_ids if entity_id in entity_display
            ]

        ranked_direct = sorted(event_score, key=event_score.get, reverse=True)[
            : self._seed_event_count
        ]
        ranked_evidence = sorted(evidence_score, key=evidence_score.get, reverse=True)[
            : self._seed_event_count
        ]
        lexical_ids = self._store.search_event_fts(normalized_query, limit=self._seed_event_count)
        lexical_score = {event_id: 1.0 / (rank + 1) for rank, event_id in enumerate(lexical_ids)}

        initial = set(ranked_direct) | set(ranked_evidence) | set(linked_events) | set(lexical_ids)
        seen = set(initial)
        frontier = set(initial)
        expansion_hop: dict[str, int] = {event_id: 0 for event_id in initial}
        for hop in range(1, self._expansion_hops + 1):
            rows = self._store.expand_events(sorted(frontier))
            next_frontier: set[str] = set()
            for row in rows:
                neighbor = row["neighbor_event_id"]
                if neighbor not in event_by_id:
                    continue
                event_shared_entities.setdefault(neighbor, []).append(row["display_name"])
                if neighbor not in seen:
                    seen.add(neighbor)
                    next_frontier.add(neighbor)
                    expansion_hop[neighbor] = hop
            frontier = next_frontier
            if not frontier:
                break

        preliminary: dict[str, float] = {}
        for event_id in seen:
            hop = expansion_hop.get(event_id, 0)
            expansion_bonus = 0.12 * (0.75 ** max(hop - 1, 0)) if hop else 0.0
            preliminary[event_id] = (
                0.42 * event_score.get(event_id, 0.0)
                + 0.23 * evidence_score.get(event_id, 0.0)
                + 0.25 * event_entity_score.get(event_id, 0.0)
                + 0.10 * lexical_score.get(event_id, 0.0)
                + expansion_bonus
            )
        ranked_candidates = sorted(preliminary, key=preliminary.get, reverse=True)[
            : self._candidate_limit
        ]
        selector_input = [
            {
                "event_id": event_id,
                "event": str(event_by_id[event_id]["event_text"]),
                "title": str(event_by_id[event_id]["title"]),
                "section": event_by_id[event_id]["section_path"],
                "pre_score": round(preliminary[event_id], 6),
            }
            for event_id in ranked_candidates
        ]
        selected = self._candidate_selector.select(normalized_query, selector_input, top_k)
        for event_id in ranked_candidates:
            if len(selected) >= top_k:
                break
            if event_id not in selected:
                selected.append(event_id)

        hits: list[SagSearchHit] = []
        for event_id in selected[:top_k]:
            event = event_by_id[event_id]
            hop = expansion_hop.get(event_id, 0)
            reasons: list[str] = []
            if event_score.get(event_id, 0.0) > 0:
                reasons.append("event-vector")
            if evidence_score.get(event_id, 0.0) > 0:
                reasons.append("evidence-vector")
            if event_entity_score.get(event_id, 0.0) > 0:
                reasons.append("entity-seed")
            if event_id in lexical_score:
                reasons.append("full-text")
            if hop:
                reasons.append(f"sql-hyperedge-hop-{hop}")
            selection_reason = "+".join(reasons) or "candidate-selection"
            trace = RetrievalTrace(
                direct_event_score=round(event_score.get(event_id, 0.0), 6),
                direct_evidence_score=round(evidence_score.get(event_id, 0.0), 6),
                entity_score=round(event_entity_score.get(event_id, 0.0), 6),
                lexical_score=round(lexical_score.get(event_id, 0.0), 6),
                expansion_hop=hop,
                shared_entities=list(dict.fromkeys(event_shared_entities.get(event_id, [])))[:12],
                selection_reason=selection_reason,
            )
            hits.append(
                SagSearchHit(
                    event_id=event_id,
                    evidence_id=str(event["evidence_id"]),
                    source_id=str(event["source_id"]),
                    source_path=str(event["source_path"]),
                    title=str(event["title"]),
                    section_path=list(event["section_path"]),
                    anchors=list(event["anchors"]),
                    event_text=str(event["event_text"]),
                    evidence_content=str(event["content"]),
                    score=round(preliminary[event_id], 6),
                    trace=trace,
                )
            )
        return hits


def candidate_ids(hits: Sequence[SagSearchHit]) -> list[str]:
    return [hit.event_id for hit in hits]
