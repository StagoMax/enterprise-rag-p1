from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.models import GraphPath, SearchHit
from enterprise_rag.retrieval import InMemoryHybridStore


@dataclass(frozen=True)
class RetrievalResult:
    hits: list[SearchHit]
    graph_paths: list[GraphPath]
    graph_used: bool


class GraphRagRetriever:
    def __init__(
        self,
        hybrid_store: InMemoryHybridStore,
        graph: VersionedKnowledgeGraph,
        *,
        seed_count: int = 2,
        max_hops: int = 2,
        expansion_limit: int = 12,
        score_decay: float = 0.82,
    ) -> None:
        self._hybrid_store = hybrid_store
        self._graph = graph
        self._seed_count = seed_count
        self._max_hops = max_hops
        self._expansion_limit = expansion_limit
        self._score_decay = score_decay

    def search(
        self,
        query: str,
        roles: frozenset[str],
        *,
        top_k: int,
        exact: bool,
        min_score: float,
        use_graph: bool,
    ) -> RetrievalResult:
        base_hits = self._hybrid_store.search(
            query,
            roles,
            top_k=max(top_k, self._seed_count),
            exact=exact,
            min_score=min_score,
        )
        if exact or not use_graph or not base_hits:
            return RetrievalResult(hits=base_hits[:top_k], graph_paths=[], graph_used=False)

        title_matches = self._hybrid_store.title_matched_document_ids(query, roles)
        if title_matches:
            title_ids = set(title_matches[: self._seed_count])
            title_hits = self._hybrid_store.search(
                query,
                roles,
                top_k=max(len(title_ids) * 4, self._seed_count),
                exact=False,
                min_score=0.0,
                candidate_document_ids=title_ids,
            )
            base_hits = [
                *title_hits,
                *(hit for hit in base_hits if hit.chunk.document_id not in title_ids),
            ]

        seed_hits: list[SearchHit] = []
        seed_ids: set[str] = set()
        for hit in base_hits:
            if hit.chunk.document_id in seed_ids:
                continue
            seed_hits.append(hit)
            seed_ids.add(hit.chunk.document_id)
            if len(seed_hits) == self._seed_count:
                break

        paths = self._graph.expand(
            [hit.chunk.document_id for hit in seed_hits],
            self._hybrid_store.authorized_document_ids(roles),
            max_hops=self._max_hops,
            limit=self._expansion_limit,
        )
        if not paths:
            return RetrievalResult(hits=base_hits[:top_k], graph_paths=[], graph_used=True)

        best_paths: dict[str, tuple[GraphPath, float]] = {}
        seed_scores = {hit.chunk.document_id: hit.score for hit in seed_hits}
        for path in paths:
            target_id = path.node_ids[-1]
            graph_score = (
                seed_scores.get(path.node_ids[0], 0.0)
                * path.confidence
                * (self._score_decay ** len(path.relations))
            )
            previous = best_paths.get(target_id)
            if previous is None or graph_score > previous[1]:
                best_paths[target_id] = (path, graph_score)

        target_ids = set(best_paths)
        graph_candidates = self._hybrid_store.search(
            query,
            roles,
            top_k=max(len(target_ids) * 4, top_k),
            exact=False,
            min_score=0.0,
            candidate_document_ids=target_ids,
        )
        best_target_hits: dict[str, SearchHit] = {}
        for hit in graph_candidates:
            best_target_hits.setdefault(hit.chunk.document_id, hit)

        graph_hits: list[SearchHit] = []
        for target_id, (path, graph_score) in best_paths.items():
            hit = best_target_hits.get(target_id)
            if hit is None:
                continue
            graph_hits.append(
                hit.model_copy(
                    update={
                        "score": round(graph_score, 6),
                        "retrieval_mode": "graph",
                        "graph_path": path.node_ids,
                        "graph_relations": path.relations,
                    }
                )
            )
        graph_hits.sort(key=lambda hit: hit.score, reverse=True)

        ordered = [seed_hits[0], *graph_hits, *base_hits[1:]]
        selected: list[SearchHit] = []
        selected_documents: set[str] = set()
        for hit in ordered:
            if hit.chunk.document_id in selected_documents:
                continue
            selected.append(hit)
            selected_documents.add(hit.chunk.document_id)
            if len(selected) == top_k:
                break

        included_targets = {
            hit.chunk.document_id for hit in selected if hit.retrieval_mode == "graph"
        }
        included_paths = [
            path for path in paths if path.node_ids[-1] in included_targets
        ]
        return RetrievalResult(
            hits=selected,
            graph_paths=included_paths,
            graph_used=True,
        )
