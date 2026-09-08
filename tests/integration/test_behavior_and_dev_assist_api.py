from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.profile import (
    ExperienceLevel,
    InvestmentHorizon,
    LiquidityNeed,
    ReturnExpectation,
    RiskQuestionnaire,
    build_profile_draft,
    finalize_profile,
)
from app.store import SQLiteDecisionEventStore


NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
OWNER = "api-behavior-owner"


def profile_payload() -> dict:
    questionnaire = RiskQuestionnaire(
        questionnaire_id="api-q-001",
        owner_id=OWNER,
        answered_at=NOW,
        loss_tolerance_score=4,
        investment_horizon=InvestmentHorizon.LONG,
        liquidity_need=LiquidityNeed.LOW,
        experience_level=ExperienceLevel.INTERMEDIATE,
        return_expectation=ReturnExpectation.HIGH,
        max_drawdown_tolerance_pct=Decimal("25"),
    )
    profile = finalize_profile(
        build_profile_draft(questionnaire), profile_id="api-profile-001", created_at=NOW
    )
    return profile.model_dump(mode="json")


def events_payload() -> list[dict]:
    events = []
    for index in range(3):
        events.append({
            "schema_version": "behavior-event.v1",
            "event_id": f"api-trade-{index}",
            "owner_id": OWNER,
            "event_type": "TRADE",
            "occurred_at": (NOW - timedelta(days=20 - index)).isoformat(),
            "source": "integration fixture",
            "asset_id": "300750.SZ",
            "asset_type": "STOCK",
            "side": "BUY",
            "quantity": "100",
            "price_cny": "100",
            "portfolio_value_cny": "100000",
        })
    for index in range(2):
        events.append({
            "schema_version": "behavior-event.v1",
            "event_id": f"api-snapshot-{index}",
            "owner_id": OWNER,
            "event_type": "POSITION_SNAPSHOT",
            "occurred_at": (NOW - timedelta(days=10 - index)).isoformat(),
            "source": "integration fixture",
            "portfolio_value_cny": "100000",
            "equity_weight_pct": "40",
            "max_position_weight_pct": "15",
            "max_sector_weight_pct": "25",
            "drawdown_pct": "5",
        })
    return events


def test_behavior_api_persists_recomputes_and_is_owner_scoped() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        headers = {"X-Owner-ID": OWNER}
        write = client.post(
            "/api/v1/advisor/behavior/events",
            headers=headers,
            json={"schema_version": "behavior-events-write-request.v1", "owner_id": OWNER, "events": events_payload()},
        )
        assert write.status_code == 200
        assert write.json()["created_count"] == 5
        repeated = client.post(
            "/api/v1/advisor/behavior/events",
            headers=headers,
            json={"schema_version": "behavior-events-write-request.v1", "owner_id": OWNER, "events": events_payload()},
        )
        assert repeated.json()["created_count"] == 0

        policy = client.patch(
            "/api/v1/advisor/display-policy",
            headers=headers,
            json={"schema_version": "display-policy-update-request.v1", "owner_id": OWNER, "trust_score": 20, "updated_at": NOW.isoformat()},
        )
        assert policy.json()["policy"]["mode"] == "AUDIT_EXPANDED"

        recompute = client.post(
            "/api/v1/advisor/behavior/recompute",
            headers=headers,
            json={"schema_version": "behavior-profile-recompute-request.v1", "owner_id": OWNER, "calculated_at": NOW.isoformat(), "questionnaire_profile": profile_payload()},
        )
        assert recompute.status_code == 200
        assert recompute.json()["profile"]["display_policy"]["trust_score"] == 20
        lookup = client.get("/api/v1/advisor/behavior/profile", headers=headers)
        assert lookup.status_code == 200
        assert lookup.json()["status"] == "CALCULATED"
        other = client.get("/api/v1/advisor/behavior/profile", headers={"X-Owner-ID": "other"})
        assert other.status_code == 200
        assert other.json() == {
            "schema_version": "behavior-profile-lookup-response.v1",
            "status": "INSUFFICIENT_DATA",
            "profile": None,
        }
        rule_row = store._connection.execute(
            "SELECT config_json FROM behavior_rule_versions WHERE ruleset_version = ?",
            ("behavior-profile-rules.v1",),
        ).fetchone()
        assert rule_row is not None
        assert '"C5":[82,100]' in rule_row[0]


def test_behavior_event_ids_are_scoped_by_owner() -> None:
    store = SQLiteDecisionEventStore(":memory:")
    with TestClient(create_app(store=store, clock=lambda: NOW)) as client:
        first_event = events_payload()[0]
        for owner_id in (OWNER, "second-owner"):
            scoped = {**first_event, "owner_id": owner_id}
            response = client.post(
                "/api/v1/advisor/behavior/events",
                headers={"X-Owner-ID": owner_id},
                json={"owner_id": owner_id, "events": [scoped]},
            )
            assert response.status_code == 200
            assert response.json()["created_count"] == 1


def test_chat_emits_structured_display_policy_without_chain_of_thought() -> None:
    with TestClient(create_app(clock=lambda: NOW)) as client:
        response = client.post(
            "/api/v1/copilot/chat",
            headers={"X-Owner-ID": OWNER},
            json={"message": "分析持仓", "owner_id": OWNER, "stream": True},
        )
        assert response.status_code == 200
        text = response.text
        assert '"type": "analysis_context"' in text
        assert '"mode": "STANDARD"' in text
        assert "analysis_steps" in text
        assert "profile_version" in text
        assert "chain-of-thought" not in text


def test_dev_assist_api_is_owner_scoped_and_never_executes() -> None:
    with TestClient(create_app(clock=lambda: NOW)) as client:
        response = client.post(
            "/api/v1/dev-assist/runs",
            headers={"X-Owner-ID": OWNER},
            json={
                "schema_version": "dev-assist-request.v1",
                "run_id": "dev-api-001",
                "owner_id": OWNER,
                "requested_at": NOW.isoformat(),
                "prd_text": "实现画像接口、权限与验收标准。",
                "technical_text": "使用 FastAPI，包含异常降级和测试。",
                "target_stack": "Python 3.11, FastAPI, Pydantic, vanilla JavaScript",
            },
        )
        assert response.status_code == 200
        assert response.json()["execution_performed"] is False
        forbidden = client.post(
            "/api/v1/dev-assist/runs",
            headers={"X-Owner-ID": "other-owner"},
            json={
                "schema_version": "dev-assist-request.v1",
                "run_id": "dev-api-002",
                "owner_id": OWNER,
                "requested_at": NOW.isoformat(),
                "prd_text": "实现画像。",
                "technical_text": "使用 FastAPI。",
            },
        )
        assert forbidden.status_code == 403
