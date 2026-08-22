"""Prepare the official mf_demo questions with their reference table names."""

import csv
import json
from pathlib import Path

from dataengineer.utils.sql_utils import extract_table_names


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT_ROOT / "benchmark" / "semantic_layer" / "testing_set.csv"
OUTPUT = PROJECT_ROOT / "benchmark" / "semantic_layer" / "mf_demo_official_v1.json"


def main() -> int:
    records = []
    with SOURCE.open(encoding="utf-8", newline="") as csv_file:
        for question_id, row in enumerate(csv.DictReader(csv_file), start=1):
            records.append(
                {
                    "question_id": question_id,
                    "question": row["question"].strip(),
                    "gold_sql": row["sql"].strip(),
                    "gold_tables": sorted(extract_table_names(row["sql"], dialect="duckdb", ignore_empty=True)),
                }
            )

    OUTPUT.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PREPARED={len(records)} OUTPUT={OUTPUT}")
    for record in records:
        print(f"{record['question_id']}|{', '.join(record['gold_tables'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
