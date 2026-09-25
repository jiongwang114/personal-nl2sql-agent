from scripts.compare_pi_variants import summarize


def test_summarize_groups_variants_and_averages_metrics():
    report = summarize(
        [
            {"variant": "single", "task_id": "1", "result_correct": True, "latency_ms": 10},
            {"variant": "single", "task_id": "2", "result_correct": False, "latency_ms": 30},
            {"variant": "multi", "task_id": "1", "result_correct": True, "latency_ms": 50},
            {"variant": "legacy", "task_id": "1", "result_correct": True, "latency_ms": 5},
        ]
    )

    assert report["single"]["tasks"] == 2
    assert report["single"]["result_correct"] == 0.5
    assert report["single"]["latency_ms"] == 20
    assert report["multi"]["result_correct"] == 1
    assert "legacy" not in report


def test_summarize_omits_correctness_until_all_answers_are_reviewed():
    report = summarize(
        [
            {"variant": "single", "task_id": "1", "result_correct": False, "error": "timeout", "latency_ms": 180000},
            {"variant": "single", "task_id": "2", "result_correct": None, "error": None, "latency_ms": 1200},
        ]
    )

    assert report["single"]["completion_rate"] == 0.5
    assert "result_correct" not in report["single"]
