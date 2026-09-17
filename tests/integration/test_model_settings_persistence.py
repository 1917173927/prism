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
            "admin": True,
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


def test_model_settings_uses_deepseek_v4_flash_when_model_is_omitted(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    client, db = _client(protected, tmp_path / "accounts.json")
    try:
        response = client.put("/api/v1/user/model-settings", headers=_headers(), json={
            "api_key": "default-model-test-key",
        })
        assert response.status_code == 200
        assert response.json()["model"] == "deepseek-v4-flash"
    finally:
        db.close()


def test_global_model_setting_survives_app_restart_without_key_disclosure(tmp_path) -> None:
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
        "scope": "GLOBAL",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "connection_verified": False,
        "persistence": "OS_PROTECTED",
    }
    assert "persistent-secret-value" not in response.text
    first_db.close()

    restarted, restarted_db = _client(protected, accounts)
    restored = restarted.get("/api/v1/user/model-settings", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["is_configured"] is True
    assert restored.json()["scope"] == "GLOBAL"
    assert "persistent-secret-value" not in restored.text
    restarted_db.close()


def test_empty_key_preserves_setting_until_explicit_delete(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    client, db = _client(protected, tmp_path / "accounts.json")
    headers = _headers()
    client.put("/api/v1/user/model-settings", headers=headers, json={
        "api_key": "delete-me",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    })

    saved = client.put("/api/v1/user/model-settings", headers=headers, json={
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    })

    assert saved.status_code == 200
    assert saved.json()["is_configured"] is True
    assert json.loads(protected.get("llm:global"))["api_key"] == "delete-me"
    deleted = client.delete("/api/v1/user/model-settings", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["scope"] == "SERVER"
    assert protected.get("llm:global") is None
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
    assert second.get("/api/v1/user/model-settings", headers=headers).json()["scope"] == "GLOBAL"
    second.put("/api/v1/user/model-settings", headers=headers, json={**base, "api_key": "rotated-key"})
    assert "rotated-key" in first_store.get("llm:global")

    second.delete("/api/v1/user/model-settings", headers=headers)
    refreshed = first.get("/api/v1/user/model-settings", headers=headers).json()
    assert refreshed["scope"] == "SERVER"
    assert refreshed["is_configured"] is False
    first_db.close()
    second_db.close()


def test_empty_key_cannot_reuse_another_providers_credential(tmp_path):
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    client, db = _client(protected, tmp_path / "accounts.json")
    try:
        client.put("/api/v1/user/model-settings", headers=_headers(), json={"api_key": "deepseek-secret"})
        response = client.put("/api/v1/user/model-settings", headers=_headers(), json={
            "api_key": "", "base_url": "https://api.openai.com/v1", "model": "other-model"})
        assert response.status_code == 422
        assert json.loads(protected.get("llm:global"))["api_key"] == "deepseek-secret"
    finally:
        db.close()


def test_unauthenticated_local_mode_uses_global_machine_scoped_secret(tmp_path) -> None:
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
    assert protected.get("llm:global") is not None
    assert "process-only-key" not in protected.path.read_text(encoding="utf-8")

    restarted_store = SQLiteDecisionEventStore(":memory:")
    restarted = TestClient(create_app(restarted_store, secret_store=protected))
    restored = restarted.get(
        "/api/v1/user/model-settings",
        headers={"X-Owner-ID": "another-local-owner-label"},
    )
    assert restored.status_code == 200
    assert restored.json()["is_configured"] is True
    assert restored.json()["scope"] == "GLOBAL"
    assert "process-only-key" not in restored.text
    restarted_store.close()
    store.close()


def test_fuyao_global_setting_is_loaded_for_every_owner_and_probed(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    protected.set("provider:fuyao", json.dumps({
        "api_key": "shared-fuyao-secret",
        "base_url": "https://fuyao.aicubes.cn",
    }))
    store = SQLiteDecisionEventStore(":memory:")
    reset_runtime_mode_controller(mode=DataMode.LIVE)

    try:
        with patch(
            "app.providers.fuyao.FuyaoFinanceProvider.probe_capabilities",
            new_callable=AsyncMock,
            return_value={"stock_quote": True, "fund_lookthrough": True},
        ) as probe:
            client = TestClient(create_app(store, secret_store=protected))
            response = client.get(
                "/api/v1/runtime/data-mode",
                headers={"X-Owner-ID": "any-local-owner"},
            )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["live_configured"] is True
        assert body["capabilities"]["LIVE"]["stock_quote"] is True
        assert body["capabilities"]["LIVE"]["fund_lookthrough"] is True
        probe.assert_awaited_once()
        assert "shared-fuyao-secret" not in response.text
        assert "shared-fuyao-secret" not in protected.path.read_text(encoding="utf-8")
    finally:
        reset_runtime_mode_controller(mode=DataMode.MOCK)
        store.close()


def test_global_machine_slot_is_available_to_authenticated_owner(tmp_path) -> None:
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
    assert response.json()["is_configured"] is True
    assert response.json()["scope"] == "GLOBAL"
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


def test_saved_unverified_wencai_contract_is_probed_on_first_runtime_read(tmp_path) -> None:
    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    protected.set("provider:wencai", json.dumps({
        "api_key": "auto-probe-secret",
        "base_url": "https://openapi.iwencai.com",
        "contract_verified": False,
    }))
    store = SQLiteDecisionEventStore(":memory:")
    reset_runtime_mode_controller()
    client = TestClient(create_app(store, secret_store=protected))
    probe_rows = tuple(
        {"name": f"skill-{index}", "skill_id": f"skill-{index}",
         "status": "SUCCESS", "record_count": 1, "item_count": 1, "error_code": None}
        for index in range(9)
    )
    with patch.object(
        WencaiSkillHubProvider, "probe_installed_skills", new_callable=AsyncMock
    ) as probe:
        probe.return_value = probe_rows
        response = client.get("/api/v1/runtime/data-mode")

    assert response.status_code == 200
    status = response.json()["data"]
    assert status["data_mode"] == "LIVE"
    assert status["wencai_ready"] is True
    assert status["contract_verified"] is True
    assert status["portfolio_metadata_ready"] is True
    assert probe.await_count == 1
    assert json.loads(protected.get("provider:wencai"))["contract_verified"] is True
    store.close()


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


def test_model_connection_test_reports_safe_provider_error():
    async def rejected(self, messages, tools=None):
        yield {"type": "error", "message": "模型服务返回 HTTP 401，请检查服务配置或稍后重试。"}
    store = SQLiteDecisionEventStore(":memory:")
    client = TestClient(create_app(store))
    headers = {"X-Owner-ID": "probe-owner"}
    assert client.put("/api/v1/user/model-settings", headers=headers, json={"api_key": "invalid-test-secret"}).status_code == 200
    with patch("app.api.main.AsyncLLMClient.stream_chat", rejected):
        response = client.post("/api/v1/user/model-settings/test", headers=headers)
    assert response.status_code == 502
    assert "HTTP 401" in response.json()["message"]
    assert "invalid-test-secret" not in response.text
    assert client.get("/api/v1/user/model-settings", headers=headers).json()["connection_verified"] is False
    store.close()


def test_successful_model_connection_status_is_shared_and_persisted(tmp_path):
    async def accepted(self, messages, tools=None):
        yield {"type": "content", "delta": "OK"}

    protected = ProtectedSecretStore(tmp_path / "protected.json", ReversibleTestProtector())
    first_store = SQLiteDecisionEventStore(":memory:")
    first = TestClient(create_app(first_store, secret_store=protected))
    assert first.put("/api/v1/user/model-settings", headers={"X-Owner-ID": "owner-a"}, json={
        "api_key": "valid-test-secret",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    }).status_code == 200

    with patch("app.api.main.AsyncLLMClient.stream_chat", accepted):
        tested = first.post(
            "/api/v1/user/model-settings/test", headers={"X-Owner-ID": "owner-a"}
        )
    assert tested.status_code == 200
    assert first.get(
        "/api/v1/user/model-settings", headers={"X-Owner-ID": "owner-b"}
    ).json()["connection_verified"] is True
    assert json.loads(protected.get("llm:global"))["connection_verified"] is True
    first_store.close()

    restarted_store = SQLiteDecisionEventStore(":memory:")
    restarted = TestClient(create_app(restarted_store, secret_store=protected))
    restored = restarted.get(
        "/api/v1/user/model-settings", headers={"X-Owner-ID": "owner-c"}
    ).json()
    assert restored["scope"] == "GLOBAL"
    assert restored["connection_verified"] is True
    assert "valid-test-secret" not in json.dumps(restored)
    restarted_store.close()
