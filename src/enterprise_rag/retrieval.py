import math
import re
from collections import Counter
from collections.abc import Iterable

import numpy as np

from enterprise_rag.embeddings import EmbeddingProvider, Reranker
from enterprise_rag.models import Chunk, DocumentRecord, DocumentStatus, SearchHit


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_-]+|[\u4e00-\u9fff]", text.lower())


def _identifiers(text: str) -> set[str]:
    return set(
        match.lower()
        for match in re.findall(
            r"\b(?:[A-Z]{2,10}-\d{2,10}|swg\w+|v?\d+\.\d+(?:\.\d+)?)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


class InMemoryHybridStore:
    """P1 adapter preserving filter-before-score semantics used by OpenSearch later."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        dense_weight: float = 0.5,
        reranker: Reranker | None = None,
    ) -> None:
        if not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be between 0 and 1")
        self._embeddings = embeddings
        self._dense_weight = dense_weight
        self._reranker = reranker
        self._documents: dict[str, DocumentRecord] = {}
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, np.ndarray] = {}

    def upsert_document(self, document: DocumentRecord, chunks: list[Chunk]) -> None:
        self.upsert_documents([(document, chunks)])

    def upsert_documents(self, items: list[tuple[DocumentRecord, list[Chunk]]]) -> None:
        document_ids = {document.document_id for document, _ in items}
        stale_ids = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if chunk.document_id in document_ids
        ]
        for chunk_id in stale_ids:
            self._chunks.pop(chunk_id, None)
            self._vectors.pop(chunk_id, None)

        all_chunks = [chunk for _, chunks in items for chunk in chunks]
        vectors = self._embeddings.embed_documents(
            [f"{chunk.title}\n{chunk.content}" for chunk in all_chunks]
        )
        for document, _ in items:
            self._documents[document.document_id] = document
        for chunk, vector in zip(all_chunks, vectors, strict=True):
            self._chunks[chunk.chunk_id] = chunk
            self._vectors[chunk.chunk_id] = vector

    @staticmethod
    def _authorized(chunk: Chunk, roles: frozenset[str]) -> bool:
        return chunk.status == DocumentStatus.ACTIVE and bool(chunk.allowed_roles & roles)

    @staticmethod
    def _lexical_scores(query: str, chunks: list[Chunk]) -> dict[str, float]:
        """Compute query-time BM25 with title and identifier boosts over the ACL-filtered set."""
        query_terms = list(dict.fromkeys(_tokens(query)))
        if not query_terms:
            return {chunk.chunk_id: 0.0 for chunk in chunks}

        term_counts: dict[str, Counter[str]] = {}
        document_frequencies: Counter[str] = Counter()
        lengths: dict[str, int] = {}
        for chunk in chunks:
            tokens = _tokens(f"{chunk.document_id} {chunk.title} {chunk.content}")
            counts = Counter(tokens)
            term_counts[chunk.chunk_id] = counts
            lengths[chunk.chunk_id] = len(tokens)
            for term in query_terms:
                if counts[term]:
                    document_frequencies[term] += 1

        document_count = len(chunks)
        average_length = sum(lengths.values()) / max(document_count, 1)
        identifiers = _identifiers(query)
        raw_scores: dict[str, float] = {}
        k1 = 1.5
        b = 0.75
        for chunk in chunks:
            counts = term_counts[chunk.chunk_id]
            length_ratio = lengths[chunk.chunk_id] / max(average_length, 1.0)
            title_terms = Counter(_tokens(f"{chunk.document_id} {chunk.title}"))
            score = 0.0
            for term in query_terms:
                frequency = counts[term]
                if not frequency:
                    continue
                frequency += 1.5 * title_terms[term]
                document_frequency = document_frequencies[term]
                inverse_document_frequency = math.log(
                    1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                score += inverse_document_frequency * (
                    (frequency * (k1 + 1))
                    / (frequency + k1 * (1 - b + b * length_ratio))
                )

            haystack = f"{chunk.document_id} {chunk.title} {chunk.content}".lower()
            if identifiers and any(identifier in haystack for identifier in identifiers):
                score += 8.0
            if query.strip().lower() in haystack:
                score += 4.0
            raw_scores[chunk.chunk_id] = score

        maximum = max(raw_scores.values(), default=0.0)
        if maximum <= 0:
            return {chunk_id: 0.0 for chunk_id in raw_scores}
        return {chunk_id: score / maximum for chunk_id, score in raw_scores.items()}

    def search(
        self,
        query: str,
        roles: frozenset[str],
        *,
        top_k: int = 5,
        exact: bool = False,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        # Authorization is deliberately evaluated before any candidate is scored.
        candidates = [chunk for chunk in self._chunks.values() if self._authorized(chunk, roles)]
        if not candidates:
            return []

        query_identifiers = _identifiers(query)
        if exact and query_identifiers:
            if re.search(r"\bdocument\s+(?:id|number)\b", query, flags=re.IGNORECASE):
                candidates = [
                    chunk
                    for chunk in candidates
                    if chunk.document_id.lower() in query_identifiers
                ]
            else:
                candidates = [
                    chunk
                    for chunk in candidates
                    if any(
                        identifier
                        in f"{chunk.document_id} {chunk.title} {chunk.content}".lower()
                        for identifier in query_identifiers
                    )
                ]
            if not candidates:
                return []

        lexical_scores = self._lexical_scores(query, candidates)
        query_vector = None if exact else self._embeddings.embed_queries([query])[0]
        hits: list[SearchHit] = []
        for chunk in candidates:
            lexical = lexical_scores[chunk.chunk_id]
            dense = 0.0
            if query_vector is not None:
                dense = max(float(np.dot(query_vector, self._vectors[chunk.chunk_id])), 0.0)
            score = (
                lexical
                if exact
                else ((1 - self._dense_weight) * lexical) + (self._dense_weight * dense)
            )
            if score >= min_score:
                hits.append(
                    SearchHit(
                        chunk=chunk,
                        score=round(score, 6),
                        lexical_score=round(lexical, 6),
                        dense_score=round(dense, 6),
                    )
                )

        ranked = sorted(hits, key=lambda hit: hit.score, reverse=True)
        if self._reranker is not None and not exact:
            rerank_candidates = ranked[: max(top_k * 4, 20)]
            rerank_scores = self._reranker.score(
                query,
                [f"{hit.chunk.title}\n{hit.chunk.content}" for hit in rerank_candidates],
            )
            ranked = [
                hit
                for _, hit in sorted(
                    zip(rerank_scores, rerank_candidates, strict=True),
                    key=lambda item: float(item[0]),
                    reverse=True,
                )
            ]
        return ranked[:top_k]

    def documents(self) -> Iterable[DocumentRecord]:
        return self._documents.values()

    def authorized_documents(self, roles: frozenset[str]) -> list[DocumentRecord]:
        return [
            document
            for document in self._documents.values()
            if document.status == DocumentStatus.ACTIVE and bool(document.allowed_roles & roles)
        ]
