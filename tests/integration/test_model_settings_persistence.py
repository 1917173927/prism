import base64
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api import create_app
from app.api.access import password_digest
from app.security import ProtectedSecretStore, SecretProtectionError
from app.store import SQLiteDecisionEventStore
from app.runtime.mode import DataMode, get_runtime_mode_controller, reset_runtime_mode_controller
from app.providers.skillhub import WencaiSkillHubProvider


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


def test_unauthenticated_local_mode_persists_one_machine_scoped_secret(tmp_path) -> None:
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
    assert saved.json()["persistence"] == "OS_PROTECTED"
    assert protected.path.exists()
    assert protected.get("llm:local:workbench") is not None
    assert "process-only-key" not in protected.path.read_text(encoding="utf-8")

    restarted_store = SQLiteDecisionEventStore(":memory:")
    restarted = TestClient(create_app(restarted_store, secret_store=protected))
    restored = restarted.get(
        "/api/v1/user/model-settings",
        headers={"X-Owner-ID": "another-local-owner-label"},
    )
    assert restored.status_code == 200
    assert restored.json()["is_configured"] is True
    assert restored.json()["scope"] == "LOCAL_MACHINE"
    assert "process-only-key" not in restored.text
    restarted_store.close()
    store.close()


def test_local_machine_slot_does_not_collide_with_authenticated_owner(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    anonymous_store = SQLiteDecisionEventStore(":memory:")
    anonymous = TestClient(create_app(anonymous_store, secret_store=protected))
    anonymous.put("/api/v1/user/model-settings", headers={"X-Owner-ID": "any"}, json={
        "api_key": "local-machine-secret",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    })

    salt = "22" * 16
    accounts = tmp_path / "accounts-collision.json"
    accounts.write_text(json.dumps([{
        "username": "named-user",
        "owner_id": "local-workbench",
        "salt": salt,
        "password_hash": password_digest(PASSWORD, salt),
        "admin": False,
    }]), encoding="utf-8")
    encoded = base64.b64encode(f"named-user:{PASSWORD}".encode()).decode()
    authenticated_store = SQLiteDecisionEventStore(":memory:")
    authenticated = TestClient(create_app(
        authenticated_store,
        secret_store=protected,
        auth_accounts_path=accounts,
    ))
    response = authenticated.get("/api/v1/user/model-settings", headers={
        "X-Owner-ID": "local-workbench",
        "Authorization": f"Basic {encoded}",
    })
    assert response.status_code == 200
    assert response.json()["is_configured"] is False
    assert "local-machine-secret" not in response.text
    authenticated_store.close()
    anonymous_store.close()


def test_wencai_setting_is_project_scoped_and_survives_restart(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    first_store = SQLiteDecisionEventStore(":memory:")
    reset_runtime_mode_controller(mode=DataMode.MOCK)
    first = TestClient(create_app(first_store, secret_store=protected))

    saved = first.put("/api/v1/runtime/wencai-settings", json={
        "api_key": "wencai-project-secret",
        "base_url": "https://openapi.iwencai.com",
    })

    assert saved.status_code == 200
    assert saved.json()["is_configured"] is True
    assert saved.json()["persistence"] == "OS_PROTECTED"
    assert saved.json()["contract_verified"] is False
    assert len(saved.json()["installed_skills"]) == 9
    assert "wencai-project-secret" not in saved.text
    assert "wencai-project-secret" not in protected.path.read_text(encoding="utf-8")
    first_store.close()

    restarted_store = SQLiteDecisionEventStore(":memory:")
    reset_runtime_mode_controller(mode=DataMode.MOCK)
    restarted = TestClient(create_app(restarted_store, secret_store=protected))
    restored = restarted.get("/api/v1/runtime/wencai-settings")
    assert restored.status_code == 200
    assert restored.json()["is_configured"] is True
    assert restored.json()["base_url"] == "https://openapi.iwencai.com"
    assert "wencai-project-secret" not in restored.text
    restarted_store.close()


def test_wencai_partial_skill_metadata_from_another_worktree_loads_safely(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    protected.set("provider:wencai", json.dumps({
        "api_key": "partial-secret", "base_url": "https://openapi.iwencai.com",
        "contract_verified": False, "verified_skills": ["announcement-search"],
    }))
    store = SQLiteDecisionEventStore(":memory:")
    try:
        client = TestClient(create_app(store, secret_store=protected))
        response = client.get("/api/v1/runtime/wencai-settings")
        assert response.status_code == 200
        assert response.json()["is_configured"] is True
        assert response.json()["contract_verified"] is False
        assert "partial-secret" not in response.text
        assert json.loads(protected.get("provider:wencai"))["verified_skills"] == ["announcement-search"]
    finally:
        store.close()


def test_wencai_real_probe_status_is_persisted_for_restart(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    store = SQLiteDecisionEventStore(":memory:")
    reset_runtime_mode_controller(mode=DataMode.MOCK)
    client = TestClient(create_app(store, secret_store=protected))
    client.put("/api/v1/runtime/wencai-settings", json={
        "api_key": "verified-secret",
        "base_url": "https://openapi.iwencai.com",
    })
    probe_rows = tuple(
        {"name": f"skill-{index}", "skill_id": f"skill-{index}",
         "status": "SUCCESS", "record_count": 1, "item_count": 1, "error_code": None}
        for index in range(9)
    )
    with patch.object(
        WencaiSkillHubProvider, "probe_installed_skills", new_callable=AsyncMock
    ) as probe:
        probe.return_value = probe_rows
        response = client.post("/api/v1/runtime/wencai-settings/test")
    assert response.status_code == 200
    assert response.json()["status"] == "PASS"
    assert get_runtime_mode_controller().is_wencai_ready is True
    store.close()

    reset_runtime_mode_controller(mode=DataMode.MOCK)
    restarted_store = SQLiteDecisionEventStore(":memory:")
    restarted = TestClient(create_app(restarted_store, secret_store=protected))
    status = restarted.get("/api/v1/runtime/data-mode").json()["data"]
    assert status["wencai_configured"] is True
    assert status["contract_verified"] is True
    assert status["wencai_ready"] is True
    assert "verified-secret" not in restarted.get(
        "/api/v1/runtime/wencai-settings"
    ).text
    restarted_store.close()


def test_wencai_empty_probe_does_not_verify_live_contract(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    store = SQLiteDecisionEventStore(":memory:")
    reset_runtime_mode_controller(mode=DataMode.MOCK)
    client = TestClient(create_app(store, secret_store=protected))
    client.put("/api/v1/runtime/wencai-settings", json={
        "api_key": "empty-probe-secret",
        "base_url": "https://openapi.iwencai.com",
    })
    probe_rows = tuple(
        {
            "name": f"skill-{index}", "skill_id": f"skill-{index}",
            "status": "EMPTY" if index == 4 else "SUCCESS",
            "record_count": 0 if index == 4 else 1,
            "item_count": 0 if index == 4 else 1,
            "error_code": None,
        }
        for index in range(9)
    )
    with patch.object(
        WencaiSkillHubProvider, "probe_installed_skills", new_callable=AsyncMock
    ) as probe:
        probe.return_value = probe_rows
        response = client.post("/api/v1/runtime/wencai-settings/test")
    assert response.status_code == 502
    assert response.json()["status"] == "FAILED"
    assert get_runtime_mode_controller().is_wencai_ready is False
    stored = json.loads(protected.get("provider:wencai"))
    assert stored["contract_verified"] is False
    store.close()
