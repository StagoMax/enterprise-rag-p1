from pathlib import Path

import pytest

from enterprise_rag.sql_tool import ReadOnlySqlTool, initialize_demo_database


def test_sql_validator_rejects_mutation(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite"
    initialize_demo_database(path)
    tool = ReadOnlySqlTool(path)

    with pytest.raises(ValueError, match="SELECT"):
        tool.validate_sql("DELETE FROM sales")


def test_sql_validator_rejects_non_allowlisted_table(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite"
    initialize_demo_database(path)
    tool = ReadOnlySqlTool(path)

    with pytest.raises(ValueError, match="allowlist"):
        tool.validate_sql("SELECT * FROM sqlite_master")
