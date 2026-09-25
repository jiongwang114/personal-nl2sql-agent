from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from dataengineer.api import deps
from dataengineer.api.models.cli_models import StreamChatInput
from dataengineer.api.routes import config_routes
from dataengineer.api.routes.config_routes import PiSettingsRequest
from dataengineer.api.services.credential_store import CredentialStore
from dataengineer.api.services.pi_runtime_service import PiRunResult, PiRuntimeError, PiRuntimeService
from dataengineer.configuration.project_config import ProjectOverride, save_project_override


def test_pi_key_is_passed_by_environment_reference_and_never_written_to_models_json(tmp_path, monkeypatch):
    assert "frontend-next-03-04-sandbox" in str(tmp_path)
    secret_file = tmp_path / "pi-test-vault.json"
    monkeypatch.setenv("DATAENGINEER_CREDENTIAL_STORE", "file-test")
    monkeypatch.setenv("DATAENGINEER_TEST_SECRET_FILE", str(secret_file))
    secret = "non-production-secret-marker"
    CredentialStore().set("scope-a", "custom", secret)

    project = tmp_path / "project"
    project.mkdir()
    save_project_override(
        ProjectOverride(pi_provider="custom", pi_model="test-model", pi_base_url="https://provider.example/v1"),
        cwd=str(project),
    )
    agent_config = SimpleNamespace(
        provider_catalog={
            "providers": {
                "custom": {
                    "type": "openai",
                    "base_url": "https://provider.example/v1",
                    "api_key_env": "CUSTOM_API_KEY",
                }
            }
        }
    )
    runtime = PiRuntimeService(project_root=project, agent_config=agent_config, credential_scope="scope-a")

    agent_dir, env, returned_secret = runtime._prepare_pi_agent(tmp_path / "runtime", "custom/test-model", "custom")

    models_json = (agent_dir / "models.json").read_text(encoding="utf-8")
    assert secret not in models_json
    assert "${DATAENGINEER_PI_API_KEY}" in models_json
    assert env["DATAENGINEER_PI_API_KEY"] == secret
    assert returned_secret == secret
    CredentialStore().delete("scope-a", "custom")


def test_request_thinking_level_is_validated_against_model_map(tmp_path):
    cli = tmp_path / ".pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")
    runtime = PiRuntimeService(project_root=tmp_path)

    valid = StreamChatInput(message="query", model="deepseek/deepseek-flash", thinking_level="low")
    command = runtime.build_command("single", valid, "demo")
    assert command[command.index("--thinking") + 1] == "low"

    invalid = StreamChatInput(message="query", model="deepseek/deepseek-flash", thinking_level="medium")
    try:
        runtime.build_command("single", invalid, "demo")
    except PiRuntimeError as exc:
        assert "not supported" in str(exc)
    else:
        raise AssertionError("unsupported reasoning level should be rejected")


def test_saved_pi_project_defaults_apply_to_requests_without_overrides(tmp_path):
    cli = tmp_path / ".pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")
    save_project_override(
        ProjectOverride(
            pi_provider="deepseek",
            pi_model="deepseek-flash",
            pi_thinking="low",
        ),
        cwd=str(tmp_path),
    )
    runtime = PiRuntimeService(project_root=tmp_path)
    request = StreamChatInput(message="query")

    command = runtime.build_command("single", request, "readonly_demo")

    assert command[command.index("--model") + 1] == "deepseek/deepseek-flash"
    assert command[command.index("--thinking") + 1] == "low"


def test_pi_builtin_model_thinking_map_excludes_null_levels():
    workspace = Path(__file__).resolve().parents[4]
    runtime = PiRuntimeService(project_root=workspace)

    assert runtime.thinking_levels("deepseek", "deepseek-v4-flash") == ["low", "high", "max"]


def test_runtime_uses_explicit_sql_bridge_python_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_SQL_PYTHON", "sandbox-python")
    runtime = PiRuntimeService(project_root=tmp_path)
    request = StreamChatInput(message="query", model="custom/test-model")

    env, _, _ = runtime._runtime_env("single", tmp_path / "agent.yml", tmp_path, request)

    assert env["PI_SQL_PYTHON"] == "sandbox-python"


def test_provider_error_redacts_key_and_preserves_simulated_403():
    from dataengineer.api.routes.config_routes import _redact_probe_error

    status, message = _redact_probe_error(
        RuntimeError("HTTP 403 insufficient_quota api_key=simulated-secret"), "simulated-secret"
    )

    assert status == 403
    assert "simulated-secret" not in message
    assert "HTTP 403" in message


def _settings_service(project: Path):
    catalog = {
        "providers": {
            "custom": {
                "type": "openai",
                "base_url": "https://provider.example/v1",
                "api_key_env": "CUSTOM_API_KEY",
                "models": ["test-model"],
            },
            "deepseek": {
                "type": "deepseek",
                "base_url": "https://api.deepseek.com",
                "api_key_env": "DEEPSEEK_API_KEY",
                "models": ["deepseek-flash"],
            },
        }
    }
    agent = SimpleNamespace(
        project_root=str(project),
        provider_catalog=catalog,
        target="custom/test-model",
        provider_available=lambda _provider: False,
    )
    scope = CredentialStore.scope_id("scope-test", project)
    runtime = PiRuntimeService(project_root=project, agent_config=agent, credential_scope=scope)
    return SimpleNamespace(agent_config=agent, pi_runtime=runtime)


@pytest.mark.asyncio
async def test_pi_settings_save_preserves_existing_project_fields_and_never_writes_secret(tmp_path, monkeypatch):
    secret_file = tmp_path / "vault.json"
    monkeypatch.setenv("DATAENGINEER_CREDENTIAL_STORE", "file-test")
    monkeypatch.setenv("DATAENGINEER_TEST_SECRET_FILE", str(secret_file))
    monkeypatch.setattr(deps, "_service_cache", None)
    project = tmp_path / "project"
    config_file = project / ".dataengineer" / "config.yml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("target: custom/old-model\ndefault_datasource: sales\nlanguage: zh\n", encoding="utf-8")
    svc = _settings_service(project)
    audit_messages = []
    monkeypatch.setattr(config_routes.logger, "info", lambda *args, **kwargs: audit_messages.append(args))

    result = await config_routes.update_pi_settings_endpoint(
        PiSettingsRequest(
            provider="custom",
            model="test-model",
            base_url="https://provider.example/v1",
            thinking_level="minimal",
            api_key="new-test-secret",
        ),
        svc,
        SimpleNamespace(project_id="scope-test"),
    )

    saved = config_file.read_text(encoding="utf-8")
    assert result.success is True
    assert "target: custom/old-model" in saved
    assert "default_datasource: sales" in saved
    assert "language: zh" in saved
    assert "new-test-secret" not in saved
    assert result.data["settings"]["key_configured"] is True
    assert audit_messages == [("Pi provider API key %s (provider=%s)", "saved", "custom")]
    assert all("new-test-secret" not in repr(message) for message in audit_messages)
    credential_scope = CredentialStore.scope_id("scope-test", project)
    assert CredentialStore().get(credential_scope, "custom") == "new-test-secret"
    CredentialStore().delete(credential_scope, "custom")


@pytest.mark.asyncio
async def test_pi_model_probe_returns_simulated_403_without_key(monkeypatch, tmp_path):
    monkeypatch.setattr(
        config_routes,
        "_probe_llm_sync",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("HTTP 403 insufficient_quota key=probe-secret")),
    )
    monkeypatch.setenv("DATAENGINEER_CREDENTIAL_STORE", "file-test")
    monkeypatch.setenv("DATAENGINEER_TEST_SECRET_FILE", str(tmp_path / "vault.json"))
    svc = _settings_service(tmp_path)

    result = await config_routes.test_pi_settings_endpoint(
        PiSettingsRequest(
            provider="deepseek", model="deepseek-flash", thinking_level="low", api_key="probe-secret"
        ),
        svc,
        SimpleNamespace(project_id="scope-test"),
    )

    assert result.data["ok"] is False
    assert result.data["status_code"] == 403
    assert "probe-secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_pi_model_probe_redacts_simulated_401(monkeypatch, tmp_path):
    monkeypatch.setattr(
        config_routes,
        "_probe_llm_sync",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("HTTP 401 api_key=invalid-test-key")),
    )
    monkeypatch.setenv("DATAENGINEER_CREDENTIAL_STORE", "file-test")
    monkeypatch.setenv("DATAENGINEER_TEST_SECRET_FILE", str(tmp_path / "vault.json"))
    svc = _settings_service(tmp_path)

    result = await config_routes.test_pi_settings_endpoint(
        PiSettingsRequest(
            provider="deepseek", model="deepseek-flash", thinking_level="low", api_key="invalid-test-key"
        ),
        svc,
        SimpleNamespace(project_id="scope-test"),
    )

    assert result.data["ok"] is False
    assert result.data["status_code"] == 401
    assert "invalid-test-key" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_pi_settings_reject_unsupported_thinking_level_and_embedded_url_credentials(tmp_path):
    svc = _settings_service(tmp_path)
    with pytest.raises(HTTPException) as unsupported:
        config_routes._validate_pi_settings(
            PiSettingsRequest(provider="deepseek", model="deepseek-flash", thinking_level="medium"), svc
        )
    assert unsupported.value.status_code == 422

    with pytest.raises(HTTPException) as unsafe_url:
        config_routes._validate_pi_settings(
            PiSettingsRequest(
                provider="custom",
                model="test-model",
                base_url="https://user:password@provider.example/v1",
            ),
            svc,
        )
    assert unsafe_url.value.status_code == 422


@pytest.mark.asyncio
async def test_sse_end_contains_effective_model_and_thinking_level(tmp_path, monkeypatch):
    runtime = PiRuntimeService(project_root=tmp_path)

    async def fake_stream_run(variant, request, datasource):
        yield PiRunResult(text="answer", model="custom/test-model", thinking_level="high")

    monkeypatch.setattr(runtime, "stream_run", fake_stream_run)
    events = [
        event
        async for event in runtime.stream_chat(
            StreamChatInput(message="query", runtime_variant="single"), "demo"
        )
    ]
    ending = next(event for event in events if event.event == "end")
    assert ending.data.model == "custom/test-model"
    assert ending.data.thinking_level == "high"
