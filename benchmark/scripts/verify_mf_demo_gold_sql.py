"""Verify that mf_demo benchmark reference SQL runs against the local DuckDB file."""

import csv
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "tests" / "data" / "dataengineer_metricflow_db" / "duck.db"
SOURCES = [
    PROJECT_ROOT / "benchmark" / "semantic_layer" / "testing_set.csv",
]


def main() -> int:
    results = []
    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        for source in SOURCES:
            with source.open(encoding="utf-8", newline="") as csv_file:
                for index, row in enumerate(csv.DictReader(csv_file), start=1):
                    try:
                        output = connection.execute(row["sql"]).fetchall()
                        results.append((source.name, index, "PASS", len(output), ""))
                    except Exception as exc:
                        results.append((source.name, index, "FAIL", 0, str(exc).splitlines()[0]))

    passed = sum(status == "PASS" for _, _, status, _, _ in results)
    print(f"TOTAL={len(results)} PASS={passed} FAIL={len(results) - passed}")
    for source, index, status, row_count, error in results:
        print(f"{source}|{index}|{status}|rows={row_count}|{error}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
