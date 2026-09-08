"""Real PostgreSQL tests, enabled only by PRISM_TEST_POSTGRES_DSN.

Each test creates and removes a unique schema in an explicitly supplied test
database. No SQLite/mock substitute is used when PostgreSQL is unavailable.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import os
from uuid import uuid4

import pytest

from app.store.postgres import PostgresDecisionEventStore
from app.store.sqlite import StoreConflictError, StoreCorruptError, StoreError, StoreOwnerError, _MIGRATION_DIR
from tests.unit.test_store import _blocked_event, _pass_event
from tests.unit.test_behavior_profile import behavior_events


@pytest.fixture
def postgres_dsn():
    dsn = os.getenv("PRISM_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("real PostgreSQL test DSN not configured")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    schema = "prism_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(dsn, options=f"-c search_path={schema}")
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_migrations_roundtrip_owner_conflict_and_integrity(postgres_dsn):
    store = PostgresDecisionEventStore(postgres_dsn)
    event = _pass_event()
    try:
        assert store.save(event) == (event, True)
        assert store.save(event) == (event, False)
        assert store.get("other", event.event_id) is None
        assert store.list("other") == ()
        with pytest.raises(StoreOwnerError):
            store.list("api_key-owner")
        refusal = _blocked_event("first")
        store.save(refusal)
        with pytest.raises(StoreConflictError):
            store.save(_blocked_event("different"))
        assert len(store._connection.execute("SELECT * FROM schema_migrations").fetchall()) == len(list(_MIGRATION_DIR.glob("*.sql")))
    finally:
        store.close()
    store = PostgresDecisionEventStore(postgres_dsn)
    try:
        assert store.get(event.owner_id, event.event_id) == event
        store._connection.execute("UPDATE decision_events SET content_hash=? WHERE event_id=?", ("f" * 64, event.event_id))
        with pytest.raises(StoreCorruptError):
            store.get(event.owner_id, event.event_id)
    finally:
        store.close()


@pytest.mark.parametrize("kind", ["truth", "workflow"])
def test_postgres_cross_connection_cas_and_rollback(postgres_dsn, kind):
    now = datetime.now(UTC).isoformat()
    stores = [PostgresDecisionEventStore(postgres_dsn) for _ in range(3)]
    def write(store):
        try:
            if kind == "truth":
                store.save_session_truth("owner", "session", {"mode":"MOCK"}, 0, now)
            else:
                store.save_workflow("owner", {"owner_id":"owner", "nodes":[]}, 0, now)
            return "created"
        except StoreConflictError:
            return "conflict"
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(write, stores))
        assert results.count("created") == 1
        assert results.count("conflict") == 2
        for store in stores:
            # All losing transactions rolled back and remain usable.
            store.record_access("owner", "GET", "/test", 200)
        assert len(stores[0].list_access("owner")) == 3
        assert stores[0].list_access("other") == []
        if kind == "truth":
            assert stores[0].get_session_truth("other", "session") is None
            stores[0].save_session_truth("owner", "session", {}, 1, now)
            assert stores[1].get_session_truth("owner", "session")["revision"] == 2
        else:
            assert stores[0].get_workflow("other") is None
            with pytest.raises(StoreOwnerError):
                stores[0].save_workflow("other", {"owner_id":"owner"}, 0, now)
            stores[0].save_workflow("owner", {"owner_id":"owner"}, 1, now)
            assert stores[1].get_workflow("owner")["revision"] == 2
    finally:
        for store in stores:
            store.close()


def test_postgres_failed_migrations_are_atomic(postgres_dsn, tmp_path, monkeypatch):
    import psycopg
    (tmp_path / "001_test.sql").write_text("CREATE TABLE migration_probe (id INTEGER PRIMARY KEY);", encoding="utf-8")
    (tmp_path / "002_invalid.sql").write_text("THIS IS INVALID SQL;", encoding="utf-8")
    monkeypatch.setattr("app.store.postgres._MIGRATION_DIR", tmp_path)
    with pytest.raises(StoreError):
        PostgresDecisionEventStore(postgres_dsn)
    with psycopg.connect(postgres_dsn) as connection:
        assert connection.execute("SELECT to_regclass('migration_probe'), to_regclass('schema_migrations')").fetchone() == (None, None)
    (tmp_path / "002_invalid.sql").write_text("CREATE TABLE migration_probe_two (id INTEGER PRIMARY KEY);", encoding="utf-8")
    store = PostgresDecisionEventStore(postgres_dsn)
    try:
        assert len(store._connection.execute("SELECT * FROM schema_migrations").fetchall()) == 2
    finally:
        store.close()


def test_postgres_database_errors_rollback_without_leaking_payload(postgres_dsn):
    store = PostgresDecisionEventStore(postgres_dsn)
    try:
        store._connection.execute("BEGIN IMMEDIATE")
        store._connection.execute("INSERT INTO access_audit(owner_id,method,route,status_code,observed_at) VALUES (?,?,?,?,?)",
                                  ("owner", "GET", "/rolled-back", 200, "now"))
        with pytest.raises(StoreError) as exc:
            store._connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (1, "private-test-value"))
        assert "private-test-value" not in str(exc.value)
        store._connection.execute("ROLLBACK")
        assert store.list_access("owner") == []
        store.record_access("owner", "GET", "/committed", 200)
        assert len(store.list_access("owner")) == 1
    finally:
        store.close()


def test_postgres_behavior_batch_conflict_rolls_back_earlier_inserts(postgres_dsn):
    from decimal import Decimal
    store = PostgresDecisionEventStore(postgres_dsn)
    events = behavior_events("owner")
    try:
        store.save_behavior_events("owner", (events[0],))
        conflicting = events[0].model_copy(update={"price_cny":Decimal("101")})
        with pytest.raises(StoreConflictError):
            store.save_behavior_events("owner", (events[1], conflicting))
        assert store.list_behavior_events("owner") == (events[0],)
        # Owner-scoped event IDs can repeat in a different tenant.
        others = behavior_events("other")
        store.save_behavior_events("other", (others[0],))
        assert store.list_behavior_events("other") == (others[0],)
        store.save_behavior_events("owner", (events[1],))
        assert len(store.list_behavior_events("owner")) == 2
    finally:
        store.close()


def test_postgres_remaining_contracts_roundtrip_and_upserts(postgres_dsn):
    from app.portfolio import PortfolioOcrConfirmation
    from app.profile import build_display_policy, calculate_behavior_profile
    from app.profile.questionnaire import build_questionnaire_snapshot
    from app.store import build_context_memory_record
    from tests.unit.test_context_memory import _request
    from tests.unit.test_full_questionnaire import answers
    now = datetime(2026, 9, 8, 9, tzinfo=UTC)
    request = _request("owner")
    context = build_context_memory_record(request, saved_at=now)
    snapshot = build_questionnaire_snapshot("owner", answers(), confirmed_at=now, snapshot_version=1)
    policy = build_display_policy("owner", 20, updated_at=now)
    profile = calculate_behavior_profile(snapshot.profile, behavior_events("owner"), calculated_at=now, display_policy=policy)
    portfolio = {"portfolio":request.portfolio.model_dump(mode="json")}
    ocr = PortfolioOcrConfirmation(confirmation_id="ocr-test", owner_id="owner", image_digest="a" * 64,
                                   confirmed_payload_hash="b" * 64, confirmed_at=now, portfolio=request.portfolio)
    store = PostgresDecisionEventStore(postgres_dsn)
    try:
        assert store.save_context_memory(context) == (context, True)
        assert store.save_context_memory(context) == (context, False)
        assert store.get_context_memory("other", context.memory_id) is None
        assert store.list_context_memory("owner") == (context,)
        assert store.save_questionnaire_snapshot(snapshot) == (snapshot, True)
        assert store.save_questionnaire_snapshot(snapshot) == (snapshot, False)
        assert store.get_latest_questionnaire_snapshot("other") is None
        assert store.save_behavior_profile(profile) == profile
        assert store.get_latest_behavior_profile("other") is None
        assert store.save_display_policy(policy) == policy
        updated = build_display_policy("owner", 70, updated_at=now)
        assert store.save_display_policy(updated) == updated
        assert store.get_display_policy("other") is None
        store.save_current_portfolio("owner", "MOCK", portfolio)
        store.save_current_portfolio("owner", "MOCK", {**portfolio, "annotation":"更新"})
        assert store.get_current_portfolio("other", "MOCK") is None
        assert store.get_current_portfolio("owner", "LIVE") is None
        assert store.save_portfolio_ocr_confirmation(ocr) == (ocr, True)
        assert store.save_portfolio_ocr_confirmation(ocr) == (ocr, False)
        with pytest.raises(StoreConflictError):
            store.save_portfolio_ocr_confirmation(ocr.model_copy(update={"confirmed_payload_hash":"c" * 64}))
    finally:
        store.close()
    store = PostgresDecisionEventStore(postgres_dsn)
    try:
        assert store.get_context_memory("owner", context.memory_id) == context
        assert store.get_latest_questionnaire_snapshot("owner") == snapshot
        assert store.get_latest_behavior_profile("owner") == profile
        assert store.get_display_policy("owner") == updated
        assert store.get_current_portfolio("owner", "MOCK")["annotation"] == "更新"
        assert store.save_portfolio_ocr_confirmation(ocr) == (ocr, False)
        store._connection.execute("UPDATE context_memory SET content_hash=?", ("f" * 64,))
        with pytest.raises(StoreCorruptError):
            store.get_context_memory("owner", context.memory_id)
        store._connection.execute("UPDATE current_portfolios SET payload_json='{}'")
        with pytest.raises(StoreCorruptError):
            store.get_current_portfolio("owner", "MOCK")
    finally:
        store.close()


def test_postgres_app_factory_workflow_restart(postgres_dsn, monkeypatch):
    # Protect the module-level default application from using a user's database.
    monkeypatch.setenv("PRISM_DB_PATH", ":memory:")
    from fastapi.testclient import TestClient
    from app.api.main import create_app
    headers = {"X-Owner-ID":"workflow-owner"}
    endpoint = "/api/v1/advisor/workflow"
    with TestClient(create_app(database_url=postgres_dsn)) as client:
        initial = client.get(endpoint, headers=headers).json()
        response = client.post(endpoint, headers=headers, json={"definition":initial["definition"], "expected_revision":0})
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == 1
        assert client.post(endpoint, headers=headers, json={"definition":initial["definition"], "expected_revision":0}).status_code == 409
    with TestClient(create_app(database_url=postgres_dsn)) as client:
        assert client.get(endpoint, headers=headers).json()["revision"] == 1
        assert client.get(endpoint, headers={"X-Owner-ID":"other"}).json()["revision"] == 0


def test_postgres_concurrent_migration_and_lock_timeout_recovery(postgres_dsn):
    with ThreadPoolExecutor(max_workers=3) as executor:
        stores = list(executor.map(lambda _: PostgresDecisionEventStore(postgres_dsn), range(3)))
    try:
        count = len(list(_MIGRATION_DIR.glob("*.sql")))
        assert len(stores[0]._connection.execute("SELECT version FROM schema_migrations").fetchall()) == count
        stores[0]._connection.execute("BEGIN IMMEDIATE")
        try:
            stores[1]._connection.execute("SET lock_timeout = '30ms'")
            with pytest.raises(StoreError):
                stores[1].save_workflow("owner", {"owner_id":"owner"}, 0, "now")
        finally:
            stores[0]._connection.execute("ROLLBACK")
        assert stores[1].get_workflow("owner") is None
        assert stores[1].save_workflow("owner", {"owner_id":"owner"}, 0, "now")["revision"] == 1
    finally:
        for store in stores:
            store.close()
