import pytest

from benchmark.scripts.schema_recall_metrics import (
    GoldTask,
    compare_runs,
    evaluate_run,
    evaluate_task,
    normalize_table_name,
)


def test_normalize_table_name_ignores_database_alias():
    assert normalize_table_name("duck.mf_demo.orders") == "mf_demo.orders"
    assert normalize_table_name({"schema_name": "mf_demo", "table_name": "orders"}) == "mf_demo.orders"


def test_evaluate_task_calculates_macro_precision_recall_and_f1():
    task = GoldTask("1", "question", ("mf_demo.orders", "mf_demo.customers"))
    trajectory = {
        "workflow": {
            "nodes": [
                {
                    "type": "schema_linking",
                    "result": {
                        "table_schemas": [
                            {"identifier": "duck.mf_demo.orders"},
                            {"identifier": "duck.mf_demo.customers"},
                            {"identifier": "duck.mf_demo.products"},
                        ]
                    },
                }
            ]
        }
    }

    metrics = evaluate_task(task, trajectory)

    assert metrics.predicted_top_k == ("mf_demo.orders", "mf_demo.customers", "mf_demo.products")
    assert metrics.matched_tables == ("mf_demo.orders", "mf_demo.customers")
    assert metrics.precision == 2 / 3
    assert metrics.recall == 1.0
    assert metrics.f1 == 0.8
    assert metrics.top_k_exact_match is True


def test_evaluate_run_uses_first_and_last_execute_nodes(tmp_path):
    trajectory = tmp_path / "1_123.yaml"
    trajectory.write_text(
        """
workflow:
  task:
    id: '1'
  creation_time: 10
  completion_time: 12
  nodes:
    - type: schema_linking
      result:
        table_schemas:
          - identifier: duck.mf_demo.orders
    - type: execute_sql
      status: completed
      start_time: 10.5
      result:
        success: false
    - type: execute_sql
      status: completed
      start_time: 11.5
      result:
        success: true
""",
        encoding="utf-8",
    )
    gold = {"1": GoldTask("1", "question", ("mf_demo.orders",))}

    report = evaluate_run(tmp_path, gold)

    assert report["macro_f1"] == 1.0
    assert report["top_k_exact_accuracy"] == 1.0
    assert report["first_execution_success_rate"] == 0.0
    assert report["final_execution_success_rate"] == 1.0
    assert report["first_failure_task_ids"] == ["1"]
    assert report["auto_repaired_task_ids"] == ["1"]
    assert report["auto_repair_rate"] == 1.0
    assert report["reflection_task_count"] == 0
    assert report["end_to_end_p95_ms"] == 2000.0
    assert report["schema_retrieval_avg_ms"] is None
    assert report["missing_schema_retrieval_duration_task_ids"] == ["1"]


def test_evaluate_run_reports_schema_retrieval_latency(tmp_path):
    trajectory = tmp_path / "1_123.yaml"
    trajectory.write_text(
        """
workflow:
  task:
    id: '1'
  creation_time: 10
  completion_time: 12
  nodes:
    - type: schema_linking
      start_time: 10.1
      end_time: 10.25
      result:
        table_schemas:
          - identifier: duck.mf_demo.orders
""",
        encoding="utf-8",
    )
    gold = {"1": GoldTask("1", "question", ("mf_demo.orders",))}

    report = evaluate_run(tmp_path, gold, allow_incomplete=True)

    assert report["schema_retrieval_count"] == 1
    assert report["schema_retrieval_avg_ms"] == pytest.approx(150.0)
    assert report["schema_retrieval_min_ms"] == pytest.approx(150.0)
    assert report["schema_retrieval_max_ms"] == pytest.approx(150.0)


def test_evaluate_run_reports_no_auto_repair_denominator_for_all_first_successes(tmp_path):
    trajectory = tmp_path / "1_123.yaml"
    trajectory.write_text(
        """
workflow:
  task:
    id: '1'
  creation_time: 10
  completion_time: 12
  nodes:
    - type: schema_linking
      start_time: 10.1
      end_time: 10.25
      result:
        table_schemas:
          - identifier: duck.mf_demo.orders
    - type: execute_sql
      status: completed
      start_time: 10.5
      end_time: 10.6
      result:
        success: true
    - type: reflect
      status: completed
      result:
        success: true
        strategy: SUCCESS
""",
        encoding="utf-8",
    )
    gold = {"1": GoldTask("1", "question", ("mf_demo.orders",))}

    report = evaluate_run(tmp_path, gold)

    assert report["auto_repair_rate"] is None
    assert report["reflection_task_ids"] == ["1"]


def test_compare_runs_reports_absolute_and_relative_improvement():
    baseline = {"top_k": 5, "task_count": 10, "gold_task_count": 10, "macro_f1": 0.71, "top_k_exact_accuracy": 0.65}
    optimized = {"top_k": 5, "task_count": 10, "gold_task_count": 10, "macro_f1": 0.89, "top_k_exact_accuracy": 0.82}

    comparison = compare_runs(baseline, optimized)

    assert comparison["macro_f1"]["absolute_delta"] == pytest.approx(0.18)
    assert comparison["macro_f1"]["relative_improvement"] == pytest.approx(0.18 / 0.71)
    assert comparison["top_k_exact_accuracy"]["absolute_delta"] == pytest.approx(0.17)
