"""Run the project-local Pi SQL runtime and adapt its output to chat SSE events."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Literal

import yaml

from dataengineer.api.models.cli_models import (
    IMessageContent,
    SSEDataType,
    SSEEndData,
    SSEErrorData,
    SSEEvent,
    SSEMessageData,
    SSEMessagePayload,
    SSESessionData,
    StreamChatInput,
)

RuntimeVariant = Literal["single", "multi"]

SINGLE_TOOLS = "list_schemas,list_tables,describe_table,get_table_ddl,validate_sql,execute_readonly_sql"
MULTI_TOOLS = "sql_subagent,validate_sql,execute_readonly_sql"
SQL_EXTENSIONS = ("sql-tools", "sql-agents", "sql-observability")


@dataclass
class PiRunResult:
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    tool_calls: int = 0
    raw_messages: list[dict] = field(default_factory=list)


class PiRuntimeError(RuntimeError):
    """Safe error returned when the Pi child cannot complete."""


class PiRuntimeService:
    def __init__(self, project_root: Path | None = None, model: str = "custom/gpt-5.5", timeout: float = 300.0):
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.model = model
        self.timeout = timeout

    def build_command(self, variant: RuntimeVariant, request: StreamChatInput, datasource: str) -> list[str]:
        cli = (
            self.project_root
            / ".pi"
            / "node_modules"
            / "@earendil-works"
            / "pi-coding-agent"
            / "dist"
            / "bundle"
            / "cli.js"
        )
        if not cli.is_file():
            raise PiRuntimeError("Pi runtime is not installed for this project")

        tools = SINGLE_TOOLS if variant == "single" else MULTI_TOOLS
        command = [
            "node",
            str(cli),
            "--mode",
            "json",
            "-p",
            "--no-session",
            "--model",
            self.model,
            "--thinking",
            "minimal",
        ]
        for extension in SQL_EXTENSIONS:
            command.extend(["-e", str(self.project_root / ".pi" / "extensions" / extension / "index.ts")])
        command.extend(["--tools", tools])
        if variant == "single":
            command.extend(["--append-system-prompt", str(self.project_root / ".pi" / "agents" / "baseline-agent.md")])
        command.append(f"Datasource: {datasource}\nQuestion: {request.message}")
        return command

    def prepare_runtime_config(self, datasource: str, temp_dir: Path) -> Path:
        config_path = self.project_root / "conf" / "agent.yml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        datasource_config = config["agent"]["services"]["datasources"].get(datasource)
        if not isinstance(datasource_config, dict):
            raise PiRuntimeError(f"Datasource {datasource} is not configured")
        if datasource_config.get("type") == "duckdb":
            uri = str(datasource_config.get("uri", ""))
            source = Path(uri.removeprefix("duckdb:///"))
            if not source.is_absolute():
                source = self.project_root / source
            if not source.is_file():
                raise PiRuntimeError(f"DuckDB datasource file does not exist: {source}")
            snapshot = temp_dir / source.name
            shutil.copy2(source, snapshot)
            datasource_config["uri"] = f"duckdb:///{snapshot.as_posix()}"
            datasource_config["read_only"] = True
        runtime_config = temp_dir / "agent.yml"
        runtime_config.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return runtime_config

    async def run(self, variant: RuntimeVariant, request: StreamChatInput, datasource: str) -> PiRunResult:
        command = self.build_command(variant, request, datasource)
        with tempfile.TemporaryDirectory(prefix="pi-sql-runtime-") as temp:
            runtime_config = self.prepare_runtime_config(datasource, Path(temp))
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    env={
                        **os.environ,
                        "PI_SQL_RUNTIME_VARIANT": variant,
                        "PI_SQL_PYTHON": sys.executable,
                        "PI_SQL_CONFIG": str(runtime_config),
                    },
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except OSError as exc:
                raise PiRuntimeError("Pi runtime could not be started") from exc
            communicate = asyncio.create_task(asyncio.to_thread(process.communicate))
            try:
                stdout, _stderr = await asyncio.wait_for(asyncio.shield(communicate), timeout=self.timeout)
            except asyncio.CancelledError:
                process.terminate()
                await communicate
                raise
            except TimeoutError:
                process.terminate()
                await communicate
                raise PiRuntimeError("Pi runtime timed out") from None

            if process.returncode != 0:
                raise PiRuntimeError("Pi runtime failed; inspect server logs for the child process status")
        return self.parse_output(stdout.decode("utf-8", errors="replace"))

    @staticmethod
    def parse_output(output: str) -> PiRunResult:
        result = PiRunResult()
        for line in output.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "tool_execution_start":
                result.tool_calls += 1
            if event.get("type") != "message_end" or not isinstance(event.get("message"), dict):
                continue
            message = event["message"]
            result.raw_messages.append(message)
            if message.get("role") != "assistant":
                continue
            content = message.get("content", [])
            result.text = "\n".join(
                part["text"]
                for part in content
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
            )
            usage = message.get("usage", {})
            if isinstance(usage, dict):
                result.input_tokens += int(usage.get("input", 0) or 0)
                result.output_tokens += int(usage.get("output", 0) or 0)
                result.cached_tokens += int(usage.get("cacheRead", 0) or 0)
        if not result.text:
            raise PiRuntimeError("Pi runtime returned no assistant message")
        return result

    async def stream_chat(self, request: StreamChatInput, datasource: str) -> AsyncGenerator[SSEEvent, None]:
        variant = request.runtime_variant
        if variant not in ("single", "multi"):
            raise ValueError(f"Pi runtime does not support variant {variant}")
        session_id = request.session_id or f"pi_{variant}_{uuid.uuid4().hex}"
        started = datetime.now()
        yield SSEEvent(id=1, event="session", data=SSESessionData(session_id=session_id, llm_session_id=None))
        try:
            result = await self.run(variant, request, datasource)
        except PiRuntimeError as exc:
            yield SSEEvent(
                id=2,
                event="error",
                data=SSEErrorData(error=str(exc), error_type=type(exc).__name__, session_id=session_id),
            )
            return

        message_id = uuid.uuid4().hex
        yield SSEEvent(
            id=2,
            event="message",
            data=SSEMessageData(
                type=SSEDataType.UPDATE_MESSAGE,
                payload=SSEMessagePayload(
                    message_id=message_id,
                    role="assistant",
                    content=[IMessageContent(type="markdown", payload={"content": result.text})],
                ),
            ),
        )
        yield SSEEvent(
            id=3,
            event="end",
            data=SSEEndData(
                session_id=session_id,
                total_events=3,
                action_count=result.tool_calls,
                duration=(datetime.now() - started).total_seconds(),
                requests=1,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.input_tokens + result.output_tokens + result.cached_tokens,
                cached_tokens=result.cached_tokens,
            ),
        )
