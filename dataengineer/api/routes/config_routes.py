"""
API routes for configuration status and metadata.

This module provides endpoints for initialization status checks
and supported provider/database type listings.
"""

import asyncio
import os
import re
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dataengineer.api import deps
from dataengineer.api.deps import AppContextDep, ServiceDep
from dataengineer.api.models.base_models import Result
from dataengineer.api.services.credential_store import CredentialStore, CredentialStoreError
from dataengineer.configuration.agent_config import _SAFE_NAME_RE, DbConfig, load_model_config
from dataengineer.configuration.agent_config_loader import configuration_manager
from dataengineer.configuration.project_config import ProjectOverride, load_project_override, save_project_override
from dataengineer.models.base import LLMBaseModel
from dataengineer.utils.exceptions import DataEngineerException, ErrorCode
from dataengineer.utils.loggings import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["configuration"])

_SENSITIVE_CONFIG_KEYS = {"api_key", "password", "token", "access_token", "client_secret", "secret", "headers"}


def _public_config(value):
    """Convert configuration values to JSON-safe data and redact credentials."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    elif is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in _SENSITIVE_CONFIG_KEYS and item else _public_config(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_public_config(item) for item in value]
    if isinstance(value, str) and "://" in value:
        return re.sub(r"(://[^:/@]+:)[^@/]+(@)", r"\1***\2", value)
    return value


class UpdateDatasourcesRequest(BaseModel):
    """Full desired state for `services.datasources`.

    Any existing datasource key absent from `datasources` will be deleted.
    """

    datasources: Dict[str, Dict[str, Any]]


class UpdateModelsRequest(BaseModel):
    """Optional full-replace for `models` and/or update to `target`.

    At least one of `models` or `target` must be provided.
    """

    models: Optional[Dict[str, Dict[str, Any]]] = None
    target: Optional[str] = None


class ProbeModelRequest(BaseModel):
    """Single LLM model config dict — flat shape matching IModelInfo."""

    model_config = {"extra": "allow"}

    type: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ProbeDatasourceRequest(BaseModel):
    """Single datasource config dict — flat shape matching IDatasourceConfig."""

    model_config = {"extra": "allow"}

    type: str


class PiSettingsRequest(BaseModel):
    provider: str
    model: str
    base_url: Optional[str] = None
    thinking_level: str = "minimal"
    api_key: Optional[str] = None
    clear_api_key: bool = False


def _pi_provider_catalog(svc, scope: str) -> list[dict[str, Any]]:
    catalog = svc.agent_config.provider_catalog
    providers = catalog.get("providers", {}) if isinstance(catalog, dict) else {}
    store = CredentialStore()
    entries = []
    for provider, raw in providers.items():
        if not isinstance(provider, str) or not isinstance(raw, dict):
            continue
        models = raw.get("models")
        if not isinstance(models, list):
            continue
        try:
            key_stored = bool(store.get(scope, provider))
        except CredentialStoreError:
            key_stored = False
        entries.append(
            {
                "id": provider,
                "type": str(raw.get("type", "openai")),
                "base_url": raw.get("base_url"),
                "models": [_pi_model_summary(svc, provider, item, catalog) for item in models if isinstance(item, str) and item],
                "key_stored": key_stored,
                "key_configured": key_stored or svc.agent_config.provider_available(provider),
            }
        )
    return entries


def _pi_model_summary(svc, provider: str, model: str, catalog: dict[str, Any]) -> dict[str, Any]:
    runtime_model = svc.pi_runtime.model_definition(provider, model) or {}
    specs = catalog.get("model_specs", {}) if isinstance(catalog, dict) else {}
    spec = specs.get(model, {}) if isinstance(specs, dict) else {}
    if not isinstance(spec, dict):
        spec = {}
    if not spec and isinstance(specs, dict):
        prefix = next((key for key in sorted(specs, key=len, reverse=True) if model.startswith(key)), None)
        spec = specs.get(prefix, {}) if prefix else {}
        if not isinstance(spec, dict):
            spec = {}
    context_length = runtime_model.get("contextWindow") or spec.get("context_length")
    max_tokens = runtime_model.get("maxTokens") or spec.get("max_tokens")
    return {
        "id": model,
        "thinking_levels": svc.pi_runtime.thinking_levels(provider, model),
        "context_length": context_length if isinstance(context_length, int) else None,
        "max_tokens": max_tokens if isinstance(max_tokens, int) else None,
        "reasoning": runtime_model.get("reasoning") if isinstance(runtime_model.get("reasoning"), bool) else None,
    }


def _pi_settings(svc, scope: str) -> dict[str, Any]:
    project_root = Path(svc.agent_config.project_root)
    override = load_project_override(cwd=str(project_root)) or ProjectOverride()
    provider = override.pi_provider or ""
    model = override.pi_model or ""
    if not provider or not model:
        target = str(svc.agent_config.target or "")
        if "/" in target:
            provider, model = target.split("/", 1)
        else:
            provider = provider or "custom"
            model = model or target
    store = CredentialStore()
    try:
        key_stored = bool(provider and store.get(scope, provider))
    except CredentialStoreError:
        key_stored = False
    providers = _pi_provider_catalog(svc, scope)
    provider_meta = next((item for item in providers if item["id"] == provider), {})
    default_url = provider_meta.get("base_url") or ""
    if provider and model:
        model_info = svc.pi_runtime.model_definition(provider, model)
        if model_info and model_info.get("baseUrl"):
            default_url = model_info["baseUrl"]
    levels = svc.pi_runtime.thinking_levels(provider, model) if provider and model else ["minimal"]
    return {
        "provider": provider,
        "model": model,
        "base_url": override.pi_base_url or default_url,
        "thinking_level": override.pi_thinking
        or ("minimal" if "minimal" in levels else (levels[0] if levels else "off")),
        "key_stored": key_stored,
        "key_configured": key_stored or bool(provider and svc.agent_config.provider_available(provider)),
        "credential_backend": "file-test"
        if os.getenv("DATAENGINEER_CREDENTIAL_STORE") == "file-test"
        else "os-keyring",
        "providers": providers,
    }


def _validate_pi_settings(body: PiSettingsRequest, svc) -> dict[str, Any]:
    catalog = svc.agent_config.provider_catalog
    providers = catalog.get("providers", {}) if isinstance(catalog, dict) else {}
    provider = providers.get(body.provider) if isinstance(providers, dict) else None
    if not isinstance(provider, dict) or body.model not in (provider.get("models") or []):
        raise HTTPException(status_code=422, detail="Provider/model is not in the configured allowlist")
    if body.thinking_level not in svc.pi_runtime.thinking_levels(body.provider, body.model):
        raise HTTPException(status_code=422, detail="Unsupported Pi thinking level")
    base_url = (body.base_url or provider.get("base_url") or "").strip()
    if len(base_url) > 2048:
        raise HTTPException(status_code=422, detail="Base URL is too long")
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(status_code=422, detail="Base URL must be an HTTP(S) URL without embedded credentials")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Base URL contains an invalid port") from exc
        if parsed.query or parsed.fragment:
            raise HTTPException(status_code=422, detail="Base URL cannot contain a query or fragment")
    return {"provider": body.provider, "model": body.model, "base_url": base_url, "provider_meta": provider}


def _redact_probe_error(error: object, secret: str | None = None) -> tuple[int | None, str]:
    message = str(error) if error is not None else "Model connectivity test failed"
    status = None
    match = re.search(r"\b(?:HTTP|status(?: code)?)\s*[:( ]?([1-5]\d\d)\b", message, re.IGNORECASE)
    if match:
        status = int(match.group(1))
    if secret:
        message = message.replace(secret, "[redacted]")
    message = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1[redacted]", message)
    if status == 403 or "quota" in message.lower() or "insufficient_quota" in message.lower():
        return status or 403, "Provider quota or permission denied (HTTP 403)"
    return status, message[:500]


def _probe_llm_sync(payload: Dict[str, Any]) -> None:
    """Build a one-shot LLM client from a raw dict and send a tiny probe."""
    model_cfg = load_model_config(payload)
    model_class_name = LLMBaseModel.MODEL_TYPE_MAP.get(model_cfg.type)
    if model_class_name is None:
        raise DataEngineerException(
            ErrorCode.COMMON_FIELD_INVALID,
            message=f"Unsupported model type: {model_cfg.type}",
        )
    module = __import__(f"dataengineer.models.{model_cfg.type}_model", fromlist=[model_class_name])
    model_class = getattr(module, model_class_name)
    client = model_class(model_config=model_cfg)
    client.generate("Hello")


def _probe_datasource_sync(payload: Dict[str, Any]) -> None:
    """Build a one-shot connector from a raw dict and run a SELECT 1 probe."""
    from dataengineer.tools.db_tools.db_manager import DBManager

    kwargs = dict(payload)
    kwargs.setdefault("name", "_probe_")
    db_config = DbConfig.filter_kwargs(DbConfig, kwargs)

    manager = DBManager({"_probe_": {"_probe_": db_config}})
    try:
        conn = manager.get_conn("_probe_")
        conn.test_connection()
    finally:
        manager.close()


def _validate_keys(entries: Dict[str, Any], kind: str) -> None:
    """Ensure every key matches the naming policy used by AgentConfig."""
    for name in entries.keys():
        if not _SAFE_NAME_RE.match(name):
            raise DataEngineerException(
                ErrorCode.COMMON_FIELD_INVALID,
                message=(
                    f"Invalid {kind} name '{name}'. Only alphanumeric characters, underscores, and hyphens are allowed."
                ),
            )


async def _evict_current_project(project_id: str) -> None:
    """Drop the cached DataEngineerService so the next request reloads from YAML."""
    cache = deps._service_cache
    if cache is None:
        return
    try:
        await cache.evict(project_id)
    except Exception:
        logger.exception(f"Failed to evict service cache for project {project_id}")


@router.get(
    "/config/agent",
    response_model=Result[dict],
    summary="Get Agent Configuration",
    description="Get the current project's agent configuration (models, datasource, agentic_nodes)",
)
async def get_agent_config_endpoint(
    svc: ServiceDep,
) -> Result[dict]:
    """Return the project's loaded AgentConfig summary."""
    config = svc.agent_config
    flat_datasources: dict = {}

    for db_name, inner in config.datasource_configs.items():
        if not inner:
            continue
        db_config = inner.get(db_name)
        if db_config is None:
            db_config = next(iter(inner.values()))
        public_db = _public_config(db_config)
        if not isinstance(public_db, dict):
            public_db = {"type": str(getattr(db_config, "type", ""))}
        db_type = public_db.get("type")
        db_type = db_type.value if hasattr(db_type, "value") else str(db_type or "")
        uri = str(getattr(db_config, "uri", None) or public_db.get("uri") or "")
        if db_type in {"sqlite", "duckdb"} and uri.startswith(("sqlite:///", "duckdb:///")):
            extra = getattr(db_config, "extra", None) or public_db.get("extra")
            extra = extra if isinstance(extra, dict) else {}
            public_db["read_only"] = bool(public_db.get("read_only") or extra.get("read_only"))
            project_root = getattr(config, "project_root", None)
            managed_import = False
            try:
                if isinstance(project_root, (str, Path)) and uri.startswith(("sqlite:///", "duckdb:///")):
                    source_path = Path(uri.split("///", 1)[1])
                    if not source_path.is_absolute():
                        source_path = Path(project_root) / source_path
                    import_root = (Path(project_root) / ".dataengineer" / "imported-databases").resolve()
                    managed_import = source_path.resolve().is_relative_to(import_root)
            except OSError:
                managed_import = False
            public_db["managed_import"] = managed_import
        flat_datasources[db_name] = public_db

    return Result(
        success=True,
        data={
            "target": config.target,
            "models": _public_config(config.models),
            "current_datasource": config.current_datasource,
            "datasources": flat_datasources,
            "home": config.home,
        },
    )


@router.get("/config/pi", response_model=Result[dict], summary="Get Pi Runtime Settings")
async def get_pi_settings_endpoint(svc: ServiceDep, ctx: AppContextDep) -> Result[dict]:
    scope = CredentialStore.scope_id(ctx.project_id, svc.agent_config.project_root)
    return Result(success=True, data=_pi_settings(svc, scope))


@router.put("/config/pi", response_model=Result[dict], summary="Save Pi Runtime Settings")
async def update_pi_settings_endpoint(
    body: PiSettingsRequest,
    svc: ServiceDep,
    ctx: AppContextDep,
) -> Result[dict]:
    safe = _validate_pi_settings(body, svc)
    scope = CredentialStore.scope_id(ctx.project_id, svc.agent_config.project_root)
    store = CredentialStore()
    try:
        if body.api_key and body.api_key.strip():
            previous_key = store.get(scope, body.provider)
            store.set(scope, body.provider, body.api_key.strip())
            action = "replaced" if previous_key else "saved"
            logger.info("Pi provider API key %s (provider=%s)", action, body.provider)
        elif body.clear_api_key:
            had_key = bool(store.get(scope, body.provider))
            store.delete(scope, body.provider)
            if had_key:
                logger.info("Pi provider API key cleared (provider=%s)", body.provider)
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    root = Path(svc.agent_config.project_root)
    override = load_project_override(cwd=str(root)) or ProjectOverride()
    override.pi_provider = safe["provider"]
    override.pi_model = safe["model"]
    default_url = safe["provider_meta"].get("base_url") or ""
    override.pi_base_url = safe["base_url"] if safe["base_url"] != default_url else None
    override.pi_thinking = body.thinking_level
    save_project_override(override, cwd=str(root))
    await _evict_current_project(scope)
    return Result(success=True, data={"updated": True, "settings": _pi_settings(svc, scope)})


@router.post("/config/pi/test", response_model=Result[dict], summary="Test Pi Model Connectivity")
async def test_pi_settings_endpoint(
    body: PiSettingsRequest,
    svc: ServiceDep,
    ctx: AppContextDep,
) -> Result[dict]:
    safe = _validate_pi_settings(body, svc)
    provider = svc.agent_config.provider_catalog["providers"][body.provider]
    try:
        scope = CredentialStore.scope_id(ctx.project_id, svc.agent_config.project_root)
        saved_key = CredentialStore().get(scope, body.provider)
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    key_env = str(provider.get("api_key_env") or "")
    test_key = body.api_key or saved_key or (os.getenv(key_env) if key_env else None)
    payload = {
        "type": provider.get("type", "openai"),
        "model": body.model,
        "api_key": test_key,
        "base_url": safe["base_url"],
    }
    started = time.monotonic()
    try:
        await asyncio.to_thread(_probe_llm_sync, payload)
        return Result(
            success=True,
            data={"ok": True, "provider": body.provider, "model": body.model, "duration_ms": round((time.monotonic() - started) * 1000)},
        )
    except Exception as exc:
        status, message = _redact_probe_error(exc, test_key)
        return Result(
            success=True,
            data={
                "ok": False,
                "provider": body.provider,
                "model": body.model,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "status_code": status,
                "message": message,
            },
        )


@router.put(
    "/config/datasources",
    response_model=Result[dict],
    summary="Update Datasources",
    description="Replace the datasources (services.datasources) block in agent.yml.",
)
async def update_datasources_endpoint(
    body: UpdateDatasourcesRequest,
    svc: ServiceDep,  # noqa: ARG001  # populates request.state.app_context; must resolve before AppContextDep
    ctx: AppContextDep,
) -> Result[dict]:
    """Full-replace `services.datasources` with the provided datasources."""
    _validate_keys(body.datasources, kind="datasource")

    cm = configuration_manager()
    services = cm.data.setdefault("services", {})
    services["datasources"] = dict(body.datasources)
    cm.save()

    await _evict_current_project(ctx.project_id or "default")

    return Result(success=True, data={"updated": True})


@router.put(
    "/config/models",
    response_model=Result[dict],
    summary="Update Models and Target",
    description="Replace the models block and/or update the default target in agent.yml.",
)
async def update_models_endpoint(
    body: UpdateModelsRequest,
    svc: ServiceDep,  # noqa: ARG001
    ctx: AppContextDep,
) -> Result[dict]:
    """Optional full-replace `models`, optional update `target`. One must be set."""
    if body.models is None and body.target is None:
        raise DataEngineerException(
            ErrorCode.COMMON_FIELD_INVALID,
            message="At least one of 'models' or 'target' must be provided.",
        )

    if body.models is not None:
        _validate_keys(body.models, kind="model")

    cm = configuration_manager()

    if body.target is not None:
        effective_models = body.models if body.models is not None else cm.data.get("models") or {}
        if body.target not in effective_models:
            raise DataEngineerException(
                ErrorCode.COMMON_FIELD_INVALID,
                message=f"target '{body.target}' does not exist in models.",
            )

    if body.models is not None:
        cm.data["models"] = dict(body.models)
    if body.target is not None:
        cm.data["target"] = body.target
    cm.save()

    await _evict_current_project(ctx.project_id or "default")

    return Result(success=True, data={"updated": True})


@router.post(
    "/config/models/test",
    response_model=Result[dict],
    summary="Test Model Connectivity",
    description="Send a tiny probe to verify an LLM model config is reachable.",
)
async def probe_model_connectivity_endpoint(
    body: ProbeModelRequest,
    svc: ServiceDep,  # noqa: ARG001
) -> Result[dict]:
    """Return `{ok: True}` if the probe succeeds, else `{ok: False, message: ...}`."""
    payload = body.model_dump()
    try:
        await asyncio.to_thread(_probe_llm_sync, payload)
        return Result(success=True, data={"ok": True})
    except Exception as e:
        _, message = _redact_probe_error(e, body.api_key)
        logger.info("Model connectivity probe failed")
        return Result(success=True, data={"ok": False, "message": message})


@router.post(
    "/config/datasources/test",
    response_model=Result[dict],
    summary="Test Datasource Connectivity",
    description="Run SELECT 1 against a datasource config to verify reachability and credentials.",
)
async def probe_datasource_connectivity_endpoint(
    body: ProbeDatasourceRequest,
    svc: ServiceDep,  # noqa: ARG001
) -> Result[dict]:
    """Return `{ok: True}` if the probe succeeds, else `{ok: False, message: ...}`."""
    payload = body.model_dump()
    try:
        await asyncio.to_thread(_probe_datasource_sync, payload)
        return Result(success=True, data={"ok": True})
    except Exception as e:
        logger.info(f"Datasource connectivity probe failed: {e}")
        return Result(success=True, data={"ok": False, "message": str(e)})
