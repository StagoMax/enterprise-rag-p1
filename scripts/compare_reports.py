"""Diff two evaluation reports and fail on regression.

Point it at a committed baseline and a freshly produced report; it exits non-zero
when any metric drops by more than the tolerance, which is what CI gates on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Lower is better for these, so the comparison flips.
LOWER_IS_BETTER = frozenset({"p50_latency_ms", "p95_latency_ms", "index_seconds"})

# Timing is machine-dependent; a shared CI runner is not a stable basis for a
# latency gate, so these are reported but never fail the build.
INFORMATIONAL = frozenset({"p50_latency_ms", "p95_latency_ms", "index_seconds"})


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    tolerance: float,
) -> tuple[list[str], list[str]]:
    base_metrics = baseline.get("metrics", {})
    new_metrics = candidate.get("metrics", {})
    regressions: list[str] = []
    notes: list[str] = []

    for key in sorted(set(base_metrics) | set(new_metrics)):
        if key not in base_metrics:
            notes.append(f"+ {key}: new metric = {new_metrics[key]}")
            continue
        if key not in new_metrics:
            regressions.append(f"- {key}: present in baseline, missing from candidate")
            continue

        before, after = base_metrics[key], new_metrics[key]
        if not isinstance(before, int | float) or not isinstance(after, int | float):
            continue

        delta = after - before
        worsened = (delta < -tolerance) if key not in LOWER_IS_BETTER else (delta > tolerance)
        if not worsened:
            continue
        line = f"{key}: {before} -> {after} ({delta:+.4f})"
        if key in INFORMATIONAL:
            notes.append(f"~ {line} (informational)")
        else:
            regressions.append(f"- {line}")

    for key, passed in sorted(candidate.get("checks", {}).items()):
        if not passed:
            threshold = candidate.get("thresholds", {}).get(key)
            regressions.append(
                f"- {key}: below threshold {threshold} (= {new_metrics.get(key)})"
            )
    return regressions, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="allowed drop before a metric counts as a regression",
    )
    parser.add_argument(
        "--ignore-thresholds",
        action="store_true",
        help="only compare against the baseline, ignore absolute threshold checks",
    )
    args = parser.parse_args()

    baseline, candidate = load(args.baseline), load(args.candidate)
    regressions, notes = compare(baseline, candidate, args.tolerance)
    if args.ignore_thresholds:
        regressions = [line for line in regressions if "below threshold" not in line]

    print(f"baseline:  {args.baseline} ({baseline.get('backend')})")
    print(f"candidate: {args.candidate} ({candidate.get('backend')})")
    for line in notes:
        print(line)
    if regressions:
        print("\nREGRESSED:")
        for line in regressions:
            print(line)
        return 1
    print("\nNo regressions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
