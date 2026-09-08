import asyncio
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.providers.fuyao import FuyaoFinanceProvider, FuyaoProviderError
from app.runtime.mode import RuntimeModeController


def test_failed_probe_keeps_error_code_and_can_recover(monkeypatch):
    monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "test-key")
    controller = RuntimeModeController()
    monkeypatch.setattr("app.api.main.get_runtime_mode_controller", lambda: controller)
    provider = FuyaoFinanceProvider(api_key="test-key")
    provider.get_quote = AsyncMock(side_effect=[FuyaoProviderError("UPSTREAM_TIMEOUT", "safe"), {"price_cny": 1}])
    provider.get_fund_lookthrough = AsyncMock(side_effect=[FuyaoProviderError("FUYAO_2001", "safe"), {"holdings": []}])
    with TestClient(create_app(live_finance_provider=provider)) as client:
        first = client.get("/api/v1/runtime/data-mode").json()["data"]
        assert first["data_mode"] == "MOCK"
        assert first["live_capability_status"]["stock_quote"]["last_error_code"] == "UPSTREAM_TIMEOUT"
        assert first["live_capability_status"]["fund_lookthrough"]["last_error_code"] == "FUYAO_2001"
        second = client.put("/api/v1/runtime/data-mode", json={"target_mode":"LIVE", "expected_revision":first["revision"]})
        assert second.status_code == 200
        assert second.json()["data"]["data_mode"] == "LIVE"
        assert second.json()["data"]["live_capability_status"]["stock_quote"]["last_error_code"] is None
