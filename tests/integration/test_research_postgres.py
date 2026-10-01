"""Research-platform PostgreSQL regressions; require a real explicit test DSN."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import os
from uuid import uuid4

import pytest

from app.providers.contracts import ProviderRequest
from app.service.knowledge import KnowledgeDocumentInput, KnowledgeService
from app.service.skill_registry import SkillRegistry
from app.store.postgres import PostgresDecisionEventStore
from app.store.sqlite import StoreConflictError, _MIGRATION_DIR

NOW = datetime(2026, 10, 1, tzinfo=UTC)


class DisabledEmbedder:
    model_id, revision = "backend-regression", "disabled"
    def encode(self, *args, **kwargs):
        raise RuntimeError("embedding not used in storage-backend validation")


@pytest.fixture
def postgres_dsn():
    dsn = os.getenv("PRISM_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("real PostgreSQL test DSN not configured")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    schema = "prism_research_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(dsn, options=f"-c search_path={schema}")
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def document(**overrides):
    return KnowledgeDocumentInput.model_validate({"title": "基金穿透方法", "text": "基金穿透应保留披露持仓、单位和报告期。",
        "source": "后端回归资料", "canonical_source": "backend-test:fund", "visibility": "PRIVATE",
        "published_at": "2026-09-20T00:00:00+00:00", "subject": "fund", "period": "2026H1", **overrides})


def test_new_migrations_and_postgres_fulltext_owner_time_filter(postgres_dsn):
    store = PostgresDecisionEventStore(postgres_dsn)
    try:
        versions = {row["version"] for row in store._connection.execute("SELECT version FROM schema_migrations").fetchall()}
        assert versions == {int(path.name.split("_", 1)[0]) for path in _MIGRATION_DIR.glob("*.sql")}
        assert {18, 19, 20}.issubset(versions)
        service = KnowledgeService(store, clock=lambda: NOW, embedder=DisabledEmbedder())
        assert service.fulltext_backend == "POSTGRES_TSVECTOR_BIGRAM"
        saved = service.ingest("alice", document())
        assert service.search("alice", "基金", subject="fund", period="2026H1")["matches"][0]["document_id"] == saved["document_id"]
        assert service.search("bob", "基金")["matches"] == []
        assert service.search("alice", "基金", as_of="2026-09-01T00:00:00+00:00")["matches"] == []
        assert service.search("alice", "基金", period="2025H1")["matches"] == []
        hits = store._connection.execute("SELECT chunk_id FROM knowledge_fts_pg WHERE to_tsvector('simple',search_text) @@ plainto_tsquery('simple',?)", ("基金",)).fetchall()
        assert hits
        snapshot_columns = store._connection.execute("SELECT * FROM research_fact_snapshots LIMIT 1").fetchall()
        assert snapshot_columns == []
    finally:
        store.close()


def test_postgres_document_correction_and_deletion_invalidate_index_and_quotes(postgres_dsn):
    store = PostgresDecisionEventStore(postgres_dsn)
    try:
        service = KnowledgeService(store, clock=lambda: NOW, embedder=DisabledEmbedder())
        saved = service.ingest("alice", document())
        match = service.search("alice", "基金")["matches"][0]
        citation = {**match, "quote": match["text"]}
        assert service.verify_citations("alice", [citation])["status"] == "PASS"
        changed = service.ingest("alice", document(text="基金穿透方法的版本已更正。", expected_revision=1))
        assert changed["revision"] == 2
        assert service.verify_citations("alice", [citation])["status"] == "UNVERIFIED"
        assert store._connection.execute("SELECT chunk_id FROM knowledge_fts_pg WHERE chunk_id=?", (match["chunk_id"],)).fetchone() is None
        assert service.delete("alice", saved["document_id"], expected_revision=2)
        assert service.search("alice", "基金")["matches"] == []
        assert store._connection.execute("SELECT COUNT(*) AS n FROM knowledge_document_versions").fetchone()["n"] == 2
    finally:
        store.close()


def test_postgres_skill_selection_cas_across_independent_connections(postgres_dsn):
    stores = [PostgresDecisionEventStore(postgres_dsn) for _ in range(3)]
    try:
        registries = [SkillRegistry(store, clock=lambda: NOW) for store in stores]
        def choose(registry):
            try:
                registry.select("alice", "hithink-market-query", enabled=False, expected_revision=0)
                return "created"
            except StoreConflictError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(choose, registries))
        assert results.count("created") == 1
        assert results.count("conflict") == 2
        query = ProviderRequest(request_id="storage-only-regression", operation="MARKET_DATA", subject="600519")
        assert registries[0].resolve(query, "bob").skill_id == "hithink-market-query"
        assert next(item for item in registries[0].list("alice") if item["skill_id"] == "hithink-market-query")["selection_revision"] == 1
        registries[1].select("alice", "hithink-market-query", enabled=True, expected_revision=1)
        assert registries[2].resolve(query, "alice").skill_id == "hithink-market-query"
    finally:
        for store in stores:
            store.close()
