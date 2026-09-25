import io
import sqlite3
from types import SimpleNamespace

import duckdb
import pytest
import yaml
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from dataengineer.api import deps
from dataengineer.api.models.cli_models import ExecuteSQLInput
from dataengineer.api.routes.datasource_import_routes import (
    DefaultDatasourceRequest,
    import_datasource,
    set_default_datasource,
    unbind_imported_datasource,
)
from dataengineer.api.services.cli_service import CLIService
from dataengineer.configuration.agent_config_loader import load_agent_config
from dataengineer.configuration.project_config import load_project_override


def _sqlite_bytes(amounts=(12.5,)) -> bytes:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, amount REAL)")
    connection.executemany("INSERT INTO transactions(amount) VALUES (?)", [(amount,) for amount in amounts])
    database = connection.serialize()
    connection.close()
    return database


def _upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


class _ConnectedRequest:
    async def is_disconnected(self):
        return False


class _DisconnectedRequest:
    async def is_disconnected(self):
        return True


@pytest.mark.asyncio
async def test_import_registers_sqlite_read_only_and_reports_no_absolute_path(tmp_path, monkeypatch):
    project = tmp_path / "project"
    config_path = project / "conf" / "agent.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"agent:\n  target: custom\n  home: {project.as_posix()}/home\n  services:\n    datasources: {{}}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATAENGINEER_CONFIG", str(config_path))
    monkeypatch.setattr(deps, "_service_cache", None)
    svc = SimpleNamespace(agent_config=SimpleNamespace(project_root=str(project)))
    ctx = SimpleNamespace(project_id="test-project")

    result = await import_datasource(
        svc, ctx, _ConnectedRequest(), _upload(_sqlite_bytes(), "local.sqlite"), "local_demo", False
    )

    assert result.success is True
    assert result.data["datasource_id"] == "local_demo"
    assert result.data["read_only"] is True
    assert result.data["table_count"] == 1
    destination = project / ".dataengineer" / "imported-databases" / "local_demo.sqlite"
    assert destination.is_file()
    assert str(destination) not in repr(result.data)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    registered = config["agent"]["services"]["datasources"]["local_demo"]
    assert registered["read_only"] is True
    assert registered["uri"].startswith("sqlite:///")

    agent_config = load_agent_config(
        reload=True,
        config=str(config_path),
        datasource="local_demo",
        project_root=str(project),
    )
    sql = CLIService(agent_config=agent_config)
    query = await sql.execute_sql(
        ExecuteSQLInput(
            datasource_id="local_demo",
            sql_query="SELECT amount FROM transactions",
            result_format="json",
        )
    )
    assert query.success is True
    assert '12.5' in query.data.sql_return
    write = await sql.execute_sql(
        ExecuteSQLInput(
            datasource_id="local_demo",
            sql_query="INSERT INTO transactions(amount) VALUES (1)",
            result_format="json",
        )
    )
    check = await sql.execute_sql(
        ExecuteSQLInput(
            datasource_id="local_demo",
            sql_query="SELECT COUNT(*) AS n FROM transactions",
            result_format="json",
        )
    )
    assert write.success is False
    assert '"n": 1' in check.data.sql_return


@pytest.mark.asyncio
async def test_import_rejects_duplicate_name_and_path_traversal_without_partial_files(tmp_path, monkeypatch):
    project = tmp_path / "project"
    config_path = project / "conf" / "agent.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("agent:\n  services:\n    datasources: {}\n", encoding="utf-8")
    monkeypatch.setenv("DATAENGINEER_CONFIG", str(config_path))
    monkeypatch.setattr(deps, "_service_cache", None)
    svc = SimpleNamespace(agent_config=SimpleNamespace(project_root=str(project)))
    ctx = SimpleNamespace(project_id="test-project")

    await import_datasource(svc, ctx, _ConnectedRequest(), _upload(_sqlite_bytes(), "local.sqlite"), "local_demo", False)
    with pytest.raises(HTTPException) as duplicate:
        await import_datasource(
            svc, ctx, _ConnectedRequest(), _upload(_sqlite_bytes(), "local.sqlite"), "local_demo", False
        )
    assert duplicate.value.status_code == 409
    with pytest.raises(HTTPException) as traversal:
        await import_datasource(
            svc, ctx, _ConnectedRequest(), _upload(_sqlite_bytes(), "local.sqlite"), "../escape", False
        )
    assert traversal.value.status_code == 422
    import_dir = project / ".dataengineer" / "imported-databases"
    assert [path.name for path in import_dir.iterdir()] == ["local_demo.sqlite"]


@pytest.mark.asyncio
async def test_import_rejects_corrupt_database_and_unsupported_extension(tmp_path, monkeypatch):
    project = tmp_path / "project"
    config_path = project / "conf" / "agent.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("agent:\n  services:\n    datasources: {}\n", encoding="utf-8")
    monkeypatch.setenv("DATAENGINEER_CONFIG", str(config_path))
    monkeypatch.setattr(deps, "_service_cache", None)
    svc = SimpleNamespace(agent_config=SimpleNamespace(project_root=str(project)))
    ctx = SimpleNamespace(project_id="test-project")

    with pytest.raises(HTTPException) as corrupt:
        await import_datasource(
            svc, ctx, _ConnectedRequest(), _upload(b"not a sqlite database", "bad.sqlite"), "bad_db", False
        )
    assert corrupt.value.status_code == 422
    with pytest.raises(HTTPException) as empty:
        await import_datasource(svc, ctx, _ConnectedRequest(), _upload(b"", "empty.sqlite"), "empty_db", False)
    assert empty.value.status_code == 422
    with pytest.raises(HTTPException) as unsupported:
        await import_datasource(svc, ctx, _ConnectedRequest(), _upload(b"payload", "bad.csv"), "bad_csv", False)
    assert unsupported.value.status_code == 415
    import_dir = project / ".dataengineer" / "imported-databases"
    assert not list(import_dir.iterdir())


@pytest.mark.asyncio
async def test_import_registers_duckdb_and_enforces_size_limit(tmp_path, monkeypatch):
    project = tmp_path / "project"
    config_path = project / "conf" / "agent.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("agent:\n  services:\n    datasources: {}\n", encoding="utf-8")
    monkeypatch.setenv("DATAENGINEER_CONFIG", str(config_path))
    monkeypatch.setattr(deps, "_service_cache", None)
    svc = SimpleNamespace(agent_config=SimpleNamespace(project_root=str(project)))
    ctx = SimpleNamespace(project_id="test-project")
    source = tmp_path / "source.duckdb"
    connection = duckdb.connect(str(source))
    connection.execute("CREATE TABLE imported_rows (id INTEGER)")
    connection.close()

    result = await import_datasource(
        svc, ctx, _ConnectedRequest(), _upload(source.read_bytes(), "source.duckdb"), "duck_demo", False
    )

    assert result.success is True
    assert result.data["type"] == "duckdb"
    assert result.data["table_count"] == 1
    destination = project / ".dataengineer" / "imported-databases" / "duck_demo.duckdb"
    readonly = duckdb.connect(str(destination), read_only=True)
    assert readonly.execute("SELECT COUNT(*) FROM imported_rows").fetchone() == (0,)
    with pytest.raises(duckdb.Error):
        readonly.execute("CREATE TABLE forbidden (id INTEGER)")
    readonly.close()

    monkeypatch.setattr("dataengineer.api.routes.datasource_import_routes.MAX_UPLOAD_BYTES", 16)
    with pytest.raises(HTTPException) as too_large:
        await import_datasource(
            svc, ctx, _ConnectedRequest(), _upload(b"x" * 17, "large.db"), "too_large", False
        )
    assert too_large.value.status_code == 413
    assert not (project / ".dataengineer" / "imported-databases" / "too_large.db").exists()


@pytest.mark.asyncio
async def test_cancelled_import_is_not_registered(tmp_path, monkeypatch):
    project = tmp_path / "project"
    config_path = project / "conf" / "agent.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("agent:\n  services:\n    datasources: {}\n", encoding="utf-8")
    monkeypatch.setenv("DATAENGINEER_CONFIG", str(config_path))
    monkeypatch.setattr(deps, "_service_cache", None)
    svc = SimpleNamespace(agent_config=SimpleNamespace(project_root=str(project)))
    ctx = SimpleNamespace(project_id="test-project")

    with pytest.raises(HTTPException) as cancelled:
        await import_datasource(
            svc, ctx, _DisconnectedRequest(), _upload(_sqlite_bytes(), "cancelled.sqlite"), "cancelled", False
        )

    assert cancelled.value.status_code == 499
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["agent"]["services"]["datasources"] == {}
    import_dir = project / ".dataengineer" / "imported-databases"
    assert not list(import_dir.iterdir())


@pytest.mark.asyncio
async def test_default_switch_unbind_and_same_file_reimport(tmp_path, monkeypatch):
    project = tmp_path / "project"
    config_path = project / "conf" / "agent.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "agent:\n  services:\n    datasources:\n      existing:\n        type: sqlite\n        uri: sqlite:///existing.sqlite\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATAENGINEER_CONFIG", str(config_path))
    monkeypatch.setattr(deps, "_service_cache", None)
    svc = SimpleNamespace(agent_config=SimpleNamespace(project_root=str(project), current_datasource="existing"))
    ctx = SimpleNamespace(project_id="test-project")
    bytes_db = _sqlite_bytes()
    await import_datasource(svc, ctx, _ConnectedRequest(), _upload(bytes_db, "local.sqlite"), "local_demo", False)

    result = await set_default_datasource(DefaultDatasourceRequest(datasource_id="local_demo"), svc, ctx)
    assert result.data["default_datasource"] == "local_demo"
    assert load_project_override(cwd=str(project)).default_datasource == "local_demo"

    await set_default_datasource(DefaultDatasourceRequest(datasource_id="existing"), svc, ctx)
    unbound = await unbind_imported_datasource("local_demo", svc, ctx)
    assert unbound.data["file_retained"] is True
    retained_file = project / ".dataengineer" / "imported-databases" / "local_demo.sqlite"
    assert retained_file.read_bytes() == bytes_db
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "local_demo" not in config["agent"]["services"]["datasources"]

    with pytest.raises(HTTPException) as conflict:
        await import_datasource(
            svc, ctx, _ConnectedRequest(), _upload(_sqlite_bytes((99.0,)), "local.sqlite"), "local_demo", False
        )
    assert conflict.value.status_code == 409
    assert retained_file.read_bytes() == bytes_db

    restored = await import_datasource(
        svc, ctx, _ConnectedRequest(), _upload(bytes_db, "local.sqlite"), "local_demo", False
    )
    assert restored.success is True
    assert retained_file.is_file()
