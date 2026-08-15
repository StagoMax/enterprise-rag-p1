from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from enterprise_sag.context_pack import DraftContextPackBuilder
from enterprise_sag.ingestion import IncrementalIngestionService
from enterprise_sag.ingestion_models import IngestionOptions
from enterprise_sag.models import ContextPackRequest
from enterprise_sag.pipeline import SagIndexBuilder
from enterprise_sag.runtime import (
    create_chat_model,
    create_embedding_provider,
    create_multi_route_retriever,
)
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import SagSqliteStore
from enterprise_sag.temporal_cli import register_temporal_commands


def _settings_from_args(args: argparse.Namespace) -> SagSettings:
    settings = SagSettings()
    updates: dict[str, object] = {}
    for name in (
        "source_root",
        "database_path",
        "asset_store_path",
        "extractor",
        "embedding_backend",
        "nemotron_device",
    ):
        value = getattr(args, name, None)
        if value is not None:
            updates[name] = Path(value) if name.endswith(("root", "path")) else value
    if getattr(args, "allow_extractor_fallback", False):
        updates["allow_extractor_fallback"] = True
    if getattr(args, "maximum_tokens", None) is not None:
        updates["context_pack_maximum_tokens"] = args.maximum_tokens
    return settings.model_copy(update=updates)


def _build(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    builder = SagIndexBuilder(settings, progress=lambda message: print(f"[SAG] {message}"))
    report = builder.build(max_files=args.max_files)
    database_path = settings.database_path.resolve()
    report_path = database_path.parent / f"{database_path.stem}-build-report.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "built",
                "database": str(settings.database_path.resolve()),
                "report": str(report_path),
                "index_version": report.index_version,
                "sources": report.unique_sources,
                "evidence_units": report.evidence_units,
                "events": report.events,
                "entities": report.entities,
                "llm_requests": report.llm_requests,
                "agent_loop_integration": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _preview(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    store = SagSqliteStore(settings.database_path.resolve())
    metadata = store.metadata()
    embeddings = create_embedding_provider(settings)
    chat_model = None if args.no_deepseek_query else create_chat_model(settings)
    try:
        retriever = create_multi_route_retriever(settings, store, embeddings, chat_model)
        request = ContextPackRequest(
            query=args.query,
            purpose=args.purpose,
            subject_refs=args.subject_ref or [],
            allowed_namespaces=args.namespace or [],
            maximum_tokens=settings.context_pack_maximum_tokens,
        )
        result = retriever.search(request, top_k=args.top_k)
        pack = DraftContextPackBuilder(maximum_tokens=settings.context_pack_maximum_tokens).build(
            request=request,
            plan=result.plan,
            index_version=str(metadata["index_version"]),
            hits=result.hits,
        )
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = (
            Path(args.output)
            if args.output
            else settings.preview_dir / f"context-pack-{timestamp}.json"
        ).resolve()
        pack.save_json(output)
        markdown_output = output.with_suffix(".md")
        pack.save_markdown(markdown_output)
        print(
            json.dumps(
                {
                    "status": pack.status.value,
                    "purpose": pack.purpose,
                    "json_output": str(output),
                    "markdown_output": str(markdown_output),
                    "items": len(pack.items),
                    "excluded": len(pack.excluded_items),
                    "evidence_needs": len(pack.plan.needs),
                    "coverage": {item.need_id: item.status for item in pack.coverage},
                    "route_candidates": result.candidate_counts,
                    "estimated_tokens": pack.estimated_tokens,
                    "maximum_tokens": pack.maximum_tokens,
                    "prompt_injection": False,
                    "agent_loop_integration": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if chat_model is not None:
            chat_model.close()


def _inspect(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    store = SagSqliteStore(settings.database_path.resolve())
    print(
        json.dumps(
            {
                "database": str(store.path),
                "metadata": store.metadata(),
                "stats": store.stats(),
                "integrity_check": store.integrity_check(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _ingest(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    try:
        metadata = json.loads(args.metadata_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--metadata-json is not valid JSON: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SystemExit("--metadata-json must contain a JSON object")
    service = IncrementalIngestionService(settings)
    try:
        result = service.ingest_path(
            Path(args.path),
            options=IngestionOptions(
                asset_id=args.asset_id,
                source_key=args.source_key,
                namespace=args.namespace,
                title=args.title,
                metadata=metadata,
            ),
            origin="cli",
        )
        print(result.model_dump_json(indent=2))
        return 0
    finally:
        service.close()


def _sources(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    store = SagSqliteStore(settings.database_path.resolve())
    print(json.dumps(store.list_source_assets(), ensure_ascii=False, indent=2, default=str))
    return 0


def _panel(args: argparse.Namespace) -> int:
    from enterprise_sag.panel import run_panel

    return run_panel(host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="enterprise-sag",
        description="Manual SAG projection and review-only Draft Context Pack tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="manually rebuild the isolated SAG projection")
    build.add_argument("--source-root")
    build.add_argument("--database-path")
    build.add_argument("--extractor", choices=("deepseek", "deterministic"))
    build.add_argument("--embedding-backend", choices=("nemotron", "hashing"))
    build.add_argument("--nemotron-device", choices=("cuda", "cpu"))
    build.add_argument("--allow-extractor-fallback", action="store_true")
    build.add_argument("--max-files", type=int)
    build.set_defaults(handler=_build)

    preview = subparsers.add_parser(
        "preview", help="build a Draft Context Pack without injecting it into an Agent"
    )
    preview.add_argument("query")
    preview.add_argument("--database-path")
    preview.add_argument("--embedding-backend", choices=("nemotron", "hashing"))
    preview.add_argument("--nemotron-device", choices=("cuda", "cpu"))
    preview.add_argument("--top-k", type=int, default=10)
    preview.add_argument("--maximum-tokens", type=int)
    preview.add_argument("--purpose", default="evidence_review")
    preview.add_argument("--subject-ref", action="append")
    preview.add_argument("--namespace", action="append")
    preview.add_argument("--output")
    preview.add_argument("--no-deepseek-query", action="store_true")
    preview.set_defaults(handler=_preview)

    inspect = subparsers.add_parser("inspect", help="show projection metadata and counts")
    inspect.add_argument("--database-path")
    inspect.set_defaults(handler=_inspect)

    ingest = subparsers.add_parser(
        "ingest",
        help="incrementally add or version one document without rebuilding the corpus",
    )
    ingest.add_argument("path")
    ingest.add_argument("--database-path")
    ingest.add_argument("--asset-store-path")
    ingest.add_argument("--asset-id")
    ingest.add_argument("--source-key")
    ingest.add_argument("--namespace", default="enterprise_knowledge")
    ingest.add_argument("--title")
    ingest.add_argument("--metadata-json", default="{}")
    ingest.add_argument("--extractor", choices=("deepseek", "deterministic"))
    ingest.add_argument("--embedding-backend", choices=("nemotron", "hashing"))
    ingest.add_argument("--nemotron-device", choices=("cuda", "cpu"))
    ingest.add_argument("--allow-extractor-fallback", action="store_true")
    ingest.set_defaults(handler=_ingest)

    sources = subparsers.add_parser("sources", help="list active ingested source assets")
    sources.add_argument("--database-path")
    sources.set_defaults(handler=_sources)

    panel = subparsers.add_parser(
        "panel",
        help="run the local review-only SAG Retrieval Inspector",
    )
    panel.add_argument("--host", default="127.0.0.1")
    panel.add_argument("--port", type=int, default=8765)
    panel.set_defaults(handler=_panel)

    register_temporal_commands(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
