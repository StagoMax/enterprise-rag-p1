from collections.abc import Sequence

import numpy as np

from enterprise_rag.chunking import build_document
from enterprise_rag.models import Chunk, DocumentInput, DocumentStatus, SearchHit
from enterprise_rag.retrieval import (
    InMemoryHybridStore,
    aggregate_document_candidates,
    explicit_features,
    feature_search_text,
    focused_retrieval_query,
    rank_document_candidates,
    retrieval_feature_boost,
    retrieval_queries,
)
from enterprise_rag.vector_store import MilvusHybridStore


class ZeroEmbeddingProvider:
    dimensions = 8

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return np.zeros((len(texts), self.dimensions), dtype=np.float32)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return np.zeros((len(texts), self.dimensions), dtype=np.float32)


class RecordingReranker:
    def __init__(self) -> None:
        self.documents: list[str] = []

    def score(self, query: str, documents: Sequence[str]) -> np.ndarray:
        self.documents = list(documents)
        return np.asarray(
            [1.0 if "import the signer certificate" in item.lower() else 0.0 for item in documents],
            dtype=np.float32,
        )


def make_chunk(
    document_id: str,
    position: int,
    content: str,
    *,
    title: str | None = None,
    roles: frozenset[str] = frozenset({"engineering"}),
) -> Chunk:
    return Chunk(
        chunk_id=f"{document_id}:1.0:{position}",
        document_id=document_id,
        title=title or document_id,
        content=content,
        position=position,
        anchor=f"section:{position + 1}",
        allowed_roles=roles,
        version="1.0",
        status=DocumentStatus.ACTIVE,
        business_class="technical-guide",
    )


def make_hit(chunk: Chunk, score: float) -> SearchHit:
    return SearchHit(
        chunk=chunk,
        score=score,
        lexical_score=score,
        dense_score=score,
    )


def make_document(document_id: str, title: str, content: str):
    return build_document(
        DocumentInput(
            document_id=document_id,
            title=title,
            content=content,
            owner="test",
            business_class="technical-guide",
            allowed_roles={"engineering"},
        )
    )


def test_explicit_features_cover_product_component_error_and_version():
    features = explicit_features(
        "DataPower jms reports mqrc_not_authorized on version 10.5.0"
    )

    assert features.products == {"datapower"}
    assert features.components == {"jms"}
    assert features.identifiers == {"mqrc_not_authorized"}
    assert features.versions == {"10.5.0"}


def test_focused_query_keeps_headline_and_exact_constraints():
    query = (
        "Why does MQ fail with 2035 MQRC_NOT_AUTHORIZED after BPM migration?\n\n"
        "We moved from version 8.0 to 8.5.7 and the following long stack trace repeats."
    )

    focused = focused_retrieval_query(query)

    assert focused.startswith("Why does MQ fail")
    assert "mqrc_not_authorized" in focused.lower()
    assert "8.5.7" in focused
    assert "long stack trace" not in focused
    assert retrieval_queries(query, rewrite_enabled=True) == (query, focused)


def test_feature_search_text_normalizes_error_codes_versions_and_document_ids():
    text = feature_search_text(
        "IBM MQ 2035 MQRC_NOT_AUTHORIZED on version 8.5.7",
        document_id="swg21636093",
    )

    assert "identifier_mq_2035" in text
    assert "identifier_mqrc_not_authorized" in text
    assert "version_8_5_7" in text
    assert "document_swg21636093" in text


def test_rerank_strategies_support_pure_and_weighted_rrf_comparison():
    candidates = aggregate_document_candidates(
        [
            make_hit(make_chunk("a", 0, "A"), 0.9),
            make_hit(make_chunk("b", 0, "B"), 0.8),
            make_hit(make_chunk("c", 0, "C"), 0.7),
        ],
        "question",
        document_limit=3,
    )
    reranker_scores = [2.0, 1.0, 3.0]

    replaced = rank_document_candidates(
        candidates,
        reranker_scores,
        strategy="replace",
        reranker_weight=0.5,
        rrf_k=60,
    )
    fused = rank_document_candidates(
        candidates,
        reranker_scores,
        strategy="weighted_rrf",
        reranker_weight=0.5,
        rrf_k=60,
    )

    assert [item.evidence_hit.chunk.document_id for item in replaced] == ["c", "a", "b"]
    assert [item.evidence_hit.chunk.document_id for item in fused] == ["a", "c", "b"]


def test_document_aggregation_includes_non_top_evidence_and_selects_it():
    query = "How do I rotate the DataPower TLS certificate and import the signer certificate?"
    overview = make_chunk(
        "correct",
        0,
        "DataPower appliance architecture and certificate concepts.",
        title="DataPower TLS certificate rotation",
    )
    answer = make_chunk(
        "correct",
        1,
        "Rotate the DataPower TLS certificate, then import the signer certificate into the store.",
        title="DataPower TLS certificate rotation",
    )
    distractor = make_chunk(
        "distractor",
        0,
        "General TLS background for another product.",
        title="TLS background",
    )

    candidates = aggregate_document_candidates(
        [make_hit(overview, 0.99), make_hit(distractor, 0.9), make_hit(answer, 0.8)],
        query,
        document_limit=2,
    )

    assert len(candidates) == 2
    assert [hit.chunk.position for hit in candidates[0].hits] == [0, 1]
    assert "Passage 1:" in candidates[0].reranker_text
    assert "Passage 2:" in candidates[0].reranker_text
    assert "import the signer certificate" in candidates[0].reranker_text
    assert candidates[0].evidence_hit.chunk.position == 1


def test_document_aggregation_prefers_deduplicated_parent_context_for_reranking():
    parent = (
        "WebSphere resource limits background. The supported resolution is to set "
        "nproc to 131072 before restarting the application server."
    )
    first = make_chunk(
        "correct",
        0,
        "WebSphere resource limits background.",
        title="WebSphere Linux limits",
    ).model_copy(update={"parent_id": "correct:1.0:parent:0", "parent_content": parent})
    second = make_chunk(
        "correct",
        1,
        "Additional operating system notes.",
        title="WebSphere Linux limits",
    ).model_copy(update={"parent_id": "correct:1.0:parent:0", "parent_content": parent})

    candidate = aggregate_document_candidates(
        [make_hit(first, 0.9), make_hit(second, 0.8)],
        "What nproc value should WebSphere use?",
        document_limit=1,
    )[0]

    assert "nproc to 131072" in candidate.reranker_text
    assert candidate.reranker_text.count("Passage ") == 1


def test_in_memory_reranker_uses_document_context_and_returns_answer_chunk():
    reranker = RecordingReranker()
    store = InMemoryHybridStore(
        ZeroEmbeddingProvider(),
        dense_weight=1.0,
        reranker=reranker,
    )
    correct = make_document(
        "correct",
        "DataPower TLS certificate rotation",
        "placeholder",
    )
    other = make_document("other", "Domino TLS certificate rotation", "placeholder")
    store.upsert_documents(
        [
            (
                correct,
                [
                    make_chunk(
                        "correct",
                        0,
                        "DataPower appliance architecture and certificate concepts.",
                        title=correct.title,
                    ),
                    make_chunk(
                        "correct",
                        1,
                        "Rotate the DataPower TLS certificate and import the signer certificate.",
                        title=correct.title,
                    ),
                ],
            ),
            (
                other,
                [
                    make_chunk(
                        "other",
                        0,
                        "Domino certificate rotation guidance.",
                        title=other.title,
                    )
                ],
            ),
        ]
    )

    hits = store.search(
        "How do I rotate the DataPower TLS certificate and import the signer certificate?",
        frozenset({"engineering"}),
        top_k=1,
    )

    assert len(reranker.documents) == 2
    assert any("Passage 2:" in document for document in reranker.documents)
    assert hits[0].chunk.document_id == "correct"
    assert hits[0].chunk.position == 1


def test_product_feature_boost_reorders_without_hard_filtering():
    query = "How do I configure SHA-2 certificates in DataPower?"
    datapower = make_chunk(
        "datapower-doc",
        0,
        "SHA-2 certificate configuration steps.",
        title="DataPower certificate configuration",
    )
    domino = make_chunk(
        "domino-doc",
        0,
        "SHA-2 certificate configuration steps.",
        title="Domino certificate configuration",
    )
    assert retrieval_feature_boost(query, datapower) > retrieval_feature_boost(query, domino)

    store = InMemoryHybridStore(ZeroEmbeddingProvider(), dense_weight=1.0)
    store.upsert_documents(
        [
            (
                make_document("datapower-doc", datapower.title, datapower.content),
                [datapower],
            ),
            (
                make_document("domino-doc", domino.title, domino.content),
                [domino],
            ),
        ]
    )
    hits = store.search(query, frozenset({"engineering"}), top_k=2)

    assert [hit.chunk.document_id for hit in hits] == ["datapower-doc", "domino-doc"]


def test_expanded_error_identifiers_preserve_exact_search():
    store = InMemoryHybridStore(ZeroEmbeddingProvider(), dense_weight=1.0)
    matching = make_chunk(
        "mq-2035",
        0,
        "IBM MQ 2035 authorization failure guidance.",
        title="MQ authorization failure",
    )
    unrelated = make_chunk(
        "mq-other",
        0,
        "IBM MQ connection guidance.",
        title="MQ connection",
    )
    store.upsert_documents(
        [
            (
                make_document("mq-2035", matching.title, matching.content),
                [matching],
            ),
            (
                make_document("mq-other", unrelated.title, unrelated.content),
                [unrelated],
            ),
        ]
    )

    hits = store.search(
        "MQ 2035",
        frozenset({"engineering"}),
        top_k=2,
        exact=True,
    )

    assert [hit.chunk.document_id for hit in hits] == ["mq-2035"]


def test_milvus_rescore_uses_the_same_product_feature_boost():
    store = object.__new__(MilvusHybridStore)
    store._dense_weight = 1.0
    datapower = make_chunk(
        "datapower-doc",
        0,
        "SHA-2 certificate configuration steps.",
        title="DataPower certificate configuration",
    )
    domino = make_chunk(
        "domino-doc",
        0,
        "SHA-2 certificate configuration steps.",
        title="Domino certificate configuration",
    )

    def entity(chunk: Chunk) -> dict[str, object]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "title": chunk.title,
            "content": chunk.content,
            "position": chunk.position,
            "anchor": chunk.anchor,
            "allowed_roles": list(chunk.allowed_roles),
            "version": chunk.version,
            "status": chunk.status.value,
            "business_class": chunk.business_class,
        }

    hits = store._rescore(
        "How do I configure SHA-2 certificates in DataPower?",
        {
            datapower.chunk_id: entity(datapower),
            domino.chunk_id: entity(domino),
        },
        {datapower.chunk_id: 0.0, domino.chunk_id: 0.0},
        exact=False,
    )

    assert [hit.chunk.document_id for hit in hits] == ["datapower-doc", "domino-doc"]
