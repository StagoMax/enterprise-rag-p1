from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from enterprise_rag.embeddings import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    NemotronEmbeddingProvider,
)
from enterprise_rag.llm import OpenAiCompatibleChatModel
from enterprise_rag.parsing import (
    SUPPORTED_SUFFIXES,
    DoclingDocumentParser,
    ParsedDocument,
    parse_documents,
)
from enterprise_sag.chunking import SagChunkingConfig, build_evidence_units
from enterprise_sag.extraction import (
    DeepSeekEventExtractor,
    DeterministicEventExtractor,
    EventExtractor,
)
from enterprise_sag.models import (
    EventExtraction,
    EvidenceUnit,
    IndexBuildReport,
    SourceDocument,
)
from enterprise_sag.pipeline_contract import pipeline_contract
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import (
    SagSqliteStore,
    collect_unique_entities,
    event_id_for,
)

ProgressCallback = Callable[[str], None]


def _normalized_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _batched[T](values: Sequence[T], size: int) -> list[Sequence[T]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _embed(
    provider: EmbeddingProvider,
    texts: Sequence[str],
    *,
    batch_size: int,
) -> np.ndarray:
    if not texts:
        return np.empty((0, provider.dimensions), dtype=np.float32)
    batches = [provider.embed_documents(batch) for batch in _batched(texts, batch_size)]
    return np.concatenate(batches, axis=0)


class SagIndexBuilder:
    """Manual, replace-all builder for an isolated SAG memory read projection."""

    def __init__(self, settings: SagSettings, *, progress: ProgressCallback | None = None) -> None:
        self.settings = settings
        self._progress = progress or (lambda _: None)

    def _embedding_provider(self) -> EmbeddingProvider:
        if self.settings.embedding_backend == "nemotron":
            return NemotronEmbeddingProvider(
                model_id=self.settings.nemotron_model_id,
                dimensions=self.settings.nemotron_dimensions,
                device=self.settings.nemotron_device,
                batch_size=self.settings.embedding_batch_size,
            )
        return HashingEmbeddingProvider(self.settings.hashing_dimensions)

    def _event_extractor(
        self,
    ) -> tuple[EventExtractor, OpenAiCompatibleChatModel | None]:
        deterministic = DeterministicEventExtractor()
        if self.settings.extractor == "deterministic":
            return deterministic, None

        base_url, api_key, model = self.settings.require_llm()
        chat_model = OpenAiCompatibleChatModel(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_tokens=self.settings.llm_max_tokens,
            temperature=0.0,
            max_retries=self.settings.llm_max_retries,
        )
        fallback = deterministic if self.settings.allow_extractor_fallback else None
        return DeepSeekEventExtractor(chat_model, fallback=fallback), chat_model

    def _parse_sources(
        self, paths: Sequence[Path]
    ) -> tuple[list[SourceDocument], list[ParsedDocument], list[dict[str, str]]]:
        parser = DoclingDocumentParser(prefer_docling=False)
        parsed = parse_documents(paths, parser=parser)
        failed = [
            {"path": item.source_path, "error": item.error or "unknown parse error"}
            for item in parsed
            if item.failed or not item.text.strip()
        ]

        groups: dict[str, list[ParsedDocument]] = {}
        for item in parsed:
            if item.failed or not item.text.strip():
                continue
            groups.setdefault(_normalized_hash(item.text), []).append(item)

        sources: list[SourceDocument] = []
        unique_parsed: list[ParsedDocument] = []
        for content_hash, duplicates in sorted(groups.items()):
            duplicates.sort(key=lambda item: item.source_path)
            canonical = duplicates[0]
            canonical_path = Path(canonical.source_path)
            source_id = f"src_{content_hash[:24]}"
            aliases = [str(Path(item.source_path).resolve()) for item in duplicates]
            modified_at = datetime.fromtimestamp(canonical_path.stat().st_mtime, tz=UTC)
            sources.append(
                SourceDocument(
                    source_id=source_id,
                    canonical_path=str(canonical_path.resolve()),
                    aliases=aliases,
                    title=canonical.title or canonical_path.stem,
                    doc_format=canonical.doc_format,
                    content_hash=content_hash,
                    modified_at=modified_at,
                )
            )
            unique_parsed.append(canonical)
        return sources, unique_parsed, failed

    def build(self, *, max_files: int | None = None) -> IndexBuildReport:
        root = self.settings.source_root.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"SAG source root does not exist: {root}")
        store = SagSqliteStore(self.settings.database_path.resolve())
        managed_paths = store.active_source_paths() if store.path.exists() else []
        paths = sorted(
            set(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
            )
            | {
                path.resolve()
                for path in managed_paths
                if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
            }
        )
        if max_files is not None:
            paths = paths[:max_files]
        if not paths:
            raise RuntimeError(f"No supported documents found under {root}")

        self._progress(f"Parsing {len(paths)} source files")
        sources, parsed_documents, failed = self._parse_sources(paths)
        source_by_path = {source.canonical_path: source for source in sources}
        chunking = SagChunkingConfig(
            target_tokens=self.settings.chunk_target_tokens,
            max_tokens=self.settings.chunk_max_tokens,
        )
        units: list[EvidenceUnit] = []
        document_units: list[list[EvidenceUnit]] = []
        for parsed in parsed_documents:
            source = source_by_path[str(Path(parsed.source_path).resolve())]
            current_units = build_evidence_units(
                parsed, source_id=source.source_id, config=chunking
            )
            units.extend(current_units)
            document_units.append(current_units)
        if not units:
            raise RuntimeError("Parsing succeeded but produced no SAG evidence units")
        self._progress(f"Built {len(units)} non-overlapping event evidence units")

        extractor, chat_model = self._event_extractor()
        extractions: list[EventExtraction] = []
        try:
            batches = [
                batch
                for current_units in document_units
                for batch in _batched(current_units, self.settings.extractor_batch_size)
            ]
            for batch_number, batch in enumerate(batches, start=1):
                self._progress(f"Extracting Event/Entity batch {batch_number}/{len(batches)}")
                extractions.extend(extractor.extract(batch))

            provider = self._embedding_provider()
            self._progress(
                f"Embedding {len(units)} evidence units with {self.settings.embedding_backend}"
            )
            evidence_matrix = _embed(
                provider,
                [unit.content for unit in units],
                batch_size=self.settings.embedding_batch_size,
            )
            event_ids = [event_id_for(item) for item in extractions]
            event_matrix = _embed(
                provider,
                [item.event_text for item in extractions],
                batch_size=self.settings.embedding_batch_size,
            )
            unique_entities = collect_unique_entities(extractions)
            entity_ids = list(unique_entities)
            entity_matrix = _embed(
                provider,
                [
                    f"{unique_entities[entity_id][1]}: {unique_entities[entity_id][0]}"
                    for entity_id in entity_ids
                ],
                batch_size=self.settings.embedding_batch_size,
            )

            evidence_vectors = {
                unit.evidence_id: evidence_matrix[index] for index, unit in enumerate(units)
            }
            event_vectors = {
                event_id: event_matrix[index] for index, event_id in enumerate(event_ids)
            }
            entity_vectors = {
                entity_id: entity_matrix[index] for index, entity_id in enumerate(entity_ids)
            }

            contract = pipeline_contract(
                self.settings,
                extractor_name=extractor.name,
                embedding_dimensions=provider.dimensions,
            )
            version_payload = {
                "sources": [source.content_hash for source in sources],
                **contract,
            }
            digest = hashlib.sha256(
                json.dumps(version_payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            index_version = f"sag-personal-v1-{digest[:16]}"
            self._progress(f"Publishing isolated projection {index_version}")
            store.replace_projection(
                metadata={
                    "index_version": index_version,
                    "source_root": str(root),
                    **contract,
                    "pipeline_signature": contract["signature"],
                    "index_generation": 1,
                    "created_at": datetime.now(UTC).isoformat(),
                    "agent_loop_integration": False,
                    "context_pack_mode": "draft-preview-only",
                },
                sources=sources,
                units=units,
                extractions=extractions,
                evidence_vectors=evidence_vectors,
                event_vectors=event_vectors,
                entity_vectors=entity_vectors,
            )
            stats = store.stats()
            if store.integrity_check() != "ok":
                raise RuntimeError("Published SAG SQLite projection failed integrity_check")

            report = IndexBuildReport(
                source_root=str(root),
                database_path=str(store.path),
                discovered_files=len(paths),
                parsed_files=len(paths) - len(failed),
                failed_files=failed,
                unique_sources=stats["sources"],
                duplicate_aliases=stats["source_aliases"] - stats["sources"],
                evidence_units=stats["evidence_units"],
                events=stats["events"],
                entities=stats["entities"],
                event_entity_links=stats["event_entities"],
                extractor=extractor.name,
                embedding_backend=self.settings.embedding_backend,
                embedding_dimensions=provider.dimensions,
                llm_requests=chat_model.request_count if chat_model else 0,
                index_version=index_version,
            )
            self._progress("SAG projection build completed")
            return report
        finally:
            if chat_model is not None:
                chat_model.close()
