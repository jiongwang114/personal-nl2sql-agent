"""Run the project-local Pi SQL runtime and adapt its output to chat SSE events."""

import asyncio
import json
import os
import re
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
from dataengineer.api.services.credential_store import CredentialStore, CredentialStoreError
from dataengineer.configuration.project_config import load_project_override

RuntimeVariant = Literal["single", "multi"]

SINGLE_TOOLS = "list_schemas,list_tables,describe_table,get_table_ddl,validate_sql,execute_readonly_sql"
MULTI_TOOLS = "sql_subagent,validate_sql,execute_readonly_sql"
SQL_EXTENSIONS = ("sql-tools", "sql-agents", "sql-observability")


@dataclass
class PiRunResult:
    text: str = ""
    error_message: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    tool_calls: int = 0
    model: str = ""
    thinking_level: str = ""
    raw_messages: list[dict] = field(default_factory=list)


class PiRuntimeError(RuntimeError):
    """Safe error returned when the Pi child cannot complete."""


class PiRuntimeService:
    def __init__(
        self,
        project_root: Path | None = None,
        model: str = "custom/gpt-6-luna",
        timeout: float = 300.0,
        config_path: Path | None = None,
        agent_config=None,
        credential_scope: str = "default",
    ):
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.config_path = config_path or self.project_root / "conf" / "agent.yml"
        self.agent_config = agent_config
        self.credential_scope = credential_scope
        self.model = model
        self.timeout = timeout
        self._model_catalog_cache: dict[str, dict] = {}

    def _settings(self):
        return load_project_override(cwd=str(self.project_root))

    def _effective_model(self, request: StreamChatInput) -> tuple[str, str, str]:
        settings = self._settings()
        provider = getattr(settings, "pi_provider", None) if settings else None
        configured_model = getattr(settings, "pi_model", None) if settings else None
        configured = f"{provider}/{configured_model}" if provider and configured_model else ""
        model = request.model or configured or self.model
        if "/" in model:
            selected_provider = model.split("/", 1)[0]
        else:
            selected_provider = provider or "custom"
            model = f"{selected_provider}/{model}"
        bare_model = model.split("/", 1)[1]
        model_info = self.model_definition(selected_provider, bare_model)
        supported = self._supported_thinking_levels(selected_provider, bare_model, model_info)
        default_thinking = "minimal" if "minimal" in supported else "low"
        thinking = request.thinking_level or getattr(settings, "pi_thinking", None) or default_thinking
        if thinking not in supported:
            raise PiRuntimeError(f"Thinking level '{thinking}' is not supported by {model}")
        return model, selected_provider, thinking

    def build_command(self, variant: RuntimeVariant, request: StreamChatInput, datasource: str) -> list[str]:
        model, _, thinking = self._effective_model(request)
        if self.config_path.is_file():
            config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
            datasource = self._resolve_datasource_key(config["agent"]["services"]["datasources"], datasource)
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
            model,
            "--thinking",
            thinking,
        ]
        for extension in SQL_EXTENSIONS:
            command.extend(["-e", str(self.project_root / ".pi" / "extensions" / extension / "index.ts")])
        command.extend(["--tools", tools])
        if variant == "single":
            command.extend(["--append-system-prompt", str(self.project_root / ".pi" / "agents" / "baseline-agent.md")])
        command.append(f"Datasource: {datasource}\nQuestion: {request.message}")
        return command

    def prepare_runtime_config(self, datasource: str, temp_dir: Path) -> Path:
        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        datasources = config["agent"]["services"]["datasources"]
        datasource_key = self._resolve_datasource_key(datasources, datasource)
        datasource_config = datasources.get(datasource_key)
        if not isinstance(datasource_config, dict):
            raise PiRuntimeError(f"Datasource {datasource} is not configured")
        if datasource_config.get("type") in {"duckdb", "sqlite"}:
            uri = str(datasource_config.get("uri", ""))
            db_type = str(datasource_config["type"])
            source = Path(uri.removeprefix(f"{db_type}:///"))
            if not source.is_absolute():
                source = self.project_root / source
            if not source.is_file():
                raise PiRuntimeError(f"{db_type} datasource file does not exist")
            snapshot = temp_dir / source.name
            if db_type == "sqlite":
                import sqlite3

                source_conn = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
                target_conn = sqlite3.connect(snapshot)
                try:
                    source_conn.backup(target_conn)
                finally:
                    target_conn.close()
                    source_conn.close()
            else:
                shutil.copy2(source, snapshot)
            datasource_config["uri"] = f"{db_type}:///{snapshot.as_posix()}"
            datasource_config["read_only"] = True
        runtime_config = temp_dir / "agent.yml"
        runtime_config.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return runtime_config

    def model_definition(self, provider: str, model: str) -> dict | None:
        aliases = {
            "claude": "anthropic",
            "gemini": "google",
            "kimi": "moonshotai",
            "qwen": "qwen-token-plan",
            "minimax": "minimax",
            "glm": "zai",
        }
        catalog_provider = aliases.get(provider, provider)
        if catalog_provider not in self._model_catalog_cache:
            self._model_catalog_cache[catalog_provider] = {}
        data_file = (
            self.project_root
            / ".pi"
            / "node_modules"
            / "@earendil-works"
            / "pi-ai"
            / "dist"
            / "providers"
            / "data"
            / f"{catalog_provider}.json"
        )
        cache = self._model_catalog_cache[catalog_provider]
        if not cache and data_file.is_file():
            try:
                groups = json.loads(data_file.read_text(encoding="utf-8"))
                for entries in groups.values():
                    if isinstance(entries, dict):
                        cache.update({key: value for key, value in entries.items() if isinstance(value, dict)})
            except (OSError, json.JSONDecodeError):
                return None
        definition = cache.get(model)
        return dict(definition) if isinstance(definition, dict) else None

    def thinking_levels(self, provider: str, model: str) -> list[str]:
        return self._supported_thinking_levels(provider, model, self.model_definition(provider, model))

    @staticmethod
    def _pi_api(provider: str, provider_meta: dict, model_info: dict | None = None) -> str:
        if model_info and isinstance(model_info.get("api"), str):
            return model_info["api"]
        provider_type = str(provider_meta.get("type", "openai")).lower()
        if provider_type in {"anthropic", "claude"}:
            return "anthropic-messages"
        if provider_type in {"gemini", "google"}:
            return "google-generative-ai"
        if provider in {"openai", "custom"}:
            return "openai-responses"
        return "openai-completions"

    @staticmethod
    def _thinking_map(provider: str, model: str, model_info: dict | None = None) -> dict:
        if model_info:
            level_map = model_info.get("thinkingLevelMap")
            if isinstance(level_map, dict) and level_map:
                return level_map
            if model_info.get("reasoning") is False:
                return {"off": None}
        if provider == "deepseek" and "flash" in model.lower():
            return {"off": None, "low": "low", "high": "high", "max": "max"}
        if provider in {"openai", "custom"}:
            return {"off": None, "minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}
        return {"off": None, "minimal": "minimal", "low": "low", "medium": "medium", "high": "high"}

    @classmethod
    def _supported_thinking_levels(cls, provider: str, model: str, model_info: dict | None = None) -> list[str]:
        if model_info and model_info.get("reasoning") is False:
            return ["off"]
        levels = [
            level
            for level, mapping in cls._thinking_map(provider, model, model_info).items()
            if mapping is not None
        ]
        return levels or ["off"]

    def _prepare_pi_agent(self, temp_dir: Path, model: str, provider: str) -> tuple[Path | None, dict[str, str], str | None]:
        if self.agent_config is None:
            return None, {}, None
        providers = self.agent_config.provider_catalog.get("providers", {})
        meta = providers.get(provider, {}) if isinstance(providers, dict) else {}
        if not isinstance(meta, dict):
            return None, {}, None
        settings = self._settings()
        configured_provider = getattr(settings, "pi_provider", None) if settings else None
        override_url = getattr(settings, "pi_base_url", None) if settings and configured_provider == provider else None
        bare_model = model.split("/", 1)[1] if "/" in model else model
        model_info = self.model_definition(provider, bare_model)
        base_url = override_url or (model_info or {}).get("baseUrl") or meta.get("base_url") or ""
        try:
            secret = CredentialStore().get(self.credential_scope, provider)
        except CredentialStoreError as exc:
            raise PiRuntimeError(str(exc)) from exc
        key_env = str(meta.get("api_key_env") or "")
        if not secret and not override_url:
            return None, {}, None
        secret = secret or (os.getenv(key_env) if key_env else None)

        env_name = "DATAENGINEER_PI_API_KEY"
        model_definition = {
            key: value
            for key, value in (model_info or {}).items()
            if key in {"id", "name", "reasoning", "input", "contextWindow", "maxTokens", "thinkingLevelMap", "compat"}
        }
        model_definition.setdefault("id", bare_model)
        model_definition.setdefault("name", bare_model)
        model_definition.setdefault("reasoning", True)
        model_definition.setdefault("input", ["text"])
        model_definition.setdefault("contextWindow", 262144)
        model_definition.setdefault("maxTokens", 16384)
        model_definition["thinkingLevelMap"] = self._thinking_map(provider, bare_model, model_info)
        agent_dir = temp_dir / "pi-agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "providers": {
                provider: {
                    "name": provider,
                    "baseUrl": base_url,
                    "api": self._pi_api(provider, meta, model_info),
                    "apiKey": f"${{{env_name}}}",
                    "models": [model_definition],
                }
            }
        }
        (agent_dir / "models.json").write_text(json.dumps(payload), encoding="utf-8")
        env = {env_name: secret} if secret else {}
        return agent_dir, env, secret

    def _runtime_env(self, variant: RuntimeVariant, runtime_config: Path, temp_dir: Path, request: StreamChatInput):
        model, provider, _ = self._effective_model(request)
        agent_dir, credentials, secret = self._prepare_pi_agent(temp_dir, model, provider)
        env = {
            **os.environ,
            **credentials,
            "PI_SQL_RUNTIME_VARIANT": variant,
            "PI_SQL_PYTHON": os.getenv("PI_SQL_PYTHON") or sys.executable,
            "PI_SQL_CONFIG": str(runtime_config),
        }
        if agent_dir is not None:
            env["PI_CODING_AGENT_DIR"] = str(agent_dir)
        return env, model, secret

    @staticmethod
    def _resolve_datasource_key(datasources: dict, requested: str) -> str:
        """Resolve catalog display names such as ``duckdb-demo`` to config keys."""
        if requested in datasources:
            return requested
        requested_lower = requested.lower()
        for key, raw in datasources.items():
            if not isinstance(raw, dict):
                continue
            aliases = {str(key).lower(), str(raw.get("name", "")).lower()}
            uri = str(raw.get("uri", ""))
            aliases.add(Path(uri.split("///")[-1]).stem.lower())
            if requested_lower in aliases:
                return str(key)
        return requested

    async def run(self, variant: RuntimeVariant, request: StreamChatInput, datasource: str) -> PiRunResult:
        command = self.build_command(variant, request, datasource)
        with tempfile.TemporaryDirectory(prefix="pi-sql-runtime-") as temp:
            temp_dir = Path(temp)
            runtime_config = self.prepare_runtime_config(datasource, temp_dir)
            runtime_env, model, secret = self._runtime_env(variant, runtime_config, temp_dir, request)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    env=runtime_env,
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

            output = stdout.decode("utf-8", errors="replace")
            if process.returncode != 0:
                try:
                    self.parse_output(output, secret=secret)
                except PiRuntimeError as exc:
                    raise exc
                raise PiRuntimeError("Pi runtime failed; inspect server logs for the child process status")
        result = self.parse_output(output, secret=secret)
        result.model, _, result.thinking_level = self._effective_model(request)
        return result

    @staticmethod
    def parse_output(output: str, secret: str | None = None) -> PiRunResult:
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
            PiRuntimeService._record_message(result, event["message"], secret)
        if result.error_message:
            raise PiRuntimeError(result.error_message)
        if not result.text.strip():
            raise PiRuntimeError("Pi runtime returned no assistant message")
        return result

    @staticmethod
    def _safe_provider_error(error_message: object, secret: str | None = None) -> str:
        if not isinstance(error_message, str) or not error_message.strip():
            return ""

        raw = error_message.strip()
        status_match = re.search(r"(?:\bHTTP|\bAPI error)\s*\(?([1-5]\d\d)\)?", raw, re.IGNORECASE)
        payload = {}
        payload_start = raw.find("{")
        if payload_start >= 0:
            try:
                parsed, _ = json.JSONDecoder().raw_decode(raw[payload_start:])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                payload = parsed

        details = []
        if status_match:
            details.append(f"HTTP {status_match.group(1)}")
        code = payload.get("code")
        if isinstance(code, str) and code:
            details.append(code)
        message = payload.get("message")
        if details:
            summary = f"Provider request failed ({', '.join(details)})"
            if isinstance(message, str) and message:
                summary += f": {message}"
        else:
            summary = raw

        summary = re.sub(
            r"(?i)((?:api[_-]?key|authorization|access[_-]?token|refresh[_-]?token|secret|password)\s*[:=]\s*)"
            r"[\"']?[^,\s}\"']+",
            r"\1[REDACTED]",
            summary,
        )
        summary = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", summary)
        for name, value in os.environ.items():
            if value and any(marker in name.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
                summary = summary.replace(value, "[REDACTED]")
        if secret:
            summary = summary.replace(secret, "[REDACTED]")
        return summary[:1000]

    @staticmethod
    def _record_message(result: PiRunResult, message: dict, secret: str | None = None) -> None:
        result.raw_messages.append(message)
        if message.get("role") != "assistant":
            return

        error_message = PiRuntimeService._safe_provider_error(message.get("errorMessage"), secret)
        result.error_message = error_message if message.get("stopReason") == "error" or error_message else ""
        content = message.get("content", [])
        text = "\n".join(
            part["text"]
            for part in content
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
        )
        if text:
            result.text = text
        usage = message.get("usage", {})
        if isinstance(usage, dict):
            result.input_tokens += int(usage.get("input", 0) or 0)
            result.output_tokens += int(usage.get("output", 0) or 0)
            result.cached_tokens += int(usage.get("cacheRead", 0) or 0)

    async def stream_run(
        self, variant: RuntimeVariant, request: StreamChatInput, datasource: str
    ) -> AsyncGenerator[dict | PiRunResult, None]:
        """Yield Pi JSON events as they arrive, followed by the accumulated result."""
        command = self.build_command(variant, request, datasource)
        model, _, thinking = self._effective_model(request)
        result = PiRunResult(model=model, thinking_level=thinking)
        with tempfile.TemporaryDirectory(prefix="pi-sql-runtime-") as temp:
            temp_dir = Path(temp)
            runtime_config = self.prepare_runtime_config(datasource, temp_dir)
            runtime_env, _, secret = self._runtime_env(variant, runtime_config, temp_dir, request)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    env=runtime_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=1,
                )
            except OSError as exc:
                raise PiRuntimeError("Pi runtime could not be started") from exc

            assert process.stdout is not None
            stderr_task = asyncio.create_task(asyncio.to_thread(process.stderr.read)) if process.stderr is not None else None
            try:
                async with asyncio.timeout(self.timeout):
                    while True:
                        raw_line = await asyncio.to_thread(process.stdout.readline)
                        if not raw_line:
                            break
                        try:
                            event = json.loads(raw_line.decode("utf-8", errors="replace"))
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        self._accumulate_event(result, event, secret)
                        yield event
                    await asyncio.to_thread(process.wait)
            except asyncio.CancelledError:
                if process.poll() is None:
                    process.terminate()
                await asyncio.to_thread(process.wait)
                if stderr_task:
                    await stderr_task
                raise
            except TimeoutError:
                if process.poll() is None:
                    process.terminate()
                await asyncio.to_thread(process.wait)
                if stderr_task:
                    await stderr_task
                raise PiRuntimeError("Pi runtime timed out") from None
            finally:
                if stderr_task and not stderr_task.done():
                    await stderr_task

            if process.returncode != 0:
                if result.error_message:
                    raise PiRuntimeError(result.error_message)
                raise PiRuntimeError("Pi runtime failed; inspect server logs for the child process status")
        if result.error_message:
            raise PiRuntimeError(result.error_message)
        if not result.text.strip():
            raise PiRuntimeError("Pi runtime returned no assistant message")
        yield result

    @staticmethod
    def _accumulate_event(result: PiRunResult, event: dict, secret: str | None = None) -> None:
        if event.get("type") == "tool_execution_start":
            result.tool_calls += 1
        if event.get("type") != "message_end" or not isinstance(event.get("message"), dict):
            return
        PiRuntimeService._record_message(result, event["message"], secret)

    @staticmethod
    def _event_content(event: dict) -> IMessageContent | None:
        event_type = event.get("type")
        if event_type == "tool_execution_start":
            tool_call = event.get("toolCall") if isinstance(event.get("toolCall"), dict) else {}
            return IMessageContent(
                type="call-tool",
                payload={
                    "callToolId": event.get("toolCallId") or tool_call.get("id") or uuid.uuid4().hex,
                    "toolName": event.get("toolName") or tool_call.get("name") or "tool",
                    "toolParams": event.get("args") or tool_call.get("arguments") or {},
                },
            )
        if event_type == "tool_execution_end":
            return IMessageContent(
                type="call-tool-result",
                payload={
                    "callToolId": event.get("toolCallId") or uuid.uuid4().hex,
                    "toolName": event.get("toolName") or "tool",
                    "result": event.get("result"),
                    "shortDesc": "Failed" if event.get("isError") else "Completed",
                },
            )
        if event_type in {"agent_start", "agent_end"}:
            return IMessageContent(
                type="progress",
                payload={
                    "event": event_type,
                    "content": "Agent started" if event_type == "agent_start" else "Agent completed",
                },
            )
        return None

    async def stream_chat(self, request: StreamChatInput, datasource: str) -> AsyncGenerator[SSEEvent, None]:
        variant = request.runtime_variant
        if variant not in ("single", "multi"):
            raise ValueError(f"Pi runtime does not support variant {variant}")
        session_id = request.session_id or f"pi_{variant}_{uuid.uuid4().hex}"
        started = datetime.now()
        yield SSEEvent(id=1, event="session", data=SSESessionData(session_id=session_id, llm_session_id=None))
        result = None
        event_id = 2
        try:
            async for item in self.stream_run(variant, request, datasource):
                if isinstance(item, PiRunResult):
                    result = item
                    continue
                content = self._event_content(item)
                if content is None:
                    continue
                yield SSEEvent(
                    id=event_id,
                    event="message",
                    data=SSEMessageData(
                        type=SSEDataType.CREATE_MESSAGE,
                        payload=SSEMessagePayload(
                            message_id=f"pi-event-{event_id}", role="assistant", content=[content]
                        ),
                    ),
                )
                event_id += 1
        except PiRuntimeError as exc:
            yield SSEEvent(
                id=event_id,
                event="error",
                data=SSEErrorData(error=str(exc), error_type=type(exc).__name__, session_id=session_id),
            )
            return

        if result is None:
            raise PiRuntimeError("Pi runtime did not return a result")
        if not result.text.strip():
            yield SSEEvent(
                id=event_id,
                event="error",
                data=SSEErrorData(
                    error="Pi runtime returned no assistant message",
                    error_type="PiRuntimeError",
                    session_id=session_id,
                ),
            )
            return
        message_id = uuid.uuid4().hex
        yield SSEEvent(
            id=event_id,
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
        event_id += 1
        yield SSEEvent(
            id=event_id,
            event="end",
            data=SSEEndData(
                session_id=session_id,
                total_events=event_id,
                action_count=result.tool_calls,
                duration=(datetime.now() - started).total_seconds(),
                requests=1,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.input_tokens + result.output_tokens + result.cached_tokens,
                cached_tokens=result.cached_tokens,
                model=result.model,
                thinking_level=result.thinking_level,
            ),
        )
