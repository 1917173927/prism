import base64
import json

from fastapi.testclient import TestClient

from app.api import create_app
from app.api.access import password_digest
from app.security import ProtectedSecretStore, SecretProtectionError
from app.store import SQLiteDecisionEventStore


class ReversibleTestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"test:" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        if not ciphertext.startswith(b"test:"):
            raise SecretProtectionError("invalid test ciphertext")
        return ciphertext.removeprefix(b"test:")[::-1]


OWNER = "persistent-owner"
PASSWORD = "test-password"


def _accounts_file(path):
    if not path.exists():
        salt = "11" * 16
        path.write_text(json.dumps([{
            "username": "local-user",
            "owner_id": OWNER,
            "salt": salt,
            "password_hash": password_digest(PASSWORD, salt),
            "admin": False,
        }]), encoding="utf-8")
    return path


def _headers():
    encoded = base64.b64encode(f"local-user:{PASSWORD}".encode()).decode()
    return {"X-Owner-ID": OWNER, "Authorization": f"Basic {encoded}"}


def _client(secret_store, accounts_path):
    store = SQLiteDecisionEventStore(":memory:")
    return TestClient(create_app(
        store,
        secret_store=secret_store,
        auth_accounts_path=_accounts_file(accounts_path),
    )), store


def test_user_model_setting_survives_app_restart_without_key_disclosure(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    accounts = tmp_path / "accounts.json"
    first, first_db = _client(protected, accounts)
    headers = _headers()
    payload = {
        "api_key": "persistent-secret-value",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    }
    response = first.put("/api/v1/user/model-settings", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json() == {
        "is_configured": True,
        "scope": "USER",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "persistence": "OS_PROTECTED",
    }
    assert "persistent-secret-value" not in response.text
    first_db.close()

    restarted, restarted_db = _client(protected, accounts)
    restored = restarted.get("/api/v1/user/model-settings", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["is_configured"] is True
    assert restored.json()["scope"] == "USER"
    assert "persistent-secret-value" not in restored.text
    restarted_db.close()


def test_empty_key_deletes_persisted_user_setting(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    client, db = _client(protected, tmp_path / "accounts.json")
    headers = _headers()
    client.put("/api/v1/user/model-settings", headers=headers, json={
        "api_key": "delete-me",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    })

    deleted = client.put("/api/v1/user/model-settings", headers=headers, json={
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    })

    assert deleted.status_code == 200
    assert deleted.json()["scope"] == "SERVER"
    assert protected.get(f"llm:{OWNER}") is None
    db.close()


def test_rotation_and_delete_invalidate_another_app_instance(tmp_path) -> None:
    path = tmp_path / "protected.json"
    first_store = ProtectedSecretStore(path, ReversibleTestProtector())
    second_store = ProtectedSecretStore(path, ReversibleTestProtector())
    accounts = tmp_path / "accounts.json"
    first, first_db = _client(first_store, accounts)
    second, second_db = _client(second_store, accounts)
    headers = _headers()
    base = {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"}

    first.put("/api/v1/user/model-settings", headers=headers, json={**base, "api_key": "first-key"})
    assert second.get("/api/v1/user/model-settings", headers=headers).json()["scope"] == "USER"
    second.put("/api/v1/user/model-settings", headers=headers, json={**base, "api_key": "rotated-key"})
    assert "rotated-key" in first_store.get(f"llm:{OWNER}")

    second.put("/api/v1/user/model-settings", headers=headers, json={**base, "api_key": ""})
    refreshed = first.get("/api/v1/user/model-settings", headers=headers).json()
    assert refreshed["scope"] == "SERVER"
    assert refreshed["is_configured"] is False
    first_db.close()
    second_db.close()


def test_unauthenticated_development_mode_does_not_persist_owner_secret(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store, secret_store=protected))
    headers = {"X-Owner-ID": "spoofable-development-owner"}

    saved = client.put("/api/v1/user/model-settings", headers=headers, json={
        "api_key": "process-only-key",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    })

    assert saved.status_code == 200
    assert saved.json()["persistence"] == "PROCESS_ONLY"
    assert not protected.path.exists()
    store.close()
