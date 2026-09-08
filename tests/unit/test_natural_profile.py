import asyncio
from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pytest

from app.service.natural_profile import NaturalProfileRequest, NaturalProfileError, extract_natural_profile


def extract(text, client=None):
    return asyncio.run(extract_natural_profile(NaturalProfileRequest(owner_id="owner", text=text),
        client or SimpleNamespace(is_configured=False), datetime.now(UTC)))


def test_offline_subset_preserves_numeric_quote_and_requires_confirmation():
    result = extract("长期投资，没有短期用钱需求，最多接受亏损15%。")
    assert result["extraction"]["max_drawdown_tolerance_pct"] == "15"
    assert result["extraction"]["investment_horizon"] == "LONG"
    assert result["profile_changed"] is False
    assert result["status"] == "REQUIRES_CONFIRMATION"
    assert result["method"] == "LIMITED_LITERAL_MATCHING"
    assert all(item["quote"] in "长期投资，没有短期用钱需求，最多接受亏损15%。" for item in result["evidence"])


def test_negation_and_conflicts_do_not_become_unqualified_preferences():
    result = extract("我不追求高收益，也不是投资经验丰富。长期投资，短期投资。")
    assert result["status"] == "NEEDS_MORE_INPUT"
    assert result["extraction"]["investment_horizon"] is None
    assert result["extraction"]["return_expectation"] is None
    assert any("矛盾" in warning for warning in result["warnings"])
    assert extract("长期投资不是我的目标。朋友追求高收益。最大回撤15%并不是我的底线。")["status"] == "NEEDS_MORE_INPUT"


class Model:
    is_configured = True
    def __init__(self, fields): self.fields = fields
    async def stream_chat(self, messages):
        yield {"type":"content", "delta":json.dumps({"fields":self.fields})}


def test_model_slots_must_have_exact_source_and_valid_percent():
    base = {"field":"max_drawdown_tolerance_pct", "value":"15", "quote":"最大回撤15%", "confidence":.7}
    assert extract("最大回撤15%", Model([base]))["extraction"]["confidence"] == "0.7"
    for change in [{"quote":"虚构原文15%"}, {"value":"99"}, {"value":"not-number"}]:
        with pytest.raises(NaturalProfileError):
            extract("最大回撤15%", Model([{**base, **change}]))


def test_credentials_are_refused_before_model_call():
    with pytest.raises(NaturalProfileError):
        extract("我的 API_KEY 是 test")


def test_api_owner_scope_and_no_implicit_profile_persistence(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import create_app
    from app.llm.client import AsyncLLMClient
    monkeypatch.setattr(AsyncLLMClient, "is_configured", property(lambda _: False))
    with TestClient(create_app()) as client:
        headers = {"X-Owner-ID":"owner"}
        assert client.post("/api/v1/advisor/profile-extractions", headers=headers,
            json={"owner_id":"other", "text":"长期投资"}).status_code == 403
        result = client.post("/api/v1/advisor/profile-extractions", headers=headers,
            json={"owner_id":"owner", "text":"长期投资"})
        assert result.status_code == 200
        assert result.json()["profile_changed"] is False
