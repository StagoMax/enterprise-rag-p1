from __future__ import annotations

import argparse
import csv
import json
import zipfile
from pathlib import Path

PREFIX = "minidev/MINIDEV/dev_databases/financial/"
QUESTIONS_PATH = "minidev/MINIDEV/mini_dev_sqlite.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path("data/raw/bird/minidev.zip"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/bird_financial"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.archive) as archive:
        names = archive.namelist()
        database_name = f"{PREFIX}financial.sqlite"
        database_path = args.output / "financial.sqlite"
        database_path.write_bytes(archive.read(database_name))

        description_dir = args.output / "database_description"
        description_dir.mkdir(parents=True, exist_ok=True)
        description_names = [
            name
            for name in names
            if name.startswith(f"{PREFIX}database_description/") and name.endswith(".csv")
        ]
        for name in description_names:
            (description_dir / Path(name).name).write_bytes(archive.read(name))

        questions = json.loads(archive.read(QUESTIONS_PATH).decode("utf-8"))
        financial_questions = [row for row in questions if row["db_id"] == "financial"]

    with (args.output / "questions.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in financial_questions:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    schema_rows: list[dict[str, str]] = []
    for path in sorted(description_dir.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        schema_rows.append(
            {
                "table": path.stem,
                "description_file": path.name,
                "described_columns": str(len(rows)),
            }
        )
    with (args.output / "schema_manifest.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["table", "description_file", "described_columns"],
        )
        writer.writeheader()
        writer.writerows(schema_rows)

    summary = {
        "source": "BIRD-SQL Mini-Dev",
        "license": "CC BY-SA 4.0",
        "database": "financial",
        "database_bytes": database_path.stat().st_size,
        "tables": len(schema_rows),
        "questions": len(financial_questions),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

