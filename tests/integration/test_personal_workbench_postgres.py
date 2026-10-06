"""Real PostgreSQL persistence of private research versions and style policies."""
import os
from uuid import uuid4

import pytest

from app.service.personal_research import PersonalResearchService, PersonalResearchSave, profitability_template
from app.service.investment_memory import InvestmentMemoryService, PreferenceMemoryWrite, InvestmentPolicyConfirmation
from app.service.research_runtime import ResearchRuntime
from app.service.skill_registry import SkillRegistry
from app.store.postgres import PostgresDecisionEventStore
from app.store.sqlite import StoreConflictError


@pytest.fixture
def isolated_postgres():
    dsn = os.getenv("PRISM_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("real PostgreSQL test configuration is absent")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    schema = "prism_personal_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(dsn, options=f"-c search_path={schema}")
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_private_versions_preferences_confirmation_and_restart(isolated_postgres):
    store = PostgresDecisionEventStore(isolated_postgres)
    try:
        service = PersonalResearchService(store=store, provider=None, registry=SkillRegistry(store), runtime=ResearchRuntime())
        definition = PersonalResearchSave(definition=profitability_template(), expected_revision=0)
        assert service.save("alice", "profitability", definition)["revision"] == 1
        assert service.list("bob") == []
        with pytest.raises(StoreConflictError):
            service.save("alice", "profitability", definition)
        memory = InvestmentMemoryService(store)
        state = memory.save_preferences("alice", PreferenceMemoryWrite.model_validate({
            "expected_revision": 0, "preferences": {"max_turnover_pct": "5", "minimum_cash_pct": "10"}}))
        candidate = state["candidate"]
        memory.confirm_policy("alice", InvestmentPolicyConfirmation(candidate_id=candidate.candidate_id,
            expected_memory_revision=1, expected_style_profile_version=0))
        assert memory.state("alice")["policy_status"] == "ACTIVE"
        assert memory.state("bob")["memory"] is None
    finally:
        store.close()
    restarted = PostgresDecisionEventStore(isolated_postgres)
    try:
        service = PersonalResearchService(store=restarted, provider=None, registry=SkillRegistry(restarted), runtime=ResearchRuntime())
        assert service.get("alice", "profitability")["definition"]["name"] == "盈利质量观察"
        memory = InvestmentMemoryService(restarted)
        assert memory.resolve_policy("alice", 1).parameters.max_turnover_pct == 5
        state = memory.save_preferences("alice", PreferenceMemoryWrite.model_validate({"expected_revision": 1, "preferences": {}}))
        assert state["policy_status"] == "STALE"
        versions = {row["version"] for row in restarted._connection.execute("SELECT version FROM schema_migrations").fetchall()}
        assert {22, 23} <= versions
    finally:
        restarted.close()
