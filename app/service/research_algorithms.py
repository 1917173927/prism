"""Paper-based deterministic estimators, with explicit point-in-time inputs.

The HMM and factor construction are A-share adaptations, not a reproduction of
the papers' portfolio allocation experiments. Returns use decimal fractions.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from hashlib import sha256
import json
import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AlgorithmInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: str = Field(min_length=1, max_length=500)
    as_of: datetime

    @model_validator(mode="after")
    def timestamp(self):
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of requires a timezone")
        return self


class ReturnPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    time: date
    value: float


class RegimeInput(AlgorithmInput):
    returns: list[ReturnPoint] = Field(max_length=5000)
    training_size: int = Field(default=252, ge=252, le=2520)


class CovarianceInput(AlgorithmInput):
    series: dict[str, list[ReturnPoint]] = Field(max_length=100)

    @model_validator(mode="after")
    def bounded_series(self):
        if any(len(points) > 5000 for points in self.series.values()):
            raise ValueError("at most 5000 returns per asset")
        return self


class AnnualFundamental(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    security_id: str = Field(min_length=1)
    formation_year: int = Field(ge=1991, le=2200)
    fiscal_year: int
    published_at: datetime
    market_cap_december: float | None = None
    market_cap_june: float | None = None
    book_equity: float | None = None
    revenue: float | None = None
    cost_of_goods_sold: float | None = None
    selling_general_administrative: float | None = None
    interest_expense: float | None = None
    total_assets: float | None = None
    prior_total_assets: float | None = None

    @model_validator(mode="after")
    def timestamp(self):
        if self.published_at.tzinfo is None:
            raise ValueError("publication time requires timezone")
        return self


class MonthlySecurityReturn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    security_id: str = Field(min_length=1)
    total_return: float = Field(ge=-1)
    beginning_market_cap: float = Field(gt=0)


class FactorMonth(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    risk_free_return: float | None = None
    securities: list[MonthlySecurityReturn] = Field(max_length=10000)


class FiveFactorInput(AlgorithmInput):
    fundamentals: list[AnnualFundamental] = Field(max_length=50000)
    months: list[FactorMonth] = Field(max_length=600)
    universe_id: str = Field(min_length=1, max_length=200)
    universe_complete: bool = False


def _result(request, method, *, reason=None, **values):
    encoded = request.model_dump(mode="json")
    return {"status": "UNAVAILABLE" if reason else "CALCULATED", "reason": reason,
            "method_version": method, "source": request.source, "as_of": request.as_of.isoformat(),
            "input_snapshot_id": sha256(json.dumps(encoded, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "return_unit": "DECIMAL_FRACTION", "notice": "仅供研究参考，不构成投资建议。", **values}


def _returns(points, cutoff):
    times = [point.time for point in points]
    if times != sorted(set(times)):
        raise ValueError("return dates must be unique and sorted")
    if any(point.time > cutoff for point in points):
        raise ValueError("future returns are ineligible")
    if any(not math.isfinite(point.value) for point in points):
        raise ValueError("returns must be finite")
    return np.array([point.value for point in points], dtype=float)


def regime_probabilities(request: RegimeInput):
    request = RegimeInput.model_validate(request.model_dump())
    values = _returns(request.returns, request.as_of.date())
    if len(values) < request.training_size:
        return _result(request, "gaussian-hmm-2state-ashare.v1", reason="INSUFFICIENT_RETURNS", required=request.training_size)
    train = values[:request.training_size]
    scale = float(np.std(train))
    if scale <= 1e-12:
        return _result(request, "gaussian-hmm-2state-ashare.v1", reason="DEGENERATE_TRAINING_RETURNS")
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        return _result(request, "gaussian-hmm-2state-ashare.v1", reason="RESEARCH_DEPENDENCY_UNAVAILABLE")
    location = float(train.mean())
    standardized = (values-location)/scale
    fitted = []
    for seed in (0, 1, 2):
        model = GaussianHMM(n_components=2, covariance_type="diag", random_state=seed,
                            n_iter=500, tol=1e-6, min_covar=1e-6)
        try:
            model.fit(standardized[:request.training_size, None])
        except (ValueError, FloatingPointError):
            continue
        history = list(model.monitor_.history)
        if len(history) < 2 or abs(history[-1]-history[-2]) > 1e-6:
            continue
        likelihood = float(model.score(standardized[:request.training_size, None]))
        if math.isfinite(likelihood):
            fitted.append((likelihood, seed, model))
    if not fitted:
        return _result(request, "gaussian-hmm-2state-ashare.v1", reason="MODEL_NOT_CONVERGED")
    likelihood, seed, model = max(fitted, key=lambda item: (item[0], -item[1]))
    variances = np.asarray(model.covars_).reshape(2)
    if np.any(variances <= 0) or not np.isfinite(variances).all():
        return _result(request, "gaussian-hmm-2state-ashare.v1", reason="DEGENERATE_FITTED_STATES")
    means = model.means_.reshape(2)
    order = np.argsort(variances, kind="stable")
    # Forward-only filtering. predict_proba uses smoothing and future observations.
    probability = np.array(model.startprob_, dtype=float)
    series = []
    for index, value in enumerate(standardized):
        if index:
            probability = probability @ model.transmat_
        log_emission = -0.5*(np.log(2*np.pi*variances)+(value-means)**2/variances)
        posterior = probability*np.exp(log_emission-log_emission.max())
        denominator = posterior.sum()
        if denominator <= 0 or not math.isfinite(float(denominator)):
            return _result(request, "gaussian-hmm-2state-ashare.v1", reason="NUMERICAL_FILTER_FAILURE")
        probability = posterior/denominator
        # Parameters become available at the end of the fixed training window.
        # Earlier fitted probabilities are never represented as historical signals.
        if index >= request.training_size-1:
            series.append({"time": request.returns[index].time.isoformat(),
                           "low_variance": float(probability[order[0]]),
                           "high_variance": float(probability[order[1]])})
    return _result(request, "gaussian-hmm-2state-ashare.v1", series=series,
        training_start=request.returns[0].time.isoformat(),
        training_end=request.returns[request.training_size-1].time.isoformat(),
        sample_count=len(values), training_size=request.training_size, selected_seed=seed,
        training_log_likelihood=likelihood, state_variances=(variances[order]*scale**2).tolist(),
        transition_matrix=model.transmat_[np.ix_(order, order)].tolist(),
        out_of_sample_count=len(values)-request.training_size,
        interpretation="A股日频两状态波动模型；状态按条件方差排序，不直接代表牛熊或买卖指令。")


def constant_correlation_shrinkage(request: CovarianceInput):
    request = CovarianceInput.model_validate(request.model_dump())
    names = sorted(request.series)
    if len(names) < 2:
        return _result(request, "ledoit-wolf-constant-correlation.v1", reason="INSUFFICIENT_ASSETS")
    maps = {}
    for name in names:
        _returns(request.series[name], request.as_of.date())
        maps[name] = {point.time: point.value for point in request.series[name]}
    dates = sorted(set.intersection(*(set(row) for row in maps.values())))
    if len(dates) < 60:
        return _result(request, "ledoit-wolf-constant-correlation.v1", reason="INSUFFICIENT_ALIGNED_RETURNS", sample_count=len(dates))
    x = np.array([[maps[name][day] for name in names] for day in dates])
    x -= x.mean(axis=0)
    count, dimensions = x.shape
    sample = x.T @ x/count
    variances = np.diag(sample)
    if np.any(variances <= 1e-20):
        return _result(request, "ledoit-wolf-constant-correlation.v1", reason="ZERO_VARIANCE_ASSET")
    deviation = np.sqrt(variances)
    correlation = sample/np.outer(deviation, deviation)
    average = float((correlation.sum()-dimensions)/(dimensions*(dimensions-1)))
    target = average*np.outer(deviation, deviation)
    np.fill_diagonal(target, variances)
    # Appendix B: fourth-moment pi and delta-method rho, covariance uses 1/T.
    squares = x**2
    pi_matrix = squares.T @ squares/count-sample**2
    theta = (x**3).T @ x/count-variances[:, None]*sample
    rho = float(np.trace(pi_matrix))
    for i in range(dimensions):
        for j in range(dimensions):
            if i != j:
                rho += average/2*(deviation[j]/deviation[i]*theta[i, j]
                                 + deviation[i]/deviation[j]*theta[j, i])
    gamma = float(np.sum((target-sample)**2))
    intensity = float(np.clip((pi_matrix.sum()-rho)/(gamma*count), 0, 1)) if gamma > 1e-30 else 1.0
    estimate = intensity*target+(1-intensity)*sample
    eigenvalues = np.linalg.eigvalsh(estimate)
    if eigenvalues.min() < -1e-10:
        return _result(request, "ledoit-wolf-constant-correlation.v1", reason="NON_PSD_ESTIMATE")
    return _result(request, "ledoit-wolf-constant-correlation.v1", assets=names, sample_count=count,
        input_start=dates[0].isoformat(), input_end=dates[-1].isoformat(), shrinkage=intensity,
        average_correlation=average, covariance=estimate.tolist(), sample_covariance=sample.tolist(),
        target_covariance=target.tolist(), correlation=(estimate/np.sqrt(np.outer(np.diag(estimate), np.diag(estimate)))).tolist(),
        minimum_eigenvalue=float(eigenvalues.min()), covariance_unit="DECIMAL_RETURN_SQUARED", target="CONSTANT_CORRELATION")


def five_factors(request: FiveFactorInput):
    request = FiveFactorInput.model_validate(request.model_dump())
    method = "fama-french-5-ashare-2x3.v1"
    months = [row.month for row in request.months]
    if not months or months != sorted(set(months)):
        return _result(request, method, reason="MONTHS_MUST_BE_NONEMPTY_SORTED_UNIQUE")
    annual = {}
    for row in request.fundamentals:
        key = (row.formation_year, row.security_id)
        if key in annual:
            return _result(request, method, reason="DUPLICATE_ANNUAL_RECORD")
        annual[key] = row
    output = []
    formations = {}
    for month in request.months:
        year, number = map(int, month.month.split("-"))
        month_end = date(year, number, calendar.monthrange(year, number)[1])
        if month_end > request.as_of.date():
            return _result(request, method, reason="FUTURE_MONTH_RETURN")
        if month.risk_free_return is None:
            return _result(request, method, reason="RISK_FREE_RETURN_MISSING", month=month.month)
        formation = year if number >= 7 else year-1
        if formation not in formations:
            entries = [row for (y, _), row in annual.items() if y == formation]
            eligible = []
            cutoff = date(formation, 6, 30)
            for row in entries:
                if row.fiscal_year != formation-1 or row.published_at.date() > cutoff or row.published_at > request.as_of:
                    return _result(request, method, reason="FINANCIAL_POINT_IN_TIME_INVALID", security_id=row.security_id)
                required = ("market_cap_december", "market_cap_june", "book_equity", "revenue", "cost_of_goods_sold",
                            "selling_general_administrative", "interest_expense", "total_assets", "prior_total_assets")
                missing = [key for key in required if getattr(row, key) is None]
                if missing:
                    return _result(request, method, reason="FUNDAMENTAL_FIELDS_MISSING", security_id=row.security_id, missing_fields=missing)
                if row.market_cap_december <= 0 or row.market_cap_june <= 0 or row.total_assets <= 0 or row.prior_total_assets <= 0:
                    return _result(request, method, reason="NONPOSITIVE_CAP_OR_ASSETS", security_id=row.security_id)
                if row.book_equity <= 0:
                    continue  # Explicit method exclusion, not a missing-value fill.
                eligible.append({"security_id": row.security_id, "size": row.market_cap_june,
                    "bm": row.book_equity/row.market_cap_december,
                    "op": (row.revenue-row.cost_of_goods_sold-row.selling_general_administrative-row.interest_expense)/row.book_equity,
                    "inv": (row.total_assets-row.prior_total_assets)/row.prior_total_assets})
            if len(eligible) < 6:
                return _result(request, method, reason="INSUFFICIENT_FORMATION_UNIVERSE", formation_year=formation)
            size_cut = float(np.quantile([row["size"] for row in eligible], .5, method="linear"))
            groups = {}
            for feature in ("bm", "op", "inv"):
                low, high = np.quantile([row[feature] for row in eligible], [.3, .7], method="linear")
                groups[feature] = {key: [] for key in ("SL", "SN", "SH", "BL", "BN", "BH")}
                for row in eligible:
                    size = "S" if row["size"] <= size_cut else "B"
                    bucket = "L" if row[feature] <= low else "H" if row[feature] > high else "N"
                    groups[feature][size+bucket].append(row["security_id"])
                if any(not members for members in groups[feature].values()):
                    return _result(request, method, reason="EMPTY_2X3_PORTFOLIO", feature=feature, formation_year=formation)
            formations[formation] = groups
        monthly = {row.security_id: row for row in month.securities}
        if len(monthly) != len(month.securities) or not monthly:
            return _result(request, method, reason="MONTHLY_UNIVERSE_INVALID")
        portfolios = {}
        for feature, groups in formations[formation].items():
            values = {}
            for key, members in groups.items():
                if any(name not in monthly for name in members):
                    return _result(request, method, reason="FORMATION_MEMBER_RETURN_MISSING", month=month.month, feature=feature)
                weight = sum(monthly[name].beginning_market_cap for name in members)
                values[key] = sum(monthly[name].beginning_market_cap*monthly[name].total_return for name in members)/weight
            portfolios[feature] = values
        smb = sum((sum(values[key] for key in ("SL", "SN", "SH"))-sum(values[key] for key in ("BL", "BN", "BH")))/3
                  for values in portfolios.values())/3
        def spread(feature, high_minus_low):
            values = portfolios[feature]
            result = (values["SH"]+values["BH"]-values["SL"]-values["BL"])/2
            return result if high_minus_low else -result
        market_weight = sum(row.beginning_market_cap for row in monthly.values())
        market_return = sum(row.beginning_market_cap*row.total_return for row in monthly.values())/market_weight
        output.append({"time": month.month, "MKT_RF": market_return-month.risk_free_return, "SMB": smb,
                       "HML": spread("bm", True), "RMW": spread("op", True), "CMA": spread("inv", False),
                       "portfolios": portfolios, "formation_year": formation})
    return _result(request, method, series=output, universe_id=request.universe_id,
        scope="INPUT_UNIVERSE", universe_complete=request.universe_complete,
        parameters={"size_quantile": .5, "feature_quantiles": [.3, .7], "reconstitution_month": 7,
                    "weights": "BEGINNING_MONTH_MARKET_CAP", "quantile_method": "linear"},
        interpretation="A股输入集合适配；不等同官方美国因子或科技/红利风格，不证明全市场覆盖。")
