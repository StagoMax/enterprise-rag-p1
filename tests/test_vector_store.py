import sys

import pytest

from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.embeddings import HashingEmbeddingProvider
from enterprise_rag.models import Chunk, DocumentInput, DocumentStatus, SearchHit
from enterprise_rag.retrieval import feature_search_text, select_distinct_documents
from enterprise_rag.vector_store import (
    _RecallBranch,
    build_acl_expression,
    encode_role_keys,
    encode_roles,
    is_embedded_uri,
    validate_document_id,
    validate_role,
)

pymilvus = pytest.importorskip("pymilvus")

from enterprise_rag.vector_store import MilvusHybridStore  # noqa: E402


def test_document_selection_keeps_highest_scoring_chunk_per_document():
    from enterprise_rag.models import Chunk, SearchHit

    def hit(document_id: str, position: int, score: float) -> SearchHit:
        return SearchHit(
            chunk=Chunk(
                chunk_id=f"{document_id}:1.0:{position}",
                document_id=document_id,
                title=document_id,
                content="content",
                position=position,
                anchor=f"chunk-{position}",
                allowed_roles=frozenset({"engineering"}),
                version="1.0",
                status=DocumentStatus.ACTIVE,
                business_class="test",
            ),
            score=score,
            lexical_score=score,
            dense_score=score,
        )

    selected = select_distinct_documents(
        [
            hit("document-a", 0, 0.99),
            hit("document-a", 1, 0.98),
            hit("document-b", 0, 0.8),
        ],
        top_k=2,
    )

    assert [item.chunk.document_id for item in selected] == ["document-a", "document-b"]


def test_adaptive_recall_expands_until_it_has_requested_distinct_documents():
    def hit(document_id: str, position: int) -> SearchHit:
        chunk = Chunk(
            chunk_id=f"{document_id}:1.0:{position}",
            document_id=document_id,
            title=document_id,
            content="content",
            position=position,
            anchor=f"section:{position}",
            allowed_roles=frozenset({"engineering"}),
            version="1.0",
            status=DocumentStatus.ACTIVE,
            business_class="test",
        )
        return SearchHit(chunk=chunk, score=1.0, lexical_score=1.0, dense_score=1.0)

    store = object.__new__(MilvusHybridStore)
    store._active_version = "v1"
    store._tenant_id = "demo"
    store._reranker = None
    store._search_multiplier = 1
    store._adaptive_recall_enabled = True
    store._adaptive_recall_max_chunks = 80
    store._rerank_candidates = 20
    store._field_names = lambda collection_name: set()
    store._alias = "chunks"
    store._recall_branches = lambda query: []
    store._hydrate_parent_content = lambda hits: hits
    limits: list[int] = []

    def hybrid_hits(query, expression, limit, roles, tenant_id, *, branches=None):
        limits.append(limit)
        if limit == 20:
            return [hit("same-document", position) for position in range(20)]
        return [hit(f"document-{index}", 0) for index in range(20)]

    store._hybrid_hits = hybrid_hits
    hits = store.search(
        "query",
        frozenset({"engineering"}),
        top_k=20,
        min_score=0.0,
    )

    assert limits == [20, 40]
    assert len(hits) == 20
    assert len({item.chunk.document_id for item in hits}) == 20


def test_reranker_uses_same_chunk_budget_as_direct_top20_retrieval():
    def hit(index: int) -> SearchHit:
        chunk = Chunk(
            chunk_id=f"document-{index}:1.0:0",
            document_id=f"document-{index}",
            title=f"document-{index}",
            content="content",
            position=0,
            anchor="section:0",
            allowed_roles=frozenset({"engineering"}),
            version="1.0",
            status=DocumentStatus.ACTIVE,
            business_class="test",
        )
        return SearchHit(chunk=chunk, score=1.0, lexical_score=1.0, dense_score=1.0)

    class Reranker:
        def __init__(self) -> None:
            self.document_count = 0

        def score(self, query, documents):
            self.document_count = len(documents)
            return [float(len(documents) - index) for index in range(len(documents))]

    reranker = Reranker()
    store = object.__new__(MilvusHybridStore)
    store._active_version = "v1"
    store._tenant_id = "demo"
    store._reranker = reranker
    store._search_multiplier = 30
    store._adaptive_recall_enabled = True
    store._adaptive_recall_max_chunks = 4096
    store._rerank_candidates = 20
    store._rerank_strategy = "replace"
    store._reranker_weight = 0.5
    store._rerank_rrf_k = 60
    store._field_names = lambda collection_name: set()
    store._alias = "chunks"
    store._recall_branches = lambda query: []
    store._hydrate_parent_content = lambda hits: hits
    limits: list[int] = []

    def hybrid_hits(query, expression, limit, roles, tenant_id, *, branches=None):
        limits.append(limit)
        return [hit(index) for index in range(20)]

    store._hybrid_hits = hybrid_hits
    results = store.search(
        "query",
        frozenset({"engineering"}),
        top_k=3,
        min_score=0.0,
    )

    assert limits == [600]
    assert reranker.document_count == 20
    assert len(results) == 3


def test_candidate_restricted_reranking_caps_adaptive_target_to_allow_list():
    def hit(index: int) -> SearchHit:
        document_id = f"document-{index}"
        chunk = Chunk(
            chunk_id=f"{document_id}:1.0:0",
            document_id=document_id,
            title=document_id,
            content="content",
            position=0,
            anchor="section:0",
            allowed_roles=frozenset({"engineering"}),
            version="1.0",
            status=DocumentStatus.ACTIVE,
            business_class="test",
        )
        return SearchHit(chunk=chunk, score=1.0, lexical_score=1.0, dense_score=1.0)

    class Reranker:
        def __init__(self) -> None:
            self.document_count = 0

        def score(self, query, documents):
            self.document_count = len(documents)
            return [float(len(documents) - index) for index in range(len(documents))]

    reranker = Reranker()
    store = object.__new__(MilvusHybridStore)
    store._active_version = "v1"
    store._tenant_id = "demo"
    store._reranker = reranker
    store._search_multiplier = 30
    store._adaptive_recall_enabled = True
    store._adaptive_recall_max_chunks = 4096
    store._rerank_candidates = 20
    store._rerank_strategy = "replace"
    store._reranker_weight = 0.5
    store._rerank_rrf_k = 60
    store._field_names = lambda collection_name: set()
    store._alias = "chunks"
    store._recall_branches = lambda query: []
    store._hydrate_parent_content = lambda hits: hits
    limits: list[int] = []

    def hybrid_hits(query, expression, limit, roles, tenant_id, *, branches=None):
        limits.append(limit)
        return [hit(index) for index in range(12)]

    store._hybrid_hits = hybrid_hits
    results = store.search(
        "query",
        frozenset({"engineering"}),
        top_k=48,
        min_score=0.0,
        candidate_document_ids={f"document-{index}" for index in range(12)},
    )

    assert limits == [360]
    assert reranker.document_count == 12
    assert len(results) == 12


def test_parent_hydration_fetches_one_representative_per_parent():
    parent_id = "doc:1.0:parent:0"
    first = Chunk(
        chunk_id="doc:1.0:0",
        document_id="doc",
        title="Document",
        content="first child",
        position=0,
        anchor="section:1",
        allowed_roles=frozenset({"engineering"}),
        version="1.0",
        status=DocumentStatus.ACTIVE,
        business_class="test",
        parent_id=parent_id,
    )
    second = first.model_copy(
        update={"chunk_id": "doc:1.0:1", "content": "second child", "position": 1}
    )

    class ParentClient:
        def __init__(self) -> None:
            self.ids: list[str] = []

        def get(self, collection_name, *, ids, output_fields):
            self.ids = list(ids)
            assert collection_name == "chunks"
            assert output_fields == ["chunk_id", "parent_id", "parent_content"]
            return [
                {
                    "chunk_id": ids[0],
                    "parent_id": parent_id,
                    "parent_content": "complete parent resolution",
                }
            ]

    client = ParentClient()
    store = object.__new__(MilvusHybridStore)
    store._alias = "chunks"
    store._client = client
    store._field_names = lambda collection_name: {"parent_id", "parent_content"}

    hydrated = store._hydrate_parent_content(
        [
            SearchHit(chunk=first, score=0.9, lexical_score=0.9, dense_score=0.9),
            SearchHit(chunk=second, score=0.8, lexical_score=0.8, dense_score=0.8),
        ]
    )

    assert client.ids == ["doc:1.0:0"]
    assert all(hit.chunk.parent_content == "complete parent resolution" for hit in hydrated)


def make_documents() -> list[DocumentInput]:
    documents = []
    # 让受限文档在词法上更强：标题和正文都塞满查询词，逼出越权泄漏。
    for index in range(12):
        documents.append(
            DocumentInput(
                document_id=f"restricted-{index}",
                title="VPN certificate topology restricted detail",
                content=(
                    "vpn certificate error VPN-401 topology restricted secret "
                    "vpn certificate topology " * 4
                ),
                owner="security",
                business_class="restricted-design",
                sensitivity="restricted",
                allowed_roles={"restricted"},
            )
        )
    for index in range(8):
        documents.append(
            DocumentInput(
                document_id=f"eng-{index}",
                title=f"Engineering runbook {index}",
                content="device certificate enrollment guidance for engineering staff",
                owner="it-platform",
                business_class="technical-guide",
                allowed_roles={"engineering"},
            )
        )
    return documents


@pytest.fixture
def store(tmp_path):
    embeddings = HashingEmbeddingProvider(dimensions=64)
    store = MilvusHybridStore(
        embeddings,
        uri=str(tmp_path / "milvus" / "test.db"),
        collection="test_chunks",
        dense_weight=0.5,
    )
    items = []
    for document_input in make_documents():
        document = build_document(document_input)
        items.append((document, chunk_document(document)))
    store.upsert_documents(items)
    store.commit("v1")
    return store


def test_role_validation_rejects_expression_injection():
    with pytest.raises(ValueError):
        validate_role('engineering" or status == "active')
    assert validate_role("engineering") == "engineering"


def test_empty_roles_deny_all_instead_of_allowing_all():
    assert build_acl_expression(frozenset()) == "false"


def test_acl_expression_includes_status_and_roles():
    expression = build_acl_expression(frozenset({"engineering"}), tenant_id="demo")
    assert 'status == "active"' in expression
    # 走 VARCHAR LIKE 而不是 array_contains_any：后者在 147k 分块下要 37.7s。
    assert 'roles_text like "%|engineering|%"' in expression
    assert "array_contains_any" not in expression
    assert 'tenant_id == "demo"' in expression


def test_acl_expression_ors_multiple_roles():
    expression = build_acl_expression(frozenset({"engineering", "operations"}))
    assert 'roles_text like "%|engineering|%"' in expression
    assert 'roles_text like "%|operations|%"' in expression
    assert " or " in expression


def test_role_encoding_prevents_prefix_collisions():
    encoded = encode_roles({"engineering", "ops"})
    assert encoded == "|engineering|ops|"
    # 分隔符保证 "eng" 不会命中 "engineering"
    assert "|eng|" not in encoded
    assert "|engineering|" in encoded


def test_encoded_role_keys_remove_like_wildcards():
    encoded = encode_role_keys({"restr_cted", "engineering"})
    expression = build_acl_expression(
        frozenset({"restr_cted"}),
        tenant_id="demo",
        encoded_roles=True,
    )

    assert "_" not in encoded
    assert 'roles_key like "%|72657374725f63746564|%"' in expression
    assert "roles_text" not in expression


def test_document_id_validation_rejects_filter_injection():
    assert validate_document_id("swg21636093:1.0") == "swg21636093:1.0"
    with pytest.raises(ValueError):
        validate_document_id('eng-1"] or status == "active')


def test_embedded_backend_does_not_index_sparse_field(tmp_path):
    """回归：milvus-lite 给 BM25 稀疏字段建索引会在规模上来后让 load_collection 直接失败。

    嵌入式部署必须默认不建该索引；独立部署没有这个限制。
    """
    embedded = MilvusHybridStore(
        HashingEmbeddingProvider(dimensions=32),
        uri=str(tmp_path / "m" / "embedded.db"),
        collection="c1",
    )
    assert embedded._index_sparse is False
    # 独立部署走另一套引擎，应当仍然给稀疏字段建索引。
    assert not is_embedded_uri("http://localhost:19530")


def test_bm25_still_ranks_without_sparse_index(store):
    """不建稀疏索引后 BM25 仍必须真的参与排序，否则混合检索就退化成纯向量了。"""
    hits = store.search(
        "device certificate enrollment guidance",
        frozenset({"engineering"}),
        top_k=5,
    )
    assert hits
    assert any(hit.lexical_score > 0 for hit in hits), "BM25 分支没有产生任何词法得分"


def test_embedded_uri_detection():
    assert is_embedded_uri("data/milvus/x.db")
    assert not is_embedded_uri("http://localhost:19530")
    assert not is_embedded_uri("grpc://milvus:19530")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only milvus-lite patch")
def test_windows_rename_patch_is_applied():
    import os

    from enterprise_rag.vector_store import apply_milvus_lite_windows_patch

    apply_milvus_lite_windows_patch()
    import milvus_lite.storage.manifest as manifest

    assert manifest.os.rename is os.replace


def test_hybrid_search_never_leaks_unauthorized_chunks(store):
    """回归用例：hybrid_search 顶层 filter 曾静默失效，导致 6 条里泄漏 5 条越权文档。"""
    hits = store.search(
        "vpn certificate topology restricted",
        frozenset({"engineering"}),
        top_k=10,
    )
    assert hits, "授权角色应当仍能召回自己的文档"
    leaked = [hit for hit in hits if "engineering" not in hit.chunk.allowed_roles]
    assert leaked == [], f"越权泄漏：{[hit.chunk.document_id for hit in leaked]}"


def test_fielded_schema_and_native_hybrid_enforce_acl(store, tmp_path):
    assert {
        "title_text",
        "feature_text",
        "title_sparse",
        "feature_sparse",
    } <= store._field_names(store._alias)

    native = MilvusHybridStore(
        HashingEmbeddingProvider(dimensions=64),
        uri=str(tmp_path / "milvus" / "test.db"),
        collection="test_chunks",
        dense_weight=0.5,
        query_rewrite_enabled=True,
        fielded_search_enabled=True,
        search_mode="native_rrf",
    )
    native.rollback("v1")
    hits = native.search(
        "vpn certificate topology restricted",
        frozenset({"engineering"}),
        top_k=10,
    )

    assert hits
    assert all("engineering" in hit.chunk.allowed_roles for hit in hits)


def test_native_hybrid_places_acl_filter_on_every_request():
    store = object.__new__(MilvusHybridStore)
    store._hybrid_rrf_k = 60
    captured = {}

    class Client:
        def hybrid_search(self, collection, requests, **kwargs):
            captured["collection"] = collection
            captured["requests"] = requests
            captured["kwargs"] = kwargs
            return [[]]

    store._client = Client()
    store._alias = "chunks"
    expression = build_acl_expression(frozenset({"engineering"}), tenant_id="demo")
    rows = store._native_hybrid_hits(
        "query",
        [
            _RecallBranch([0.0, 1.0], "dense", "IP", 1.0),
            _RecallBranch("query", "sparse", "BM25", 1.0),
        ],
        expression,
        5,
        frozenset({"engineering"}),
        "demo",
    )

    assert rows == []
    assert [request.expr for request in captured["requests"]] == [expression, expression]
    assert "filter" not in captured["kwargs"]
    assert captured["kwargs"]["limit"] == 10


def test_native_hybrid_caps_milvus_result_window():
    store = object.__new__(MilvusHybridStore)
    store._hybrid_rrf_k = 60
    captured = {}

    class Client:
        def hybrid_search(self, collection, requests, **kwargs):
            captured["limit"] = kwargs["limit"]
            return [[]]

    store._client = Client()
    store._alias = "chunks"
    store._native_hybrid_hits(
        "query",
        [
            _RecallBranch([0.0, 1.0], "dense", "IP", 1.0),
            _RecallBranch("query", "sparse", "BM25", 1.0),
        ],
        build_acl_expression(frozenset({"engineering"}), tenant_id="demo"),
        10_000,
        frozenset({"engineering"}),
        "demo",
    )

    assert captured["limit"] == 16_384


def test_tenant_is_enforced_at_request_and_result_boundaries(store):
    assert store.search(
        "vpn",
        frozenset({"engineering"}),
        tenant_id="other-tenant",
    ) == []
    assert store.search("vpn", frozenset({"engineering"}), tenant_id="") == []
    row = {
        "entity": {
            "status": "active",
            "allowed_roles": ["engineering"],
            "tenant_id": "other-tenant",
        }
    }
    assert store._guard([row], frozenset({"engineering"}), "demo") == []


def test_title_and_feature_sparse_fields_are_searchable(store):
    expression = build_acl_expression(frozenset({"engineering"}), tenant_id="demo")
    title_rows = store._branch(
        "engineering runbook",
        "title_sparse",
        "BM25",
        expression,
        20,
        frozenset({"engineering"}),
        "demo",
    )
    restricted_expression = build_acl_expression(
        frozenset({"restricted"}), tenant_id="demo"
    )
    feature_rows = store._branch(
        feature_search_text("VPN-401"),
        "feature_sparse",
        "BM25",
        restricted_expression,
        20,
        frozenset({"restricted"}),
        "demo",
    )

    assert title_rows
    assert feature_rows
    assert all(row["entity"]["document_id"].startswith("restricted-") for row in feature_rows)


def test_exact_search_also_enforces_acl(store):
    hits = store.search(
        "VPN-401 certificate",
        frozenset({"engineering"}),
        top_k=10,
        exact=True,
    )
    assert all("engineering" in hit.chunk.allowed_roles for hit in hits)


def test_restricted_role_sees_only_restricted(store):
    hits = store.search("vpn certificate topology", frozenset({"restricted"}), top_k=10)
    assert hits
    assert all("restricted" in hit.chunk.allowed_roles for hit in hits)


def test_role_underscore_is_not_treated_as_like_wildcard(store):
    assert store.search(
        "vpn certificate topology",
        frozenset({"restr_cted"}),
        top_k=10,
    ) == []


def test_unknown_role_gets_nothing(store):
    assert store.search("vpn certificate", frozenset({"finance"}), top_k=5) == []


def test_candidate_restriction_scopes_results(store):
    hits = store.search(
        "certificate enrollment",
        frozenset({"engineering"}),
        top_k=5,
        candidate_document_ids={"eng-1"},
    )
    assert {hit.chunk.document_id for hit in hits} == {"eng-1"}


def test_empty_candidate_set_returns_nothing(store):
    hits = store.search(
        "certificate",
        frozenset({"engineering"}),
        top_k=5,
        candidate_document_ids=set(),
    )
    assert hits == []


@pytest.mark.parametrize("search_mode", ["separate", "native_rrf"])
def test_candidate_restriction_rejects_expression_injection(store, search_mode):
    store._search_mode = search_mode
    with pytest.raises(ValueError):
        store.search(
            "certificate",
            frozenset({"engineering"}),
            candidate_document_ids={'eng-1"] or status == "active'},
        )


@pytest.mark.parametrize(
    ("retrieval_method", "exact"),
    [("_hybrid_hits", False), ("_exact_hits", True)],
)
def test_candidate_restriction_is_rechecked_after_retrieval(
    store,
    monkeypatch,
    retrieval_method,
    exact,
):
    def hit(document_id: str) -> SearchHit:
        return SearchHit(
            chunk=Chunk(
                chunk_id=f"{document_id}:1.0:0",
                document_id=document_id,
                title=document_id,
                content="certificate enrollment",
                position=0,
                anchor="chunk-0",
                allowed_roles=frozenset({"engineering"}),
                version="1.0",
                status=DocumentStatus.ACTIVE,
                business_class="test",
            ),
            score=1.0,
            lexical_score=1.0,
            dense_score=1.0,
        )

    monkeypatch.setattr(
        store,
        retrieval_method,
        lambda *args, **kwargs: [hit("eng-2"), hit("eng-1")],
    )

    hits = store.search(
        "certificate",
        frozenset({"engineering"}),
        top_k=5,
        exact=exact,
        candidate_document_ids={"eng-1"},
    )

    assert [item.chunk.document_id for item in hits] == ["eng-1"]


def test_model_document_ids_reject_filter_metacharacters():
    with pytest.raises(ValueError):
        DocumentInput(
            document_id='eng-1"]',
            title="Unsafe",
            content="Unsafe identifier",
            owner="security",
            business_class="test",
            allowed_roles={"engineering"},
        )


def test_document_metadata_and_counts(store):
    assert store.active_version == "v1"
    assert store.chunk_count() > 0
    assert len(store.document_ids()) == 20
    assert store.authorized_document_ids(frozenset({"engineering"})) == {
        f"eng-{index}" for index in range(8)
    }


def test_publish_and_rollback_are_paired_and_persistent(store, tmp_path):
    new_document = build_document(
        DocumentInput(
            document_id="eng-new",
            title="Engineering rollback probe",
            content="rollback probe content for engineering",
            owner="it-platform",
            business_class="technical-guide",
            allowed_roles={"engineering"},
        )
    )
    store.upsert_documents([(new_document, chunk_document(new_document))])
    store.commit("v2")
    assert store.active_version == "v2"
    assert "eng-new" in store.document_ids()

    store.rollback("v1")
    assert store.active_version == "v1"
    assert "eng-new" not in store.document_ids()

    with pytest.raises(ValueError):
        store.rollback("v-missing")


def test_version_survives_process_restart(store, tmp_path):
    """新建 client 指向同一 URI，应当还能看到已发布版本——内存实现做不到这点。"""
    reopened = MilvusHybridStore(
        HashingEmbeddingProvider(dimensions=64),
        uri=str(tmp_path / "milvus" / "test.db"),
        collection="test_chunks",
    )
    assert reopened.has_version("v1")
    reopened.rollback("v1")
    hits = reopened.search("certificate enrollment", frozenset({"engineering"}), top_k=3)
    assert hits
    assert all("engineering" in hit.chunk.allowed_roles for hit in hits)
    assert all(hit.chunk.parent_id for hit in hits)
    assert all(hit.chunk.parent_content for hit in hits)
    assert all(hit.chunk.chunking_version == "structured-parent-child-v1" for hit in hits)


def test_unpublished_version_can_resume_before_alias_switch(tmp_path):
    store = MilvusHybridStore(
        HashingEmbeddingProvider(dimensions=64),
        uri=str(tmp_path / "milvus" / "resume.db"),
        collection="resume_chunks",
    )
    documents = [build_document(item) for item in make_documents()[-2:]]
    items = [(document, chunk_document(document)) for document in documents]

    store.begin_unpublished_version("v1")
    store.append_unpublished_documents("v1", items[:1])
    assert store.unpublished_document_ids("v1") == {documents[0].document_id}
    assert store.is_version_published("v1") is False
    with pytest.raises(ValueError, match="incomplete"):
        store.publish_unpublished_version(
            "v1",
            expected_document_ids={document.document_id for document in documents},
        )

    store.append_unpublished_documents("v1", items[1:])
    assert store.version_chunk_count("v1") == sum(len(chunks) for _, chunks in items)
    store.publish_unpublished_version(
        "v1",
        expected_document_ids={document.document_id for document in documents},
    )

    assert store.active_version == "v1"
    assert store.is_version_published("v1") is True
    assert store.document_ids() == {document.document_id for document in documents}
    with pytest.raises(ValueError, match="published"):
        store.append_unpublished_documents("v1", items[:1])


def test_expired_documents_are_not_retrievable(tmp_path):
    embeddings = HashingEmbeddingProvider(dimensions=64)
    store = MilvusHybridStore(
        embeddings,
        uri=str(tmp_path / "milvus" / "expired.db"),
        collection="expired_chunks",
    )
    document = build_document(
        DocumentInput(
            document_id="stale-doc",
            title="Expired engineering notice",
            content="expired certificate rotation notice",
            owner="it-platform",
            business_class="technical-guide",
            allowed_roles={"engineering"},
            status=DocumentStatus.EXPIRED,
        )
    )
    store.upsert_documents([(document, chunk_document(document))])
    store.commit("v1")
    assert store.search("certificate rotation", frozenset({"engineering"}), top_k=5) == []
