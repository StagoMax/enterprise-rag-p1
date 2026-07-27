from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from enterprise_rag.models import GraphEdge, GraphPath, GraphRelationType


class GraphSnapshot(BaseModel):
    version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    edges: list[GraphEdge] = Field(default_factory=list)


class VersionedKnowledgeGraph:
    """Versioned document graph that filters nodes before traversing any edge."""

    def __init__(self, state_path: Path | None = None) -> None:
        self._state_path = state_path
        self._snapshots: dict[str, GraphSnapshot] = {}
        self._active_version: str | None = None
        self._load()

    @property
    def active_version(self) -> str | None:
        return self._active_version

    def has_version(self, version: str) -> bool:
        return version in self._snapshots

    def versions(self) -> list[str]:
        return list(self._snapshots)

    def current_edges(self) -> list[GraphEdge]:
        if self._active_version is None:
            return []
        return list(self._snapshots[self._active_version].edges)

    def edge_count(self) -> int:
        return len(self.current_edges())

    def relation_counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for edge in self.current_edges():
            counts[edge.relation.value] += 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _validated_edges(edges: list[GraphEdge], document_ids: set[str]) -> list[GraphEdge]:
        unknown = sorted(
            {
                document_id
                for edge in edges
                for document_id in (edge.source_id, edge.target_id)
                if document_id not in document_ids
            }
        )
        if unknown:
            preview = ", ".join(unknown[:5])
            raise ValueError(f"graph relations reference unknown documents: {preview}")

        unique: dict[tuple[str, str, GraphRelationType], GraphEdge] = {}
        for edge in edges:
            key = (edge.source_id, edge.target_id, edge.relation)
            previous = unique.get(key)
            if previous is None or edge.confidence > previous.confidence:
                unique[key] = edge
        return sorted(
            unique.values(),
            key=lambda edge: (edge.source_id, edge.target_id, edge.relation.value),
        )

    def publish(self, version: str, edges: list[GraphEdge], document_ids: set[str]) -> None:
        if version in self._snapshots:
            raise ValueError(f"graph version already exists: {version}")
        validated = self._validated_edges(edges, document_ids)
        self._snapshots[version] = GraphSnapshot(version=version, edges=validated)
        self._active_version = version
        self._persist()

    def bootstrap(self, version: str, edges: list[GraphEdge], document_ids: set[str]) -> None:
        if version not in self._snapshots:
            self.publish(version, edges, document_ids)
            return
        self._validated_edges(self._snapshots[version].edges, document_ids)
        self._active_version = version
        self._persist()

    def rollback(self, version: str) -> None:
        if version not in self._snapshots:
            raise ValueError(f"unknown graph version: {version}")
        self._active_version = version
        self._persist()

    def expand(
        self,
        seed_ids: list[str],
        allowed_document_ids: set[str],
        *,
        max_hops: int = 2,
        limit: int = 20,
    ) -> list[GraphPath]:
        if self._active_version is None or max_hops < 1 or limit < 1:
            return []

        allowed_seeds = [seed for seed in seed_ids if seed in allowed_document_ids]
        adjacency: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in self.current_edges():
            if edge.source_id in allowed_document_ids and edge.target_id in allowed_document_ids:
                adjacency[edge.source_id].append(edge)

        paths: list[GraphPath] = []
        queue: deque[tuple[str, list[str], list[GraphRelationType], float]] = deque(
            (seed, [seed], [], 1.0) for seed in allowed_seeds
        )
        while queue and len(paths) < limit:
            node_id, node_path, relation_path, confidence = queue.popleft()
            if len(relation_path) >= max_hops:
                continue
            for edge in adjacency.get(node_id, []):
                if edge.target_id in node_path:
                    continue
                next_nodes = [*node_path, edge.target_id]
                next_relations = [*relation_path, edge.relation]
                next_confidence = confidence * edge.confidence
                paths.append(
                    GraphPath(
                        node_ids=next_nodes,
                        relations=next_relations,
                        confidence=next_confidence,
                    )
                )
                if len(paths) >= limit:
                    break
                queue.append(
                    (edge.target_id, next_nodes, next_relations, next_confidence)
                )

        return sorted(paths, key=lambda path: (len(path.relations), -path.confidence))[:limit]

    def _load(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        self._active_version = payload.get("active_version")
        self._snapshots = {
            version: GraphSnapshot.model_validate(snapshot)
            for version, snapshot in payload.get("snapshots", {}).items()
        }
        if self._active_version not in self._snapshots:
            self._active_version = None

    def _persist(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_version": self._active_version,
            "snapshots": {
                version: snapshot.model_dump(mode="json")
                for version, snapshot in self._snapshots.items()
            },
        }
        temporary = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._state_path)
