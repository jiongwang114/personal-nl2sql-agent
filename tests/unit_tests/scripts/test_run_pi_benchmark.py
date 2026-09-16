import json

from scripts.run_pi_benchmark import completed_keys, load_cases, parse_sse


def test_load_cases_supports_csv(tmp_path):
    path = tmp_path / "cases.csv"
    path.write_text('question,sql\n"How many?","SELECT COUNT(*) FROM t"\n', encoding="utf-8")

    cases = load_cases(path)

    assert cases[0].task_id == "case-1"
    assert cases[0].question == "How many?"
    assert cases[0].expected_sql == "SELECT COUNT(*) FROM t"


def test_parse_sse_extracts_message_and_metrics():
    text = (
        'event: message\ndata: {"payload":{"content":[{"payload":{"content":"answer"}}]}}\n\n'
        'event: end\ndata: {"action_count":2,"input_tokens":4}\n\n'
    )

    result = parse_sse(text)

    assert result["answer"] == "answer"
    assert result["metrics"]["action_count"] == 2


def test_completed_keys_supports_resume(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_text(json.dumps({"task_id": "case-1", "variant": "single"}) + "\n", encoding="utf-8")

    assert completed_keys(path) == {("case-1", "single")}
