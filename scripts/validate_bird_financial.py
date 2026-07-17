from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any

from enterprise_rag.sql_tool import ReadOnlySqlTool


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    return ordered[min(round((len(ordered) - 1) * percent), len(ordered) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/processed/bird_financial"))
    parser.add_argument("--output", type=Path, default=Path("reports/bird-financial.json"))
    args = parser.parse_args()

    database = (args.data / "financial.sqlite").resolve()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    tool = ReadOnlySqlTool(database, allowed_tables=tables)
    questions = [
        json.loads(line)
        for line in (args.data / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    results: list[dict[str, Any]] = []
    for row in questions:
        started = time.perf_counter()
        error = None
        returned_rows = 0
        try:
            tool.validate_sql(row["SQL"])
            cursor = connection.execute(row["SQL"])
            returned_rows = len(cursor.fetchmany(1000))
        except (ValueError, sqlite3.Error) as exc:
            error = str(exc)
        results.append(
            {
                "question_id": row["question_id"],
                "difficulty": row["difficulty"],
                "success": error is None,
                "returned_rows": returned_rows,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "error": error,
            }
        )
    connection.close()

    latencies = [row["latency_ms"] for row in results]
    successes = sum(row["success"] for row in results)
    report = {
        "dataset": "BIRD-SQL Mini-Dev",
        "database": "financial",
        "license": "CC BY-SA 4.0",
        "tables": sorted(tables),
        "questions": len(results),
        "successful_executions": successes,
        "execution_rate": round(successes / len(results), 4),
        "p50_latency_ms": round(statistics.median(latencies), 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
        "failures": [row for row in results if not row["success"]],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(
        "\n".join(
            [
                "# BIRD Financial SQL Validation",
                "",
                f"- Database: `{report['database']}`",
                f"- Tables: {len(report['tables'])}",
                f"- Questions: {report['questions']}",
                f"- Successful executions: {report['successful_executions']}",
                f"- Execution rate: {report['execution_rate']:.2%}",
                f"- P50 latency: {report['p50_latency_ms']} ms",
                f"- P95 latency: {report['p95_latency_ms']} ms",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

