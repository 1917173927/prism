"""Verify retained historical market inputs without any new provider request."""
from decimal import Decimal
from datetime import datetime
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import statistics
import time

from app.market_research import research_metrics
from app.service.research_algorithms import RegimeInput, regime_probabilities


def chart_api_latency(market, captured_at):
    from fastapi.testclient import TestClient
    from app.api.main import create_app

    class Unavailable:
        is_configured = False

    class RetainedMarket:
        async def get_index_quote(self, symbol):
            return {"symbol": market["symbol"], "source": market["source"], "observed_at": market["observed_at"]}

        async def get_index_history(self, *args, **kwargs):
            return market["bars"]

    application = create_app(auth_enabled=False, clock=lambda: datetime.fromisoformat(captured_at.replace("Z", "+00:00")),
        market_provider=RetainedMarket(), live_finance_provider=Unavailable(),
        yahoo_finance_provider=Unavailable(), etnet_provider=Unavailable())
    times = []
    try:
        # No lifespan: this focused retained-input read never starts a crawler.
        client = TestClient(application)
        for _ in range(30):
            began = time.perf_counter()
            response = client.get("/api/v1/market/analysis/CN/sse-composite?interval=1d", headers={"X-Owner-ID": "retained-input-benchmark"})
            if response.status_code != 200 or response.json()["status"] != "CALCULATED":
                raise RuntimeError("retained-input API validation failed")
            times.append((time.perf_counter()-began)*1000)
        client.close()
    finally:
        asyncio.run(application.state.knowledge_crawler.close())
        application.state.knowledge_service.store.close()
    return {"sample_count": 30, "p50": statistics.median(times), "p95": sorted(times)[28],
            "scope": "REAL_ROUTE_ASGI_WITH_RETAINED_HISTORY_PROVIDER_NO_NETWORK_NOT_CURRENT_LIVE"}


def main():
    snapshot_path = Path("app/api/static/pages-snapshot.json")
    raw = snapshot_path.read_bytes()
    snapshot = json.loads(raw)
    key = "GET /api/v1/market/analysis/CN/sse-composite?interval=1d"
    market = json.loads(snapshot["routes"][key]["body"])
    bars = market["bars"]
    returns = [{"time": bars[i]["time"], "value": float(Decimal(bars[i]["close"])/Decimal(bars[i-1]["close"])-1)}
               for i in range(1, len(bars))]
    source = f"Retained historical API snapshot: {market['source']}"
    request = RegimeInput(source=source, as_of=snapshot["captured_at"], returns=returns)
    result = regime_probabilities(request)
    times = []
    for _ in range(30):
        began = time.perf_counter()
        metrics = research_metrics(bars, source=source, subject=market["symbol"])
        json.dumps({key: metric.model_dump(mode="json") for key, metric in metrics.items()})
        times.append((time.perf_counter()-began)*1000)
    report = {"schema_version": "research-retained-history-verification.v1",
        "input_kind": "PUBLIC_ARCHIVED_MARKET_API_RESPONSE", "snapshot_file_sha256": sha256(raw).hexdigest(),
        "captured_at": snapshot["captured_at"], "market_source": market["source"],
        "fresh_live_request_performed": False, "source_independently_reverified": False,
        "sample_count": len(returns), "input_start": bars[0]["time"], "input_end": bars[-1]["time"],
        "return_method": "DAILY_PRICE_INDEX_CLOSE_RATIO_MINUS_ONE_NOT_TOTAL_RETURN",
        "regime": result, "probability_sum_max_error": max((abs(row["low_variance"]+row["high_variance"]-1)
             for row in result.get("series", [])), default=None),
        "retained_chart_calculation_latency_ms": {"sample_count": 30, "p50": statistics.median(times),
             "p95": sorted(times)[28], "scope": "DETERMINISTIC_METRICS_AND_JSON_SERIALIZATION_NOT_HTTP_OR_UPSTREAM"},
        "retained_chart_api_latency_ms": chart_api_latency(market, snapshot["captured_at"]),
        "covariance": {"status": "UNAVAILABLE", "reason": "ONLY_ONE_RETAINED_ASSET"},
        "five_factors": {"status": "UNAVAILABLE", "missing_fields": ["historical_constituents", "adjusted_asset_returns",
             "fundamentals_and_publication_times", "risk_free_returns"]},
        "notice": "真实历史输入的计算复验，不证明当前行情、全市场覆盖或供应商配额。"}
    destination = Path("docs/submission/test-evidence/research-retained-history-20261001.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(destination), "sample_count": len(returns), "regime_status": result["status"],
                      "reason": result.get("reason"), "probability_sum_max_error": report["probability_sum_max_error"]}))


if __name__ == "__main__":
    main()
