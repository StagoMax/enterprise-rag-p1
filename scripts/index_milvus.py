"""把处理后的语料批量建入 Milvus。

用法：
    .venv\\Scripts\\python.exe scripts\\index_milvus.py \\
        --corpus data/processed/techqa_p3/documents.jsonl \\
        --version p3-techqa-28481-v1 --backend hashing

嵌入和写入都是分批的，进程内不会同时持有全量向量。发布完成后 alias 才切过去，
因此中途失败不会污染当前在线版本。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from enterprise_rag.bootstrap import load_documents
from enterprise_rag.chunking import (
    LEGACY_CHUNKING_VERSION,
    ChunkingConfig,
    build_document,
    chunk_document,
    count_tokens,
)
from enterprise_rag.config import Settings
from enterprise_rag.embeddings import (
    BgeM3EmbeddingProvider,
    HashingEmbeddingProvider,
    NemotronEmbeddingProvider,
)
from enterprise_rag.vector_store import MilvusHybridStore


def build_embeddings(args: argparse.Namespace, settings: Settings):
    if args.backend == "nemotron":
        return NemotronEmbeddingProvider(
            model_id=args.model or settings.nemotron_model_id,
            dimensions=args.dimensions or settings.nemotron_dimensions,
            device=args.device,
            batch_size=args.embedding_batch_size,
        )
    if args.backend == "bge_m3":
        return BgeM3EmbeddingProvider(model_id=settings.bge_model_id, device=args.device)
    return HashingEmbeddingProvider(settings.hashing_dimensions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("data/processed/techqa_p3/documents.jsonl"),
    )
    parser.add_argument("--uri", default="data/milvus/enterprise-rag.db")
    parser.add_argument("--collection", default="enterprise_chunks")
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--backend", choices=["hashing", "nemotron", "bge_m3"], default="hashing"
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--dimensions", type=int, default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--embedding-batch-size", type=int, default=8)
    parser.add_argument("--batch-documents", type=int, default=200)
    parser.add_argument(
        "--chunk-strategy",
        choices=["legacy", "structured_parent_child"],
        default=None,
    )
    parser.add_argument("--chunk-max-tokens", type=int, default=None)
    parser.add_argument("--chunk-overlap-tokens", type=int, default=None)
    parser.add_argument("--chunk-parent-max-tokens", type=int, default=None)
    parser.add_argument("--chunking-version", default=None)
    parser.add_argument("--legacy-max-characters", type=int, default=900)
    parser.add_argument("--legacy-overlap-characters", type=int, default=100)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume an unpublished version and skip documents already written",
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        help="write at most this many remaining documents before exiting",
    )
    parser.add_argument("--limit", type=int, default=None, help="只索引前 N 篇，用于冒烟")
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="build a complete isolated version without switching the collection alias",
    )
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    settings = Settings()
    chunk_strategy = args.chunk_strategy or settings.chunking_strategy
    chunking_version = args.chunking_version or (
        LEGACY_CHUNKING_VERSION
        if chunk_strategy == "legacy"
        else settings.chunking_version
    )
    chunking_config = ChunkingConfig(
        strategy=chunk_strategy,
        child_max_tokens=(
            settings.chunk_max_tokens
            if args.chunk_max_tokens is None
            else args.chunk_max_tokens
        ),
        child_overlap_tokens=(
            settings.chunk_overlap_tokens
            if args.chunk_overlap_tokens is None
            else args.chunk_overlap_tokens
        ),
        parent_max_tokens=(
            settings.chunk_parent_max_tokens
            if args.chunk_parent_max_tokens is None
            else args.chunk_parent_max_tokens
        ),
        version=chunking_version,
    )
    corpus_documents = load_documents(args.corpus)
    if args.limit:
        corpus_documents = corpus_documents[: args.limit]
    if not corpus_documents:
        raise SystemExit(f"语料为空：{args.corpus}")
    corpus_document_ids = {document.document_id for document in corpus_documents}
    if len(corpus_document_ids) != len(corpus_documents):
        raise SystemExit("corpus contains duplicate document IDs")
    if args.max_documents is not None and args.max_documents < 1:
        raise SystemExit("--max-documents must be positive")

    embeddings = build_embeddings(args, settings)
    store = MilvusHybridStore(
        embeddings,
        uri=args.uri,
        collection=args.collection,
        dense_weight=settings.dense_weight,
        batch_documents=args.batch_documents,
    )
    if store.has_version(args.version) and not args.resume:
        raise SystemExit(f"版本已存在，换一个 --version 或先删除：{args.version}")

    if store.has_version(args.version):
        if store.is_version_published(args.version):
            raise SystemExit(
                f"cannot resume published index version: {args.version}; use a new version"
            )
        completed_ids = store.unpublished_document_ids(args.version)
        existing_chunking_versions = store.unpublished_chunking_versions(args.version)
        if existing_chunking_versions and existing_chunking_versions != {chunking_config.version}:
            raise SystemExit(
                "cannot resume with a different chunking contract: "
                f"existing={sorted(existing_chunking_versions)}, "
                f"requested={chunking_config.version}"
            )
        unexpected_ids = completed_ids - corpus_document_ids
        if unexpected_ids:
            raise SystemExit(
                "unpublished index contains document IDs absent from the current corpus: "
                f"{len(unexpected_ids)}"
            )
    else:
        store.begin_unpublished_version(args.version)
        completed_ids = set()

    remaining_documents = [
        document
        for document in corpus_documents
        if document.document_id not in completed_ids
    ]
    if args.max_documents:
        remaining_documents = remaining_documents[: args.max_documents]

    chunk_start = time.perf_counter()
    total_chunks = 0
    parent_ids: set[str] = set()
    maximum_chunk_tokens = 0
    maximum_parent_tokens = 0
    items = []
    for document_input in remaining_documents:
        document = build_document(document_input)
        chunks = chunk_document(
            document,
            config=chunking_config,
            max_characters=args.legacy_max_characters,
            overlap_characters=args.legacy_overlap_characters,
        )
        total_chunks += len(chunks)
        parent_ids.update(chunk.parent_id for chunk in chunks if chunk.parent_id)
        maximum_chunk_tokens = max(
            maximum_chunk_tokens,
            *(chunk.token_count for chunk in chunks),
        )
        maximum_parent_tokens = max(
            maximum_parent_tokens,
            *(
                count_tokens(chunk.parent_content)
                for chunk in chunks
                if chunk.parent_content
            ),
        )
        items.append((document, chunks))
    chunk_seconds = time.perf_counter() - chunk_start
    print(
        f"切块完成：{len(items)} 篇 -> {total_chunks} 分块，用时 {chunk_seconds:.1f}s",
        flush=True,
    )

    def on_progress(done: int, total: int, written: int) -> None:
        elapsed = time.perf_counter() - index_start
        rate = done / elapsed if elapsed else 0.0
        remaining = (total - done) / rate if rate else 0.0
        print(
            f"  {done}/{total} 篇，已写入 {written} 分块，"
            f"{rate:.1f} 篇/s，预计剩余 {remaining / 60:.1f} 分钟",
            flush=True,
        )

    index_start = time.perf_counter()
    written_chunks = store.append_unpublished_documents(
        args.version,
        items,
        progress=on_progress,
    )
    index_seconds = time.perf_counter() - index_start
    indexed_document_ids = store.unpublished_document_ids(args.version)
    indexed_documents = len(indexed_document_ids)
    indexed_chunks_total = store.version_chunk_count(args.version)
    complete = indexed_document_ids == corpus_document_ids
    published = complete and not args.no_publish
    if published:
        store.publish_unpublished_version(
            args.version,
            expected_document_ids=corpus_document_ids,
        )

    summary = {
        "version": args.version,
        "backend": args.backend,
        "uri": args.uri,
        "documents": len(corpus_documents),
        "already_indexed_documents": len(completed_ids),
        "indexed_documents": indexed_documents,
        "indexed_chunks_total": indexed_chunks_total,
        "chunks_written": written_chunks,
        "parents_built": len(parent_ids),
        "maximum_chunk_tokens": maximum_chunk_tokens,
        "maximum_parent_tokens": maximum_parent_tokens,
        "chunking": {
            "strategy": chunking_config.strategy,
            "version": chunking_config.version,
            "child_max_tokens": chunking_config.child_max_tokens,
            "child_overlap_tokens": chunking_config.child_overlap_tokens,
            "parent_max_tokens": chunking_config.parent_max_tokens,
        },
        "complete": complete,
        "published": published,
        "chunk_seconds": round(chunk_seconds, 2),
        "index_seconds": round(index_seconds, 2),
        "documents_per_second": round(len(items) / index_seconds, 2) if index_seconds else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
