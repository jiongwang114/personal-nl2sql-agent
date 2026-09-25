"""Credential storage for Pi providers.

Production secrets are delegated to the operating-system credential vault. A
plain JSON backend exists only for explicitly enabled, sandboxed tests.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from threading import RLock


class CredentialStoreError(RuntimeError):
    """Raised when secure credential storage is unavailable."""


class CredentialStore:
    SERVICE = "dataengineer.pi"
    _lock = RLock()

    @staticmethod
    def _test_path() -> Path | None:
        if os.getenv("DATAENGINEER_CREDENTIAL_STORE") != "file-test":
            return None
        raw_path = os.getenv("DATAENGINEER_TEST_SECRET_FILE", "").strip()
        if not raw_path:
            raise CredentialStoreError("file-test credential storage requires DATAENGINEER_TEST_SECRET_FILE")
        path = Path(raw_path).resolve()
        workspace_root = Path(__file__).resolve().parents[3]
        sandbox = workspace_root / "reports" / "frontend-next-03-04-sandbox"
        if not path.is_relative_to(sandbox.resolve()):
            raise CredentialStoreError("file-test credential storage is restricted to the acceptance sandbox")
        return path

    @staticmethod
    def _account(scope: str, provider: str) -> str:
        scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:24]
        return f"{scope_hash}:{provider}"

    @staticmethod
    def scope_id(project_id: str | None, project_root: str | Path) -> str:
        return f"{project_id or 'default'}:{Path(project_root).resolve()}"

    def get(self, scope: str, provider: str) -> str | None:
        path = self._test_path()
        if path is not None:
            if not path.is_file():
                return None
            try:
                values = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CredentialStoreError("test credential store is unreadable") from exc
            return values.get(self._account(scope, provider))
        try:
            import keyring

            value = keyring.get_password(self.SERVICE, self._account(scope, provider))
        except Exception as exc:
            raise CredentialStoreError("operating-system credential vault is unavailable") from exc
        return value

    def set(self, scope: str, provider: str, secret: str) -> None:
        path = self._test_path()
        if path is not None:
            with self._lock:
                values = {}
                if path.is_file():
                    try:
                        values = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        values = {}
                values[self._account(scope, provider)] = secret
                path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = path.with_suffix(path.suffix + ".tmp")
                temp_path.write_text(json.dumps(values), encoding="utf-8")
                os.replace(temp_path, path)
            return
        try:
            import keyring

            keyring.set_password(self.SERVICE, self._account(scope, provider), secret)
        except Exception as exc:
            raise CredentialStoreError("operating-system credential vault is unavailable") from exc

    def delete(self, scope: str, provider: str) -> None:
        path = self._test_path()
        if path is not None:
            with self._lock:
                if not path.is_file():
                    return
                try:
                    values = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return
                values.pop(self._account(scope, provider), None)
                temp_path = path.with_suffix(path.suffix + ".tmp")
                temp_path.write_text(json.dumps(values), encoding="utf-8")
                os.replace(temp_path, path)
            return
        try:
            import keyring

            keyring.delete_password(self.SERVICE, self._account(scope, provider))
        except Exception as exc:
            if type(exc).__name__ != "PasswordDeleteError":
                raise CredentialStoreError("operating-system credential vault is unavailable") from exc
