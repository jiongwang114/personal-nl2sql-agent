from pathlib import Path

import pytest
import yaml

from dataengineer.api.models.cli_models import SSEDataType, StreamChatInput
from dataengineer.api.services.pi_runtime_service import PiRunResult, PiRuntimeError, PiRuntimeService


def test_build_command_uses_variant_tools(tmp_path: Path):
    cli = tmp_path / ".pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")
    service = PiRuntimeService(project_root=tmp_path)
    request = StreamChatInput(message="question", runtime_variant="multi")

    single = service.build_command("single", request, "demo")
    multi = service.build_command("multi", request, "demo")

    assert "custom/gpt-6-luna" in single
    assert "list_schemas,list_tables,describe_table,get_table_ddl,validate_sql,execute_readonly_sql" in single
    assert "sql_subagent,validate_sql,execute_readonly_sql" in multi
    assert "--append-system-prompt" in single
    assert "--append-system-prompt" not in multi
    expected_extensions = [
        str(tmp_path / ".pi/extensions/sql-tools/index.ts"),
        str(tmp_path / ".pi/extensions/sql-agents/index.ts"),
        str(tmp_path / ".pi/extensions/sql-observability/index.ts"),
    ]
    for command in (single, multi):
        thinking_index = command.index("--thinking")
        assert command[thinking_index + 1] == "minimal"
        assert command.count("-e") == len(expected_extensions)
        assert all(extension in command for extension in expected_extensions)


def test_build_command_uses_request_model(tmp_path: Path):
    cli = tmp_path / ".pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")
    service = PiRuntimeService(project_root=tmp_path)
    request = StreamChatInput(message="question", runtime_variant="single", model="custom/gpt-6-luna")

    command = service.build_command("single", request, "demo")

    assert command[command.index("--model") + 1] == "custom/gpt-6-luna"


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


def test_prepare_runtime_config_resolves_catalog_display_name(tmp_path: Path):
    project = tmp_path / "project"
    (project / "conf").mkdir(parents=True)
    (project / "sample_data").mkdir()
    (project / "sample_data/duckdb-demo.duckdb").write_bytes(b"database")
    (project / "conf/agent.yml").write_text(
        "agent:\n  services:\n    datasources:\n      demo:\n        type: duckdb\n        uri: duckdb:///sample_data/duckdb-demo.duckdb\n",
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    runtime_config = PiRuntimeService(project_root=project).prepare_runtime_config("duckdb-demo", runtime_dir)
    config = yaml.safe_load(runtime_config.read_text(encoding="utf-8"))

    assert "demo" in config["agent"]["services"]["datasources"]


def test_parse_output_rejects_missing_assistant_message():
    with pytest.raises(PiRuntimeError):
        PiRuntimeService.parse_output('{"type":"agent_end","messages":[]}')


def test_parse_output_surfaces_provider_error_without_secrets(monkeypatch):
    monkeypatch.setenv("WLB_API_KEY", "test-secret-marker")
    output = (
        '{"type":"message_end","message":{"role":"assistant","stopReason":"error",'
        '"errorMessage":"OpenAI API error (403): '
        '{\\"code\\":\\"sub2_weekly_quota_exhausted\\",'
        '\\"message\\":\\"weekly quota exhausted; key=test-secret-marker\\"}","content":[]}}\n'
    )

    with pytest.raises(PiRuntimeError) as error:
        PiRuntimeService.parse_output(output)

    assert "HTTP 403" in str(error.value)
    assert "sub2_weekly_quota_exhausted" in str(error.value)
    assert "weekly quota exhausted" in str(error.value)
    assert "test-secret-marker" not in str(error.value)


@pytest.mark.asyncio
async def test_stream_chat_returns_provider_error_as_sse(monkeypatch):
    service = PiRuntimeService()

    async def failed_stream_run(variant, request, datasource):
        raise PiRuntimeError("Provider request failed (HTTP 403, quota_exhausted): weekly quota exhausted")
        yield

    monkeypatch.setattr(service, "stream_run", failed_stream_run)
    request = StreamChatInput(message="question", session_id="s1", runtime_variant="single")

    events = [event async for event in service.stream_chat(request, "demo")]

    assert [event.event for event in events] == ["session", "error"]
    assert "HTTP 403" in events[-1].data.error
    assert "quota_exhausted" in events[-1].data.error


@pytest.mark.asyncio
async def test_stream_chat_maps_result_to_sse(monkeypatch):
    service = PiRuntimeService()

    async def fake_stream_run(variant, request, datasource):
        yield {"type": "tool_execution_start", "toolName": "list_tables", "args": {}}
        yield {"type": "tool_execution_end", "toolName": "list_tables", "result": ["orders"]}
        yield PiRunResult(text="done", input_tokens=3, output_tokens=2, tool_calls=1)

    monkeypatch.setattr(service, "stream_run", fake_stream_run)
    request = StreamChatInput(message="question", session_id="s1", runtime_variant="single")

    events = [event async for event in service.stream_chat(request, "demo")]

    assert [event.event for event in events] == ["session", "message", "message", "message", "end"]
    assert [event.id for event in events] == [1, 2, 3, 4, 5]
    assert events[1].data.payload.content[0].type == "call-tool"
    assert events[2].data.payload.content[0].type == "call-tool-result"
    assert events[3].data.type == SSEDataType.UPDATE_MESSAGE
    assert events[3].data.payload.content[0].type == "markdown"
    assert events[3].data.payload.content[0].payload["content"] == "done"
    assert events[4].data.total_tokens == 5


@pytest.mark.asyncio
async def test_stream_chat_does_not_end_without_nonempty_assistant_answer(monkeypatch):
    service = PiRuntimeService()

    async def empty_stream_run(variant, request, datasource):
        yield PiRunResult(text=" \n ")

    monkeypatch.setattr(service, "stream_run", empty_stream_run)
    request = StreamChatInput(message="question", session_id="s1", runtime_variant="single")

    events = [event async for event in service.stream_chat(request, "demo")]

    assert [event.event for event in events] == ["session", "error"]
    assert "no assistant message" in events[-1].data.error
