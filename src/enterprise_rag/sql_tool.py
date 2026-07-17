import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class SqlToolResult:
    sql: str
    rows: list[dict[str, Any]]
    source_id: str = "demo-sales-db"
    schema_version: str = "1"


class ReadOnlySqlTool:
    def __init__(self, path: Path, allowed_tables: set[str] | None = None) -> None:
        self._path = path.resolve()
        self._allowed_tables = allowed_tables or {"sales"}

    def validate_sql(self, sql: str) -> None:
        statements = sqlglot.parse(sql, read="sqlite")
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise ValueError("only one SELECT statement is allowed")

        statement = statements[0]
        forbidden = (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Drop,
            exp.Alter,
            exp.Create,
            exp.Command,
        )
        if any(statement.find(node_type) is not None for node_type in forbidden):
            raise ValueError("mutating SQL is forbidden")

        tables = {table.name for table in statement.find_all(exp.Table)}
        if not tables or not tables <= self._allowed_tables:
            raise ValueError("query references a table outside the allowlist")

    @staticmethod
    def _plan(question: str) -> str:
        lowered = question.lower()
        region = None
        if "华东" in question or "east" in lowered:
            region = "华东"
        elif "华南" in question or "south" in lowered:
            region = "华南"

        if (
            "订单数量" in question
            or "count" in lowered
            or "how many" in lowered
            or "多少条" in question
        ):
            select = "COUNT(*) AS order_count"
        elif "平均" in question or "average" in lowered:
            select = "ROUND(AVG(amount), 2) AS average_amount"
        else:
            select = "ROUND(SUM(amount), 2) AS total_amount"

        sql = f"SELECT {select} FROM sales"
        filters: list[str] = []
        if region:
            filters.append(f"region = '{region}'")
        if "2026q1" in lowered or "2026 Q1" in question or "2026年第一季度" in question:
            filters.append("period = '2026Q1'")
        elif "2026q2" in lowered or "2026 Q2" in question or "2026年第二季度" in question:
            filters.append("period = '2026Q2'")
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        return sql + " LIMIT 100"

    def execute_question(self, question: str) -> SqlToolResult:
        sql = self._plan(question)
        self.validate_sql(sql)
        connection = sqlite3.connect(f"file:{self._path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = [dict(row) for row in connection.execute(sql).fetchall()]
        finally:
            connection.close()
        return SqlToolResult(sql=sql, rows=rows)


def initialize_demo_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sales (
                order_id TEXT PRIMARY KEY,
                region TEXT NOT NULL,
                period TEXT NOT NULL,
                amount REAL NOT NULL
            );
            DELETE FROM sales;
            """
        )
        connection.executemany(
            "INSERT INTO sales(order_id, region, period, amount) VALUES (?, ?, ?, ?)",
            [
                ("SO-1001", "华东", "2026Q1", 120000.0),
                ("SO-1002", "华东", "2026Q1", 80000.0),
                ("SO-1003", "华南", "2026Q1", 95000.0),
                ("SO-1004", "华东", "2026Q2", 110000.0),
            ],
        )
        connection.commit()
    finally:
        connection.close()
