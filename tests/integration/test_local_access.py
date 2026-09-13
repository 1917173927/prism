from dataclasses import asdict
import json

from fastapi.testclient import TestClient
import pytest

from app.api.access import LocalAccount, load_accounts, password_digest
from app.api.main import create_app


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
    assert client.get("/").status_code == 401
    assert client.get("/api/v1/advisor/portfolio/current").status_code == 401
    assert client.get("/", auth=("alice", "wrong-password")).status_code == 401
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
