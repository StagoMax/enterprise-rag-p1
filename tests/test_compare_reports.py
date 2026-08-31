import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "compare_reports", REPO_ROOT / "scripts" / "compare_reports.py"
)
compare_reports = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_reports)

compare = compare_reports.compare


def report(**metrics):
    checks = metrics.pop("_checks", {})
    return {"metrics": metrics, "checks": checks, "thresholds": {}}


def test_identical_reports_have_no_regressions():
    base = report(p1_top1_citation_accuracy=0.8625, mrr_at_3=0.91)
    regressions, _ = compare(base, base, 0.0)
    assert regressions == []


def test_metric_drop_is_flagged():
    base = report(p1_top1_citation_accuracy=0.90)
    candidate = report(p1_top1_citation_accuracy=0.85)
    regressions, _ = compare(base, candidate, 0.0)
    assert len(regressions) == 1
    assert "p1_top1_citation_accuracy" in regressions[0]


def test_improvement_is_not_flagged():
    base = report(p1_top1_citation_accuracy=0.85)
    candidate = report(p1_top1_citation_accuracy=0.95)
    regressions, _ = compare(base, candidate, 0.0)
    assert regressions == []


def test_tolerance_absorbs_small_drops():
    base = report(mrr_at_3=0.900)
    candidate = report(mrr_at_3=0.895)
    assert compare(base, candidate, 0.01)[0] == []
    assert compare(base, candidate, 0.0)[0] != []


def test_latency_direction_is_inverted_and_informational():
    base = report(p95_latency_ms=1000.0)
    candidate = report(p95_latency_ms=1500.0)
    regressions, notes = compare(base, candidate, 0.0)
    # Slower is worse, but timing must not fail a shared CI runner.
    assert regressions == []
    assert any("p95_latency_ms" in note for note in notes)


def test_faster_latency_is_not_reported():
    base = report(p95_latency_ms=1000.0)
    candidate = report(p95_latency_ms=800.0)
    regressions, notes = compare(base, candidate, 0.0)
    assert regressions == []
    assert notes == []


def test_graph_gain_drop_is_informational_when_base_recall_improves():
    base = report(
        graph_target_recall_at_3=1.0,
        graph_hybrid_target_recall_at_3=0.2,
        graph_recall_gain=0.8,
    )
    candidate = report(
        graph_target_recall_at_3=1.0,
        graph_hybrid_target_recall_at_3=0.6,
        graph_recall_gain=0.4,
    )

    regressions, notes = compare(base, candidate, 0.0)

    assert regressions == []
    assert any("graph_recall_gain" in note for note in notes)


def test_new_metric_is_a_note_not_a_regression():
    base = report(route_accuracy=1.0)
    candidate = report(route_accuracy=1.0, ndcg_at_3=0.88)
    regressions, notes = compare(base, candidate, 0.0)
    assert regressions == []
    assert any("ndcg_at_3" in note for note in notes)


def test_disappearing_metric_is_a_regression():
    base = report(route_accuracy=1.0, ndcg_at_3=0.88)
    candidate = report(route_accuracy=1.0)
    regressions, _ = compare(base, candidate, 0.0)
    assert any("ndcg_at_3" in line for line in regressions)


def test_failed_threshold_check_is_a_regression():
    base = report(p1_top1_citation_accuracy=0.86)
    candidate = report(p1_top1_citation_accuracy=0.86, _checks={"p1_top1_citation_accuracy": False})
    regressions, _ = compare(base, candidate, 0.0)
    assert any("below threshold" in line for line in regressions)


def test_non_numeric_metrics_are_skipped():
    base = report(backend_note="hashing")
    candidate = report(backend_note="nemotron")
    assert compare(base, candidate, 0.0)[0] == []
