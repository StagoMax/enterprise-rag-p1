"""Milvus 向量存储适配器。

同一份代码覆盖两种部署形态，只由 URI 决定：
  - 本地文件路径（如 ``data/milvus/enterprise-rag.db``）-> 嵌入式 Milvus Lite
  - ``http(s)://`` 或 ``grpc`` 地址 -> Milvus Standalone / 集群

设计上把 ACL 放在检索算子内部，而不是检索之后再过滤，与 P1 的
filter-before-score 语义保持一致。
"""

import os
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from enterprise_rag.embeddings import EmbeddingProvider, Reranker
from enterprise_rag.models import (
    ROLE_PATTERN,
    Chunk,
    DocumentRecord,
    DocumentStatus,
    SearchHit,
)
from enterprise_rag.retrieval import (
    RERANK_CHUNKS_PER_DOCUMENT,
    InMemoryHybridStore,
    _identifiers,
    aggregate_document_candidates,
    feature_search_text,
    rank_document_candidates,
    retrieval_feature_boost,
    retrieval_queries,
    select_distinct_documents,
)

_ROLE_TOKEN = re.compile(ROLE_PATTERN)
_DOCUMENT_ID_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

# (已处理文档数, 文档总数, 已写入分块数)
ProgressCallback = Callable[[int, int, int], None]


@dataclass(frozen=True, slots=True)
class _RecallBranch:
    data: Any
    anns_field: str
    metric_type: str
    weight: float


def apply_milvus_lite_windows_patch() -> bool:
    """milvus-lite 3.1.0 用 os.rename 做原子替换，Windows 下目标已存在会抛 WinError 183。

    os.replace 在所有平台都是原子覆盖，因此只在 Windows 上把它替换掉。
    返回是否实际打了补丁，便于测试断言和启动日志。
    """
    if sys.platform != "win32":
        return False
    patched = False
    for module_name in (
        "milvus_lite.storage.manifest",
        "milvus_lite.schema.persistence",
        "milvus_lite.db",
    ):
        try:
            __import__(module_name)
        except ImportError:
            continue
        module = sys.modules[module_name]
        if getattr(module.os, "rename", None) is not os.replace:
            module.os.rename = os.replace  # type: ignore[attr-defined]
            patched = True
    return patched


def is_embedded_uri(uri: str) -> bool:
    return not uri.startswith(("http://", "https://", "grpc://", "unix:", "tcp://"))


def validate_role(role: str) -> str:
    """角色会拼进 Milvus 过滤表达式，必须先做白名单校验以杜绝表达式注入。"""
    if not _ROLE_TOKEN.fullmatch(role):
        raise ValueError(f"角色名含有不允许的字符，无法安全构造过滤表达式：{role!r}")
    return role


def validate_document_id(document_id: str) -> str:
    """Validate IDs before interpolating them into a Milvus filter expression."""
    if not _DOCUMENT_ID_TOKEN.fullmatch(document_id):
        raise ValueError(
            "document ID contains characters that cannot be used safely in a filter: "
            f"{document_id!r}"
        )
    return document_id


def encode_roles(roles: Iterable[str]) -> str:
    """把角色集合编码成带分隔符的字符串，例如 ``|engineering|operations|``。

    两端和中间都带 ``|``，因此 LIKE 匹配 ``%|eng|%`` 不会误命中 ``engineering``。
    """
    return "|" + "|".join(sorted(validate_role(role) for role in roles)) + "|" if roles else "||"


def encode_role_keys(roles: Iterable[str]) -> str:
    """Encode role names so LIKE cannot interpret underscores as wildcards."""
    keys = [validate_role(role).encode("utf-8").hex() for role in sorted(roles)]
    return "|" + "|".join(keys) + "|" if keys else "||"


def build_acl_expression(
    roles: frozenset[str],
    *,
    tenant_id: str | None = None,
    encoded_roles: bool = False,
) -> str:
    """构造 ACL 过滤表达式：仅 active 状态、且角色有交集、且租户匹配。

    角色匹配刻意用 VARCHAR 的 LIKE 而不是 ARRAY 的 array_contains_any：
    实测 147,358 分块下 array_contains_any 需要 37.7s，而 LIKE 只要 0.15s
    （ARRAY 字段在 Milvus 里不支持标量索引，只能逐行扫描）。
    allowed_roles 数组仍然保留，只用于把角色随结果返回。
    """
    if not roles:
        # 空角色不得退化为"无过滤"，否则等于全量放行。
        return "false"
    role_field = "roles_key" if encoded_roles else "roles_text"
    role_tokens = (
        [validate_role(role).encode("utf-8").hex() for role in sorted(roles)]
        if encoded_roles
        else [validate_role(role) for role in sorted(roles)]
    )
    role_clause = " or ".join(
        f'{role_field} like "%|{token}|%"' for token in role_tokens
    )
    clauses = [
        f'status == "{DocumentStatus.ACTIVE.value}"',
        f"({role_clause})",
    ]
    if tenant_id:
        clauses.append(f'tenant_id == "{validate_role(tenant_id)}"')
    return " and ".join(clauses)


class HybridStore(Protocol):
    """service.py 依赖的存储契约；内存实现和 Milvus 实现都满足它。"""

    @property
    def active_version(self) -> str | None: ...

    def has_version(self, version: str) -> bool: ...

    def commit(self, version: str) -> None: ...

    def rollback(self, version: str) -> None: ...

    def upsert_documents(self, items: list[tuple[DocumentRecord, list[Chunk]]]) -> None: ...

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
    ) -> list[SearchHit]: ...

    def documents(self) -> Iterable[DocumentRecord]: ...

    def document_ids(self) -> set[str]: ...

    def chunk_count(self) -> int: ...

    def authorized_document_ids(self, roles: frozenset[str]) -> set[str]: ...

    def authorized_documents(self, roles: frozenset[str]) -> list[DocumentRecord]: ...

    def title_matched_document_ids(self, query: str, roles: frozenset[str]) -> list[str]: ...


class MilvusHybridStore:
    """Milvus 混合检索存储：稠密向量 + 原生 BM25 稀疏向量，ACL 下沉到检索算子。

    版本发布用"每版本一个 collection + alias 切换"实现，因此原子发布和回滚
    都由 Milvus 保证，进程重启后依然有效。
    """

    _FIELDED_FIELDS = frozenset(
        {"title_text", "feature_text", "title_sparse", "feature_sparse", "roles_key"}
    )
    _STRUCTURED_CHUNK_FIELDS = frozenset(
        {
            "parent_id",
            "parent_content",
            "section_title",
            "chunking_version",
            "token_count",
        }
    )

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        *,
        uri: str = "data/milvus/enterprise-rag.db",
        token: str = "",
        collection: str = "enterprise_chunks",
        dense_weight: float = 0.5,
        reranker: Reranker | None = None,
        search_multiplier: int = 4,
        tenant_id: str = "demo",
        batch_documents: int = 200,
        batch_rows: int = 500,
        index_sparse: bool | None = None,
        query_rewrite_enabled: bool = False,
        fielded_search_enabled: bool = False,
        search_mode: str = "separate",
        hybrid_rrf_k: int = 60,
        rerank_strategy: str = "replace",
        reranker_weight: float = 0.5,
        rerank_rrf_k: int = 60,
        adaptive_recall_enabled: bool = False,
        adaptive_recall_max_chunks: int = 4096,
        rerank_candidates: int = 20,
    ) -> None:
        if not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be between 0 and 1")

        from pymilvus import MilvusClient

        if is_embedded_uri(uri):
            apply_milvus_lite_windows_patch()
            Path(uri).parent.mkdir(parents=True, exist_ok=True)

        self._embeddings = embeddings
        self._dense_weight = dense_weight
        self._reranker = reranker
        self._alias = collection
        self._search_multiplier = max(search_multiplier, 1)
        self._adaptive_recall_enabled = adaptive_recall_enabled
        self._adaptive_recall_max_chunks = max(adaptive_recall_max_chunks, 1)
        self._rerank_candidates = max(rerank_candidates, 1)
        self._tenant_id = tenant_id
        self._query_rewrite_enabled = query_rewrite_enabled
        self._fielded_search_enabled = fielded_search_enabled
        if search_mode not in {"separate", "native_rrf"}:
            raise ValueError(f"unsupported Milvus search mode: {search_mode}")
        self._search_mode = search_mode
        self._hybrid_rrf_k = max(hybrid_rrf_k, 1)
        self._rerank_strategy = rerank_strategy
        self._reranker_weight = reranker_weight
        self._rerank_rrf_k = rerank_rrf_k
        self._batch_documents = max(batch_documents, 1)
        self._batch_rows = max(batch_rows, 1)
        # milvus-lite 3.1.0 会把 BM25 稀疏字段当成稠密向量去建索引
        # （storage/segment.py 的 _extract_vector_array 要求 FixedSizeList），
        # 分块量大到触发段索引构建时，load_collection 直接失败。
        # 不给稀疏字段建索引即可：BM25 检索仍由 Milvus 暴力计算，实测排序正确。
        # 独立部署的 Milvus 用的是另一套引擎，没有这个限制，因此默认按 URI 形态决定。
        self._index_sparse = (
            not is_embedded_uri(uri) if index_sparse is None else index_sparse
        )
        self._client = MilvusClient(uri=uri, token=token or None)
        self._active_version: str | None = None
        # 待发布的暂存区。upsert 先落到这里，commit 时才写入带版本的 collection。
        self._pending: dict[str, tuple[DocumentRecord, list[Chunk]]] = {}
        self._documents: dict[str, DocumentRecord] = {}

    # ---- 版本与集合命名 ----

    @property
    def active_version(self) -> str | None:
        return self._active_version

    def _collection_name(self, version: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", version)
        return f"{self._alias}__{safe}"[:200]

    def has_version(self, version: str) -> bool:
        return self._client.has_collection(self._collection_name(version))

    def is_version_published(self, version: str) -> bool:
        aliases = set(self._client.list_aliases().get("aliases", []))
        if self._alias not in aliases:
            return False
        description = self._client.describe_alias(self._alias)
        return description.get("collection_name") == self._collection_name(version)

    def versions(self) -> list[str]:
        prefix = f"{self._alias}__"
        return [
            name[len(prefix) :]
            for name in self._client.list_collections()
            if name.startswith(prefix)
        ]

    # ---- 写入 ----

    def upsert_document(self, document: DocumentRecord, chunks: list[Chunk]) -> None:
        self.upsert_documents([(document, chunks)])

    def upsert_documents(self, items: list[tuple[DocumentRecord, list[Chunk]]]) -> None:
        for document, chunks in items:
            self._pending[document.document_id] = (document, chunks)
            self._documents[document.document_id] = document

    def _create_collection(self, name: str) -> None:
        from pymilvus import DataType, Function, FunctionType

        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=512)
        schema.add_field("document_id", DataType.VARCHAR, max_length=128)
        schema.add_field("title", DataType.VARCHAR, max_length=1024)
        schema.add_field("content", DataType.VARCHAR, max_length=65535)
        # BM25 必须同时看到文档编号和标题：内存实现里词法打分的输入是
        # "document_id title content"，只索引正文会让编号类查询（swg…、VPN-401）大幅退化。
        schema.add_field(
            "search_text", DataType.VARCHAR, max_length=65535, enable_analyzer=True
        )
        schema.add_field(
            "title_text", DataType.VARCHAR, max_length=2048, enable_analyzer=True
        )
        schema.add_field(
            "feature_text", DataType.VARCHAR, max_length=4096, enable_analyzer=True
        )
        schema.add_field(
            "allowed_roles",
            DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_capacity=32,
            max_length=64,
        )
        # 过滤实际走这个字段，见 build_acl_expression 里的性能说明。
        schema.add_field("roles_text", DataType.VARCHAR, max_length=2176)
        schema.add_field("roles_key", DataType.VARCHAR, max_length=8192)
        schema.add_field("status", DataType.VARCHAR, max_length=32)
        schema.add_field("tenant_id", DataType.VARCHAR, max_length=128)
        schema.add_field("business_class", DataType.VARCHAR, max_length=128)
        # owner 只用于重启后重建文档元数据，不参与检索或过滤。
        schema.add_field("owner", DataType.VARCHAR, max_length=128)
        schema.add_field("version", DataType.VARCHAR, max_length=128)
        schema.add_field("anchor", DataType.VARCHAR, max_length=256)
        schema.add_field("position", DataType.INT64)
        schema.add_field("parent_id", DataType.VARCHAR, max_length=512)
        schema.add_field("parent_content", DataType.VARCHAR, max_length=65535)
        schema.add_field("section_title", DataType.VARCHAR, max_length=1024)
        schema.add_field("chunking_version", DataType.VARCHAR, max_length=128)
        schema.add_field("token_count", DataType.INT64)
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self._embeddings.dimensions)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field("title_sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field("feature_sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(
            Function(
                name="content_bm25",
                function_type=FunctionType.BM25,
                input_field_names=["search_text"],
                output_field_names=["sparse"],
            )
        )
        schema.add_function(
            Function(
                name="title_bm25",
                function_type=FunctionType.BM25,
                input_field_names=["title_text"],
                output_field_names=["title_sparse"],
            )
        )
        schema.add_function(
            Function(
                name="feature_bm25",
                function_type=FunctionType.BM25,
                input_field_names=["feature_text"],
                output_field_names=["feature_sparse"],
            )
        )

        index_params = self._client.prepare_index_params()
        index_params.add_index(field_name="dense", index_type="AUTOINDEX", metric_type="IP")
        if self._index_sparse:
            for field_name in ("sparse", "title_sparse", "feature_sparse"):
                index_params.add_index(
                    field_name=field_name,
                    index_type="AUTOINDEX",
                    metric_type="BM25",
                )
        self._client.create_collection(name, schema=schema, index_params=index_params)

    def commit(self, version: str, *, progress: ProgressCallback | None = None) -> None:
        """发布新版本。

        分批嵌入并分批写入，绝不把整份语料的向量同时留在内存里：
        28,481 篇约 17 万分块，1024 维 float32 一次性物化会占用数 GB。
        """
        if self.has_version(version):
            raise ValueError(f"index version already exists: {version}")

        name = self._collection_name(version)
        self._create_collection(name)

        pending_document_ids = set(self._pending)
        written = 0

        # 先继承上一版本中本次未覆盖的分块，保证发布是全量快照而不是增量差集。
        if self._active_version is not None:
            buffer: list[dict[str, Any]] = []
            for row in self._iter_rows(self._collection_name(self._active_version)):
                if row["document_id"] in pending_document_ids:
                    continue
                buffer.append(row)
                if len(buffer) >= self._batch_rows:
                    self._client.insert(name, buffer)
                    written += len(buffer)
                    buffer = []
            if buffer:
                self._client.insert(name, buffer)
                written += len(buffer)

        items = list(self._pending.values())
        for start in range(0, len(items), self._batch_documents):
            batch = items[start : start + self._batch_documents]
            rows: list[dict[str, Any]] = []
            texts: list[str] = []
            pairs: list[tuple[DocumentRecord, Chunk]] = []
            for document, chunks in batch:
                for chunk in chunks:
                    pairs.append((document, chunk))
                    texts.append(f"{chunk.title}\n{chunk.content}")
            if texts:
                vectors = self._embeddings.embed_documents(texts)
                for (document, chunk), vector in zip(pairs, vectors, strict=True):
                    rows.append(self._row(document, chunk, vector))
            for offset in range(0, len(rows), self._batch_rows):
                self._client.insert(name, rows[offset : offset + self._batch_rows])
            written += len(rows)
            if progress is not None:
                progress(min(start + self._batch_documents, len(items)), len(items), written)

        if written:
            self._client.flush(name)

        self._client.load_collection(name)
        # alias 切换是发布的原子点：查询永远走 alias，不直接引用版本化名字。
        self._point_alias_at(name)
        self._active_version = version
        self._pending.clear()
        self._refresh_document_cache()

    def begin_unpublished_version(self, version: str) -> None:
        """Create a collection that can be filled across multiple processes."""
        if self.has_version(version):
            raise ValueError(f"index version already exists: {version}")
        self._create_collection(self._collection_name(version))

    def unpublished_document_ids(self, version: str) -> set[str]:
        """Return documents already written to an unpublished collection."""
        name = self._collection_name(version)
        if not self._client.has_collection(name):
            raise ValueError(f"unknown index version: {version}")
        self._client.load_collection(name)
        iterator = self._client.query_iterator(
            name,
            filter="position == 0",
            output_fields=["document_id"],
            batch_size=self._batch_rows,
        )
        document_ids: set[str] = set()
        try:
            while True:
                batch = iterator.next()
                if not batch:
                    break
                document_ids.update(row["document_id"] for row in batch)
        finally:
            iterator.close()
        return document_ids

    def unpublished_chunking_versions(self, version: str) -> set[str]:
        """Return chunking contracts already present in a resumable collection."""

        name = self._collection_name(version)
        if not self._client.has_collection(name):
            raise ValueError(f"unknown index version: {version}")
        if "chunking_version" not in self._field_names(name):
            return {"legacy-characters-v1"}
        self._client.load_collection(name)
        iterator = self._client.query_iterator(
            name,
            filter="position == 0",
            output_fields=["chunking_version"],
            batch_size=self._batch_rows,
        )
        versions: set[str] = set()
        try:
            while True:
                batch = iterator.next()
                if not batch:
                    break
                versions.update(
                    str(row.get("chunking_version") or "legacy-characters-v1")
                    for row in batch
                )
        finally:
            iterator.close()
        return versions

    def version_chunk_count(self, version: str) -> int:
        name = self._collection_name(version)
        if not self._client.has_collection(name):
            raise ValueError(f"unknown index version: {version}")
        return int(self._client.get_collection_stats(name).get("row_count", 0))

    def append_unpublished_documents(
        self,
        version: str,
        items: list[tuple[DocumentRecord, list[Chunk]]],
        *,
        progress: ProgressCallback | None = None,
    ) -> int:
        """Embed and append complete documents without publishing the version."""
        name = self._collection_name(version)
        if not self._client.has_collection(name):
            raise ValueError(f"unknown index version: {version}")
        if self.is_version_published(version):
            raise ValueError(f"cannot append to published index version: {version}")
        required_fields = self._FIELDED_FIELDS | self._STRUCTURED_CHUNK_FIELDS
        missing = required_fields - self._field_names(name)
        if missing:
            raise ValueError(
                "cannot resume an incompatible index schema; missing fields: "
                + ", ".join(sorted(missing))
            )

        written = 0
        for start in range(0, len(items), self._batch_documents):
            batch = items[start : start + self._batch_documents]
            texts: list[str] = []
            for _, chunks in batch:
                for chunk in chunks:
                    texts.append(f"{chunk.title}\n{chunk.content}")
            if texts:
                vectors = self._embeddings.embed_documents(texts)
                vector_index = 0
                row_groups: list[list[dict[str, Any]]] = []
                for document, chunks in batch:
                    group = []
                    for chunk in chunks:
                        group.append(self._row(document, chunk, vectors[vector_index]))
                        vector_index += 1
                    if group:
                        row_groups.append(group)

                insert_buffer: list[dict[str, Any]] = []
                for group in row_groups:
                    if insert_buffer and len(insert_buffer) + len(group) > self._batch_rows:
                        self._client.insert(name, insert_buffer)
                        insert_buffer = []
                    if len(group) > self._batch_rows:
                        self._client.insert(name, group)
                    else:
                        insert_buffer.extend(group)
                if insert_buffer:
                    self._client.insert(name, insert_buffer)
                written += vector_index
            if progress is not None:
                progress(min(start + self._batch_documents, len(items)), len(items), written)

        if written:
            self._client.flush(name)
        return written

    def publish_unpublished_version(
        self,
        version: str,
        *,
        expected_document_ids: set[str] | None = None,
    ) -> None:
        """Atomically expose a fully written collection through the read alias."""
        name = self._collection_name(version)
        if not self._client.has_collection(name):
            raise ValueError(f"unknown index version: {version}")
        stats = self._client.get_collection_stats(name)
        if not int(stats.get("row_count", 0)):
            raise ValueError(f"cannot publish empty index version: {version}")
        if expected_document_ids is not None:
            actual_document_ids = self.unpublished_document_ids(version)
            if actual_document_ids != expected_document_ids:
                missing = len(expected_document_ids - actual_document_ids)
                unexpected = len(actual_document_ids - expected_document_ids)
                raise ValueError(
                    "cannot publish incomplete index version: "
                    f"{missing} missing and {unexpected} unexpected document IDs"
                )
        self._client.load_collection(name)
        self._point_alias_at(name)
        self._active_version = version
        self._pending.clear()
        self._refresh_document_cache()

    def _point_alias_at(self, collection_name: str) -> None:
        existing = set(self._client.list_aliases().get("aliases", []))
        if self._alias in existing:
            self._client.alter_alias(collection_name=collection_name, alias=self._alias)
        else:
            self._client.create_alias(collection_name=collection_name, alias=self._alias)

    def rollback(self, version: str) -> None:
        name = self._collection_name(version)
        if not self._client.has_collection(name):
            raise ValueError(f"unknown index version: {version}")
        self._client.load_collection(name)
        self._point_alias_at(name)
        self._active_version = version
        self._pending.clear()
        self._refresh_document_cache()

    def _row(
        self, document: DocumentRecord, chunk: Chunk, vector: np.ndarray
    ) -> dict[str, Any]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "title": chunk.title[:1024],
            "content": chunk.content[:65535],
            "search_text": f"{chunk.document_id} {chunk.title} {chunk.content}"[:65535],
            "title_text": f"{chunk.document_id} {chunk.title}"[:2048],
            "feature_text": feature_search_text(
                f"{chunk.document_id}\n{chunk.title}\n{chunk.content}",
                document_id=chunk.document_id,
            )[:4096],
            "allowed_roles": sorted(chunk.allowed_roles),
            "roles_text": encode_roles(chunk.allowed_roles),
            "roles_key": encode_role_keys(chunk.allowed_roles),
            "status": chunk.status.value,
            "tenant_id": self._tenant_id,
            "business_class": chunk.business_class,
            "version": chunk.version,
            "anchor": chunk.anchor,
            "position": chunk.position,
            "parent_id": (chunk.parent_id or "")[:512],
            "parent_content": (chunk.parent_content or "")[:65535],
            "section_title": (chunk.section_title or "")[:1024],
            "chunking_version": chunk.chunking_version[:128],
            "token_count": chunk.token_count,
            "dense": vector.tolist(),
            "owner": document.owner,
        }

    # ---- 读取 ----

    _OUTPUT_FIELDS = (
        "chunk_id",
        "document_id",
        "title",
        "content",
        "allowed_roles",
        "status",
        "business_class",
        "version",
        "anchor",
        "position",
        "tenant_id",
        "parent_id",
        "parent_content",
        "section_title",
        "chunking_version",
        "token_count",
    )

    def _field_names(self, collection_name: str) -> set[str]:
        description = self._client.describe_collection(collection_name)
        return {field["name"] for field in description.get("fields", [])}

    def _output_fields(self, collection_name: str) -> list[str]:
        if not hasattr(self._client, "describe_collection"):
            return list(self._OUTPUT_FIELDS)
        available = self._field_names(collection_name)
        return [field for field in self._OUTPUT_FIELDS if field in available]

    def _search_output_fields(self, collection_name: str) -> list[str]:
        # Parent sections are much larger than child retrieval chunks. Fetch them
        # only after ranking instead of once per candidate and recall branch.
        return [
            field
            for field in self._output_fields(collection_name)
            if field != "parent_content"
        ]

    def _hydrate_parent_content(self, hits: list[SearchHit]) -> list[SearchHit]:
        if not hits or "parent_content" not in self._field_names(self._alias):
            return hits
        pending = [
            hit
            for hit in hits
            if hit.chunk.parent_id and not hit.chunk.parent_content
        ]
        if not pending:
            return hits
        representative_by_parent: dict[str, str] = {}
        for hit in pending:
            parent_id = hit.chunk.parent_id
            if parent_id is not None:
                representative_by_parent.setdefault(parent_id, hit.chunk.chunk_id)
        rows = self._client.get(
            self._alias,
            ids=list(representative_by_parent.values()),
            output_fields=["chunk_id", "parent_id", "parent_content"],
        )
        parents = {
            str(row.get("parent_id") or ""): str(row.get("parent_content") or "")
            for row in rows
            if row.get("parent_id")
        }
        return [
            hit.model_copy(
                update={
                    "chunk": hit.chunk.model_copy(
                        update={
                            "parent_content": (
                                parents.get(hit.chunk.parent_id or "")
                                or hit.chunk.parent_content
                            )
                        }
                    )
                }
            )
            for hit in hits
        ]

    def _iter_rows(self, collection_name: str) -> Iterator[dict[str, Any]]:
        """流式读出一个版本的全部行（含向量），供发布时继承上一版本快照。"""
        if not self._client.has_collection(collection_name):
            return
        self._client.load_collection(collection_name)
        available_fields = self._field_names(collection_name)
        requested_fields = list(
            dict.fromkeys(
                [
                    *self._OUTPUT_FIELDS,
                    "dense",
                    "owner",
                    "roles_text",
                    "roles_key",
                    "search_text",
                    "title_text",
                    "feature_text",
                ]
            )
        )
        iterator = self._client.query_iterator(
            collection_name,
            filter="position >= 0",
            # 继承上一版本时必须带上写入所需的全部字段，否则新 collection 会缺列。
            output_fields=[field for field in requested_fields if field in available_fields],
            batch_size=self._batch_rows,
        )
        try:
            while True:
                batch = iterator.next()
                if not batch:
                    break
                for row in batch:
                    row["search_text"] = (
                        f"{row['document_id']} {row['title']} {row['content']}"[:65535]
                    )
                    row["title_text"] = f"{row['document_id']} {row['title']}"[:2048]
                    row["feature_text"] = feature_search_text(
                        f"{row['document_id']}\n{row['title']}\n{row['content']}",
                        document_id=str(row["document_id"]),
                    )[:4096]
                    row["roles_key"] = encode_role_keys(row["allowed_roles"])
                    row.setdefault("parent_id", "")
                    row.setdefault("parent_content", "")
                    row.setdefault("section_title", "")
                    row.setdefault("chunking_version", "legacy-characters-v1")
                    row.setdefault("token_count", 0)
                    yield row
        finally:
            iterator.close()

    def _refresh_document_cache(self) -> None:
        """从活动 collection 重建文档级元数据缓存，使重启后仍可枚举文档。"""
        if self._active_version is None:
            return
        name = self._collection_name(self._active_version)
        if not self._client.has_collection(name):
            return
        self._client.load_collection(name)
        seen: dict[str, DocumentRecord] = {}
        iterator = self._client.query_iterator(
            name,
            filter="position == 0",
            output_fields=[
                "document_id",
                "title",
                "allowed_roles",
                "status",
                "business_class",
                "version",
                "content",
                "owner",
            ],
            batch_size=500,
        )
        while True:
            batch = iterator.next()
            if not batch:
                break
            for row in batch:
                document_id = row["document_id"]
                if document_id in seen:
                    continue
                cached = self._documents.get(document_id)
                seen[document_id] = cached or DocumentRecord(
                    document_id=document_id,
                    title=row["title"],
                    content=row.get("content") or " ",
                    owner=row.get("owner") or "unknown",
                    business_class=row.get("business_class") or "unknown",
                    allowed_roles=set(row.get("allowed_roles") or []),
                    version=row.get("version") or "1.0",
                    status=DocumentStatus(row.get("status") or "active"),
                    checksum="restored",
                )
        iterator.close()
        if seen:
            self._documents = seen

    def documents(self) -> Iterable[DocumentRecord]:
        return self._documents.values()

    def document_ids(self) -> set[str]:
        return set(self._documents)

    def chunk_count(self) -> int:
        if self._active_version is None:
            return 0
        name = self._collection_name(self._active_version)
        if not self._client.has_collection(name):
            return 0
        stats = self._client.get_collection_stats(name)
        return int(stats.get("row_count", 0))

    def authorized_documents(self, roles: frozenset[str]) -> list[DocumentRecord]:
        return [
            document
            for document in self._documents.values()
            if document.status == DocumentStatus.ACTIVE and bool(document.allowed_roles & roles)
        ]

    def authorized_document_ids(self, roles: frozenset[str]) -> set[str]:
        return {document.document_id for document in self.authorized_documents(roles)}

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

    # ---- 检索 ----

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
        if self._active_version is None:
            return []

        requested_tenant = self._tenant_id if tenant_id is None else tenant_id
        if requested_tenant != self._tenant_id:
            return []

        expression = build_acl_expression(
            roles,
            tenant_id=requested_tenant,
            encoded_roles="roles_key" in self._field_names(self._alias),
        )
        validated_candidate_ids: set[str] | None = None
        if candidate_document_ids is not None:
            if not candidate_document_ids:
                return []
            validated_candidate_ids = {
                validate_document_id(document_id)
                for document_id in candidate_document_ids
            }
            ids = ", ".join(f'"{doc}"' for doc in sorted(validated_candidate_ids))
            expression = f"{expression} and document_id in [{ids}]"

        document_target = top_k
        limit = max(top_k * self._search_multiplier, top_k)
        if self._reranker is not None and not exact:
            rerank_document_limit = max(top_k * 4, self._rerank_candidates)
            document_target = max(document_target, rerank_document_limit)
            # Use the same chunk-level recall budget as a direct Top-N document
            # retrieval. Otherwise a Top-3 response would rerank 20 documents
            # recalled from only ``3 * multiplier`` chunks, while Recall@20 is
            # measured from ``20 * multiplier`` chunks.
            limit = max(
                limit,
                rerank_document_limit * self._search_multiplier,
                rerank_document_limit * RERANK_CHUNKS_PER_DOCUMENT,
            )

        recall_branches = None if exact else self._recall_branches(query)
        maximum_limit = max(limit, self._adaptive_recall_max_chunks)
        while True:
            hits = (
                self._exact_hits(query, expression, limit, roles, requested_tenant)
                if exact
                else self._hybrid_hits(
                    query,
                    expression,
                    limit,
                    roles,
                    requested_tenant,
                    branches=recall_branches,
                )
            )
            if validated_candidate_ids is not None:
                hits = [
                    hit
                    for hit in hits
                    if hit.chunk.document_id in validated_candidate_ids
                ]
            hits = [hit for hit in hits if hit.score >= min_score]
            distinct_documents = len({hit.chunk.document_id for hit in hits})
            if (
                exact
                or not self._adaptive_recall_enabled
                or distinct_documents >= document_target
            ):
                break
            if limit >= maximum_limit:
                raise RuntimeError(
                    "adaptive recall could not produce the required distinct documents: "
                    f"required={document_target}, available={distinct_documents}, "
                    f"chunk_limit={limit}"
                )
            limit = min(limit * 2, maximum_limit)

        if self._reranker is not None and not exact and hits:
            candidate_limit = max(top_k * 4, self._rerank_candidates)
            candidates = aggregate_document_candidates(
                hits,
                query,
                candidate_limit,
            )
            hydrated_candidate_hits = self._hydrate_parent_content(
                [hit for candidate in candidates for hit in candidate.hits]
            )
            candidates = aggregate_document_candidates(
                hydrated_candidate_hits,
                query,
                candidate_limit,
            )
            scores = self._reranker.score(
                query,
                [candidate.reranker_text for candidate in candidates],
            )
            ranked_candidates = rank_document_candidates(
                candidates,
                scores,
                strategy=self._rerank_strategy,
                reranker_weight=self._reranker_weight,
                rrf_k=self._rerank_rrf_k,
            )
            hits = [candidate.evidence_hit for candidate in ranked_candidates]
        selected = select_distinct_documents(hits, top_k)
        return self._hydrate_parent_content(selected)

    def _branch(
        self,
        data: Any,
        anns_field: str,
        metric_type: str,
        expression: str,
        limit: int,
        roles: frozenset[str],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """Run one filtered ANN branch for the legacy/separate execution mode."""
        results = self._client.search(
            self._alias,
            data=[data],
            anns_field=anns_field,
            limit=limit,
            filter=expression,
            search_params={"metric_type": metric_type, "params": {}},
            output_fields=self._search_output_fields(self._alias),
        )
        return self._guard(results[0] if results else [], roles, tenant_id)

    @staticmethod
    def _max_normalize(scores: dict[str, float]) -> dict[str, float]:
        maximum = max(scores.values(), default=0.0)
        if maximum <= 0:
            return dict.fromkeys(scores, 0.0)
        return {key: value / maximum for key, value in scores.items()}

    def _rescore(
        self,
        query: str,
        entities: dict[str, dict[str, Any]],
        dense_scores: dict[str, float],
        *,
        exact: bool,
    ) -> list[SearchHit]:
        """在 Milvus 召回的候选池上，复用 P1/P2 已验证的词法打分逻辑。

        Milvus 自带的 BM25 只按分词命中打分，缺少本项目依赖的编号加权、
        标题加权和精确模式的编号预过滤；直接采用会明显低于内存实现的引用准确率
        （同规模同嵌入下 Top-1 0.80 -> 0.49）。因此把 Milvus 当作可扩展的
        ACL + 召回层，精排仍走原有实现。
        """
        chunks = {chunk_id: self._to_chunk(entity) for chunk_id, entity in entities.items()}
        if exact:
            identifiers = _identifiers(query)
            if identifiers:
                if re.search(r"\bdocument\s+(?:id|number)\b", query, flags=re.IGNORECASE):
                    chunks = {
                        chunk_id: chunk
                        for chunk_id, chunk in chunks.items()
                        if chunk.document_id.lower() in identifiers
                    }
                else:
                    chunks = {
                        chunk_id: chunk
                        for chunk_id, chunk in chunks.items()
                        if any(
                            identifier
                            in f"{chunk.document_id} {chunk.title} {chunk.content}".lower()
                            for identifier in identifiers
                        )
                    }
        if not chunks:
            return []

        lexical_scores = InMemoryHybridStore._lexical_scores(query, list(chunks.values()))
        hits: list[SearchHit] = []
        for chunk_id, chunk in chunks.items():
            lexical = lexical_scores[chunk_id]
            dense = 0.0 if exact else dense_scores.get(chunk_id, 0.0)
            score = (
                lexical
                if exact
                else ((1 - self._dense_weight) * lexical) + (self._dense_weight * dense)
            )
            if not exact:
                score += retrieval_feature_boost(query, chunk)
            hits.append(
                SearchHit(
                    chunk=chunk,
                    score=round(score, 6),
                    lexical_score=round(lexical, 6),
                    dense_score=round(dense, 6),
                )
            )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)

    def _hybrid_hits(
        self,
        query: str,
        expression: str,
        limit: int,
        roles: frozenset[str],
        tenant_id: str,
        *,
        branches: Sequence[_RecallBranch] | None = None,
    ) -> list[SearchHit]:
        branches = list(branches) if branches is not None else self._recall_branches(query)
        if self._search_mode == "native_rrf":
            return self._native_hybrid_hits(
                query,
                branches,
                expression,
                limit,
                roles,
                tenant_id,
            )

        branch_results = [
            (
                branch,
                self._branch(
                    branch.data,
                    branch.anns_field,
                    branch.metric_type,
                    expression,
                    limit,
                    roles,
                    tenant_id,
                ),
            )
            for branch in branches
        ]
        if len(branch_results) == 2:
            entities: dict[str, dict[str, Any]] = {}
            dense_scores: dict[str, float] = {}
            for row in branch_results[0][1]:
                entity = row["entity"]
                entities[entity["chunk_id"]] = entity
                dense_scores[entity["chunk_id"]] = max(float(row["distance"]), 0.0)
            for row in branch_results[1][1]:
                entities[row["entity"]["chunk_id"]] = row["entity"]
            return self._rescore(query, entities, dense_scores, exact=False)

        entities: dict[str, dict[str, Any]] = {}
        recall_scores: dict[str, float] = {}
        for branch, rows in branch_results:
            for rank, row in enumerate(rows, start=1):
                entity = row["entity"]
                chunk_id = entity["chunk_id"]
                entities[chunk_id] = entity
                recall_scores[chunk_id] = recall_scores.get(chunk_id, 0.0) + (
                    branch.weight / (self._hybrid_rrf_k + rank)
                )
        return self._rescore(
            query,
            entities,
            self._max_normalize(recall_scores),
            exact=False,
        )

    def _recall_branches(self, query: str) -> list[_RecallBranch]:
        planned_queries = retrieval_queries(
            query,
            rewrite_enabled=self._query_rewrite_enabled,
        )
        vectors = self._embeddings.embed_queries(list(planned_queries))
        branches = [
            _RecallBranch(vector.tolist(), "dense", "IP", 1.0)
            for vector in vectors
        ]
        branches.extend(
            _RecallBranch(item, "sparse", "BM25", 1.0)
            for item in planned_queries
        )
        if not self._fielded_search_enabled:
            return branches

        required = {"title_sparse", "feature_sparse"}
        missing = required - self._field_names(self._alias)
        if missing:
            raise RuntimeError(
                "fielded search requires a fielded index version; missing fields: "
                + ", ".join(sorted(missing))
            )
        focused = planned_queries[-1]
        branches.append(_RecallBranch(focused, "title_sparse", "BM25", 1.0))
        feature_query = feature_search_text(query)
        if feature_query:
            branches.append(
                _RecallBranch(feature_query, "feature_sparse", "BM25", 1.0)
            )
        return branches

    def _native_hybrid_hits(
        self,
        query: str,
        branches: Sequence[_RecallBranch],
        expression: str,
        limit: int,
        roles: frozenset[str],
        tenant_id: str,
    ) -> list[SearchHit]:
        from pymilvus import AnnSearchRequest, RRFRanker

        requests = [
            AnnSearchRequest(
                data=[branch.data],
                anns_field=branch.anns_field,
                param={"metric_type": branch.metric_type, "params": {}},
                limit=limit,
                filter=expression,
            )
            for branch in branches
        ]
        # Preserve the full per-branch candidate union before application reranking.
        hybrid_limit = limit * len(requests)
        results = self._client.hybrid_search(
            self._alias,
            requests,
            ranker=RRFRanker(self._hybrid_rrf_k),
            limit=hybrid_limit,
            output_fields=self._search_output_fields(self._alias),
        )
        rows = self._guard(results[0] if results else [], roles, tenant_id)
        entities = {row["entity"]["chunk_id"]: row["entity"] for row in rows}
        fused_scores = self._max_normalize(
            {
                row["entity"]["chunk_id"]: max(float(row["distance"]), 0.0)
                for row in rows
            }
        )
        return self._rescore(query, entities, fused_scores, exact=False)

    def _exact_hits(
        self,
        query: str,
        expression: str,
        limit: int,
        roles: frozenset[str],
        tenant_id: str,
    ) -> list[SearchHit]:
        use_features = "feature_sparse" in self._field_names(self._alias) and bool(
            feature_search_text(query)
        )
        rows = self._branch(
            feature_search_text(query) if use_features else query,
            "feature_sparse" if use_features else "sparse",
            "BM25",
            expression,
            limit,
            roles,
            tenant_id,
        )
        entities = {row["entity"]["chunk_id"]: row["entity"] for row in rows}
        return self._rescore(query, entities, {}, exact=True)

    def _guard(
        self,
        rows: Sequence[dict[str, Any]],
        roles: frozenset[str],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """纵深防御：在结果侧再核一次状态、角色和租户。

        检索端的过滤表达式是第一道防线，但 Milvus 的 hybrid_search 已经出现过
        顶层 filter 被静默忽略的情况，所以这里独立复核一遍。allowed_roles 本来
        就在返回字段里，复核成本可以忽略，却能把"过滤失效"从数据泄漏降级为少召回。
        """
        safe: list[dict[str, Any]] = []
        for row in rows:
            entity = row.get("entity") or {}
            if entity.get("status") != DocumentStatus.ACTIVE.value:
                continue
            if not (frozenset(entity.get("allowed_roles") or ()) & roles):
                continue
            if entity.get("tenant_id") != tenant_id:
                continue
            safe.append(row)
        return safe

    @staticmethod
    def _to_chunk(entity: dict[str, Any]) -> Chunk:
        return Chunk(
            chunk_id=entity["chunk_id"],
            document_id=entity["document_id"],
            title=entity["title"],
            content=entity["content"],
            position=int(entity["position"]),
            anchor=entity["anchor"],
            allowed_roles=frozenset(entity.get("allowed_roles") or ()),
            version=entity["version"],
            status=DocumentStatus(entity["status"]),
            business_class=entity["business_class"],
            parent_id=entity.get("parent_id") or None,
            parent_content=entity.get("parent_content") or None,
            section_title=entity.get("section_title") or None,
            chunking_version=entity.get("chunking_version") or "legacy-characters-v1",
            token_count=int(entity.get("token_count") or 0),
        )
