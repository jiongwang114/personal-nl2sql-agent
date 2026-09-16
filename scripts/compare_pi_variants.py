import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

METRICS = (
    "result_correct",
    "first_sql_executable",
    "repair_success",
    "dangerous_sql_rejected",
    "latency_ms",
    "token_cost",
    "tool_calls",
    "human_intervention",
)


def load_records(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or "variant" not in value or "task_id" not in value:
                raise ValueError(f"{path}:{line_number} must contain variant and task_id")
            records.append(value)
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["variant"])].append(record)

    result: dict[str, dict[str, float]] = {}
    for variant, items in sorted(grouped.items()):
        summary: dict[str, float] = {"tasks": float(len(items))}
        for metric in METRICS:
            values = [item[metric] for item in items if isinstance(item.get(metric), (int, float, bool))]
            if values:
                summary[metric] = sum(float(value) for value in values) / len(values)
        result[variant] = summary
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare legacy, single-Agent, and multi-Agent JSONL results")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = [record for input_path in args.inputs for record in load_records(input_path)]
    report = summarize(records)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
