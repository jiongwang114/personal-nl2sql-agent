import argparse
import asyncio
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class BenchmarkCase:
    task_id: str
    question: str
    expected_sql: str = ""
    datasource: str = "demo"


def load_cases(path: Path, limit: int = 0) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle), start=1):
                question = (row.get("question") or "").strip()
                if question:
                    cases.append(
                        BenchmarkCase(
                            task_id=(row.get("task_id") or f"case-{index}").strip(),
                            question=question,
                            expected_sql=(row.get("sql") or row.get("expected_sql") or "").strip(),
                            datasource=(row.get("datasource") or "demo").strip(),
                        )
                    )
    else:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                cases.append(
                    BenchmarkCase(
                        task_id=str(row.get("task_id") or f"case-{index}"),
                        question=str(row["question"]),
                        expected_sql=str(row.get("sql") or row.get("expected_sql") or ""),
                        datasource=str(row.get("datasource") or "demo"),
                    )
                )
    return cases[:limit] if limit > 0 else cases


def parse_sse(text: str) -> dict[str, Any]:
    answer_parts: list[str] = []
    error = ""
    metrics: dict[str, Any] = {}
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event_name = ""
        payload: dict[str, Any] = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                value = json.loads(line.removeprefix("data:").strip())
                if isinstance(value, dict):
                    payload = value
        if event_name == "message":
            for content in payload.get("payload", {}).get("content", []):
                value = content.get("payload", {}).get("content")
                if isinstance(value, str):
                    answer_parts.append(value)
        elif event_name == "error":
            error = str(payload.get("error", "runtime error"))
        elif event_name == "end":
            metrics = payload
    return {"answer": "\n".join(answer_parts), "error": error, "metrics": metrics}


def completed_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                keys.add((str(row["task_id"]), str(row["variant"])))
    return keys


async def run_case(client: httpx.AsyncClient, base_url: str, case: BenchmarkCase, variant: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = await client.post(
        f"{base_url.rstrip('/')}/api/v1/chat/stream",
        json={
            "message": case.question,
            "session_id": f"benchmark_{variant}_{case.task_id}",
            "source": "benchmark",
            "runtime_variant": variant,
            "database": case.datasource,
        },
        timeout=None,
    )
    response.raise_for_status()
    parsed = parse_sse(response.text)
    metrics = parsed["metrics"]
    error = parsed["error"] or None
    if not parsed["answer"].strip() and error is None:
        error = "EMPTY_ANSWER: runtime completed without assistant text"
    return {
        "variant": variant,
        "task_id": case.task_id,
        "question": case.question,
        "expected_sql": case.expected_sql,
        "answer": parsed["answer"],
        "error": error,
        "result_correct": None,
        "needs_human_review": True,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "action_count": metrics.get("action_count"),
        "input_tokens": metrics.get("input_tokens"),
        "output_tokens": metrics.get("output_tokens"),
        "token_cost": None,
        "human_intervention": 0,
    }


async def run(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases, args.limit)
    if args.datasource:
        cases = [
            BenchmarkCase(
                task_id=case.task_id,
                question=case.question,
                expected_sql=case.expected_sql,
                datasource=args.datasource,
            )
            for case in cases
        ]
    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    invalid = set(variants) - {"legacy", "single", "multi"}
    if invalid:
        raise ValueError(f"Unknown variants: {', '.join(sorted(invalid))}")
    done = completed_keys(args.output) if args.resume else set()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        with args.output.open("a", encoding="utf-8") as handle:
            for case in cases:
                for variant in variants:
                    if (case.task_id, variant) in done:
                        continue
                    record = await run_case(client, args.base_url, case, variant)
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    handle.flush()
                    print(f"{case.task_id} {variant}: {'error' if record['error'] else 'complete'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run legacy, single-Agent, and multi-Agent through the Web API")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8501")
    parser.add_argument("--variants", default="legacy,single,multi")
    parser.add_argument("--datasource", default="", help="Override the datasource for every benchmark case")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
