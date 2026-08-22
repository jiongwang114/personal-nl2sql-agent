"""Evaluate schema retrieval quality from saved Agent trajectories.

The evaluator treats the first five schema-linking results as the Top-5
retrieval list. It reports macro F1, exact Top-5 accuracy, and the duration of
the Schema Linking node, where a query is an exact hit only when every gold
table appears in the Top-5 list.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml


@dataclass(frozen=True)
class GoldTask:
    task_id: str
    question: str
    gold_tables: tuple[str, ...]


@dataclass(frozen=True)
class TaskMetrics:
    task_id: str
    question: str
    gold_tables: tuple[str, ...]
    predicted_top_k: tuple[str, ...]
    matched_tables: tuple[str, ...]
    precision: float
    recall: float
    f1: float
    top_k_exact_match: bool


def normalize_table_name(value: Any) -> str:
    """Normalize qualified table names to ``schema.table`` form."""

    if isinstance(value, Mapping):
        identifier = value.get("identifier")
        if identifier:
            value = identifier
        else:
            parts = [
                str(value.get(key, "")).strip()
                for key in ("database_name", "schema_name", "table_name")
                if value.get(key)
            ]
            value = ".".join(parts)

    text = str(value).strip().strip("`").strip('"')
    text = text.replace('"."', ".").replace("`.`", ".")
    parts = [part.strip().strip("`").strip('"').lower() for part in text.split(".") if part.strip()]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return parts[0] if parts else ""


def _unique_normalized(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_table_name(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def load_gold_tasks(path: Path) -> dict[str, GoldTask]:
    with path.open("r", encoding="utf-8") as handle:
        raw_tasks = json.load(handle)

    if not isinstance(raw_tasks, list):
        raise ValueError(f"Gold file must contain a JSON list: {path}")

    tasks: dict[str, GoldTask] = {}
    for item in raw_tasks:
        if not isinstance(item, Mapping):
            raise ValueError(f"Invalid gold task in {path}: {item!r}")
        task_id = str(item.get("question_id", "")).strip()
        gold_tables = tuple(_unique_normalized(item.get("gold_tables", [])))
        if not task_id or not gold_tables:
            raise ValueError(f"Gold task must have question_id and gold_tables: {item!r}")
        if task_id in tasks:
            raise ValueError(f"Duplicate gold question_id: {task_id}")
        tasks[task_id] = GoldTask(
            task_id=task_id,
            question=str(item.get("question", "")),
            gold_tables=gold_tables,
        )
    return tasks


def _load_trajectory(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, Mapping) or not isinstance(data.get("workflow"), Mapping):
        raise ValueError(f"Invalid trajectory format: {path}")
    return data


def _workflow_nodes(trajectory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nodes = trajectory["workflow"].get("nodes", [])
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, Mapping)]


def _schema_tables(trajectory: Mapping[str, Any], top_k: int) -> tuple[str, ...]:
    schema_nodes = [node for node in _workflow_nodes(trajectory) if node.get("type") == "schema_linking"]
    if not schema_nodes:
        return ()

    result = schema_nodes[0].get("result") or {}
    if not isinstance(result, Mapping):
        return ()
    tables = result.get("table_schemas") or []
    if not isinstance(tables, list):
        return ()
    return tuple(_unique_normalized(tables)[:top_k])


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _execute_nodes(trajectory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nodes = [node for node in _workflow_nodes(trajectory) if node.get("type") == "execute_sql"]
    return sorted(nodes, key=lambda node: _number(node.get("start_time"), math.inf))


def _reflect_nodes(trajectory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [node for node in _workflow_nodes(trajectory) if node.get("type") == "reflect"]


def _execution_succeeded(node: Mapping[str, Any]) -> bool:
    result = node.get("result") or {}
    if not isinstance(result, Mapping):
        return False
    status = str(node.get("status", "")).lower()
    return bool(result.get("success")) and status not in {"failed", "error"}


def _duration_ms(trajectory: Mapping[str, Any]) -> float | None:
    workflow = trajectory["workflow"]
    start = _number(workflow.get("creation_time"), math.nan)
    end = _number(workflow.get("completion_time"), math.nan)
    if math.isfinite(start) and math.isfinite(end) and end >= start:
        return (end - start) * 1000
    return None


def _schema_retrieval_duration_ms(trajectory: Mapping[str, Any]) -> float | None:
    """Return the Schema Linking node duration in milliseconds."""

    schema_nodes = [node for node in _workflow_nodes(trajectory) if node.get("type") == "schema_linking"]
    if not schema_nodes:
        return None
    node = schema_nodes[0]
    start = _number(node.get("start_time"), math.nan)
    end = _number(node.get("end_time"), math.nan)
    if math.isfinite(start) and math.isfinite(end) and end >= start:
        return (end - start) * 1000
    return None


def evaluate_task(task: GoldTask, trajectory: Mapping[str, Any], top_k: int = 5) -> TaskMetrics:
    predicted = _schema_tables(trajectory, top_k)
    predicted_set = set(predicted)
    gold_set = set(task.gold_tables)
    matched = tuple(table for table in predicted if table in gold_set)
    true_positive = len(matched)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = true_positive / len(gold_set)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return TaskMetrics(
        task_id=task.task_id,
        question=task.question,
        gold_tables=task.gold_tables,
        predicted_top_k=predicted,
        matched_tables=matched,
        precision=precision,
        recall=recall,
        f1=f1,
        top_k_exact_match=gold_set.issubset(predicted_set),
    )


def _trajectory_task_id(trajectory: Mapping[str, Any], path: Path) -> str:
    task = trajectory["workflow"].get("task") or {}
    if isinstance(task, Mapping) and task.get("id") not in (None, ""):
        return str(task["id"])
    return path.name.split("_", 1)[0]


def _trajectory_files(path: Path) -> list[Path]:
    if not path.exists():
        raise FileNotFoundError(f"Trajectory directory does not exist: {path}")
    return sorted(path.glob("*_*.yaml"))


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def evaluate_run(
    trajectory_dir: Path,
    gold_tasks: Mapping[str, GoldTask],
    top_k: int = 5,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    trajectories: dict[str, Mapping[str, Any]] = {}
    for path in _trajectory_files(trajectory_dir):
        trajectory = _load_trajectory(path)
        task_id = _trajectory_task_id(trajectory, path)
        if task_id in trajectories:
            raise ValueError(f"Duplicate trajectory for task {task_id}: {trajectory_dir}")
        trajectories[task_id] = trajectory

    missing = sorted(set(gold_tasks) - set(trajectories))
    unexpected = sorted(set(trajectories) - set(gold_tasks))
    if missing and not allow_incomplete:
        raise ValueError(f"Missing trajectories for {len(missing)} gold tasks: {', '.join(missing)}")

    task_metrics: list[TaskMetrics] = []
    first_successes = 0
    final_successes = 0
    first_failure_task_ids: list[str] = []
    auto_repaired_task_ids: list[str] = []
    reflection_task_ids: list[str] = []
    durations: list[float] = []
    schema_retrieval_durations: list[float] = []
    missing_execution: list[str] = []
    missing_duration: list[str] = []
    missing_schema_retrieval_duration: list[str] = []
    for task_id in sorted(set(gold_tasks).intersection(trajectories)):
        trajectory = trajectories[task_id]
        task_metrics.append(evaluate_task(gold_tasks[task_id], trajectory, top_k=top_k))
        execute_nodes = _execute_nodes(trajectory)
        if execute_nodes:
            first_success = _execution_succeeded(execute_nodes[0])
            final_success = _execution_succeeded(execute_nodes[-1])
            first_successes += int(first_success)
            final_successes += int(final_success)
            if not first_success:
                first_failure_task_ids.append(task_id)
                if final_success:
                    auto_repaired_task_ids.append(task_id)
        else:
            missing_execution.append(task_id)
        if _reflect_nodes(trajectory):
            reflection_task_ids.append(task_id)
        duration = _duration_ms(trajectory)
        if duration is not None:
            durations.append(duration)
        else:
            missing_duration.append(task_id)
        schema_duration = _schema_retrieval_duration_ms(trajectory)
        if schema_duration is not None:
            schema_retrieval_durations.append(schema_duration)
        else:
            missing_schema_retrieval_duration.append(task_id)

    denominator = len(task_metrics)
    if denominator == 0:
        raise ValueError("No gold tasks have matching trajectories")
    if missing_duration and not allow_incomplete:
        raise ValueError(f"Missing end-to-end timestamps for tasks: {', '.join(missing_duration)}")
    return {
        "trajectory_dir": str(trajectory_dir),
        "top_k": top_k,
        "task_count": denominator,
        "gold_task_count": len(gold_tasks),
        "missing_task_ids": missing,
        "unexpected_task_ids": unexpected,
        "missing_execution_task_ids": missing_execution,
        "missing_duration_task_ids": missing_duration,
        "missing_schema_retrieval_duration_task_ids": missing_schema_retrieval_duration,
        "macro_precision": sum(item.precision for item in task_metrics) / denominator,
        "macro_recall": sum(item.recall for item in task_metrics) / denominator,
        "macro_f1": sum(item.f1 for item in task_metrics) / denominator,
        "top_k_exact_accuracy": sum(item.top_k_exact_match for item in task_metrics) / denominator,
        "first_execution_success_rate": first_successes / denominator,
        "final_execution_success_rate": final_successes / denominator,
        "first_failure_task_ids": first_failure_task_ids,
        "auto_repaired_task_ids": auto_repaired_task_ids,
        "auto_repair_rate": (
            len(auto_repaired_task_ids) / len(first_failure_task_ids) if first_failure_task_ids else None
        ),
        "reflection_task_ids": reflection_task_ids,
        "reflection_task_count": len(reflection_task_ids),
        "end_to_end_p95_ms": _percentile(durations, 0.95),
        "schema_retrieval_count": len(schema_retrieval_durations),
        "schema_retrieval_avg_ms": (
            sum(schema_retrieval_durations) / len(schema_retrieval_durations)
            if schema_retrieval_durations
            else None
        ),
        "schema_retrieval_min_ms": min(schema_retrieval_durations) if schema_retrieval_durations else None,
        "schema_retrieval_max_ms": max(schema_retrieval_durations) if schema_retrieval_durations else None,
        "tasks": [asdict(item) for item in task_metrics],
    }


def compare_runs(baseline: Mapping[str, Any], optimized: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two complete reports and expose absolute and relative gains."""

    if baseline["top_k"] != optimized["top_k"]:
        raise ValueError("Baseline and optimized reports must use the same top_k")
    if baseline["task_count"] != baseline["gold_task_count"]:
        raise ValueError("Baseline report is incomplete")
    if optimized["task_count"] != optimized["gold_task_count"]:
        raise ValueError("Optimized report is incomplete")

    comparison: dict[str, Any] = {}
    for metric in ("macro_f1", "top_k_exact_accuracy"):
        before = float(baseline[metric])
        after = float(optimized[metric])
        comparison[metric] = {
            "baseline": before,
            "optimized": after,
            "absolute_delta": after - before,
            "relative_improvement": (after - before) / before if before else None,
        }
    return comparison


def _format_percentage(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _print_summary(label: str, report: Mapping[str, Any]) -> None:
    print(f"[{label}] tasks={report['task_count']}/{report['gold_task_count']}")
    print(f"  macro F1: {_format_percentage(report['macro_f1'])}")
    print(f"  Top-{report['top_k']} exact accuracy: {_format_percentage(report['top_k_exact_accuracy'])}")
    print(f"  Top-{report['top_k']} macro recall: {_format_percentage(report['macro_recall'])}")
    print(
        f"  first/final SQL execution: {_format_percentage(report['first_execution_success_rate'])}/"
        f"{_format_percentage(report['final_execution_success_rate'])}"
    )
    repair_rate = report["auto_repair_rate"]
    if repair_rate is None:
        print("  automatic SQL repair: N/A (no first-execution failures)")
    else:
        print(f"  automatic SQL repair: {_format_percentage(repair_rate)}")
    print(f"  ReflectNode tasks: {report['reflection_task_count']}/{report['task_count']}")
    p95 = report["end_to_end_p95_ms"]
    print(f"  end-to-end P95: {p95:.2f}ms" if p95 is not None else "  end-to-end P95: N/A")
    schema_avg = report["schema_retrieval_avg_ms"]
    if schema_avg is None:
        print("  Schema Linking average latency: N/A")
    else:
        print(
            "  Schema Linking average latency: "
            f"{schema_avg:.2f}ms (min={report['schema_retrieval_min_ms']:.2f}ms, "
            f"max={report['schema_retrieval_max_ms']:.2f}ms)"
        )
    if report["missing_task_ids"]:
        print(f"  missing task ids: {', '.join(report['missing_task_ids'])}")
    if report["missing_duration_task_ids"]:
        print(f"  missing duration task ids: {', '.join(report['missing_duration_task_ids'])}")
    if report["missing_schema_retrieval_duration_task_ids"]:
        print(
            "  missing Schema Linking duration task ids: "
            f"{', '.join(report['missing_schema_retrieval_duration_task_ids'])}"
        )


def _print_comparison(comparison: Mapping[str, Any], top_k: int) -> None:
    for metric, label in (("macro_f1", "macro F1"), ("top_k_exact_accuracy", f"Top-{top_k} exact accuracy")):
        item = comparison[metric]
        relative = item["relative_improvement"]
        relative_text = "N/A" if relative is None else f"{relative * 100:+.2f}%"
        print(
            f"{label}: {item['baseline'] * 100:.2f}% -> {item['optimized'] * 100:.2f}% "
            f"({item['absolute_delta'] * 100:+.2f}pp, relative {relative_text})"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True, help="JSON file containing question_id and gold_tables")
    parser.add_argument("--trajectory-dir", type=Path, help="Saved trajectory directory for one run")
    parser.add_argument("--baseline-trajectory-dir", type=Path, help="Baseline trajectory directory for comparison")
    parser.add_argument("--optimized-trajectory-dir", type=Path, help="Optimized trajectory directory for comparison")
    parser.add_argument("--label", default="run", help="Display label for the run")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.top_k <= 0:
        raise SystemExit("--top-k must be greater than zero")
    if bool(args.baseline_trajectory_dir) != bool(args.optimized_trajectory_dir):
        raise SystemExit("--baseline-trajectory-dir and --optimized-trajectory-dir must be provided together")
    if not args.trajectory_dir and not args.baseline_trajectory_dir:
        raise SystemExit("Provide --trajectory-dir or both baseline/optimized trajectory directories")

    gold_tasks = load_gold_tasks(args.gold)
    if args.baseline_trajectory_dir and args.optimized_trajectory_dir:
        baseline = evaluate_run(args.baseline_trajectory_dir, gold_tasks, top_k=args.top_k)
        optimized = evaluate_run(args.optimized_trajectory_dir, gold_tasks, top_k=args.top_k)
        comparison = compare_runs(baseline, optimized)
        _print_summary("baseline", baseline)
        _print_summary("optimized", optimized)
        print("[comparison]")
        _print_comparison(comparison, args.top_k)
        report: Mapping[str, Any] = {"baseline": baseline, "optimized": optimized, "comparison": comparison}
    else:
        report = evaluate_run(
            args.trajectory_dir,
            gold_tasks,
            top_k=args.top_k,
            allow_incomplete=args.allow_incomplete,
        )
        _print_summary(args.label, report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
