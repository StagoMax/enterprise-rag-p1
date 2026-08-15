from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from enterprise_sag.store import blob_to_vector, vector_to_blob
from enterprise_sag.temporal_models import (
    AssertionLifecycle,
    AssertionRelation,
    AssertionState,
    AssertionUsageStats,
    ConsolidationProposal,
    MemoryEvent,
    TemporalAssertion,
    TemporalRelationType,
    TemporalUsageEvent,
)

_FTS_TERM = re.compile(r"[A-Za-z0-9_.+#/-]{2,}|[\u3400-\u9fff]{2,}")
_INVALIDATING_RELATIONS = {
    TemporalRelationType.SUPERSEDES,
    TemporalRelationType.CORRECTS,
    TemporalRelationType.RETRACTS,
}
_LIFECYCLE_BY_RELATION = {
    TemporalRelationType.SUPERSEDES: AssertionLifecycle.SUPERSEDED,
    TemporalRelationType.CORRECTS: AssertionLifecycle.CORRECTED,
    TemporalRelationType.RETRACTS: AssertionLifecycle.RETRACTED,
}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _fts_query(text: str) -> str:
    terms = list(dict.fromkeys(_FTS_TERM.findall(text)))[:24]
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


class TemporalMemoryStore:
    """Append-only temporal ledger plus disposable read projections."""

    schema_version = 2

    def __init__(self, path: Path) -> None:
        self.path = path
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS temporal_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_events (
                    event_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    occurred_at TEXT,
                    observed_at TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT,
                    session_id TEXT,
                    metadata_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS temporal_assertions (
                    assertion_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES memory_events(event_id),
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_text TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    importance REAL NOT NULL,
                    extraction_method TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assertion_relations (
                    relation_id TEXT PRIMARY KEY,
                    source_assertion_id TEXT REFERENCES temporal_assertions(assertion_id),
                    target_assertion_id TEXT NOT NULL REFERENCES temporal_assertions(assertion_id),
                    source_event_id TEXT NOT NULL REFERENCES memory_events(event_id),
                    relation_type TEXT NOT NULL,
                    effective_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS consolidation_runs (
                    proposal_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES memory_events(event_id),
                    planner TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assertion_usage_events (
                    usage_id TEXT PRIMARY KEY,
                    assertion_id TEXT NOT NULL REFERENCES temporal_assertions(assertion_id),
                    outcome TEXT NOT NULL,
                    query_ref TEXT,
                    context TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assertion_embedding_projection (
                    assertion_id TEXT PRIMARY KEY REFERENCES temporal_assertions(assertion_id)
                        ON DELETE CASCADE,
                    backend TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    computed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS current_assertion_projection (
                    assertion_id TEXT PRIMARY KEY REFERENCES temporal_assertions(assertion_id)
                        ON DELETE CASCADE,
                    subject_id TEXT NOT NULL,
                    lifecycle TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    changed_by_assertion_id TEXT,
                    changed_by_relation_id TEXT,
                    contradiction_count INTEGER NOT NULL,
                    reinforcement_count INTEGER NOT NULL,
                    computed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projection_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS assertion_fts USING fts5(
                    assertion_id UNINDEXED,
                    text,
                    tokenize='unicode61'
                );

                CREATE INDEX IF NOT EXISTS idx_memory_events_subject
                    ON memory_events(subject_id, observed_at, recorded_at);
                CREATE INDEX IF NOT EXISTS idx_temporal_assertions_subject
                    ON temporal_assertions(subject_id, predicate, scope, valid_from);
                CREATE INDEX IF NOT EXISTS idx_relations_target
                    ON assertion_relations(target_assertion_id, effective_at, recorded_at);
                CREATE INDEX IF NOT EXISTS idx_relations_source
                    ON assertion_relations(source_assertion_id, effective_at, recorded_at);
                CREATE INDEX IF NOT EXISTS idx_usage_assertion
                    ON assertion_usage_events(assertion_id, occurred_at);
                """
            )
            projection_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(current_assertion_projection)"
                ).fetchall()
            }
            if "reinforcement_count" not in projection_columns:
                connection.execute(
                    """ALTER TABLE current_assertion_projection
                       ADD COLUMN reinforcement_count INTEGER NOT NULL DEFAULT 0"""
                )
            connection.execute(
                """INSERT INTO temporal_metadata(key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                ("schema_version", json.dumps(self.schema_version)),
            )
            self._install_append_only_triggers(connection)
            connection.commit()

    @staticmethod
    def _install_append_only_triggers(connection: sqlite3.Connection) -> None:
        for table in (
            "memory_events",
            "temporal_assertions",
            "assertion_relations",
            "consolidation_runs",
            "assertion_usage_events",
        ):
            connection.executescript(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_reject_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, '{table} is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS {table}_reject_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, '{table} is append-only');
                END;
                """
            )

    def append_event(self, event: MemoryEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO memory_events(
                    event_id, subject_id, content, content_hash, occurred_at, observed_at,
                    source_kind, source_ref, session_id, metadata_json, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.subject_id,
                    event.content,
                    event.content_hash,
                    _iso(event.occurred_at) if event.occurred_at else None,
                    _iso(event.observed_at),
                    event.source_kind,
                    event.source_ref,
                    event.session_id,
                    json.dumps(event.metadata, ensure_ascii=False, default=str),
                    _iso(event.recorded_at),
                ),
            )
            connection.commit()

    def get_event(self, event_id: str) -> MemoryEvent:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown memory event: {event_id}")
        return self._event_from_row(row)

    def pending_events(self, *, limit: int = 100) -> list[MemoryEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT e.*
                   FROM memory_events e
                   WHERE NOT EXISTS (
                       SELECT 1 FROM consolidation_runs c WHERE c.event_id = e.event_id
                   )
                   ORDER BY e.observed_at, e.recorded_at
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> MemoryEvent:
        return MemoryEvent(
            event_id=row["event_id"],
            subject_id=row["subject_id"],
            content=row["content"],
            content_hash=row["content_hash"],
            occurred_at=_datetime(row["occurred_at"]) if row["occurred_at"] else None,
            observed_at=_datetime(row["observed_at"]),
            source_kind=row["source_kind"],
            source_ref=row["source_ref"],
            session_id=row["session_id"],
            metadata=json.loads(row["metadata_json"]),
            recorded_at=_datetime(row["recorded_at"]),
        )

    def apply_consolidation(
        self,
        proposal: ConsolidationProposal,
        assertions: Sequence[TemporalAssertion],
        relations: Sequence[AssertionRelation],
        *,
        embedding_backend: str,
        embeddings: Mapping[str, np.ndarray],
    ) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM consolidation_runs WHERE proposal_id = ?",
                (proposal.proposal_id,),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                return False
            event_row = connection.execute(
                "SELECT subject_id FROM memory_events WHERE event_id = ?",
                (proposal.event_id,),
            ).fetchone()
            if event_row is None:
                raise KeyError(f"Unknown memory event: {proposal.event_id}")
            if event_row["subject_id"] != proposal.subject_id:
                raise ValueError("Proposal subject does not match the source event")

            for assertion in assertions:
                if assertion.event_id != proposal.event_id:
                    raise ValueError("Every assertion must originate from the proposal event")
                if assertion.subject_id != proposal.subject_id:
                    raise ValueError("Every assertion must preserve the proposal subject")
                connection.execute(
                    """INSERT INTO temporal_assertions(
                        assertion_id, event_id, subject_id, predicate, object_text, scope,
                        valid_from, confidence, importance, extraction_method, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        assertion.assertion_id,
                        assertion.event_id,
                        assertion.subject_id,
                        assertion.predicate,
                        assertion.object_text,
                        assertion.scope,
                        _iso(assertion.valid_from),
                        assertion.confidence,
                        assertion.importance,
                        assertion.extraction_method,
                        _iso(assertion.recorded_at),
                    ),
                )
                connection.execute(
                    "INSERT INTO assertion_fts(assertion_id, text) VALUES (?, ?)",
                    (
                        assertion.assertion_id,
                        f"{assertion.predicate} {assertion.scope} {assertion.object_text}",
                    ),
                )
                vector = embeddings[assertion.assertion_id]
                connection.execute(
                    """INSERT INTO assertion_embedding_projection(
                        assertion_id, backend, dimensions, vector, computed_at
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        assertion.assertion_id,
                        embedding_backend,
                        int(np.asarray(vector).size),
                        vector_to_blob(vector),
                        _iso(datetime.now(UTC)),
                    ),
                )

            for relation in relations:
                self._validate_relation(connection, relation, proposal.subject_id)
                connection.execute(
                    """INSERT INTO assertion_relations(
                        relation_id, source_assertion_id, target_assertion_id,
                        source_event_id, relation_type, effective_at, confidence,
                        rationale, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        relation.relation_id,
                        relation.source_assertion_id,
                        relation.target_assertion_id,
                        relation.source_event_id,
                        relation.relation_type.value,
                        _iso(relation.effective_at),
                        relation.confidence,
                        relation.rationale,
                        _iso(relation.recorded_at),
                    ),
                )

            connection.execute(
                """INSERT INTO consolidation_runs(
                    proposal_id, event_id, planner, proposal_json, applied_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    proposal.proposal_id,
                    proposal.event_id,
                    proposal.planner,
                    proposal.model_dump_json(),
                    _iso(datetime.now(UTC)),
                ),
            )
            self._rebuild_current_projection(connection, computed_at=datetime.now(UTC))
            connection.commit()
        return True

    @staticmethod
    def _validate_relation(
        connection: sqlite3.Connection,
        relation: AssertionRelation,
        subject_id: str,
    ) -> None:
        if relation.source_assertion_id == relation.target_assertion_id:
            raise ValueError("A temporal relation cannot point to itself")
        target = connection.execute(
            "SELECT subject_id FROM temporal_assertions WHERE assertion_id = ?",
            (relation.target_assertion_id,),
        ).fetchone()
        if target is None:
            raise KeyError(f"Unknown target assertion: {relation.target_assertion_id}")
        if target["subject_id"] != subject_id:
            raise ValueError("Temporal relations cannot cross subjects")
        if relation.source_assertion_id:
            source = connection.execute(
                "SELECT subject_id FROM temporal_assertions WHERE assertion_id = ?",
                (relation.source_assertion_id,),
            ).fetchone()
            if source is None:
                raise KeyError(f"Unknown source assertion: {relation.source_assertion_id}")
            if source["subject_id"] != subject_id:
                raise ValueError("Temporal relations cannot cross subjects")

    def resolve_states(
        self,
        subject_id: str,
        *,
        valid_at: datetime,
        known_at: datetime,
    ) -> list[AssertionState]:
        with self._connect() as connection:
            return self._resolve_states_from_connection(
                connection,
                subject_id,
                valid_at=valid_at,
                known_at=known_at,
            )

    def _resolve_states_from_connection(
        self,
        connection: sqlite3.Connection,
        subject_id: str,
        *,
        valid_at: datetime,
        known_at: datetime,
    ) -> list[AssertionState]:
        assertion_rows = connection.execute(
            """SELECT * FROM temporal_assertions
               WHERE subject_id = ? AND recorded_at <= ?
               ORDER BY valid_from, recorded_at, assertion_id""",
            (subject_id, _iso(known_at)),
        ).fetchall()
        assertions = [self._assertion_from_row(row) for row in assertion_rows]
        if not assertions:
            return []
        assertion_ids = {item.assertion_id for item in assertions}
        placeholders = ",".join("?" for _ in assertion_ids)
        relation_rows = connection.execute(
            f"""SELECT * FROM assertion_relations
                WHERE target_assertion_id IN ({placeholders}) AND recorded_at <= ?
                ORDER BY effective_at, recorded_at, relation_id""",
            (*sorted(assertion_ids), _iso(known_at)),
        ).fetchall()
        relations_by_target: dict[str, list[AssertionRelation]] = {}
        for row in relation_rows:
            relation = self._relation_from_row(row)
            relations_by_target.setdefault(relation.target_assertion_id, []).append(relation)

        valid_point = valid_at.astimezone(UTC)
        states: list[AssertionState] = []
        for assertion in assertions:
            if assertion.valid_from > valid_point:
                states.append(
                    AssertionState(
                        assertion=assertion,
                        lifecycle=AssertionLifecycle.FUTURE,
                    )
                )
                continue
            visible_relations = [
                relation
                for relation in relations_by_target.get(assertion.assertion_id, [])
                if relation.effective_at <= valid_point
            ]
            invalidating = [
                relation
                for relation in visible_relations
                if relation.relation_type in _INVALIDATING_RELATIONS
            ]
            reinforcement_count = sum(
                relation.relation_type == TemporalRelationType.REINFORCES
                for relation in visible_relations
            )
            if invalidating:
                change = min(
                    invalidating,
                    key=lambda item: (item.effective_at, item.recorded_at, item.relation_id),
                )
                states.append(
                    AssertionState(
                        assertion=assertion,
                        lifecycle=_LIFECYCLE_BY_RELATION[change.relation_type],
                        valid_to=change.effective_at,
                        changed_by_assertion_id=change.source_assertion_id,
                        changed_by_relation_id=change.relation_id,
                        contradiction_count=sum(
                            relation.relation_type == TemporalRelationType.CONTRADICTS
                            for relation in visible_relations
                        ),
                        reinforcement_count=reinforcement_count,
                    )
                )
                continue
            contradiction_count = sum(
                relation.relation_type == TemporalRelationType.CONTRADICTS
                for relation in visible_relations
            )
            states.append(
                AssertionState(
                    assertion=assertion,
                    lifecycle=(
                        AssertionLifecycle.CONTESTED
                        if contradiction_count
                        else AssertionLifecycle.ACTIVE
                    ),
                    contradiction_count=contradiction_count,
                    reinforcement_count=reinforcement_count,
                )
            )
        return states

    def rebuild_current_projection(self, *, computed_at: datetime | None = None) -> None:
        with self._connect() as connection:
            self._rebuild_current_projection(
                connection,
                computed_at=computed_at or datetime.now(UTC),
            )
            connection.commit()

    def _rebuild_current_projection(
        self,
        connection: sqlite3.Connection,
        *,
        computed_at: datetime,
    ) -> None:
        subject_rows = connection.execute(
            "SELECT DISTINCT subject_id FROM temporal_assertions ORDER BY subject_id"
        ).fetchall()
        connection.execute("DELETE FROM current_assertion_projection")
        for subject_row in subject_rows:
            states = self._resolve_states_from_connection(
                connection,
                subject_row["subject_id"],
                valid_at=computed_at,
                known_at=computed_at,
            )
            connection.executemany(
                """INSERT INTO current_assertion_projection(
                    assertion_id, subject_id, lifecycle, valid_from, valid_to,
                    changed_by_assertion_id, changed_by_relation_id,
                    contradiction_count, reinforcement_count, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        state.assertion.assertion_id,
                        state.assertion.subject_id,
                        state.lifecycle.value,
                        _iso(state.assertion.valid_from),
                        _iso(state.valid_to) if state.valid_to else None,
                        state.changed_by_assertion_id,
                        state.changed_by_relation_id,
                        state.contradiction_count,
                        state.reinforcement_count,
                        _iso(computed_at),
                    )
                    for state in states
                ],
            )
        connection.execute(
            """INSERT INTO projection_metadata(key, value) VALUES ('current_computed_at', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (_iso(computed_at),),
        )

    @staticmethod
    def _assertion_from_row(row: sqlite3.Row) -> TemporalAssertion:
        return TemporalAssertion(
            assertion_id=row["assertion_id"],
            event_id=row["event_id"],
            subject_id=row["subject_id"],
            predicate=row["predicate"],
            object_text=row["object_text"],
            scope=row["scope"],
            valid_from=_datetime(row["valid_from"]),
            confidence=float(row["confidence"]),
            importance=float(row["importance"]),
            extraction_method=row["extraction_method"],
            recorded_at=_datetime(row["recorded_at"]),
        )

    @staticmethod
    def _relation_from_row(row: sqlite3.Row) -> AssertionRelation:
        return AssertionRelation(
            relation_id=row["relation_id"],
            source_assertion_id=row["source_assertion_id"],
            target_assertion_id=row["target_assertion_id"],
            source_event_id=row["source_event_id"],
            relation_type=TemporalRelationType(row["relation_type"]),
            effective_at=_datetime(row["effective_at"]),
            confidence=float(row["confidence"]),
            rationale=row["rationale"],
            recorded_at=_datetime(row["recorded_at"]),
        )

    def load_embeddings(
        self,
        assertion_ids: Sequence[str],
        *,
        dimensions: int,
    ) -> dict[str, np.ndarray]:
        if not assertion_ids:
            return {}
        placeholders = ",".join("?" for _ in assertion_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT assertion_id, vector
                    FROM assertion_embedding_projection
                    WHERE assertion_id IN ({placeholders}) AND dimensions = ?""",
                (*assertion_ids, dimensions),
            ).fetchall()
        return {row["assertion_id"]: blob_to_vector(row["vector"]) for row in rows}

    def search_fts(self, query: str, *, limit: int = 100) -> list[str]:
        match = _fts_query(query)
        if not match:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT assertion_id FROM assertion_fts
                   WHERE assertion_fts MATCH ?
                   ORDER BY bm25(assertion_fts)
                   LIMIT ?""",
                (match, limit),
            ).fetchall()
        return [row["assertion_id"] for row in rows]

    def append_usage(self, event: TemporalUsageEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO assertion_usage_events(
                    usage_id, assertion_id, outcome, query_ref, context, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.usage_id,
                    event.assertion_id,
                    event.outcome.value,
                    event.query_ref,
                    event.context,
                    _iso(event.occurred_at),
                ),
            )
            connection.commit()

    def usage_stats(self, assertion_ids: Sequence[str]) -> dict[str, AssertionUsageStats]:
        output = {item: AssertionUsageStats(assertion_id=item) for item in assertion_ids}
        if not assertion_ids:
            return output
        placeholders = ",".join("?" for _ in assertion_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT assertion_id,
                           COUNT(*) AS use_count,
                           SUM(CASE WHEN outcome = 'successful' THEN 1 ELSE 0 END)
                               AS successful_use_count,
                           SUM(CASE WHEN outcome = 'rejected' THEN 1 ELSE 0 END)
                               AS rejected_use_count,
                           MAX(occurred_at) AS last_used_at
                    FROM assertion_usage_events
                    WHERE assertion_id IN ({placeholders})
                    GROUP BY assertion_id""",
                tuple(assertion_ids),
            ).fetchall()
        for row in rows:
            output[row["assertion_id"]] = AssertionUsageStats(
                assertion_id=row["assertion_id"],
                use_count=int(row["use_count"] or 0),
                successful_use_count=int(row["successful_use_count"] or 0),
                rejected_use_count=int(row["rejected_use_count"] or 0),
                last_used_at=_datetime(row["last_used_at"]) if row["last_used_at"] else None,
            )
        return output

    def stats(self) -> dict[str, int]:
        tables = (
            "memory_events",
            "temporal_assertions",
            "assertion_relations",
            "consolidation_runs",
            "assertion_usage_events",
            "current_assertion_projection",
        )
        with self._connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }

    def integrity_check(self) -> str:
        with self._connect() as connection:
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
