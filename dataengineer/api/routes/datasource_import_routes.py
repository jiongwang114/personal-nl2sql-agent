"""Import local SQLite and DuckDB files as managed, read-only datasources."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path
from threading import RLock
from typing import Annotated

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from dataengineer.api.deps import AppContextDep, ServiceDep
from dataengineer.api.models.base_models import Result
from dataengineer.api.routes.config_routes import _evict_current_project
from dataengineer.configuration.agent_config import _SAFE_NAME_RE
from dataengineer.configuration.agent_config_loader import configuration_manager
from dataengineer.configuration.project_config import ProjectOverride, load_project_override, save_project_override
from dataengineer.utils.loggings import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/config/datasources", tags=["configuration"])
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
ALLOWED_SUFFIXES = {".sqlite": "sqlite", ".db": "sqlite", ".duckdb": "duckdb"}
_import_lock = RLock()


def _save_agent_config_atomic(config) -> None:
    target = config.config_path
    temp_path = target.with_name(f".{target.name}.import.tmp")
    temp_path.write_text(
        yaml.safe_dump({"agent": config.data}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.replace(temp_path, target)


def _probe_file(path: Path, db_type: str) -> int:
    if db_type == "sqlite":
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("SQLite integrity check failed")
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
            )
        finally:
            connection.close()

    import duckdb

    connection = duckdb.connect(str(path), read_only=True)
    try:
        connection.execute("SELECT 1").fetchone()
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')"
            ).fetchone()[0]
        )
    finally:
        connection.close()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class DefaultDatasourceRequest(BaseModel):
    datasource_id: str


@router.post("/import", response_model=Result[dict], summary="Import a Local Database")
async def import_datasource(
    svc: ServiceDep,
    ctx: AppContextDep,
    request: Request,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()],
    set_default: Annotated[bool, Form()] = False,
) -> Result[dict]:
    safe_name = name.strip()
    suffix = Path(file.filename or "").suffix.lower()
    db_type = ALLOWED_SUFFIXES.get(suffix)
    if len(safe_name) > 64 or not _SAFE_NAME_RE.fullmatch(safe_name):
        raise HTTPException(status_code=422, detail="Datasource name may contain letters, numbers, underscores, and hyphens")
    if db_type is None:
        raise HTTPException(status_code=415, detail="Supported database files are .sqlite, .db, and .duckdb")

    root = Path(svc.agent_config.project_root).resolve()
    import_dir = (root / ".dataengineer" / "imported-databases").resolve()
    if not import_dir.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Import directory is outside the project workspace")
    import_dir.mkdir(parents=True, exist_ok=True)
    destination = import_dir / f"{safe_name}{suffix}"
    temp_path: Path | None = None
    destination_created = False
    digest = hashlib.sha256()
    size = 0
    try:
        with tempfile.NamedTemporaryFile(prefix=".upload-", suffix=suffix, dir=import_dir, delete=False) as target:
            temp_path = Path(target.name)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Database file exceeds the 512 MiB limit")
                digest.update(chunk)
                target.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="Database file is empty")

        table_count = await asyncio.to_thread(_probe_file, temp_path, db_type)
        if await request.is_disconnected():
            raise HTTPException(status_code=499, detail="Database import was cancelled before registration")
        configured_path = os.getenv("DATAENGINEER_CONFIG") or str(root / "conf" / "agent.yml")
        config = configuration_manager(config_path=configured_path, reload=True)
        services = config.data.setdefault("services", {})
        datasources = services.setdefault("datasources", {})
        if safe_name in datasources:
            raise HTTPException(status_code=409, detail=f"Datasource '{safe_name}' already exists")

        existing_hash = None
        if destination.is_symlink() or (destination.exists() and not destination.resolve().is_relative_to(import_dir)):
            raise HTTPException(status_code=409, detail="A database file with this datasource name already exists")
        if destination.is_file():
            existing_hash = await asyncio.to_thread(_hash_file, destination)

        with _import_lock:
            if destination.exists():
                if existing_hash != digest.hexdigest():
                    raise HTTPException(status_code=409, detail="A different database file already uses this name")
                temp_path.unlink(missing_ok=True)
                temp_path = None
            else:
                os.replace(temp_path, destination)
                temp_path = None
                destination_created = True
            uri = f"{db_type}:///{destination.as_posix()}"
            datasources[safe_name] = {
                "type": db_type,
                "uri": uri,
                "read_only": True,
                "database_name": safe_name,
                "name": safe_name,
            }
            previous_override = load_project_override(cwd=str(root)) or ProjectOverride()
            override_written = False
            try:
                if set_default:
                    override = load_project_override(cwd=str(root)) or ProjectOverride()
                    override.default_datasource = safe_name
                    save_project_override(override, cwd=str(root))
                    override_written = True
                _save_agent_config_atomic(config)
            except Exception:
                datasources.pop(safe_name, None)
                if override_written:
                    try:
                        save_project_override(previous_override, cwd=str(root))
                    except Exception:
                        logger.error("Failed to restore project datasource override after import rollback")
                if destination_created:
                    destination.unlink(missing_ok=True)
                raise

        scope = ctx.project_id or "default"
        await _evict_current_project(scope)
        return Result(
            success=True,
            data={
                "datasource_id": safe_name,
                "type": db_type,
                "read_only": True,
                "size_bytes": size,
                "sha256": digest.hexdigest(),
                "table_count": table_count,
                "cache_invalidated": True,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.info("Local database import failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=422, detail="Database file could not be validated or registered") from None
    finally:
        await file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.put("/default", response_model=Result[dict], summary="Set the Default Datasource")
async def set_default_datasource(
    body: DefaultDatasourceRequest,
    svc: ServiceDep,
    ctx: AppContextDep,
) -> Result[dict]:
    configured_path = os.getenv("DATAENGINEER_CONFIG") or str(Path(svc.agent_config.project_root) / "conf" / "agent.yml")
    config = configuration_manager(config_path=configured_path, reload=True)
    datasources = config.data.get("services", {}).get("datasources", {})
    if body.datasource_id not in datasources:
        raise HTTPException(status_code=404, detail="Datasource is not configured")
    root = Path(svc.agent_config.project_root)
    override = load_project_override(cwd=str(root)) or ProjectOverride()
    override.default_datasource = body.datasource_id
    save_project_override(override, cwd=str(root))
    await _evict_current_project(ctx.project_id or "default")
    return Result(success=True, data={"default_datasource": body.datasource_id})


@router.delete("/{datasource_id}", response_model=Result[dict], summary="Unbind an Imported Datasource")
async def unbind_imported_datasource(
    datasource_id: str,
    svc: ServiceDep,
    ctx: AppContextDep,
) -> Result[dict]:
    if len(datasource_id) > 64 or not _SAFE_NAME_RE.fullmatch(datasource_id):
        raise HTTPException(status_code=422, detail="Invalid datasource identifier")
    root = Path(svc.agent_config.project_root).resolve()
    configured_path = os.getenv("DATAENGINEER_CONFIG") or str(root / "conf" / "agent.yml")
    config = configuration_manager(config_path=configured_path, reload=True)
    datasources = config.data.get("services", {}).get("datasources", {})
    raw = datasources.get(datasource_id)
    if not isinstance(raw, dict):
        raise HTTPException(status_code=404, detail="Datasource is not configured")
    import_root = (root / ".dataengineer" / "imported-databases").resolve()
    uri = str(raw.get("uri", ""))
    if raw.get("type") not in {"sqlite", "duckdb"} or not raw.get("read_only") or ":///" not in uri:
        raise HTTPException(status_code=403, detail="Only managed, read-only imported datasources can be unbound")
    source_path = Path(uri.split("///", 1)[1])
    if not source_path.is_absolute():
        source_path = root / source_path
    if source_path.is_symlink() or not source_path.resolve().is_relative_to(import_root):
        raise HTTPException(status_code=403, detail="Datasource is outside the managed import directory")

    override = load_project_override(cwd=str(root)) or ProjectOverride()
    if datasource_id == svc.agent_config.current_datasource or datasource_id == override.default_datasource:
        raise HTTPException(status_code=409, detail="Set another datasource as default before unbinding this one")
    datasources.pop(datasource_id)
    _save_agent_config_atomic(config)
    await _evict_current_project(ctx.project_id or "default")
    return Result(success=True, data={"datasource_id": datasource_id, "unbound": True, "file_retained": True})
