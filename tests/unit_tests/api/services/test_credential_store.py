import json
from pathlib import Path

import pytest

from dataengineer.api.services.credential_store import CredentialStore, CredentialStoreError


def test_file_test_store_round_trips_without_returning_secret_in_account_name(tmp_path, monkeypatch):
    store_path = tmp_path / "vault.json"
    monkeypatch.setenv("DATAENGINEER_CREDENTIAL_STORE", "file-test")
    monkeypatch.setenv("DATAENGINEER_TEST_SECRET_FILE", str(store_path))
    store = CredentialStore()

    store.set("project-a", "deepseek", "test-secret-value")

    assert store.get("project-a", "deepseek") == "test-secret-value"
    assert "test-secret-value" in store_path.read_text(encoding="utf-8")
    assert "project-a" not in store_path.read_text(encoding="utf-8")
    store.delete("project-a", "deepseek")
    assert store.get("project-a", "deepseek") is None
    assert json.loads(store_path.read_text(encoding="utf-8")) == {}


def test_file_test_store_rejects_paths_outside_acceptance_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("DATAENGINEER_CREDENTIAL_STORE", "file-test")
    outside_path = Path(__file__).resolve().parents[4] / "reports" / "outside-test-vault.json"
    monkeypatch.setenv("DATAENGINEER_TEST_SECRET_FILE", str(outside_path))

    with pytest.raises(CredentialStoreError, match="acceptance sandbox"):
        CredentialStore().get("project-a", "deepseek")
