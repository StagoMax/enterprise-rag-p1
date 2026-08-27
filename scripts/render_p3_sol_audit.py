"""Render an auditable Markdown companion for a strict Top-20 Sol rerank run.

The evaluator records final citations but deliberately keeps the reranker cache
compact: each cache row stores only the rank score for the original candidate
position.  Candidate diagnostics from a matching no-rerank run provide the
document IDs, titles and base scores.  This utility joins the two immutable
artifacts by evaluation order and produces examples that can be read without
guessing which documents the model considered.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_WORD = re.compile(r"[A-Za-z0-9_-]{4,}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def markdown(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def excerpt(document: dict[str, Any], question: str, *, length: int = 280) -> str:
    """Return a short real passage, preferring a sentence related to the query."""

    content = " ".join(str(document.get("content", "")).split())
    if not content:
        return "（源语料未提供正文）"
    terms = {term.lower() for term in _WORD.findall(question)}
    sentences = [part.strip() for part in _SENTENCE.split(content) if part.strip()]
    best = max(
        sentences,
        key=lambda sentence: sum(term in sentence.lower() for term in terms),
        default=content,
    )
    return best[:length].rstrip() + ("…" if len(best) > length else "")


def score_to_rank(scores: list[float]) -> dict[int, int]:
    """Higher score is better; tie-breaking preserves original candidate order."""

    ordered = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    return {index: rank for rank, index in enumerate(ordered, start=1)}


def example_kind(base_ids: list[str], sol_ids: list[str], gold: set[str]) -> str:
    base_hit = bool(gold.intersection(base_ids[:3]))
    sol_hit = bool(gold.intersection(sol_ids[:3]))
    if not base_hit and sol_hit:
        return "Sol 救回（基础 Top-3 漏、Sol Top-3 命中）"
    if base_hit and not sol_hit:
        return "Sol 回退（基础 Top-3 命中、Sol Top-3 漏）"
    if base_hit and sol_hit:
        return "稳定命中（两者均命中）"
    return "候选内未晋升（Gold 在 Top-20、但两者 Top-3 均漏）"


def select_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose one rescue, one regression and one stable case when available."""

    selected: list[dict[str, Any]] = []
    for kind in ("Sol 救回", "Sol 回退", "稳定命中", "候选内未晋升"):
        options = [
            row
            for row in rows
            if row["kind"].startswith(kind) and row["scores_bound"]
        ]
        if not options:
            continue
        # A larger base Gold rank makes a rescue more informative; for the
        # other types a smaller rank makes the contrast easier to inspect.
        reverse = kind == "Sol 救回"
        options.sort(key=lambda row: (row["best_gold_base_rank"], row["id"]), reverse=reverse)
        selected.append(options[0])
        if len(selected) == 3:
            break
    return selected


def render_example(row: dict[str, Any], documents: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        f"### {row['id']}：{row['kind']}",
        "",
        f"**问题**：{row['question']}",
        "",
        f"**Gold**：{', '.join(row['gold'])}",
        "",
        "| 基础名次 | 基础分数 | Sol 名次（20 候选内） | 文档 ID | 标题 | 是否 Gold | 原文摘录 |",
        "|---:|---:|---:|---|---|:---:|---|",
    ]
    for candidate in row["candidates"]:
        document_id = str(candidate["document_id"])
        document = documents.get(document_id, {})
        sol_rank = candidate["sol_rank"] or "未绑定"
        lines.append(
            "| "
            f"{candidate['base_rank']} | {float(candidate['base_score']):.6f} | "
            f"{sol_rank} | "
            f"`{document_id}` | {markdown(candidate.get('title'))} | "
            f"{'是' if candidate['is_gold'] else ''} | "
            f"{markdown(excerpt(document, row['question']))} |"
        )
    lines.extend(
        [
            "",
            "最终 API 返回的严格 Top-3："
            + "、".join(f"`{item}`" for item in row["sol_ids"])
            + "。",
            "",
        ]
    )
    return lines


def build_rows(
    rerank_report: dict[str, Any],
    baseline_report: dict[str, Any],
    cache_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    traces = baseline_report.get("candidate_diagnostics", {}).get("queries", [])
    base_results = baseline_report.get("results", [])
    rerank_results = rerank_report.get("results", [])
    if not traces:
        raise ValueError("baseline report has no candidate diagnostics")
    if not (len(traces) == len(base_results) == len(rerank_results)):
        raise ValueError(
            "cannot align reports: "
            f"traces={len(traces)}, base_results={len(base_results)}, "
            f"rerank_results={len(rerank_results)}"
        )

    rows: list[dict[str, Any]] = []
    for trace, base_result, rerank_result in zip(
        traces, base_results, rerank_results, strict=True
    ):
        row_id = str(trace["id"])
        if row_id != str(base_result["id"]) or row_id != str(rerank_result["id"]):
            raise ValueError(f"report order differs at {row_id}")
        candidates = list(trace["candidates"])
        if len(candidates) != 20:
            raise ValueError(
                f"{row_id}: strict run requires 20 candidates, got {len(candidates)}"
            )
        candidate_ids = [str(candidate["document_id"]) for candidate in candidates]
        sol_ids = [str(item) for item in rerank_result["citation_ids"]]
        matching_scores: list[list[float]] = []
        for cache in cache_records:
            candidate_scores = [float(value) for value in cache.get("scores", [])]
            if len(candidate_scores) != 20:
                continue
            ranked_indexes = sorted(
                range(20), key=lambda index: (-candidate_scores[index], index)
            )
            if [candidate_ids[index] for index in ranked_indexes[:3]] == sol_ids:
                matching_scores.append(candidate_scores)
        # Cache entries are keyed by question + ordered candidate text. Two
        # identical inputs legitimately share one entry, so bind a vector only
        # after its derived Top-3 exactly matches the actual API response.
        scores = matching_scores[0] if len(matching_scores) == 1 else None
        rank_by_index = score_to_rank(scores) if scores is not None else {}
        decorated = [
            {
                **candidate,
                "sol_rank": rank_by_index.get(index),
            }
            for index, candidate in enumerate(candidates)
        ]
        decorated.sort(key=lambda candidate: int(candidate["base_rank"]))
        gold = sorted(str(item) for item in trace["expected_source_ids"])
        gold_ranks = [
            int(candidate["base_rank"])
            for candidate in decorated
            if str(candidate["document_id"]) in gold
        ]
        base_ids = [str(item) for item in base_result["citation_ids"]]
        rows.append(
            {
                "id": row_id,
                "question": str(trace["question"]),
                "gold": gold,
                "candidates": decorated,
                "base_ids": base_ids,
                "sol_ids": sol_ids,
                "kind": example_kind(base_ids, sol_ids, set(gold)),
                "best_gold_base_rank": min(gold_ranks, default=999),
                "scores_bound": scores is not None,
            }
        )
    return rows


def metric_row(
    label: str,
    key: str,
    baseline_metrics: dict[str, Any],
    rerank_metrics: dict[str, Any],
) -> str:
    baseline_value = float(baseline_metrics[key])
    rerank_value = float(rerank_metrics[key])
    change = (rerank_value - baseline_value) * 100
    return (
        f"| {label} | {baseline_value:.4f} | {rerank_value:.4f} | "
        f"{change:+.2f} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rerank-report", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--reranker-cache", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rerank_report = load_json(args.rerank_report)
    baseline_report = load_json(args.baseline_report)
    cache_records = load_jsonl(args.reranker_cache)
    documents = {
        str(document["document_id"]): document for document in load_jsonl(args.documents)
    }
    rows = build_rows(rerank_report, baseline_report, cache_records)
    metrics = rerank_report["metrics"]
    baseline_metrics = baseline_report["metrics"]
    reranker_stats = rerank_report["reranker_stats"]
    examples = select_examples(rows)
    metric_lines = [
        metric_row("Recall@3", "semantic_rag_recall_at_3", baseline_metrics, metrics),
        metric_row(
            "Top-1 citation accuracy",
            "semantic_rag_top1_citation_accuracy",
            baseline_metrics,
            metrics,
        ),
        metric_row("MRR@3", "mrr_at_3", baseline_metrics, metrics),
        metric_row("nDCG@3", "ndcg_at_3", baseline_metrics, metrics),
    ]

    lines = [
        "# P3 严格 Top-20 Sol 重排复跑：可审计结果",
        "",
        "## 运行口径",
        "",
        f"- 评测题：P3 curated Gold 的 `rag` 类，{len(rows)} 道计分题。",
        (
            "- 候选：Milvus native RRF 检索后，先按 `document_id` 聚合；"
            "Sol 的每次输入固定为 20 篇不同文档。"
        ),
        "- 输出：`replace` 策略，只返回 Sol 排序后的前三篇不同文档。",
        (
            "- 对齐方法：基础候选来自同一 256/48 索引、同一检索参数的无重排诊断报告。"
            "Sol cache 以问题和候选正文为键；只有其推导出的 Top-3 与实际 API 返回"
            "严格一致时，才把 20 项分数绑定到案例。"
        ),
        (
            "- 注意：仓库中旧 Sol 报告使用的是历史 55 题切片；本报告为当前 115 题官方"
            "`rag` 计分切片，不能直接横向比较绝对题数或分数。"
        ),
        "",
        "## 本次真实结果",
        "",
        "| 指标 | 同配置无重排 | Sol 重排 | 变化（百分点） |",
        "|---|---:|---:|---:|",
        *metric_lines,
        "",
        f"- Sol 外部调用数：{reranker_stats['external_calls']}。",
        (
            f"- Sol 缓存命中数：{reranker_stats['cache_hits']}（"
            "本轮输入完全相同的重复题）。"
        ),
        f"- 降级调用数：{reranker_stats['degraded_calls']}。",
        "",
        "## 真实候选与重排样例",
        "",
        (
            "以下表格每行都是该题真实的 20 个候选之一。基础名次来自检索层；"
            "Sol 名次来自此次复跑的缓存分数，数值越小越靠前。原文摘录来自对应"
            "source document，而不是模型生成的理由。"
        ),
        "",
    ]
    for row in examples:
        lines.extend(render_example(row, documents))
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
