from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from enterprise_rag.embeddings import EmbeddingProvider
from enterprise_rag.llm import OpenAiCompatibleChatModel
from enterprise_rag.parsing import SUPPORTED_SUFFIXES, DoclingDocumentParser
from enterprise_sag.chunking import SagChunkingConfig, build_evidence_units
from enterprise_sag.extraction import (
    DeepSeekEventExtractor,
    DeterministicEventExtractor,
    EventExtractor,
)
from enterprise_sag.ingestion_models import IngestionOptions, IngestionResult
from enterprise_sag.models import EventExtraction, SourceDocument
from enterprise_sag.pipeline_contract import pipeline_contract
from enterprise_sag.runtime import create_chat_model, create_embedding_provider
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import (
    SagSqliteStore,
    asset_id_for,
    collect_unique_entities,
    event_id_for,
    version_id_for,
)


def normalized_content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def version_fingerprint(
    *,
    content_hash: str,
    title: str,
    metadata: dict[str, object],
) -> str:
    payload = {
        "content_hash": content_hash,
        "title": title,
        "metadata": metadata,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


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
    return np.concatenate(
        [provider.embed_documents(batch) for batch in _batched(texts, batch_size)], axis=0
    )


class IncrementalIngestionService:
    """Transport-independent, document-level incremental SAG publisher."""

    def __init__(
        self,
        settings: SagSettings | None = None,
        *,
        store: SagSqliteStore | None = None,
        embeddings: EmbeddingProvider | None = None,
        extractor: EventExtractor | None = None,
        chat_model: OpenAiCompatibleChatModel | None = None,
    ) -> None:
        self.settings = settings or SagSettings()
        self.store = store or SagSqliteStore(self.settings.database_path.resolve())
        self._embeddings = embeddings
        self._extractor = extractor
        self._chat_model = chat_model
        self._owns_chat_model = False

    def _embedding_provider(self) -> EmbeddingProvider:
        if self._embeddings is None:
            self._embeddings = create_embedding_provider(self.settings)
        return self._embeddings

    def _event_extractor(self) -> EventExtractor:
        if self._extractor is not None:
            return self._extractor
        deterministic = DeterministicEventExtractor()
        if self.settings.extractor == "deterministic":
            self._extractor = deterministic
            return self._extractor
        if self._chat_model is None:
            self._chat_model = create_chat_model(self.settings)
            self._owns_chat_model = True
        fallback = deterministic if self.settings.allow_extractor_fallback else None
        self._extractor = DeepSeekEventExtractor(self._chat_model, fallback=fallback)
        return self._extractor

    @staticmethod
    def _safe_filename(filename: str) -> str:
        safe = Path(filename.replace("\\", "/")).name.strip()
        if not safe or safe in {".", ".."}:
            raise ValueError("filename must contain a valid file name")
        if len(safe) > 255:
            raise ValueError("filename is too long")
        if Path(safe).suffix.lower() not in SUPPORTED_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise ValueError(f"unsupported document type; supported suffixes: {supported}")
        return safe

    def ingest_bytes(
        self,
        content: bytes,
        *,
        filename: str,
        options: IngestionOptions | None = None,
    ) -> IngestionResult:
        if not content:
            raise ValueError("uploaded document is empty")
        if len(content) > self.settings.ingestion_max_file_bytes:
            raise ValueError(
                f"uploaded document exceeds {self.settings.ingestion_max_file_bytes} bytes"
            )
        safe_name = self._safe_filename(filename)
        temporary_root = self.settings.asset_store_path.resolve() / ".incoming"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=Path(safe_name).suffix,
                prefix="sag-",
                dir=temporary_root,
                delete=False,
            ) as handle:
                handle.write(content)
                temporary_path = Path(handle.name)
            return self.ingest_path(
                temporary_path,
                filename=safe_name,
                options=options,
                origin="upload",
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def ingest_path(
        self,
        path: Path,
        *,
        filename: str | None = None,
        options: IngestionOptions | None = None,
        origin: str = "api",
    ) -> IngestionResult:
        resolved_path = path.resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(f"source document does not exist: {resolved_path}")
        if resolved_path.stat().st_size > self.settings.ingestion_max_file_bytes:
            raise ValueError(
                f"source document exceeds {self.settings.ingestion_max_file_bytes} bytes"
            )
        safe_name = self._safe_filename(filename or resolved_path.name)
        request = options or IngestionOptions()
        job_id = self.store.create_ingestion_job(safe_name)
        created_stored_path: Path | None = None
        try:
            existing_asset = self.store.resolve_asset(
                asset_id=request.asset_id,
                namespace=request.namespace,
                source_key=request.source_key,
            )
            if existing_asset is not None:
                asset_id = str(existing_asset["asset_id"])
                namespace = str(existing_asset["namespace"])
                source_key = str(existing_asset["source_key"])
            else:
                source_key = request.source_key or f"generated:{uuid.uuid4().hex}"
                namespace = request.namespace
                asset_id = request.asset_id or asset_id_for(namespace, source_key)
                if request.asset_id and request.source_key is None:
                    raise ValueError(
                        "source_key is required when creating a caller-supplied asset_id"
                    )

            parsed = DoclingDocumentParser(prefer_docling=False).parse(resolved_path)
            if parsed.failed or not parsed.text.strip():
                raise ValueError(parsed.error or "document parsing produced no text")
            content_hash = normalized_content_hash(parsed.text)
            title = request.title or parsed.title or Path(safe_name).stem
            fingerprint = version_fingerprint(
                content_hash=content_hash,
                title=title,
                metadata=request.metadata,
            )
            provider = self._embedding_provider()
            extractor = self._event_extractor()
            contract = pipeline_contract(
                self.settings,
                extractor_name=extractor.name,
                embedding_dimensions=provider.dimensions,
            )
            self.store.assert_incremental_compatible(contract)

            active = self.store.active_version(asset_id)
            if active is not None and active.get("version_fingerprint") == fingerprint:
                self.store.finish_ingestion_job(
                    job_id,
                    status="unchanged",
                    asset_id=asset_id,
                    version_id=str(active["version_id"]),
                )
                return IngestionResult(
                    job_id=job_id,
                    status="unchanged",
                    asset_id=asset_id,
                    version_id=str(active["version_id"]),
                    version_number=int(active["version_number"]),
                    source_id=str(active["source_id"]),
                    content_hash=content_hash,
                    namespace=namespace,
                    title=str(active["title"]),
                    stored_path=str(active["stored_path"]),
                    index_version=str(self.store.metadata().get("index_version", "unpublished")),
                    pipeline_signature=str(contract["signature"]),
                    reused_projection=True,
                )

            version_id = version_id_for(asset_id, fingerprint)
            version_root = self.settings.asset_store_path.resolve() / asset_id / version_id
            version_root.mkdir(parents=True, exist_ok=True)
            stored_path = version_root / safe_name
            if not stored_path.exists():
                shutil.copy2(resolved_path, stored_path)
                created_stored_path = stored_path

            source_id = f"src_{content_hash[:24]}"
            source = SourceDocument(
                source_id=source_id,
                canonical_path=str(stored_path),
                aliases=[str(stored_path)],
                title=title,
                doc_format=parsed.doc_format,
                content_hash=content_hash,
                modified_at=datetime.fromtimestamp(stored_path.stat().st_mtime, tz=UTC),
            )
            units = []
            extractions: list[EventExtraction] = []
            evidence_vectors: dict[str, np.ndarray] = {}
            event_vectors: dict[str, np.ndarray] = {}
            entity_vectors: dict[str, np.ndarray] = {}
            reused_projection = self.store.source_exists(source_id)
            before_requests = self._chat_model.request_count if self._chat_model is not None else 0
            if not reused_projection:
                chunking = SagChunkingConfig(
                    target_tokens=self.settings.chunk_target_tokens,
                    max_tokens=self.settings.chunk_max_tokens,
                )
                units = build_evidence_units(parsed, source_id=source_id, config=chunking)
                if not units:
                    raise ValueError("document parsing produced no evidence units")
                for batch in _batched(units, self.settings.extractor_batch_size):
                    extractions.extend(extractor.extract(batch))
                evidence_matrix = _embed(
                    provider,
                    [unit.content for unit in units],
                    batch_size=self.settings.embedding_batch_size,
                )
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
                    unit.evidence_id: evidence_matrix[index]
                    for index, unit in enumerate(units)
                }
                event_ids = [event_id_for(item) for item in extractions]
                event_vectors = {
                    event_id: event_matrix[index] for index, event_id in enumerate(event_ids)
                }
                entity_vectors = {
                    entity_id: entity_matrix[index] for index, entity_id in enumerate(entity_ids)
                }

            publication = self.store.publish_incremental(
                job_id=job_id,
                asset_id=asset_id,
                namespace=namespace,
                source_key=source_key,
                origin=origin,
                source=source,
                original_filename=safe_name,
                stored_path=str(stored_path),
                metadata=request.metadata,
                pipeline=contract,
                version_fingerprint=fingerprint,
                units=units,
                extractions=extractions,
                evidence_vectors=evidence_vectors,
                event_vectors=event_vectors,
                entity_vectors=entity_vectors,
            )
            after_requests = self._chat_model.request_count if self._chat_model is not None else 0
            return IngestionResult(
                job_id=job_id,
                status="published",
                asset_id=asset_id,
                version_id=str(publication["version_id"]),
                previous_version_id=publication.get("previous_version_id"),
                version_number=int(publication["version_number"]),
                source_id=source_id,
                content_hash=content_hash,
                namespace=namespace,
                title=title,
                stored_path=str(stored_path),
                index_version=str(publication["index_version"]),
                pipeline_signature=str(contract["signature"]),
                reused_projection=bool(publication["reused_projection"]),
                evidence_units=len(units),
                events=len(extractions),
                entities=len(collect_unique_entities(extractions)),
                llm_requests=after_requests - before_requests,
            )
        except Exception as exc:
            self.store.finish_ingestion_job(job_id, status="failed", error=str(exc))
            if created_stored_path is not None:
                created_stored_path.unlink(missing_ok=True)
                for parent in (created_stored_path.parent, created_stored_path.parent.parent):
                    try:
                        parent.rmdir()
                    except OSError:
                        break
            raise

    def close(self) -> None:
        if self._owns_chat_model and self._chat_model is not None:
            self._chat_model.close()
            self._chat_model = None
