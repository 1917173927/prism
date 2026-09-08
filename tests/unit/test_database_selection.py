import pytest

from app.api.main import create_app
from app.store import SQLiteDecisionEventStore, StoreError


def test_invalid_explicit_postgres_never_falls_back_to_sqlite(tmp_path):
    target = tmp_path / "uncreated" / "fallback.sqlite3"
    with pytest.raises(StoreError) as error:
        create_app(database_url="not-a-valid-dsn private-test-value", database_path=target)
    assert "private-test-value" not in str(error.value)
    assert not target.parent.exists()


def test_injected_store_and_postgres_selection_are_exclusive():
    store = SQLiteDecisionEventStore(":memory:")
    try:
        with pytest.raises(ValueError, match="either"):
            create_app(store=store, database_url="not-used")
        assert store.list("owner") == ()
    finally:
        store.close()
