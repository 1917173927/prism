"""Exercise the portable demo's real snapshot and local HTTP boundary."""
from decimal import Decimal
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

from tools.product_demo import DemoHandler, STATIC


def snapshot():
    text = (STATIC / "demos/product-demo/data.js").read_text(encoding="utf-8")
    return json.loads(text.split("window.PRISM_DEMO_DATA = ", 1)[1].rstrip(";\n"))


def test_demo_snapshot_preserves_currency_weights_and_failure_boundaries():
    data = snapshot()
    assert data["meta"]["synthetic"] is True
    assert data["meta"]["remote_calls"] == 0
    holdings = data["holdings"]
    amount = lambda value: Decimal(value.replace(",", ""))
    total = sum(amount(row["market_value_cny"]) for row in holdings) + amount(data["portfolio"]["cash_cny"])
    assert total == amount(data["portfolio"]["total_cny"])
    for row in holdings:
        assert amount(row["quantity"]) * amount(row["price_cny"]) == amount(row["market_value_cny"])
        assert abs(amount(row["weight_pct"].rstrip("%")) - amount(row["market_value_cny"]) / total * 100) <= Decimal(".005")
    assert abs(sum(item["value"] for item in data["allocation"]) - 100) <= 1e-8
    assert data["trend"][-1]["value"] == float(total)
    assert data["portfolio"]["risk_status"] == "OVERBOUND"
    assert data["algorithms"]["factors"]["status"] == "UNAVAILABLE"
    assert len(data["algorithms"]["factors"]["missing"]) == 4
    matrix = np.array(data["algorithms"]["covariance"]["matrix"])
    assert np.max(np.abs(matrix - matrix.T)) < 1e-10
    assert np.linalg.eigvalsh(matrix).min() >= -1e-10
    assert 0 <= float(data["algorithms"]["covariance"]["shrinkage"]) <= 1
    assert all(0 <= p["value"] <= 1 for p in data["algorithms"]["regime"]["series"])
    assert all(abs(low["value"] * 100 + high["value"] - 100) <= 1e-10 for low, high in zip(data["algorithms"]["regime"]["series"], data["algorithms"]["regime"]["display_series"]))
    for instrument in data["market"]["instruments"].values():
        candles = instrument["candles"]
        assert [p["time"] for p in candles] == sorted({p["time"] for p in candles})
        assert all(p["low"] <= min(p["open"], p["close"]) <= max(p["open"], p["close"]) <= p["high"] for p in candles)
    assert all(row["unit"] == "%" and "%" not in row["value"] for row in data["market"]["metrics"])


def test_demo_build_retains_unavailable_algorithm_reasons_without_zero_substitution(monkeypatch):
    from tools import build_product_demo_data as builder

    monkeypatch.setattr(builder, "regime_probabilities", lambda request: {
        "status": "UNAVAILABLE", "reason": "MODEL_NOT_CONVERGED", "method_version": "gaussian-hmm-2state-ashare.v1",
    })
    monkeypatch.setattr(builder, "constant_correlation_shrinkage", lambda request: {
        "status": "UNAVAILABLE", "reason": "ZERO_VARIANCE_ASSET",
    })
    data = builder.build()
    assert data["algorithms"]["regime"]["reason"] == "MODEL_NOT_CONVERGED"
    assert data["algorithms"]["regime"]["low_probability"] == "不可计算"
    covariance = data["algorithms"]["covariance"]
    assert covariance["reason"] == "ZERO_VARIANCE_ASSET"
    assert covariance["shrinkage"] == "不可计算"
    assert covariance["samples"] == "未提供"
    assert covariance["matrix"] == covariance["matrix_display"] == []


@pytest.fixture
def demo_server():
    with ThreadingHTTPServer(("127.0.0.1", 0), partial(DemoHandler, directory=str(STATIC))) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()


def test_demo_server_serves_entry_and_local_assets_without_api(demo_server):
    for path in ["/", "/demos/product-demo/data.js", "/demos/product-demo/demo.js", "/demos/product-demo/demo.css", "/design-tokens.css", "/lightweight-charts.js"]:
        with urlopen(demo_server + path, timeout=3) as response:
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
            body = response.read()
            assert body
            if path == "/":
                assert b'data-page="overview"' in body
                assert b"Directory listing" not in body


@pytest.mark.parametrize("path", [
    "/pages-snapshot.json", "/api/v1/runtime/data-mode", "/.env",
    "/demos/product-demo/%2E%2E/%2E%2E/pages-snapshot.json",
    "/demos/product-demo/%5C..%5C..%5Cpages-snapshot.json",
])
def test_demo_server_rejects_other_data_and_windows_traversal(demo_server, path):
    for method in ("GET", "HEAD"):
        with pytest.raises(HTTPError) as error:
            urlopen(Request(demo_server + path, method=method), timeout=3)
        assert error.value.code == 404
