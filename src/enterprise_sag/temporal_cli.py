from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from enterprise_sag.runtime import create_chat_model, create_embedding_provider
from enterprise_sag.settings import SagSettings
from enterprise_sag.temporal_consolidation import DeepSeekTemporalConsolidationPlanner
from enterprise_sag.temporal_models import (
    ConsolidationProposal,
    MemoryEventCreate,
    TemporalQuery,
    TemporalUsageEvent,
)
from enterprise_sag.temporal_service import TemporalMemoryService
from enterprise_sag.temporal_store import TemporalMemoryStore


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _settings(args: argparse.Namespace) -> SagSettings:
    updates: dict[str, object] = {}
    if getattr(args, "memory_database_path", None):
        updates["temporal_database_path"] = Path(args.memory_database_path)
    if getattr(args, "embedding_backend", None):
        updates["embedding_backend"] = args.embedding_backend
    if getattr(args, "nemotron_device", None):
        updates["nemotron_device"] = args.nemotron_device
    return SagSettings().model_copy(update=updates)


def _store(args: argparse.Namespace) -> TemporalMemoryStore:
    return TemporalMemoryStore(_settings(args).temporal_database_path.resolve())


def _memory_init(args: argparse.Namespace) -> int:
    store = _store(args)
    _print_json(
        {
            "status": "ready",
            "database": str(store.path),
            "schema_version": store.schema_version,
            "integrity_check": store.integrity_check(),
            "stats": store.stats(),
            "append_only_ledger": True,
            "agent_loop_integration": False,
        }
    )
    return 0


def _memory_append(args: argparse.Namespace) -> int:
    metadata = json.loads(args.metadata_json) if args.metadata_json else {}
    if not isinstance(metadata, dict):
        raise ValueError("--metadata-json must contain a JSON object")
    payload: dict[str, object] = {
        "subject_id": args.subject_id,
        "content": args.content,
        "source_kind": args.source_kind,
        "source_ref": args.source_ref,
        "session_id": args.session_id,
        "metadata": metadata,
    }
    if args.occurred_at:
        payload["occurred_at"] = args.occurred_at
    if args.observed_at:
        payload["observed_at"] = args.observed_at
    service = TemporalMemoryService(_store(args))
    event = service.append_interaction(MemoryEventCreate.model_validate(payload))
    _print_json(
        {
            "status": "appended",
            "event": event.model_dump(mode="json"),
            "extraction_started": False,
            "llm_requests": 0,
            "agent_loop_integration": False,
        }
    )
    return 0


def _memory_pending(args: argparse.Namespace) -> int:
    events = _store(args).pending_events(limit=args.limit)
    _print_json(
        {
            "count": len(events),
            "events": [event.model_dump(mode="json") for event in events],
        }
    )
    return 0


def _memory_propose(args: argparse.Namespace) -> int:
    settings = _settings(args)
    embeddings = create_embedding_provider(settings)
    chat_model = create_chat_model(settings)
    try:
        service = TemporalMemoryService(
            TemporalMemoryStore(settings.temporal_database_path.resolve()),
            embeddings,
            embedding_backend=settings.embedding_backend,
        )
        proposal = service.propose_consolidation(
            args.event_id,
            DeepSeekTemporalConsolidationPlanner(chat_model),
            candidate_limit=args.candidate_limit,
        )
        output = (
            Path(args.output)
            if args.output
            else settings.temporal_proposal_dir / f"{proposal.proposal_id}.json"
        ).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        _print_json(
            {
                "status": "proposal-created",
                "output": str(output),
                "event_id": proposal.event_id,
                "assertions": len(proposal.assertions),
                "relations": len(proposal.relations),
                "applied": False,
                "requires_manual_apply": True,
                "llm_requests": chat_model.request_count,
                "agent_loop_integration": False,
            }
        )
        return 0
    finally:
        chat_model.close()


def _memory_apply(args: argparse.Namespace) -> int:
    settings = _settings(args)
    proposal = ConsolidationProposal.model_validate_json(
        Path(args.proposal).read_text(encoding="utf-8")
    )
    service = TemporalMemoryService(
        TemporalMemoryStore(settings.temporal_database_path.resolve()),
        create_embedding_provider(settings),
        embedding_backend=settings.embedding_backend,
    )
    result = service.apply_consolidation(proposal)
    _print_json(result.model_dump(mode="json"))
    return 0


def _memory_query(args: argparse.Namespace) -> int:
    settings = _settings(args)
    payload: dict[str, object] = {
        "query": args.query,
        "subject_id": args.subject_id,
        "mode": args.mode,
        "top_k": args.top_k,
        "predicates": args.predicate or [],
        "scopes": args.scope or [],
    }
    if args.valid_at:
        payload["valid_at"] = args.valid_at
    if args.known_at:
        payload["known_at"] = args.known_at
    service = TemporalMemoryService(
        TemporalMemoryStore(settings.temporal_database_path.resolve()),
        create_embedding_provider(settings),
        embedding_backend=settings.embedding_backend,
    )
    request = TemporalQuery.model_validate(payload)
    hits = service.search(request)
    _print_json(
        {
            "request": request.model_dump(mode="json"),
            "hits": [hit.model_dump(mode="json") for hit in hits],
            "validity_gate_applied": args.mode == "latest_valid",
            "agent_loop_integration": False,
            "prompt_injection": False,
        }
    )
    return 0


def _memory_usage(args: argparse.Namespace) -> int:
    event = TemporalUsageEvent.model_validate(
        {
            "assertion_id": args.assertion_id,
            "outcome": args.outcome,
            "query_ref": args.query_ref,
            "context": args.context,
        }
    )
    store = _store(args)
    store.append_usage(event)
    _print_json(
        {
            "status": "usage-appended",
            "usage": event.model_dump(mode="json"),
            "stats": store.usage_stats([event.assertion_id])[event.assertion_id].model_dump(
                mode="json"
            ),
        }
    )
    return 0


def _memory_inspect(args: argparse.Namespace) -> int:
    store = _store(args)
    _print_json(
        {
            "database": str(store.path),
            "schema_version": store.schema_version,
            "integrity_check": store.integrity_check(),
            "stats": store.stats(),
            "pending_events": len(store.pending_events(limit=10_000)),
            "append_only_ledger": True,
            "agent_loop_integration": False,
        }
    )
    return 0


def _add_database_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--memory-database-path")


def _add_embedding_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--embedding-backend", choices=("nemotron", "hashing"))
    parser.add_argument("--nemotron-device", choices=("cuda", "cpu"))


def register_temporal_commands(subparsers: Any) -> None:
    memory = subparsers.add_parser(
        "memory",
        help="append and manually consolidate temporal memory outside the Agent Loop",
    )
    actions = memory.add_subparsers(dest="memory_command", required=True)

    initialize = actions.add_parser("init", help="initialize the append-only temporal store")
    _add_database_option(initialize)
    initialize.set_defaults(handler=_memory_init)

    append = actions.add_parser("append", help="append one interaction without extraction")
    append.add_argument("content")
    append.add_argument("--subject-id", required=True)
    append.add_argument("--occurred-at")
    append.add_argument("--observed-at")
    append.add_argument("--source-kind", default="conversation")
    append.add_argument("--source-ref")
    append.add_argument("--session-id")
    append.add_argument("--metadata-json")
    _add_database_option(append)
    append.set_defaults(handler=_memory_append)

    pending = actions.add_parser("pending", help="list events awaiting consolidation")
    pending.add_argument("--limit", type=int, default=100)
    _add_database_option(pending)
    pending.set_defaults(handler=_memory_pending)

    propose = actions.add_parser(
        "propose",
        help="use DeepSeek to create a reviewable proposal without applying it",
    )
    propose.add_argument("event_id")
    propose.add_argument("--candidate-limit", type=int, default=20)
    propose.add_argument("--output")
    _add_database_option(propose)
    _add_embedding_options(propose)
    propose.set_defaults(handler=_memory_propose)

    apply = actions.add_parser(
        "apply",
        help="explicitly apply a reviewed proposal and rebuild the read projection",
    )
    apply.add_argument("proposal")
    _add_database_option(apply)
    _add_embedding_options(apply)
    apply.set_defaults(handler=_memory_apply)

    query = actions.add_parser("query", help="query current or historical temporal memory")
    query.add_argument("query")
    query.add_argument("--subject-id", required=True)
    query.add_argument("--mode", choices=("latest_valid", "historical"), default="latest_valid")
    query.add_argument("--valid-at")
    query.add_argument("--known-at")
    query.add_argument("--top-k", type=int, default=10)
    query.add_argument("--predicate", action="append")
    query.add_argument("--scope", action="append")
    _add_database_option(query)
    _add_embedding_options(query)
    query.set_defaults(handler=_memory_query)

    usage = actions.add_parser("usage", help="append retrieval feedback without changing facts")
    usage.add_argument("assertion_id")
    usage.add_argument("--outcome", choices=("selected", "successful", "rejected"), required=True)
    usage.add_argument("--query-ref")
    usage.add_argument("--context", default="retrieval")
    _add_database_option(usage)
    usage.set_defaults(handler=_memory_usage)

    inspect = actions.add_parser("inspect", help="inspect temporal ledger and projection counts")
    _add_database_option(inspect)
    inspect.set_defaults(handler=_memory_inspect)
