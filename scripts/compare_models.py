from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        "profile": path.stem.removeprefix("baseline-"),
        "backend": report["backend"],
        "model": report["model"],
        "dimensions": report["dimensions"],
        "dense_weight": report.get("dense_weight"),
        "reranker": report.get("reranker"),
        "passed": report["passed"],
        "metrics": report["metrics"],
        "checks": report["checks"],
    }


def selection_key(profile: dict[str, Any]) -> tuple[float, float, int, float]:
    metrics = profile["metrics"]
    safety_ready = all(
        profile["checks"][key]
        for key in (
            "route_accuracy",
            "refusal_accuracy",
            "permission_isolation",
            "tool_answer_accuracy",
        )
    )
    if not safety_ready or profile["backend"] == "hashing":
        return (-1.0, -1.0, 0, float("-inf"))
    return (
        metrics["citation_accuracy"],
        metrics["retrieval_recall_at_3"],
        -int(profile["dimensions"]),
        -metrics["p95_latency_ms"],
    )


def write_comparison(profiles: list[dict[str, Any]], output: Path) -> None:
    selected = max(profiles, key=selection_key)
    payload = {
        "selected_profile": selected["profile"],
        "selection_policy": (
            "Require route/refusal/permission/tool checks, then maximize Top-1 citation, "
            "Recall@3, lower dimensions, and lower P95 latency. Hashing is test-only."
        ),
        "release_gate_passed": selected["passed"],
        "blocking_checks": [key for key, passed in selected["checks"].items() if not passed],
        "profiles": profiles,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# P1 嵌入模型对照",
        "",
        f"默认配置：`{selected['profile']}`。",
        "",
        "| 配置 | 维度 | 重排 | Recall@3 | Top-1 引用 | P95 (ms) | 索引 (s) | 验收 |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for profile in profiles:
        metrics = profile["metrics"]
        lines.append(
            "| {profile} | {dimensions} | {reranker} | {recall:.2%} | {citation:.2%} | "
            "{p95:.2f} | {index:.2f} | {passed} |".format(
                profile=profile["profile"],
                dimensions=profile["dimensions"],
                reranker=profile["reranker"] or "无",
                recall=metrics["retrieval_recall_at_3"],
                citation=metrics["citation_accuracy"],
                p95=metrics["p95_latency_ms"],
                index=metrics["index_seconds"],
                passed="通过" if profile["passed"] else "未通过",
            )
        )
    lines.extend(
        [
            "",
            "选择规则先要求路由、拒答、权限隔离和工具回答检查通过，再依次比较 "
            "Top-1 引用、Recall@3、向量维度和 P95。Hashing 仅用于测试，不参与生产选择。",
            "",
            "当前发布门槛未通过：Top-1 引用正确率仍低于 95%，因此该配置是 P1 的开发基线，"
            "不是进入 P2 的放行结论。",
        ]
    )
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/model-comparison.json"))
    args = parser.parse_args()
    write_comparison([load_report(path) for path in args.reports], args.output)
    print(f"wrote {args.output} and {args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
