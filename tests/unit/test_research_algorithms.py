from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from app.service.research_algorithms import (
    CovarianceInput, FiveFactorInput, RegimeInput,
    constant_correlation_shrinkage, five_factors, regime_probabilities,
)

BASE = {"source": "independent numerical benchmark", "as_of": datetime(2026, 10, 1, tzinfo=UTC)}


def points(values):
    return [{"time": date(2024, 1, 1)+timedelta(days=i), "value": float(value)} for i, value in enumerate(values)]


def test_covariance_matches_appendix_scalar_reference():
    rng = np.random.default_rng(12)
    x = rng.normal(size=(80, 4))*[.01, .02, .03, .025]
    request = CovarianceInput(**BASE, series={str(j): points(x[:, j]) for j in range(4)})
    actual = constant_correlation_shrinkage(request)
    x -= x.mean(axis=0)
    sample = np.array([[sum(row[i]*row[j] for row in x)/80 for j in range(4)] for i in range(4)])
    sigma = np.sqrt(sample.diagonal())
    rbar = sum(sample[i,j]/(sigma[i]*sigma[j]) for i in range(4) for j in range(4) if i != j)/12
    target = sample.copy()
    for i in range(4):
        for j in range(4):
            if i != j:
                target[i,j] = rbar*sigma[i]*sigma[j]
    pi = sum(sum((row[i]*row[j]-sample[i,j])**2 for row in x)/80 for i in range(4) for j in range(4))
    rho = sum(sum((row[i]**2-sample[i,i])**2 for row in x)/80 for i in range(4))
    for i in range(4):
        for j in range(4):
            if i != j:
                theta_i = sum((row[i]**2-sample[i,i])*(row[i]*row[j]-sample[i,j]) for row in x)/80
                theta_j = sum((row[j]**2-sample[j,j])*(row[i]*row[j]-sample[i,j]) for row in x)/80
                rho += rbar/2*(sigma[j]/sigma[i]*theta_i+sigma[i]/sigma[j]*theta_j)
    delta = np.clip((pi-rho)/(np.sum((target-sample)**2)*80), 0, 1)
    assert actual["status"] == "CALCULATED"
    assert actual["shrinkage"] == pytest.approx(delta, abs=1e-12)
    assert np.allclose(actual["covariance"], delta*target+(1-delta)*sample, atol=1e-12)
    assert actual["minimum_eigenvalue"] >= -1e-10


def test_covariance_missing_alignment_and_degenerate():
    series = {"a": points([.01]*65), "b": points([.02]*65)}
    assert constant_correlation_shrinkage(CovarianceInput(**BASE, series=series))["reason"] == "ZERO_VARIANCE_ASSET"
    series["a"] = series["a"][:59]
    assert constant_correlation_shrinkage(CovarianceInput(**BASE, series=series))["reason"] == "INSUFFICIENT_ALIGNED_RETURNS"
    with pytest.raises(ValidationError):
        CovarianceInput(**BASE, series={"a": points([float("nan")])})


def factor_request():
    # Independent six portfolios, duplicated characteristics in small/big groups.
    annual, returns = [], []
    for size in (1, 2):
        for characteristic, ret in ((1, .01), (2, .02), (3, .03)):
            identity = f"{size}-{characteristic}"
            annual.append({"security_id": identity, "formation_year": 2025, "fiscal_year": 2024,
                "published_at": "2025-04-01T00:00:00Z", "market_cap_december": 100,
                "market_cap_june": size*100, "book_equity": characteristic*100,
                "revenue": characteristic**2*100, "cost_of_goods_sold": 0,
                "selling_general_administrative": 0, "interest_expense": 0,
                "total_assets": characteristic*100, "prior_total_assets": 100})
            returns.append({"security_id": identity, "total_return": ret+(size-1)*.03, "beginning_market_cap": size*100})
    return {**BASE, "fundamentals": annual, "months": [{"month": "2025-07", "risk_free_return": .001, "securities": returns}], "universe_id": "six benchmark stocks"}


def test_factor_independent_six_portfolio_benchmark():
    actual = five_factors(FiveFactorInput(**factor_request()))
    assert actual["status"] == "CALCULATED"
    row = actual["series"][0]
    assert row["MKT_RF"] == pytest.approx(.039, abs=1e-12)
    assert row["SMB"] == pytest.approx(-.03, abs=1e-12)
    assert row["HML"] == pytest.approx(.02, abs=1e-12)
    assert row["RMW"] == pytest.approx(.02, abs=1e-12)
    assert row["CMA"] == pytest.approx(-.02, abs=1e-12)
    assert actual["scope"] == "INPUT_UNIVERSE"


@pytest.mark.parametrize("change,reason", [("publication", "FINANCIAL_POINT_IN_TIME_INVALID"), ("rf", "RISK_FREE_RETURN_MISSING"), ("return", "FORMATION_MEMBER_RETURN_MISSING"), ("field", "FUNDAMENTAL_FIELDS_MISSING")])
def test_factor_fail_closed(change, reason):
    body = factor_request()
    if change == "publication": body["fundamentals"][0]["published_at"] = "2025-07-01T00:00:00Z"
    if change == "rf": body["months"][0]["risk_free_return"] = None
    if change == "return": body["months"][0]["securities"].pop()
    if change == "field": body["fundamentals"][0]["interest_expense"] = None
    assert five_factors(FiveFactorInput(**body))["reason"] == reason


def test_hmm_short_constant_and_forward_filter():
    assert regime_probabilities(RegimeInput(**BASE, returns=points([.01]*10)))["reason"] == "INSUFFICIENT_RETURNS"
    assert regime_probabilities(RegimeInput(**BASE, returns=points([.01]*252)))["reason"] == "DEGENERATE_TRAINING_RETURNS"
    pytest.importorskip("hmmlearn")
    rng = np.random.default_rng(3)
    values = np.r_[rng.normal(0, .004, 140), rng.normal(0, .03, 160)]
    first = regime_probabilities(RegimeInput(**BASE, returns=points(values[:280])))
    extended = regime_probabilities(RegimeInput(**BASE, returns=points(values)))
    assert first["status"] == "CALCULATED"
    assert first["series"] == extended["series"][:len(first["series"])]
    assert first["series"][0]["time"] == points(values)[251]["time"].isoformat()
    assert all(abs(row["low_variance"]+row["high_variance"]-1) <= 1e-10 for row in first["series"])
    assert first["state_variances"][0] <= first["state_variances"][1]
