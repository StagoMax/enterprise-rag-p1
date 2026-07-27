from pathlib import Path

import pytest

from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.models import GraphEdge


def test_graph_expansion_is_acl_first_and_supports_two_hops(tmp_path: Path) -> None:
    graph = VersionedKnowledgeGraph(tmp_path / "graph.json")
    graph.publish(
        "v1",
        [
            GraphEdge(source_id="a", target_id="b"),
            GraphEdge(source_id="b", target_id="c"),
            GraphEdge(source_id="c", target_id="a"),
            GraphEdge(source_id="a", target_id="restricted"),
        ],
        {"a", "b", "c", "restricted"},
    )

    paths = graph.expand(["a"], {"a", "b", "c"}, max_hops=2)
    node_paths = [path.node_ids for path in paths]
    assert ["a", "b"] in node_paths
    assert ["a", "b", "c"] in node_paths
    assert all("restricted" not in path for path in node_paths)
    assert all(len(path) == len(set(path)) for path in node_paths)


def test_graph_versions_persist_and_rollback(tmp_path: Path) -> None:
    state_path = tmp_path / "graph.json"
    graph = VersionedKnowledgeGraph(state_path)
    graph.publish("v1", [GraphEdge(source_id="a", target_id="b")], {"a", "b", "c"})
    graph.publish("v2", [GraphEdge(source_id="b", target_id="c")], {"a", "b", "c"})
    graph.rollback("v1")

    reloaded = VersionedKnowledgeGraph(state_path)
    assert reloaded.active_version == "v1"
    assert reloaded.current_edges() == [GraphEdge(source_id="a", target_id="b")]
    with pytest.raises(ValueError, match="unknown documents"):
        reloaded.publish(
            "invalid",
            [GraphEdge(source_id="a", target_id="missing")],
            {"a", "b", "c"},
        )
