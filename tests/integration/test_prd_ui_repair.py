import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.portfolio.summary import portfolio_summary
from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from decimal import Decimal
from app.providers.fuyao import FuyaoFinanceProvider
from app.providers.live_market import TencentMarketProvider


def test_summary_does_not_invent_missing_cost_or_previous_close():
    data = {"cash_cny": 50, "positions": [{"quantity": 10, "price": 11, "cost_price": 10, "previous_close": 10}]}
    result = portfolio_summary(data)
    assert result["holdings_value_cny"] == "110.00"
    assert result["total_value_cny"] == "160.00"
    assert result["daily_pnl_cny"] == "10.00"
    assert result["pnl_cny"] == "10.00"
    assert result["allocation"][-1] == {"label": "现金", "weight": "31.25"}
    data["positions"].append({"quantity": 1, "price": 20})
    result = portfolio_summary(data)
    assert result["pnl_cny"] is None
    assert result["daily_pnl_cny"] is None


def test_confirmed_equity_outside_demo_catalogue_stays_unclassified():
    result = recalculate_portfolio_values([{"asset_id": "000001.SZ", "name": "平安银行", "quantity": 100, "price": 12, "cost_price": 10, "sector": "Invented"}], Decimal(0), "owner")
    assert result["positions"][0]["market_value_cny"] == 1200
    assert result["portfolio"]["position_snapshot"]["positions"][0]["sector"] == "Unclassified"


def test_model_settings_are_owner_scoped_and_not_disclosed(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "models.db")) as client:
        a, b = {"X-Owner-ID": "a"}, {"X-Owner-ID": "b"}
        before = client.get("/api/v1/user/model-settings", headers=b).json()
        cfg = {"api_key": "private-test-key", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1"}
        saved = client.put("/api/v1/user/model-settings", headers=a, json=cfg)
        assert saved.status_code == 200
        assert "private-test-key" not in saved.text
        assert saved.json()["scope"] == "USER"
        assert client.get("/api/v1/user/model-settings", headers=b).json() == before
        bad = client.put("/api/v1/user/model-settings", headers=a, json={**cfg, "base_url": "http://127.0.0.1:8080"})
        assert bad.status_code == 422
        malformed = client.put("/api/v1/user/model-settings", headers=a, json={**cfg, "base_url": "https://api.deepseek.com:invalid"})
        assert malformed.status_code == 422
        mock = client.post("/api/v1/copilot/chat", headers=a, json={"owner_id": "a", "message": "测试", "model_mode": "MOCK"})
        assert mock.status_code == 200
        assert "演示回复" in mock.text and "[DONE]" in mock.text
        assert "本轮未绑定已锁定的画像与持仓前提" in mock.text
        assert "private-test-key" not in mock.text


def test_auto_chat_refuses_implicit_mock_without_model(monkeypatch, tmp_path):
    from app.llm.client import AsyncLLMClient

    monkeypatch.setattr(AsyncLLMClient, "is_configured", property(lambda _: False))
    with TestClient(create_app(database_path=tmp_path / "no-implicit-mock.db")) as client:
        response = client.post("/api/v1/copilot/chat", json={"message": "测试", "model_mode": "AUTO"})
        assert response.status_code == 409
        assert response.json()["error_code"] == "MODEL_NOT_CONFIGURED"


def test_live_model_mode_requires_live_tool_data(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.runtime.mode import DataMode

    monkeypatch.setattr("app.api.main.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.MOCK))
    with TestClient(create_app(database_path=tmp_path / "live-model-with-mock-data.db")) as client:
        response = client.post("/api/v1/copilot/chat", json={
            "message": "测试",
            "model_mode": "LIVE",
            "llm_config": {"api_key": "test", "base_url": "https://api.deepseek.com/v1", "model": "test"},
        })
        assert response.status_code == 409
        assert response.json()["error_code"] == "DATA_MODE_NOT_LIVE"
        auto_response = client.post("/api/v1/copilot/chat", json={
            "message": "测试",
            "model_mode": "AUTO",
            "llm_config": {"api_key": "test", "base_url": "https://api.deepseek.com/v1", "model": "test"},
        })
        assert auto_response.status_code == 409
        assert auto_response.json()["error_code"] == "DATA_MODE_NOT_LIVE"


def test_unlocked_chat_strips_unverified_personal_context(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.api import main as api_main
    from app.runtime.mode import DataMode

    captured = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        yield {"type": "token", "delta": "一般回答"}

    class FakeCopilotAgent:
        def __init__(self, **kwargs):
            from app.llm.client import LLMConfig
            self.client = SimpleNamespace(is_configured=False, config=LLMConfig())

        stream_chat = staticmethod(fake_stream_chat)

    monkeypatch.setattr(api_main, "get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    monkeypatch.setattr(api_main, "CopilotAgent", FakeCopilotAgent)
    with TestClient(create_app(database_path=tmp_path / "unlocked-chat.db")) as client:
        response = client.post("/api/v1/copilot/chat", json={
            "message": "什么是市盈率",
            "model_mode": "LIVE",
            "llm_config": {"api_key": "test", "base_url": "https://api.deepseek.com/v1", "model": "test"},
            "profile_version": 99,
            "behavior_profile_version": 98,
            "portfolio_snapshot_id": "stale-snapshot",
            "persona_info": {"name": "伪造画像", "tag": "R5", "max_drawdown": 99},
            "portfolio_context": {"fabricated_holdings": "OLD_POSITION"},
            "history": [{"role": "assistant", "content": "旧持仓结论"}],
        })

    assert response.status_code == 200
    assert "一般回答" in response.text
    assert captured["persona_info"] is None
    assert captured["portfolio_context"] is None
    assert captured["history"] == []


def test_dynamic_quick_tags_keep_direct_live_intent_route():
    app_js = (Path(__file__).parents[2] / "app" / "api" / "static" / "app.js").read_text(encoding="utf-8")
    block = app_js[app_js.index("function renderQuickTags"):app_js.index("function handleCopilotIntent")]
    assert "handleCopilotIntent(t.intent, t.target)" in block
    assert "handleStreamingChat(t.label)" not in block
    intent_block = app_js[app_js.index("function handleCopilotIntent"):app_js.index("function buildCopilotLoadingCard")]
    assert "runCopilotStockResearch(target)" in intent_block
    assert "async function runCopilotStockResearch()" in app_js


def test_delete_last_position_and_restore_empty_portfolio(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "holdings.db")) as client:
        headers = {"X-Owner-ID": "a"}
        url = "/api/v1/advisor/portfolio/current"
        payload = {"owner_id": "a", "cash_cny": 0, "positions": [{"asset_id": "600519.SH", "quantity": 10, "price": 1000, "cost_price": 900}]}
        assert client.put(url, headers=headers, json=payload).status_code == 200
        assert client.get("/").headers["cache-control"] == "no-cache"
        mode = client.get("/api/v1/advisor/portfolio/summary", headers=headers).json()["data_mode"]
        wrong_mode = "LIVE" if mode == "MOCK" else "MOCK"
        assert client.put(url, headers=headers, json={**payload, "data_mode": wrong_mode}).status_code == 409
        summary = client.get("/api/v1/advisor/portfolio/summary", headers=headers).json()
        assert summary["pnl_cny"] == "1000.00"
        assert client.put(url, headers={"X-Owner-ID": "b"}, json=payload).status_code == 403
        assert client.put(url, headers=headers, json={**payload, "positions": []}).status_code == 200
        assert client.get(url, headers=headers).json()["data"] is None
        assert client.get("/api/v1/advisor/portfolio/summary", headers=headers).json()["position_count"] == 0


def test_index_quote_uses_shanghai_and_keeps_equity_quote_separate():
    requests = []
    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200, content=b'v="";')
    provider = TencentMarketProvider(transport=httpx.MockTransport(respond))
    asyncio.run(provider.get_index_quote("000001.SH"))
    asyncio.run(provider.get_quote("000001"))
    assert requests[0].endswith("q=sh000001")
    assert requests[1].endswith("q=sz000001")


def test_tencent_index_history_returns_validated_daily_ohlc():
    requested_params = []

    def respond(request):
        requested_params.append(request.url.params["param"])
        return httpx.Response(200, json={"data": {"sz399006": {"day": [
            ["2026-09-11", "3010.00", "3040.00", "3055.00", "2998.00", "1000"],
            ["2026-09-14", "3042.00", "3025.00", "3050.00", "3012.00", "1200"],
        ]}}})

    provider = TencentMarketProvider(transport=httpx.MockTransport(respond))
    bars = asyncio.run(provider.get_index_history("399006.SZ"))
    assert requested_params == ["sz399006,day,,,90,qfq"]
    assert bars == [
        {"time": "2026-09-11", "open": 3010.0, "high": 3055.0, "low": 2998.0, "close": 3040.0, "volume": 1000.0, "turnover": None},
        {"time": "2026-09-14", "open": 3042.0, "high": 3050.0, "low": 3012.0, "close": 3025.0, "volume": 1200.0, "turnover": None},
    ]


def test_fuyao_index_does_not_compare_equity_ticker_and_checks_ohlc():
    def respond(request):
        if request.url.path.endswith("snapshot"):
            return httpx.Response(200, json={"code": 0, "data": {"timestamp": 1789378524000, "item": [{"thscode": "000001.SH", "ticker": "1A0001", "last_price": 3885.33, "price_change_ratio_pct": -0.0715}]}})
        return httpx.Response(200, json={"code": 0, "data": {"item": [{"date_ms": 1789315200000, "open_price": 10, "close_price": 11, "high_price": 12, "low_price": 9}]}})
    provider = FuyaoFinanceProvider(api_key="test", transport=httpx.MockTransport(respond))
    quote = asyncio.run(provider.get_index_quote("000001.SH"))
    assert quote["symbol"] == "000001.SH" and quote["price_cny"] == 3885.33
    bars = asyncio.run(provider.get_index_history("000001.SH"))
    assert bars[0]["close"] == 11
