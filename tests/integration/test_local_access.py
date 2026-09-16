from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json

from fastapi.testclient import TestClient
import pytest

from app.api.access import LocalAccount, load_accounts, password_digest
from app.api.main import create_app
from tools.local_account import default_database_path


@pytest.fixture
def client(tmp_path):
    salt = "01" * 16
    digest = password_digest("local-test-password", salt)
    accounts = [LocalAccount("alice", "owner-a", salt, digest),
                LocalAccount("bob", "owner-b", salt, digest, True)]
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps([asdict(a) for a in accounts]), encoding="utf-8")
    app = create_app(auth_accounts_path=path, database_path=tmp_path / "test.sqlite3")
    @app.get("/failure-for-audit")
    def fail():
        raise RuntimeError("sensitive-error-must-not-be-logged")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_authentication_and_server_owned_identity(client):
    assert client.get("/api/health").status_code == 200
    redirected = client.get("/")
    assert redirected.status_code == 200
    assert redirected.url.path == "/login"
    assert client.get("/api/v1/advisor/portfolio/current").status_code == 401
    wrong_password = client.get("/", auth=("alice", "wrong-password"))
    assert wrong_password.status_code == 200
    assert wrong_password.url.path == "/login"
    client.auth = ("alice", "local-test-password")
    context = client.get("/api/v1/auth/context")
    assert context.json() == {"enabled": True, "owner_id": "owner-a", "admin": False}
    assert client.get("/api/v1/advisor/portfolio/current", headers={"X-Owner-ID": "owner-b"}).status_code == 403
    assert client.get("/api/v1/advisor/portfolio/current").status_code == 200
    assert context.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/copilot/chat", json={"owner_id":"owner-b", "message":"hello"}).status_code == 403
    assert client.post("/api/v1/copilot/chat", json={"owner_id":"owner-a", "message":"hello",
        "llm_config":{"api_key":"test-only", "base_url":"http://untrusted.invalid"}}).status_code == 403


def test_local_demo_login_issues_an_http_only_session(client):
    assert client.get("/login").status_code == 200
    response = client.post("/api/v1/auth/login", auth=("alice", "local-test-password"))
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    client.auth = None
    assert client.get("/api/v1/auth/context").json()["owner_id"] == "owner-a"
    assert client.post("/api/v1/auth/logout").json() == {"logged_out": True}
    assert client.get("/api/v1/auth/context").status_code == 401


def test_privileges_origin_and_audit_isolation(client):
    client.auth = ("alice", "local-test-password")
    assert client.put("/api/v1/runtime/data-mode", json={"mode":"MOCK"}).status_code == 403
    assert client.put("/api/v1/user/model-settings", json={"api_key":"member-key"}).status_code == 403
    assert client.post("/api/v1/user/model-settings/test").status_code == 403
    assert client.delete("/api/v1/user/model-settings").status_code == 403
    assert client.post("/api/v1/portfolio/import", headers={"Origin":"https://other.invalid"}, json={}).status_code == 403
    assert client.post("/api/v1/copilot/chat", headers={"Sec-Fetch-Site":"cross-site"}, json={}).status_code == 403
    rows = client.get("/api/v1/access-audit").json()["items"]
    assert {row["route"] for row in rows} >= {"/admin-denied", "/origin-denied"}
    assert all(row["owner_id"] == "owner-a" for row in rows)
    assert "local-test-password" not in json.dumps(rows)
    client.auth = ("bob", "local-test-password")
    assert client.get("/api/v1/access-audit").json()["items"] == []
    assert client.get("/api/v1/auth/context").json()["admin"] is True
    # Invalid input reaches validation for admins instead of the member-only gate.
    assert client.put("/api/v1/runtime/data-mode", json={}).status_code == 422
    assert client.put("/api/v1/user/model-settings", json={"model":""}).status_code == 422


def test_invalid_accounts_fail_closed(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        create_app(auth_accounts_path=path)
    path.write_text(json.dumps([asdict(LocalAccount("alice", "bad\nowner", "01" * 16, "02" * 64))]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_accounts(path)


def test_unhandled_failures_are_audited_without_exception_contents(client):
    client.auth = ("alice", "local-test-password")
    assert client.get("/failure-for-audit").status_code == 500
    rows = client.get("/api/v1/access-audit").json()["items"]
    assert rows[0]["route"] == "/failure-for-audit"
    assert rows[0]["status_code"] == 500
    assert "sensitive-error" not in json.dumps(rows)


def test_registration_persistent_sessions_owner_isolation_and_password_rotation(tmp_path):
    database = tmp_path / "accounts.sqlite3"
    app = create_app(database_path=database, auth_enabled=True)
    alice = TestClient(app)
    created = alice.post("/api/v1/auth/register", json={
        "username": "alice-new",
        "password": "alice-secure-password",
        "password_confirmation": "alice-secure-password",
    })
    assert created.status_code == 201, created.text
    owner_a = created.json()["owner_id"]
    assert owner_a.startswith("usr-")
    assert alice.get("/api/v1/advisor/portfolio/current").json()["data"] is None

    bob = TestClient(app)
    second = bob.post("/api/v1/auth/register", json={
        "username": "bob-new",
        "password": "bob-secure-password",
        "password_confirmation": "bob-secure-password",
    })
    assert second.status_code == 201
    owner_b = second.json()["owner_id"]
    assert owner_b != owner_a
    assert alice.get("/api/v1/advisor/portfolio/current", headers={"X-Owner-ID": owner_b}).status_code == 403
    assert bob.get("/api/v1/advisor/portfolio/current", headers={"X-Owner-ID": owner_a}).status_code == 403

    rotated = alice.post("/api/v1/auth/change-password", json={
        "current_password": "alice-secure-password",
        "new_password": "alice-rotated-password",
        "new_password_confirmation": "alice-rotated-password",
    })
    assert rotated.status_code == 200
    assert alice.get("/api/v1/auth/context").status_code == 401
    assert alice.post("/api/v1/auth/login", json={
        "username": "alice-new", "password": "alice-secure-password",
    }).status_code == 401
    assert alice.post("/api/v1/auth/login", json={
        "username": "alice-new", "password": "alice-rotated-password",
    }).status_code == 200


def test_persistent_session_idle_and_absolute_expiry(tmp_path):
    now = [datetime(2026, 9, 15, 8, 0, tzinfo=UTC)]
    app = create_app(database_path=tmp_path / "expiry.sqlite3", auth_enabled=True, clock=lambda: now[0])
    client = TestClient(app)
    assert client.post("/api/v1/auth/register", json={
        "username": "expiry-user",
        "password": "expiry-secure-password",
        "password_confirmation": "expiry-secure-password",
    }).status_code == 201
    now[0] += timedelta(hours=1, minutes=59)
    assert client.get("/api/v1/auth/context").status_code == 200
    now[0] += timedelta(hours=2, minutes=1)
    assert client.get("/api/v1/auth/context").status_code == 401


def test_session_cookie_survives_application_restart(tmp_path):
    database = tmp_path / "restart.sqlite3"
    first = TestClient(create_app(database_path=database, auth_enabled=True))
    response = first.post("/api/v1/auth/register", json={
        "username": "restart-user",
        "password": "restart-secure-password",
        "password_confirmation": "restart-secure-password",
    })
    assert response.status_code == 201
    cookie = first.cookies.get("prism_local_session")
    first.close()

    second = TestClient(create_app(database_path=database, auth_enabled=True))
    second.cookies.set("prism_local_session", cookie)
    context = second.get("/api/v1/auth/context")
    assert context.status_code == 200
    assert context.json()["owner_id"] == response.json()["owner_id"]
    second.close()


def test_local_account_cli_uses_prism_db_path(monkeypatch, tmp_path):
    expected = tmp_path / "configured-accounts.sqlite3"
    monkeypatch.setenv("PRISM_DB_PATH", str(expected))
    assert default_database_path() == expected
