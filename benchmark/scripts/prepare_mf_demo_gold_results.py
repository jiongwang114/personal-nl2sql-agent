"""Execute the official mf_demo reference SQL and save gold results."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_ROOT / "sample_data" / "mf-demo.duckdb"
MANIFEST = PROJECT_ROOT / "benchmark" / "semantic_layer" / "mf_demo_official_v1.json"


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def main() -> int:
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with duckdb.connect(str(DATABASE), read_only=True) as connection:
        for record in records:
            result = connection.execute(record["gold_sql"])
            record["gold_result"] = {
                "columns": [item[0] for item in result.description],
                "rows": [[json_value(value) for value in row] for row in result.fetchall()],
            }
            record["gold_result"]["row_count"] = len(record["gold_result"]["rows"])

    MANIFEST.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PREPARED_RESULTS={len(records)} OUTPUT={MANIFEST}")
    for record in records:
        result = record["gold_result"]
        print(f"{record['question_id']}|columns={len(result['columns'])}|rows={result['row_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
