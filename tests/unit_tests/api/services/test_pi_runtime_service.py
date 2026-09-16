from pathlib import Path

import pytest
import yaml

from dataengineer.api.models.cli_models import StreamChatInput
from dataengineer.api.services.pi_runtime_service import PiRunResult, PiRuntimeError, PiRuntimeService


def test_build_command_uses_variant_tools(tmp_path: Path):
    cli = tmp_path / ".pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")
    service = PiRuntimeService(project_root=tmp_path)
    request = StreamChatInput(message="question", runtime_variant="multi")

    single = service.build_command("single", request, "demo")
    multi = service.build_command("multi", request, "demo")

    assert "custom/gpt-5.5" in single
    assert "list_tables,describe_table,get_table_ddl,validate_sql,execute_readonly_sql" in single
    assert "sql_subagent,validate_sql,execute_readonly_sql" in multi
    assert "--append-system-prompt" in single
    assert "--append-system-prompt" not in multi
    expected_extensions = [
        str(tmp_path / ".pi/extensions/sql-tools/index.ts"),
        str(tmp_path / ".pi/extensions/sql-agents/index.ts"),
        str(tmp_path / ".pi/extensions/sql-observability/index.ts"),
    ]
    for command in (single, multi):
        assert command.count("-e") == len(expected_extensions)
        assert all(extension in command for extension in expected_extensions)


def test_parse_output_extracts_final_message_and_usage():
    output = (
        '{"type":"tool_execution_start"}\n'
        '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"answer"}],'
        '"usage":{"input":10,"output":4,"cacheRead":2}}}\n'
    )

    result = PiRuntimeService.parse_output(output)

    assert result.text == "answer"
    assert result.input_tokens == 10
    assert result.output_tokens == 4
    assert result.cached_tokens == 2
    assert result.tool_calls == 1


def test_prepare_runtime_config_snapshots_duckdb(tmp_path: Path):
    project = tmp_path / "project"
    (project / "conf").mkdir(parents=True)
    (project / "sample_data").mkdir()
    (project / "sample_data/demo.duckdb").write_bytes(b"database")
    (project / "conf/agent.yml").write_text(
        "agent:\n  services:\n    datasources:\n      demo:\n        type: duckdb\n        uri: duckdb:///sample_data/demo.duckdb\n",
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    runtime_config = PiRuntimeService(project_root=project).prepare_runtime_config("demo", runtime_dir)
    config = yaml.safe_load(runtime_config.read_text(encoding="utf-8"))
    datasource = config["agent"]["services"]["datasources"]["demo"]

    assert datasource["read_only"] is True
    assert datasource["uri"].startswith("duckdb:///")
    assert (runtime_dir / "demo.duckdb").read_bytes() == b"database"


def test_parse_output_rejects_missing_assistant_message():
    with pytest.raises(PiRuntimeError):
        PiRuntimeService.parse_output('{"type":"agent_end","messages":[]}')


@pytest.mark.asyncio
async def test_stream_chat_maps_result_to_sse(monkeypatch):
    service = PiRuntimeService()

    async def fake_run(variant, request, datasource):
        return PiRunResult(text="done", input_tokens=3, output_tokens=2, tool_calls=1)

    monkeypatch.setattr(service, "run", fake_run)
    request = StreamChatInput(message="question", session_id="s1", runtime_variant="single")

    events = [event async for event in service.stream_chat(request, "demo")]

    assert [event.event for event in events] == ["session", "message", "end"]
    assert events[1].data.payload.content[0].payload["content"] == "done"
    assert events[2].data.total_tokens == 5
