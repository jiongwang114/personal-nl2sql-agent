import argparse
import json

import pytest

from scripts.run_pi_benchmark import BenchmarkCase, completed_keys, load_cases, parse_sse, run, run_case


def test_load_cases_supports_csv(tmp_path):
    path = tmp_path / "cases.csv"
    path.write_text('question,sql\n"How many?","SELECT COUNT(*) FROM t"\n', encoding="utf-8")

    cases = load_cases(path)

    assert cases[0].task_id == "case-1"
    assert cases[0].question == "How many?"
    assert cases[0].expected_sql == "SELECT COUNT(*) FROM t"


def test_load_cases_uses_case_id_when_present(tmp_path):
    path = tmp_path / "cases.csv"
    path.write_text('case_id,question,sql\nB01,"How many?","SELECT COUNT(*) FROM t"\n', encoding="utf-8")

    cases = load_cases(path)

    assert cases[0].task_id == "B01"


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

    assert completed_keys(path) == {("case-1", "single", 1)}


@pytest.mark.asyncio
async def test_run_case_marks_empty_answer_as_error():
    class Response:
        text = "event: session\ndata: {}\n\n"

        @staticmethod
        def raise_for_status():
            return None

    class Client:
        @staticmethod
        async def post(*_args, **_kwargs):
            return Response()

    result = await run_case(Client(), "http://test", BenchmarkCase("case-1", "question"), "single")

    assert result["error"] == "EMPTY_ANSWER: runtime completed without assistant text"


@pytest.mark.asyncio
async def test_run_overrides_case_datasource(monkeypatch, tmp_path):
    cases = tmp_path / "cases.csv"
    cases.write_text("question,datasource\nHow many?,demo\n", encoding="utf-8")
    seen = []

    async def fake_run_case(_client, _base_url, case, variant, repeat_index):
        seen.append((case.datasource, variant, repeat_index))
        return {"task_id": case.task_id, "variant": variant, "repeat_index": repeat_index, "error": None}

    monkeypatch.setattr("scripts.run_pi_benchmark.run_case", fake_run_case)
    args = argparse.Namespace(
        cases=cases,
        output=tmp_path / "out.jsonl",
        base_url="http://test",
        variants="single",
        datasource="benchmark_demo",
        limit=0,
        resume=False,
        repeats=2,
    )

    assert await run(args) == 0
    assert seen == [("benchmark_demo", "single", 1), ("benchmark_demo", "single", 2)]


@pytest.mark.asyncio
async def test_run_defaults_to_single_and_multi(monkeypatch, tmp_path):
    cases = tmp_path / "cases.csv"
    cases.write_text("question\nHow many?\n", encoding="utf-8")
    seen = []

    async def fake_run_case(_client, _base_url, case, variant, repeat_index):
        seen.append(variant)
        return {"task_id": case.task_id, "variant": variant, "repeat_index": repeat_index, "error": None}

    monkeypatch.setattr("scripts.run_pi_benchmark.run_case", fake_run_case)
    args = argparse.Namespace(
        cases=cases,
        output=tmp_path / "out.jsonl",
        base_url="http://test",
        datasource="",
        limit=0,
        resume=False,
        repeats=1,
    )

    assert await run(args) == 0
    assert seen == ["single", "multi"]


@pytest.mark.asyncio
async def test_run_rejects_legacy_variant(tmp_path):
    cases = tmp_path / "cases.csv"
    cases.write_text("question\nHow many?\n", encoding="utf-8")
    args = argparse.Namespace(
        cases=cases,
        output=tmp_path / "out.jsonl",
        base_url="http://test",
        variants="legacy",
        datasource="",
        limit=0,
        resume=False,
        repeats=1,
    )

    with pytest.raises(ValueError, match="expected single or multi"):
        await run(args)
