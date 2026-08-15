from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from enterprise_sag.extraction import normalize_entity_name
from enterprise_sag.models import EventExtraction, EvidenceUnit, SourceDocument

_FTS_TERM = re.compile(r"[A-Za-z0-9_.+#/-]{2,}|[\u3400-\u9fff]{2,}")


def event_id_for(extraction: EventExtraction) -> str:
    digest = hashlib.sha256(
        f"{extraction.evidence_id}\0{extraction.event_text}".encode()
    ).hexdigest()
    return f"evt_{digest[:24]}"


def entity_id_for(name: str, entity_type: str) -> str:
    normalized = normalize_entity_name(name)
    digest = hashlib.sha256(f"{entity_type}\0{normalized}".encode()).hexdigest()
    return f"ent_{digest[:24]}"


def asset_id_for(namespace: str, source_key: str) -> str:
    digest = hashlib.sha256(f"{namespace}\0{source_key}".encode()).hexdigest()
    return f"ast_{digest[:24]}"


def version_id_for(asset_id: str, content_hash: str) -> str:
    digest = hashlib.sha256(f"{asset_id}\0{content_hash}".encode()).hexdigest()
    return f"ver_{digest[:24]}"


def vector_to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).reshape(-1).tobytes()


def blob_to_vector(value: bytes) -> np.ndarray:
    return np.frombuffer(value, dtype=np.float32).copy()


class SagSqliteStore:
    """Disposable SAG read projection: SQL relations, FTS, and embedding vectors."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            DROP TRIGGER IF EXISTS immutable_source_assets_update;
            DROP TRIGGER IF EXISTS immutable_source_assets_delete;
            DROP TRIGGER IF EXISTS immutable_source_versions_update;
            DROP TRIGGER IF EXISTS immutable_source_versions_delete;
            DROP TABLE IF EXISTS source_asset_projection;
            DROP TABLE IF EXISTS source_versions;
            DROP TABLE IF EXISTS source_assets;
            DROP TABLE IF EXISTS ingestion_jobs;
            DROP TABLE IF EXISTS event_fts;
            DROP TABLE IF EXISTS evidence_fts;
            DROP TABLE IF EXISTS event_entities;
            DROP TABLE IF EXISTS entities;
            DROP TABLE IF EXISTS events;
            DROP TABLE IF EXISTS evidence_units;
            DROP TABLE IF EXISTS source_aliases;
            DROP TABLE IF EXISTS sources;
            DROP TABLE IF EXISTS index_metadata;

            CREATE TABLE index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE sources (
                source_id TEXT PRIMARY KEY,
                canonical_path TEXT NOT NULL,
                title TEXT NOT NULL,
                doc_format TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                modified_at TEXT
            );

            CREATE TABLE source_aliases (
                alias_path TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE
            );

            CREATE TABLE evidence_units (
                evidence_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                title TEXT NOT NULL,
                section_path_json TEXT NOT NULL,
                anchors_json TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                vector BLOB NOT NULL,
                UNIQUE(source_id, ordinal)
            );

            CREATE TABLE events (
                event_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL UNIQUE
                    REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
                event_text TEXT NOT NULL,
                event_time TEXT,
                extraction_method TEXT NOT NULL,
                vector BLOB NOT NULL
            );

            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                normalized_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                vector BLOB NOT NULL,
                UNIQUE(entity_type, normalized_name)
            );

            CREATE TABLE event_entities (
                event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
                PRIMARY KEY(event_id, entity_id)
            );

            CREATE INDEX idx_evidence_source ON evidence_units(source_id, ordinal);
            CREATE INDEX idx_event_entities_entity ON event_entities(entity_id, event_id);
            CREATE INDEX idx_event_entities_event ON event_entities(event_id, entity_id);
            CREATE INDEX idx_entities_name ON entities(normalized_name, entity_type);

            CREATE VIRTUAL TABLE event_fts USING fts5(
                event_id UNINDEXED,
                event_text,
                tokenize='unicode61'
            );
            CREATE VIRTUAL TABLE evidence_fts USING fts5(
                evidence_id UNINDEXED,
                content,
                tokenize='unicode61'
            );
            """
        )
        SagSqliteStore._create_ingestion_schema(connection)

    @staticmethod
    def _create_ingestion_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_assets (
                asset_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                source_key TEXT NOT NULL,
                origin TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(namespace, source_key)
            );

            CREATE TABLE IF NOT EXISTS source_versions (
                version_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL REFERENCES source_assets(asset_id),
                version_number INTEGER NOT NULL,
                source_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                version_fingerprint TEXT NOT NULL,
                title TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                doc_format TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                pipeline_signature TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(asset_id, version_number),
                UNIQUE(asset_id, version_fingerprint)
            );

            CREATE TABLE IF NOT EXISTS source_asset_projection (
                asset_id TEXT PRIMARY KEY REFERENCES source_assets(asset_id),
                active_version_id TEXT NOT NULL UNIQUE REFERENCES source_versions(version_id),
                activated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ingestion_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                filename TEXT NOT NULL,
                asset_id TEXT,
                version_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_source_versions_source
                ON source_versions(source_id, version_id);
            CREATE INDEX IF NOT EXISTS idx_source_versions_asset
                ON source_versions(asset_id, version_number);

            CREATE TRIGGER IF NOT EXISTS immutable_source_assets_update
            BEFORE UPDATE ON source_assets BEGIN
                SELECT RAISE(ABORT, 'source_assets is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_source_assets_delete
            BEFORE DELETE ON source_assets BEGIN
                SELECT RAISE(ABORT, 'source_assets is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_source_versions_update
            BEFORE UPDATE ON source_versions BEGIN
                SELECT RAISE(ABORT, 'source_versions is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_source_versions_delete
            BEFORE DELETE ON source_versions BEGIN
                SELECT RAISE(ABORT, 'source_versions is append-only');
            END;
            """
        )

    def replace_projection(
        self,
        *,
        metadata: Mapping[str, object],
        sources: Sequence[SourceDocument],
        units: Sequence[EvidenceUnit],
        extractions: Sequence[EventExtraction],
        evidence_vectors: Mapping[str, np.ndarray],
        event_vectors: Mapping[str, np.ndarray],
        entity_vectors: Mapping[str, np.ndarray],
    ) -> None:
        """Build a complete staging database and publish it with one filesystem replace."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.initialize_incremental_schema()
        staging_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.staging")
        staging_store = SagSqliteStore(staging_path)
        try:
            staging_store._write_projection(
                metadata=metadata,
                sources=sources,
                units=units,
                extractions=extractions,
                evidence_vectors=evidence_vectors,
                event_vectors=event_vectors,
                entity_vectors=entity_vectors,
                bootstrap_ledger=False,
            )
            if self.path.exists():
                staging_store._copy_ingestion_ledger_from(self.path)
            staging_store._reconcile_full_projection(sources=sources, metadata=metadata)
            if staging_store.integrity_check() != "ok":
                raise RuntimeError("Staged SAG SQLite projection failed integrity_check")
            os.replace(staging_path, self.path)
        finally:
            for candidate in (
                staging_path,
                Path(f"{staging_path}-wal"),
                Path(f"{staging_path}-shm"),
            ):
                candidate.unlink(missing_ok=True)

    def _write_projection(
        self,
        *,
        metadata: Mapping[str, object],
        sources: Sequence[SourceDocument],
        units: Sequence[EvidenceUnit],
        extractions: Sequence[EventExtraction],
        evidence_vectors: Mapping[str, np.ndarray],
        event_vectors: Mapping[str, np.ndarray],
        entity_vectors: Mapping[str, np.ndarray],
        bootstrap_ledger: bool = True,
    ) -> None:
        extraction_by_evidence = {item.evidence_id: item for item in extractions}
        with self._connect() as connection:
            self._create_schema(connection)
            connection.executemany(
                "INSERT INTO index_metadata(key, value) VALUES (?, ?)",
                [
                    (key, json.dumps(value, ensure_ascii=False, default=str))
                    for key, value in metadata.items()
                ],
            )

            for source in sources:
                connection.execute(
                    """INSERT INTO sources(
                        source_id, canonical_path, title, doc_format, content_hash, modified_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        source.source_id,
                        source.canonical_path,
                        source.title,
                        source.doc_format,
                        source.content_hash,
                        source.modified_at.isoformat() if source.modified_at else None,
                    ),
                )
                connection.executemany(
                    "INSERT INTO source_aliases(alias_path, source_id) VALUES (?, ?)",
                    [(alias, source.source_id) for alias in source.aliases],
                )

            for unit in units:
                connection.execute(
                    """INSERT INTO evidence_units(
                        evidence_id, source_id, ordinal, title, section_path_json,
                        anchors_json, content, content_hash, vector
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        unit.evidence_id,
                        unit.source_id,
                        unit.ordinal,
                        unit.title,
                        json.dumps(unit.section_path, ensure_ascii=False),
                        json.dumps(unit.anchors, ensure_ascii=False),
                        unit.content,
                        unit.content_hash,
                        vector_to_blob(evidence_vectors[unit.evidence_id]),
                    ),
                )
                connection.execute(
                    "INSERT INTO evidence_fts(evidence_id, content) VALUES (?, ?)",
                    (unit.evidence_id, unit.content),
                )

                extraction = extraction_by_evidence[unit.evidence_id]
                event_id = event_id_for(extraction)
                connection.execute(
                    """INSERT INTO events(
                        event_id, evidence_id, event_text, event_time,
                        extraction_method, vector
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        unit.evidence_id,
                        extraction.event_text,
                        extraction.event_time,
                        extraction.extraction_method,
                        vector_to_blob(event_vectors[event_id]),
                    ),
                )
                connection.execute(
                    "INSERT INTO event_fts(event_id, event_text) VALUES (?, ?)",
                    (event_id, extraction.event_text),
                )

                for entity in extraction.entities:
                    entity_id = entity_id_for(entity.name, entity.entity_type)
                    connection.execute(
                        """INSERT OR IGNORE INTO entities(
                            entity_id, normalized_name, display_name, entity_type, vector
                        ) VALUES (?, ?, ?, ?, ?)""",
                        (
                            entity_id,
                            normalize_entity_name(entity.name),
                            entity.name,
                            entity.entity_type,
                            vector_to_blob(entity_vectors[entity_id]),
                        ),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO event_entities(event_id, entity_id) VALUES (?, ?)",
                        (event_id, entity_id),
                    )

            if bootstrap_ledger:
                self._bootstrap_existing_sources(connection, metadata=metadata)

    def _copy_ingestion_ledger_from(self, source_path: Path) -> None:
        """Copy immutable source history into a staged full-build projection."""

        if not source_path.exists():
            return
        old = sqlite3.connect(source_path)
        old.row_factory = sqlite3.Row
        try:
            if not self._table_exists(old, "source_assets"):
                return
            rows_by_table = {
                table: old.execute(f"SELECT * FROM {table}").fetchall()
                for table in ("source_assets", "source_versions", "ingestion_jobs")
            }
            projection_rows = old.execute("SELECT * FROM source_asset_projection").fetchall()
        finally:
            old.close()
        with self._connect() as connection:
            for row in rows_by_table["source_assets"]:
                connection.execute(
                    """INSERT OR IGNORE INTO source_assets(
                        asset_id, namespace, source_key, origin, created_at
                    ) VALUES (?, ?, ?, ?, ?)""",
                    tuple(row),
                )
            for row in rows_by_table["source_versions"]:
                connection.execute(
                    """INSERT OR IGNORE INTO source_versions(
                        version_id, asset_id, version_number, source_id, content_hash,
                        version_fingerprint, title, original_filename, stored_path,
                        doc_format, metadata_json, pipeline_signature, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    tuple(row),
                )
            for row in rows_by_table["ingestion_jobs"]:
                connection.execute(
                    """INSERT OR IGNORE INTO ingestion_jobs(
                        job_id, status, filename, asset_id, version_id, error,
                        created_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    tuple(row),
                )
            for row in projection_rows:
                connection.execute(
                    """INSERT OR IGNORE INTO source_asset_projection(
                        asset_id, active_version_id, activated_at
                    ) VALUES (?, ?, ?)""",
                    tuple(row),
                )

    def _reconcile_full_projection(
        self,
        *,
        sources: Sequence[SourceDocument],
        metadata: Mapping[str, object],
    ) -> None:
        """Make the staged ledger's active set match exactly the rebuilt corpus."""

        now = datetime.now(UTC).isoformat()
        available_source_ids = {source.source_id for source in sources}
        signature = str(metadata.get("pipeline_signature") or "legacy-unknown")
        with self._connect() as connection:
            connection.execute(
                """DELETE FROM source_asset_projection
                   WHERE active_version_id IN (
                       SELECT version_id FROM source_versions
                       WHERE source_id NOT IN (SELECT source_id FROM sources)
                   )"""
            )
            for source in sources:
                existing_active = connection.execute(
                    """SELECT 1 FROM source_asset_projection sap
                       JOIN source_versions sv ON sv.version_id=sap.active_version_id
                       WHERE sv.source_id=? LIMIT 1""",
                    (source.source_id,),
                ).fetchone()
                if existing_active is not None:
                    continue

                candidates = [source.canonical_path, *source.aliases]
                asset = None
                for candidate in candidates:
                    asset = connection.execute(
                        "SELECT * FROM source_assets WHERE source_key=? LIMIT 1",
                        (candidate,),
                    ).fetchone()
                    if asset is not None:
                        break
                if asset is None:
                    source_key = source.canonical_path
                    asset_id = asset_id_for("legacy_root", source_key.casefold())
                    connection.execute(
                        """INSERT OR IGNORE INTO source_assets(
                            asset_id, namespace, source_key, origin, created_at
                        ) VALUES (?, 'legacy_root', ?, 'root', ?)""",
                        (asset_id, source_key, now),
                    )
                else:
                    asset_id = str(asset["asset_id"])

                version = connection.execute(
                    """SELECT * FROM source_versions
                       WHERE asset_id=? AND content_hash=? ORDER BY version_number DESC LIMIT 1""",
                    (asset_id, source.content_hash),
                ).fetchone()
                if version is None:
                    version_number = int(
                        connection.execute(
                            """SELECT COALESCE(MAX(version_number), 0) + 1
                               FROM source_versions WHERE asset_id=?""",
                            (asset_id,),
                        ).fetchone()[0]
                    )
                    fingerprint = source.content_hash
                    version_id = version_id_for(asset_id, fingerprint)
                    connection.execute(
                        """INSERT INTO source_versions(
                            version_id, asset_id, version_number, source_id, content_hash,
                            version_fingerprint, title, original_filename, stored_path,
                            doc_format, metadata_json, pipeline_signature, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)""",
                        (
                            version_id,
                            asset_id,
                            version_number,
                            source.source_id,
                            source.content_hash,
                            fingerprint,
                            source.title,
                            Path(source.canonical_path).name,
                            source.canonical_path,
                            source.doc_format,
                            signature,
                            now,
                        ),
                    )
                else:
                    version_id = str(version["version_id"])
                connection.execute(
                    """INSERT INTO source_asset_projection(
                           asset_id, active_version_id, activated_at
                       )
                       VALUES (?, ?, ?)
                       ON CONFLICT(asset_id) DO UPDATE SET
                           active_version_id=excluded.active_version_id,
                           activated_at=excluded.activated_at""",
                    (asset_id, version_id, now),
                )
            active_source_ids = {
                str(row[0])
                for row in connection.execute(
                    """SELECT DISTINCT sv.source_id FROM source_asset_projection sap
                       JOIN source_versions sv ON sv.version_id=sap.active_version_id"""
                ).fetchall()
            }
            if active_source_ids != available_source_ids:
                missing = sorted(available_source_ids - active_source_ids)
                extra = sorted(active_source_ids - available_source_ids)
                raise RuntimeError(
                    "full projection ledger reconciliation failed: "
                    f"missing={missing}, extra={extra}"
                )

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _metadata_from_connection(connection: sqlite3.Connection) -> dict[str, object]:
        if not SagSqliteStore._table_exists(connection, "index_metadata"):
            return {}
        rows = connection.execute("SELECT key, value FROM index_metadata").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    @staticmethod
    def _set_metadata(connection: sqlite3.Connection, values: Mapping[str, object]) -> None:
        connection.executemany(
            """INSERT INTO index_metadata(key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            [
                (key, json.dumps(value, ensure_ascii=False, default=str))
                for key, value in values.items()
            ],
        )

    @staticmethod
    def _bootstrap_existing_sources(
        connection: sqlite3.Connection,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Represent a legacy/full-build projection in the immutable source ledger."""

        SagSqliteStore._create_ingestion_schema(connection)
        if int(connection.execute("SELECT COUNT(*) FROM source_assets").fetchone()[0]) > 0:
            return
        resolved_metadata = dict(metadata or SagSqliteStore._metadata_from_connection(connection))
        signature = str(resolved_metadata.get("pipeline_signature") or "legacy-unknown")
        now = datetime.now(UTC).isoformat()
        rows = connection.execute(
            """SELECT source_id, canonical_path, title, doc_format, content_hash
               FROM sources ORDER BY canonical_path"""
        ).fetchall()
        for row in rows:
            source_key = str(row["canonical_path"])
            asset_id = asset_id_for("legacy_root", source_key.casefold())
            version_id = version_id_for(asset_id, str(row["content_hash"]))
            connection.execute(
                """INSERT OR IGNORE INTO source_assets(
                    asset_id, namespace, source_key, origin, created_at
                ) VALUES (?, ?, ?, 'root', ?)""",
                (asset_id, "legacy_root", source_key, now),
            )
            connection.execute(
                """INSERT OR IGNORE INTO source_versions(
                    version_id, asset_id, version_number, source_id, content_hash,
                    version_fingerprint, title, original_filename, stored_path,
                    doc_format, metadata_json,
                    pipeline_signature, created_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)""",
                (
                    version_id,
                    asset_id,
                    row["source_id"],
                    row["content_hash"],
                    row["content_hash"],
                    row["title"],
                    Path(source_key).name,
                    source_key,
                    row["doc_format"],
                    signature,
                    now,
                ),
            )
            connection.execute(
                """INSERT OR IGNORE INTO source_asset_projection(
                    asset_id, active_version_id, activated_at
                ) VALUES (?, ?, ?)""",
                (asset_id, version_id, now),
            )

    def initialize_incremental_schema(
        self,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Migrate an existing projection in place, or initialize an empty one."""

        with self._connect() as connection:
            if not self._table_exists(connection, "sources"):
                self._create_schema(connection)
                self._set_metadata(connection, metadata or {})
            else:
                self._create_ingestion_schema(connection)
            self._bootstrap_existing_sources(connection, metadata=metadata)

    def assert_incremental_compatible(self, contract: Mapping[str, object]) -> None:
        """Reject mixed chunk/extractor/vector artifacts in one active projection."""

        self.initialize_incremental_schema(metadata=contract)
        current = self.metadata()
        mismatches: list[str] = []
        for key in ("chunking", "extractor", "embedding_backend", "embedding_dimensions"):
            existing = current.get(key)
            proposed = contract.get(key)
            if existing is not None and existing != proposed:
                mismatches.append(f"{key}: index={existing!r}, request={proposed!r}")
        if mismatches:
            raise ValueError(
                "Incremental ingestion pipeline does not match the active index; "
                "run a full rebuild before publishing. " + "; ".join(mismatches)
            )

    def resolve_asset(
        self,
        *,
        asset_id: str | None,
        namespace: str,
        source_key: str | None,
    ) -> dict[str, object] | None:
        self.initialize_incremental_schema()
        with self._connect() as connection:
            if asset_id:
                row = connection.execute(
                    "SELECT * FROM source_assets WHERE asset_id=?", (asset_id,)
                ).fetchone()
            elif source_key:
                row = connection.execute(
                    "SELECT * FROM source_assets WHERE namespace=? AND source_key=?",
                    (namespace, source_key),
                ).fetchone()
            else:
                row = None
        return dict(row) if row is not None else None

    def active_version(self, asset_id: str) -> dict[str, object] | None:
        self.initialize_incremental_schema()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT sv.* FROM source_asset_projection sap
                   JOIN source_versions sv ON sv.version_id=sap.active_version_id
                   WHERE sap.asset_id=?""",
                (asset_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def source_exists(self, source_id: str) -> bool:
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM sources WHERE source_id=?", (source_id,)
                ).fetchone()
                is not None
            )

    def create_ingestion_job(self, filename: str) -> str:
        self.initialize_incremental_schema()
        job_id = f"ing_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO ingestion_jobs(job_id, status, filename, created_at)
                   VALUES (?, 'processing', ?, ?)""",
                (job_id, filename, datetime.now(UTC).isoformat()),
            )
        return job_id

    def finish_ingestion_job(
        self,
        job_id: str,
        *,
        status: str,
        asset_id: str | None = None,
        version_id: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE ingestion_jobs
                   SET status=?, asset_id=?, version_id=?, error=?, completed_at=?
                   WHERE job_id=?""",
                (
                    status,
                    asset_id,
                    version_id,
                    error,
                    datetime.now(UTC).isoformat(),
                    job_id,
                ),
            )

    @staticmethod
    def _insert_incremental_source(
        connection: sqlite3.Connection,
        *,
        source: SourceDocument,
        units: Sequence[EvidenceUnit],
        extractions: Sequence[EventExtraction],
        evidence_vectors: Mapping[str, np.ndarray],
        event_vectors: Mapping[str, np.ndarray],
        entity_vectors: Mapping[str, np.ndarray],
    ) -> None:
        connection.execute(
            """INSERT INTO sources(
                source_id, canonical_path, title, doc_format, content_hash, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                source.source_id,
                source.canonical_path,
                source.title,
                source.doc_format,
                source.content_hash,
                source.modified_at.isoformat() if source.modified_at else None,
            ),
        )
        extraction_by_evidence = {item.evidence_id: item for item in extractions}
        for unit in units:
            connection.execute(
                """INSERT INTO evidence_units(
                    evidence_id, source_id, ordinal, title, section_path_json,
                    anchors_json, content, content_hash, vector
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    unit.evidence_id,
                    unit.source_id,
                    unit.ordinal,
                    unit.title,
                    json.dumps(unit.section_path, ensure_ascii=False),
                    json.dumps(unit.anchors, ensure_ascii=False),
                    unit.content,
                    unit.content_hash,
                    vector_to_blob(evidence_vectors[unit.evidence_id]),
                ),
            )
            connection.execute(
                "INSERT INTO evidence_fts(evidence_id, content) VALUES (?, ?)",
                (unit.evidence_id, unit.content),
            )
            extraction = extraction_by_evidence[unit.evidence_id]
            event_id = event_id_for(extraction)
            connection.execute(
                """INSERT INTO events(
                    event_id, evidence_id, event_text, event_time, extraction_method, vector
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    unit.evidence_id,
                    extraction.event_text,
                    extraction.event_time,
                    extraction.extraction_method,
                    vector_to_blob(event_vectors[event_id]),
                ),
            )
            connection.execute(
                "INSERT INTO event_fts(event_id, event_text) VALUES (?, ?)",
                (event_id, extraction.event_text),
            )
            for entity in extraction.entities:
                entity_id = entity_id_for(entity.name, entity.entity_type)
                connection.execute(
                    """INSERT OR IGNORE INTO entities(
                        entity_id, normalized_name, display_name, entity_type, vector
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        entity_id,
                        normalize_entity_name(entity.name),
                        entity.name,
                        entity.entity_type,
                        vector_to_blob(entity_vectors[entity_id]),
                    ),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO event_entities(event_id, entity_id) VALUES (?, ?)",
                    (event_id, entity_id),
                )

    def publish_incremental(
        self,
        *,
        job_id: str,
        asset_id: str,
        namespace: str,
        source_key: str,
        origin: str,
        source: SourceDocument,
        original_filename: str,
        stored_path: str,
        metadata: Mapping[str, object],
        pipeline: Mapping[str, object],
        version_fingerprint: str,
        units: Sequence[EvidenceUnit],
        extractions: Sequence[EventExtraction],
        evidence_vectors: Mapping[str, np.ndarray],
        event_vectors: Mapping[str, np.ndarray],
        entity_vectors: Mapping[str, np.ndarray],
    ) -> dict[str, object]:
        """Append one immutable source version and atomically switch its read projection."""

        now = datetime.now(UTC).isoformat()
        version_id = version_id_for(asset_id, version_fingerprint)
        with self._connect() as connection:
            self._create_ingestion_schema(connection)
            previous = connection.execute(
                """SELECT sv.* FROM source_asset_projection sap
                   JOIN source_versions sv ON sv.version_id=sap.active_version_id
                   WHERE sap.asset_id=?""",
                (asset_id,),
            ).fetchone()
            connection.execute(
                """INSERT OR IGNORE INTO source_assets(
                    asset_id, namespace, source_key, origin, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (asset_id, namespace, source_key, origin, now),
            )
            existing_asset = connection.execute(
                "SELECT namespace, source_key FROM source_assets WHERE asset_id=?", (asset_id,)
            ).fetchone()
            if existing_asset is None:
                raise RuntimeError("failed to create source asset")
            if (
                existing_asset["namespace"] != namespace
                or existing_asset["source_key"] != source_key
            ):
                raise ValueError("asset_id belongs to a different namespace or source_key")

            version = connection.execute(
                "SELECT * FROM source_versions WHERE asset_id=? AND version_fingerprint=?",
                (asset_id, version_fingerprint),
            ).fetchone()
            if version is None:
                version_number = int(
                    connection.execute(
                        """SELECT COALESCE(MAX(version_number), 0) + 1
                           FROM source_versions WHERE asset_id=?""",
                        (asset_id,),
                    ).fetchone()[0]
                )
                connection.execute(
                    """INSERT INTO source_versions(
                        version_id, asset_id, version_number, source_id, content_hash,
                        version_fingerprint, title, original_filename, stored_path,
                        doc_format, metadata_json,
                        pipeline_signature, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        version_id,
                        asset_id,
                        version_number,
                        source.source_id,
                        source.content_hash,
                        version_fingerprint,
                        source.title,
                        original_filename,
                        stored_path,
                        source.doc_format,
                        json.dumps(metadata, ensure_ascii=False, default=str),
                        pipeline["signature"],
                        now,
                    ),
                )
            else:
                version_id = str(version["version_id"])
                version_number = int(version["version_number"])

            reused_projection = (
                connection.execute(
                    "SELECT 1 FROM sources WHERE source_id=?", (source.source_id,)
                ).fetchone()
                is not None
            )
            if not reused_projection:
                self._insert_incremental_source(
                    connection,
                    source=source,
                    units=units,
                    extractions=extractions,
                    evidence_vectors=evidence_vectors,
                    event_vectors=event_vectors,
                    entity_vectors=entity_vectors,
                )
            connection.execute(
                """INSERT INTO source_aliases(alias_path, source_id) VALUES (?, ?)
                   ON CONFLICT(alias_path) DO UPDATE SET source_id=excluded.source_id""",
                (stored_path, source.source_id),
            )
            connection.execute(
                """INSERT INTO source_asset_projection(asset_id, active_version_id, activated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(asset_id) DO UPDATE SET
                       active_version_id=excluded.active_version_id,
                       activated_at=excluded.activated_at""",
                (asset_id, version_id, now),
            )
            generation = int(
                self._metadata_from_connection(connection).get("index_generation", 0)
            ) + 1
            index_version = f"sag-incremental-v1-{generation:08d}-{source.content_hash[:8]}"
            self._set_metadata(
                connection,
                {
                    **dict(pipeline),
                    "pipeline_signature": pipeline["signature"],
                    "index_generation": generation,
                    "index_version": index_version,
                    "created_at": now,
                    "agent_loop_integration": False,
                    "context_pack_mode": "draft-preview-only",
                },
            )
            connection.execute(
                """UPDATE ingestion_jobs SET status='published', asset_id=?, version_id=?,
                   completed_at=? WHERE job_id=?""",
                (asset_id, version_id, now, job_id),
            )
            return {
                "version_id": version_id,
                "version_number": version_number,
                "previous_version_id": str(previous["version_id"]) if previous else None,
                "index_version": index_version,
                "reused_projection": reused_projection,
            }

    def list_source_assets(self) -> list[dict[str, object]]:
        self.initialize_incremental_schema()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT sa.asset_id, sa.source_key, sa.namespace, sa.origin,
                          sv.version_id, sv.version_number, sv.source_id, sv.title,
                          sv.original_filename, sv.content_hash, sv.stored_path,
                          sv.metadata_json, sv.created_at,
                          (SELECT COUNT(*) FROM evidence_units eu
                           WHERE eu.source_id=sv.source_id) AS evidence_units,
                          (SELECT COUNT(*) FROM events ev JOIN evidence_units eu
                           ON eu.evidence_id=ev.evidence_id
                           WHERE eu.source_id=sv.source_id) AS events
                   FROM source_assets sa
                   JOIN source_asset_projection sap ON sap.asset_id=sa.asset_id
                   JOIN source_versions sv ON sv.version_id=sap.active_version_id
                   ORDER BY sv.created_at DESC, sa.asset_id"""
            ).fetchall()
        output: list[dict[str, object]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(str(item.pop("metadata_json")))
            output.append(item)
        return output

    def active_source_paths(self) -> list[Path]:
        self.initialize_incremental_schema()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT sv.stored_path FROM source_asset_projection sap
                   JOIN source_versions sv ON sv.version_id=sap.active_version_id
                   JOIN source_assets sa ON sa.asset_id=sap.asset_id
                   WHERE sa.origin='upload' ORDER BY sv.stored_path"""
            ).fetchall()
        return [Path(str(row["stored_path"])) for row in rows]

    def metadata(self) -> dict[str, object]:
        with self._connect() as connection:
            if not self._table_exists(connection, "index_metadata"):
                return {}
            rows = connection.execute("SELECT key, value FROM index_metadata").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def stats(self) -> dict[str, int]:
        tables = (
            "sources",
            "source_aliases",
            "evidence_units",
            "events",
            "entities",
            "event_entities",
        )
        with self._connect() as connection:
            if not self._table_exists(connection, "sources"):
                return {table: 0 for table in tables}
            has_projection = self._table_exists(connection, "source_asset_projection")
            if not has_projection:
                return {
                    table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in tables
                }
            active_sources = """SELECT DISTINCT sv.source_id
                FROM source_asset_projection sap
                JOIN source_versions sv ON sv.version_id=sap.active_version_id"""
            return {
                "sources": int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM sources WHERE source_id IN ({active_sources})"
                    ).fetchone()[0]
                ),
                "source_aliases": int(
                    connection.execute(
                        f"""SELECT COUNT(*) FROM source_aliases
                            WHERE source_id IN ({active_sources})"""
                    ).fetchone()[0]
                ),
                "evidence_units": int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM evidence_units WHERE source_id IN ({active_sources})"
                    ).fetchone()[0]
                ),
                "events": int(
                    connection.execute(
                        f"""SELECT COUNT(*) FROM events ev JOIN evidence_units eu
                            ON eu.evidence_id=ev.evidence_id
                            WHERE eu.source_id IN ({active_sources})"""
                    ).fetchone()[0]
                ),
                "entities": int(
                    connection.execute(
                        f"""SELECT COUNT(DISTINCT ee.entity_id) FROM event_entities ee
                            JOIN events ev ON ev.event_id=ee.event_id
                            JOIN evidence_units eu ON eu.evidence_id=ev.evidence_id
                            WHERE eu.source_id IN ({active_sources})"""
                    ).fetchone()[0]
                ),
                "event_entities": int(
                    connection.execute(
                        f"""SELECT COUNT(*) FROM event_entities ee
                            JOIN events ev ON ev.event_id=ee.event_id
                            JOIN evidence_units eu ON eu.evidence_id=ev.evidence_id
                            WHERE eu.source_id IN ({active_sources})"""
                    ).fetchone()[0]
                ),
            }

    def load_entities(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            if self._table_exists(connection, "source_asset_projection"):
                rows = connection.execute(
                    """SELECT DISTINCT entity.entity_id, entity.display_name,
                                      entity.entity_type, entity.vector
                       FROM entities entity
                       JOIN event_entities ee ON ee.entity_id=entity.entity_id
                       JOIN events ev ON ev.event_id=ee.event_id
                       JOIN evidence_units eu ON eu.evidence_id=ev.evidence_id
                       WHERE eu.source_id IN (
                           SELECT sv.source_id FROM source_asset_projection sap
                           JOIN source_versions sv ON sv.version_id=sap.active_version_id
                       )"""
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT entity_id, display_name, entity_type, vector FROM entities"
                ).fetchall()
        return [
            {
                "entity_id": row["entity_id"],
                "display_name": row["display_name"],
                "entity_type": row["entity_type"],
                "vector": blob_to_vector(row["vector"]),
            }
            for row in rows
        ]

    def load_events(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            if self._table_exists(connection, "source_asset_projection"):
                query = """
                    WITH selected_active_version AS (
                        SELECT sv.source_id, MIN(sv.version_id) AS version_id
                        FROM source_asset_projection sap
                        JOIN source_versions sv ON sv.version_id=sap.active_version_id
                        GROUP BY sv.source_id
                    )
                    SELECT ev.event_id, ev.evidence_id, ev.event_text, ev.event_time,
                           ev.vector, eu.source_id, sv.title, eu.section_path_json,
                           eu.anchors_json, eu.content, eu.vector AS evidence_vector,
                           sv.stored_path AS canonical_path
                    FROM events ev
                    JOIN evidence_units eu ON eu.evidence_id=ev.evidence_id
                    JOIN selected_active_version active ON active.source_id=eu.source_id
                    JOIN source_versions sv ON sv.version_id=active.version_id
                """
            else:
                query = """
                    SELECT ev.event_id, ev.evidence_id, ev.event_text, ev.event_time,
                           ev.vector, eu.source_id, eu.title, eu.section_path_json,
                           eu.anchors_json, eu.content, eu.vector AS evidence_vector,
                           s.canonical_path
                    FROM events ev
                    JOIN evidence_units eu ON eu.evidence_id=ev.evidence_id
                    JOIN sources s ON s.source_id=eu.source_id
                """
            rows = connection.execute(query).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "evidence_id": row["evidence_id"],
                "event_text": row["event_text"],
                "event_time": row["event_time"],
                "event_vector": blob_to_vector(row["vector"]),
                "evidence_vector": blob_to_vector(row["evidence_vector"]),
                "source_id": row["source_id"],
                "source_path": row["canonical_path"],
                "title": row["title"],
                "section_path": json.loads(row["section_path_json"]),
                "anchors": json.loads(row["anchors_json"]),
                "content": row["content"],
            }
            for row in rows
        ]

    def event_ids_for_entities(self, entity_ids: Sequence[str]) -> dict[str, list[str]]:
        if not entity_ids:
            return {}
        placeholders = ",".join("?" for _ in entity_ids)
        query = f"""
            SELECT ee.event_id, ee.entity_id
            FROM event_entities ee
            JOIN events ev ON ev.event_id=ee.event_id
            JOIN evidence_units eu ON eu.evidence_id=ev.evidence_id
            WHERE ee.entity_id IN ({placeholders})
        """
        output: dict[str, list[str]] = {}
        with self._connect() as connection:
            if self._table_exists(connection, "source_asset_projection"):
                query += """ AND eu.source_id IN (
                    SELECT sv.source_id FROM source_asset_projection sap
                    JOIN source_versions sv ON sv.version_id=sap.active_version_id
                )"""
            rows = connection.execute(query, list(entity_ids)).fetchall()
        for row in rows:
            output.setdefault(row["event_id"], []).append(row["entity_id"])
        return output

    def expand_events(self, event_ids: Sequence[str]) -> list[dict[str, str]]:
        """Instantiate local hyperedges with SQL joins over shared entities."""

        if not event_ids:
            return []
        placeholders = ",".join("?" for _ in event_ids)
        query = f"""
            SELECT seed.event_id AS seed_event_id,
                   neighbor.event_id AS neighbor_event_id,
                   entity.entity_id,
                   entity.display_name
            FROM event_entities seed
            JOIN event_entities neighbor
              ON neighbor.entity_id = seed.entity_id
             AND neighbor.event_id != seed.event_id
            JOIN entities entity ON entity.entity_id = seed.entity_id
            JOIN events neighbor_event ON neighbor_event.event_id=neighbor.event_id
            JOIN evidence_units neighbor_evidence
              ON neighbor_evidence.evidence_id=neighbor_event.evidence_id
            WHERE seed.event_id IN ({placeholders})
        """
        with self._connect() as connection:
            if self._table_exists(connection, "source_asset_projection"):
                query += """ AND neighbor_evidence.source_id IN (
                    SELECT sv.source_id FROM source_asset_projection sap
                    JOIN source_versions sv ON sv.version_id=sap.active_version_id
                )"""
            rows = connection.execute(query, list(event_ids)).fetchall()
        return [dict(row) for row in rows]

    def event_entities(self, event_ids: Sequence[str]) -> dict[str, list[dict[str, str]]]:
        if not event_ids:
            return {}
        placeholders = ",".join("?" for _ in event_ids)
        query = f"""
            SELECT ee.event_id, e.entity_id, e.display_name, e.entity_type
            FROM event_entities ee
            JOIN entities e ON e.entity_id = ee.entity_id
            WHERE ee.event_id IN ({placeholders})
        """
        output: dict[str, list[dict[str, str]]] = {}
        with self._connect() as connection:
            rows = connection.execute(query, list(event_ids)).fetchall()
        for row in rows:
            output.setdefault(row["event_id"], []).append(
                {
                    "entity_id": row["entity_id"],
                    "display_name": row["display_name"],
                    "entity_type": row["entity_type"],
                }
            )
        return output

    @staticmethod
    def _fts_query(text: str) -> str | None:
        terms = list(dict.fromkeys(_FTS_TERM.findall(text.lower())))[:12]
        return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms) or None

    def search_event_fts(self, text: str, *, limit: int) -> list[str]:
        query = self._fts_query(text)
        if query is None:
            return []
        try:
            with self._connect() as connection:
                if self._table_exists(connection, "source_asset_projection"):
                    rows = connection.execute(
                        """SELECT event_fts.event_id FROM event_fts
                           JOIN events ev ON ev.event_id=event_fts.event_id
                           JOIN evidence_units eu ON eu.evidence_id=ev.evidence_id
                           WHERE event_fts MATCH ? AND eu.source_id IN (
                               SELECT sv.source_id FROM source_asset_projection sap
                               JOIN source_versions sv ON sv.version_id=sap.active_version_id
                           )
                           ORDER BY bm25(event_fts) LIMIT ?""",
                        (query, limit),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """SELECT event_id FROM event_fts
                           WHERE event_fts MATCH ? ORDER BY bm25(event_fts) LIMIT ?""",
                        (query, limit),
                    ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [row["event_id"] for row in rows]

    def source_aliases(self, source_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT alias_path FROM source_aliases WHERE source_id=? ORDER BY alias_path",
                (source_id,),
            ).fetchall()
        return [row["alias_path"] for row in rows]

    def integrity_check(self) -> str:
        with self._connect() as connection:
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def collect_unique_entities(
    extractions: Iterable[EventExtraction],
) -> dict[str, tuple[str, str]]:
    output: dict[str, tuple[str, str]] = {}
    for extraction in extractions:
        for entity in extraction.entities:
            entity_id = entity_id_for(entity.name, entity.entity_type)
            output.setdefault(entity_id, (entity.name, entity.entity_type))
    return output
