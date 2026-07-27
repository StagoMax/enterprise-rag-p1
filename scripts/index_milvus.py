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
from enterprise_rag.chunking import build_document, chunk_document
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
    parser.add_argument("--batch-documents", type=int, default=200)
    parser.add_argument("--limit", type=int, default=None, help="只索引前 N 篇，用于冒烟")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    settings = Settings()
    documents = load_documents(args.corpus)
    if args.limit:
        documents = documents[: args.limit]
    if not documents:
        raise SystemExit(f"语料为空：{args.corpus}")

    store = MilvusHybridStore(
        build_embeddings(args, settings),
        uri=args.uri,
        collection=args.collection,
        dense_weight=settings.dense_weight,
        batch_documents=args.batch_documents,
    )
    if store.has_version(args.version):
        raise SystemExit(f"版本已存在，换一个 --version 或先删除：{args.version}")

    chunk_start = time.perf_counter()
    total_chunks = 0
    items = []
    for document_input in documents:
        document = build_document(document_input)
        chunks = chunk_document(document)
        total_chunks += len(chunks)
        items.append((document, chunks))
    chunk_seconds = time.perf_counter() - chunk_start
    print(
        f"切块完成：{len(items)} 篇 -> {total_chunks} 分块，用时 {chunk_seconds:.1f}s",
        flush=True,
    )

    store.upsert_documents(items)

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
    store.commit(args.version, progress=on_progress)
    index_seconds = time.perf_counter() - index_start

    summary = {
        "version": args.version,
        "backend": args.backend,
        "uri": args.uri,
        "documents": len(items),
        "chunks": total_chunks,
        "indexed_chunks": store.chunk_count(),
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
