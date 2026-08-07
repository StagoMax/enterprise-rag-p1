import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from enterprise_rag.embeddings import EmbeddingProvider, Reranker
from enterprise_rag.models import Chunk, DocumentRecord, DocumentStatus, SearchHit

_PRODUCT_PATTERNS = {
    "datapower": (r"(?i:\bdatapower\b)",),
    "domino": (r"(?i:\b(?:ibm\s+)?domino\b)",),
    "websphere-application-server": (
        r"(?i:\bwebsphere\s+application\s+server\b)",
        r"\bWAS\b",
    ),
    "ibm-http-server": (r"(?i:\bibm\s+http\s+server\b)", r"(?i:\bIHS\b)"),
    "ibm-mq": (r"(?i:\b(?:ibm|websphere)\s+mq\b)", r"(?i:\bMQ\b)"),
    "business-process-manager": (
        r"(?i:\b(?:ibm\s+)?business\s+process\s+manager\b)",
        r"(?i:\bBPM\b)",
    ),
    "websphere-portal": (r"(?i:\bwebsphere\s+portal\b)",),
    "tbsm": (
        r"(?i:\bTBSM\b)",
        r"(?i:\btivoli\s+business\s+service\s+manager\b)",
    ),
    "itm": (r"(?i:\bITM\b)", r"(?i:\bibm\s+tivoli\s+monitoring\b)"),
    "hats": (
        r"(?i:\bHATS\b)",
        r"(?i:\bhost\s+access\s+transformation\s+services\b)",
    ),
}

_COMPONENT_PATTERNS = {
    "jms": (r"(?i:\bJMS\b)", r"(?i:\bjava\s+message\s+service\b)"),
    "jdbc": (r"(?i:\bJDBC\b)", r"(?i:\bjava\s+database\s+connectivity\b)"),
    "sca": (r"(?i:\bSCA\b)", r"(?i:\bservice\s+component\s+architecture\b)"),
    "decision-center": (r"(?i:\bdecision\s+center\b)",),
}

_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "for",
    "how",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "with",
}

RERANK_CHUNKS_PER_DOCUMENT = 3
RERANK_DOCUMENT_CHARACTER_LIMIT = 680


@dataclass(frozen=True, slots=True)
class ExplicitFeatures:
    products: frozenset[str]
    components: frozenset[str]
    identifiers: frozenset[str]
    versions: frozenset[str]


@dataclass(frozen=True, slots=True)
class DocumentCandidate:
    hits: tuple[SearchHit, ...]
    evidence_hit: SearchHit
    reranker_text: str


def _feature_token(prefix: str, value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return f"{prefix}_{normalized}" if normalized else ""


def feature_search_text(text: str, *, document_id: str | None = None) -> str:
    """Build stable BM25 tokens for identifiers and other exact retrieval features."""
    features = explicit_features(text)
    tokens = [
        *(_feature_token("product", value) for value in sorted(features.products)),
        *(_feature_token("component", value) for value in sorted(features.components)),
        *(_feature_token("identifier", value) for value in sorted(features.identifiers)),
        *(_feature_token("version", value) for value in sorted(features.versions)),
    ]
    if document_id:
        tokens.append(_feature_token("document", document_id))
    return " ".join(token for token in tokens if token)


def focused_retrieval_query(query: str) -> str:
    """Deterministically reduce a TechQA post to its headline plus exact constraints."""
    lines = [" ".join(line.split()) for line in query.splitlines() if line.strip()]
    if not lines:
        return query.strip()
    headline = lines[0][:360]
    features = explicit_features(query)
    constraints = [
        *sorted(features.products),
        *sorted(features.components),
        *sorted(features.identifiers),
        *sorted(features.versions),
    ]
    lowered = headline.lower()
    suffix = [value for value in constraints if value.lower() not in lowered]
    return " ".join([headline, *suffix]).strip()


def retrieval_queries(query: str, *, rewrite_enabled: bool) -> tuple[str, ...]:
    """Return the original query and, when useful, a focused parallel query."""
    original = query.strip()
    if not rewrite_enabled or not original:
        return (original,)
    focused = focused_retrieval_query(original)
    if not focused or " ".join(focused.split()).lower() == " ".join(original.split()).lower():
        return (original,)
    return original, focused


def rank_document_candidates(
    candidates: Sequence[DocumentCandidate],
    reranker_scores: Sequence[float],
    *,
    strategy: str,
    reranker_weight: float,
    rrf_k: int,
) -> list[DocumentCandidate]:
    """Apply pure reranking or weighted RRF against the original document order."""
    if len(candidates) != len(reranker_scores):
        raise ValueError("candidate and reranker score counts must match")
    if strategy not in {"replace", "weighted_rrf"}:
        raise ValueError(f"unsupported rerank strategy: {strategy}")
    if not 0 <= reranker_weight <= 1:
        raise ValueError("reranker_weight must be between 0 and 1")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    reranked_indices = sorted(
        range(len(candidates)),
        key=lambda index: (-float(reranker_scores[index]), index),
    )
    if strategy == "replace":
        return [candidates[index] for index in reranked_indices]

    reranker_ranks = {
        candidate_index: rank
        for rank, candidate_index in enumerate(reranked_indices, start=1)
    }
    fused = []
    for index, candidate in enumerate(candidates):
        base_rank = index + 1
        score = (1 - reranker_weight) / (rrf_k + base_rank)
        score += reranker_weight / (rrf_k + reranker_ranks[index])
        fused.append((score, base_rank, candidate))
    return [
        candidate
        for _, _, candidate in sorted(fused, key=lambda item: (-item[0], item[1]))
    ]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_-]+|[\u4e00-\u9fff]", text.lower())


def _identifiers(text: str) -> set[str]:
    identifiers = {
        match.lower()
        for match in re.findall(
            r"\b(?:[A-Z]{2,12}-\d{2,10}|swg\w+|v?\d+\.\d+(?:\.\d+)*)\b",
            text,
            flags=re.IGNORECASE,
        )
    }
    identifiers.update(
        match.lower()
        for match in re.findall(
            r"\b(?:[A-Z]{2,12}\d{3,8}[A-Z]?|MQRC(?:_[A-Z0-9]+)+)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    identifiers.update(
        match.lower()
        for match in re.findall(
            r"\b[A-Z][A-Za-z0-9]*(?:Exception|Error)\b",
            text,
        )
    )
    identifiers.update(
        f"{prefix.lower()} {number}"
        for prefix, number in re.findall(r"(?i:\b(MQ)\s+(\d{3,8})\b)", text)
    )
    return identifiers


def _named_matches(text: str, patterns: dict[str, tuple[str, ...]]) -> frozenset[str]:
    return frozenset(
        name
        for name, aliases in patterns.items()
        if any(re.search(alias, text) for alias in aliases)
    )


def explicit_features(text: str) -> ExplicitFeatures:
    identifiers = frozenset(_identifiers(text))
    versions = frozenset(
        match.lower()
        for match in re.findall(
            r"(?<![A-Za-z0-9])v?\d+\.\d+(?:\.\d+)*(?![A-Za-z0-9])",
            text,
            flags=re.IGNORECASE,
        )
    )
    return ExplicitFeatures(
        products=_named_matches(text, _PRODUCT_PATTERNS),
        components=_named_matches(text, _COMPONENT_PATTERNS),
        identifiers=identifiers - versions,
        versions=versions,
    )


def retrieval_feature_boost(query: str, chunk: Chunk) -> float:
    """Return a bounded positive boost for explicit, high-precision feature matches."""
    query_features = explicit_features(query)
    document_features = explicit_features(
        f"{chunk.document_id}\n{chunk.title}\n{chunk.content}"
    )

    def coverage(left: frozenset[str], right: frozenset[str]) -> float:
        return len(left & right) / len(left) if left else 0.0

    boost = (
        0.08 * coverage(query_features.products, document_features.products)
        + 0.05 * coverage(query_features.components, document_features.components)
        + 0.12 * coverage(query_features.identifiers, document_features.identifiers)
        + 0.04 * coverage(query_features.versions, document_features.versions)
    )
    return min(boost, 0.2)


def _meaningful_query_tokens(query: str) -> set[str]:
    tokens = set(_tokens(query))
    meaningful = {
        token for token in tokens if token not in _QUERY_STOPWORDS and len(token) > 2
    }
    return meaningful or tokens


def _best_evidence_hit(query: str, hits: list[SearchHit]) -> SearchHit:
    query_tokens = _meaningful_query_tokens(query)
    query_identifiers = _identifiers(query)

    def evidence_key(item: tuple[int, SearchHit]) -> tuple[float, float, float, float, int]:
        index, hit = item
        content_tokens = set(_tokens(hit.chunk.content))
        content_identifiers = _identifiers(hit.chunk.content)
        identifier_coverage = (
            len(query_identifiers & content_identifiers) / len(query_identifiers)
            if query_identifiers
            else 0.0
        )
        token_coverage = (
            len(query_tokens & content_tokens) / len(query_tokens) if query_tokens else 0.0
        )
        return (
            identifier_coverage,
            token_coverage,
            retrieval_feature_boost(query, hit.chunk),
            hit.score,
            -index,
        )

    return max(enumerate(hits), key=evidence_key)[1]


def _query_excerpt(query: str, content: str, character_limit: int) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= character_limit:
        return normalized

    lowered = normalized.lower()
    positions = [
        lowered.find(token)
        for token in sorted(_meaningful_query_tokens(query), key=len, reverse=True)
        if lowered.find(token) >= 0
    ]
    center = min(positions) if positions else 0
    start = max(center - character_limit // 3, 0)
    end = min(start + character_limit, len(normalized))
    start = max(end - character_limit, 0)
    excerpt = normalized[start:end]
    if start:
        excerpt = f"...{excerpt}"
    if end < len(normalized):
        excerpt = f"{excerpt}..."
    return excerpt


def _reranker_document_text(query: str, hits: list[SearchHit]) -> str:
    first = hits[0].chunk
    header = (
        f"Document: {first.document_id[:80]}\n"
        f"Title: {first.title[:160]}\n"
        f"Version: {first.version[:32]}; Type: {first.business_class[:48]}\n"
    )
    labels_length = sum(len(f"Passage {index + 1}: \n") for index in range(len(hits)))
    available = max(RERANK_DOCUMENT_CHARACTER_LIMIT - len(header) - labels_length, 180)
    per_chunk = max(60, available // len(hits))
    passages = [
        f"Passage {index + 1}: {_query_excerpt(query, hit.chunk.content, per_chunk)}"
        for index, hit in enumerate(hits)
    ]
    return (header + "\n".join(passages))[:RERANK_DOCUMENT_CHARACTER_LIMIT]


def aggregate_document_candidates(
    hits: Iterable[SearchHit],
    query: str,
    document_limit: int,
    *,
    chunks_per_document: int = RERANK_CHUNKS_PER_DOCUMENT,
) -> list[DocumentCandidate]:
    """Group ranked chunks while retaining several passages for document reranking."""
    if document_limit <= 0 or chunks_per_document <= 0:
        return []

    groups: dict[str, list[SearchHit]] = {}
    seen_chunks: set[str] = set()
    for hit in hits:
        document_id = hit.chunk.document_id
        if document_id not in groups:
            if len(groups) == document_limit:
                continue
            groups[document_id] = []
        if hit.chunk.chunk_id in seen_chunks or len(groups[document_id]) == chunks_per_document:
            continue
        groups[document_id].append(hit)
        seen_chunks.add(hit.chunk.chunk_id)

    return [
        DocumentCandidate(
            hits=tuple(group),
            evidence_hit=_best_evidence_hit(query, group),
            reranker_text=_reranker_document_text(query, group),
        )
        for group in groups.values()
        if group
    ]


def select_distinct_documents(hits: Iterable[SearchHit], top_k: int) -> list[SearchHit]:
    """Keep the highest-scoring chunk for each document before limiting results."""
    selected: list[SearchHit] = []
    document_ids: set[str] = set()
    for hit in hits:
        if hit.chunk.document_id in document_ids:
            continue
        selected.append(hit)
        document_ids.add(hit.chunk.document_id)
        if len(selected) == top_k:
            break
    return selected


class InMemoryHybridStore:
    """P1 adapter preserving filter-before-score semantics used by OpenSearch later."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        dense_weight: float = 0.5,
        reranker: Reranker | None = None,
        *,
        tenant_id: str = "demo",
        query_rewrite_enabled: bool = False,
        rerank_strategy: str = "replace",
        reranker_weight: float = 0.5,
        rerank_rrf_k: int = 60,
    ) -> None:
        if not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be between 0 and 1")
        self._embeddings = embeddings
        self._dense_weight = dense_weight
        self._reranker = reranker
        self._tenant_id = tenant_id
        self._query_rewrite_enabled = query_rewrite_enabled
        self._rerank_strategy = rerank_strategy
        self._reranker_weight = reranker_weight
        self._rerank_rrf_k = rerank_rrf_k
        self._documents: dict[str, DocumentRecord] = {}
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, np.ndarray] = {}
        self._snapshots: dict[
            str,
            tuple[dict[str, DocumentRecord], dict[str, Chunk], dict[str, np.ndarray]],
        ] = {}
        self._active_version: str | None = None

    @property
    def active_version(self) -> str | None:
        return self._active_version

    def has_version(self, version: str) -> bool:
        return version in self._snapshots

    def commit(self, version: str) -> None:
        if version in self._snapshots:
            raise ValueError(f"index version already exists: {version}")
        self._snapshots[version] = (
            self._documents.copy(),
            self._chunks.copy(),
            self._vectors.copy(),
        )
        self._active_version = version

    def rollback(self, version: str) -> None:
        if version not in self._snapshots:
            raise ValueError(f"unknown index version: {version}")
        documents, chunks, vectors = self._snapshots[version]
        self._documents = documents.copy()
        self._chunks = chunks.copy()
        self._vectors = vectors.copy()
        self._active_version = version

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
        normalized_query = query.lower()
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
            if chunk.title.strip().lower() in normalized_query:
                score += 12.0
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
        candidate_document_ids: set[str] | None = None,
        tenant_id: str | None = None,
    ) -> list[SearchHit]:
        requested_tenant = self._tenant_id if tenant_id is None else tenant_id
        if requested_tenant != self._tenant_id:
            return []
        # Authorization is deliberately evaluated before any candidate is scored.
        candidates = [
            chunk
            for chunk in self._chunks.values()
            if self._authorized(chunk, roles)
            and (
                candidate_document_ids is None
                or chunk.document_id in candidate_document_ids
            )
        ]
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

        planned_queries = (query,) if exact else retrieval_queries(
            query,
            rewrite_enabled=self._query_rewrite_enabled,
        )
        lexical_by_query = [self._lexical_scores(item, candidates) for item in planned_queries]
        query_vectors = (
            []
            if exact
            else list(self._embeddings.embed_queries(list(planned_queries)))
        )
        hits: list[SearchHit] = []
        for chunk in candidates:
            lexical = lexical_by_query[0][chunk.chunk_id]
            dense = 0.0 if exact else max(
                float(np.dot(query_vectors[0], self._vectors[chunk.chunk_id])),
                0.0,
            )
            query_scores: list[float] = []
            for index, planned_query in enumerate(planned_queries):
                planned_lexical = lexical_by_query[index][chunk.chunk_id]
                if exact:
                    query_scores.append(planned_lexical)
                    continue
                planned_dense = max(
                    float(np.dot(query_vectors[index], self._vectors[chunk.chunk_id])),
                    0.0,
                )
                query_scores.append(
                    ((1 - self._dense_weight) * planned_lexical)
                    + (self._dense_weight * planned_dense)
                    + retrieval_feature_boost(planned_query, chunk)
                )
            score = max(query_scores, default=0.0)
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
            rerank_candidates = aggregate_document_candidates(
                ranked,
                query,
                max(top_k * 4, 20),
            )
            rerank_scores = self._reranker.score(
                query,
                [candidate.reranker_text for candidate in rerank_candidates],
            )
            ranked_candidates = rank_document_candidates(
                rerank_candidates,
                rerank_scores,
                strategy=self._rerank_strategy,
                reranker_weight=self._reranker_weight,
                rrf_k=self._rerank_rrf_k,
            )
            ranked = [candidate.evidence_hit for candidate in ranked_candidates]
        return select_distinct_documents(ranked, top_k)

    def documents(self) -> Iterable[DocumentRecord]:
        return self._documents.values()

    def document_ids(self) -> set[str]:
        return set(self._documents)

    def chunk_count(self) -> int:
        return len(self._chunks)

    def authorized_document_ids(self, roles: frozenset[str]) -> set[str]:
        return {
            document.document_id
            for document in self._documents.values()
            if document.status == DocumentStatus.ACTIVE and bool(document.allowed_roles & roles)
        }

    def title_matched_document_ids(self, query: str, roles: frozenset[str]) -> list[str]:
        normalized_query = " ".join(query.lower().split())
        matches = [
            document
            for document in self.authorized_documents(roles)
            if " ".join(document.title.lower().split()) in normalized_query
        ]
        return [
            document.document_id
            for document in sorted(matches, key=lambda item: len(item.title), reverse=True)
        ]

    def authorized_documents(self, roles: frozenset[str]) -> list[DocumentRecord]:
        return [
            document
            for document in self._documents.values()
            if document.status == DocumentStatus.ACTIVE and bool(document.allowed_roles & roles)
        ]
