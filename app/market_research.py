"""Versioned, deterministic research metrics calculated only from daily bars."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
import math
from statistics import stdev
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResearchMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    value: float | None = None
    unit: str = "%"
    status: Literal["CALCULATED", "UNAVAILABLE"]
    missing_reason: str | None = None
    method_version: str = "market-research.v1"
    parameters: dict[str, int | str] = Field(default_factory=dict)
    sample_count: int = Field(ge=0)
    input_start: str | None = None
    input_end: str | None = None
    source: str
    snapshot_id: str
    series: list[dict[str, str | float]] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent_state(self):
        if self.status == "CALCULATED" and (self.value is None or self.missing_reason):
            raise ValueError("calculated metrics require a value and no missing reason")
        if self.status == "UNAVAILABLE" and (self.value is not None or not self.missing_reason):
            raise ValueError("unavailable metrics require a reason and no value")
        return self


def research_metrics(bars: list[dict], *, source: str, subject: str = "") -> dict[str, ResearchMetric]:
    """Reject bad chronology or prices; never reinterpret monthly bars as daily."""
    times = [str(row["time"]) for row in bars]
    if times != sorted(set(times)):
        raise ValueError("daily research bars must have sorted unique dates")
    for key in times:
        date.fromisoformat(key)
    closes = [float(row["close"]) for row in bars]
    if any(not math.isfinite(value) or value <= 0 for value in closes):
        raise ValueError("research prices must be finite and positive")
    payload = {"subject": subject, "source": source, "bars": [
        {"time": t, "close": str(Decimal(str(row["close"])))} for t, row in zip(times, bars)]}
    snapshot = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    metadata = {"source": source, "snapshot_id": snapshot,
                "input_start": times[0] if times else None, "input_end": times[-1] if times else None}
    def metric(value, minimum, parameters=None, series=None, sample_count=None):
        count = len(closes) if sample_count is None else sample_count
        return ResearchMetric(value=value, status="CALCULATED" if value is not None else "UNAVAILABLE",
                              missing_reason=None if value is not None else f"INSUFFICIENT_DAILY_BARS:{minimum}",
                              sample_count=count, parameters=parameters or {}, series=series or [], **metadata)
    momentum = [{"time": times[i], "value": (closes[i] / closes[i-20] - 1) * 100}
                for i in range(20, len(closes))]
    volatility = [{"time": times[i], "value": stdev([
        math.log(closes[j] / closes[j-1]) for j in range(i-19, i+1)]) * math.sqrt(252) * 100}
        for i in range(20, len(closes))]
    peak = 0.0
    drawdowns = []
    for t, close in zip(times, closes):
        peak = max(peak, close)
        drawdowns.append({"time": t, "value": (close / peak - 1) * 100})
    return {
        "daily_return": metric((closes[-1]/closes[-2]-1)*100 if len(closes) >= 2 else None, 2,
                               {"window": 1}, sample_count=min(2, len(closes))),
        "momentum_20": metric(momentum[-1]["value"] if momentum else None, 21,
                              {"window": 20}, momentum, min(21, len(closes))),
        "realized_volatility_20": metric(volatility[-1]["value"] if volatility else None, 21,
                                         {"window": 20, "annualization": 252, "ddof": 1}, volatility,
                                         min(21, len(closes))),
        "current_drawdown": metric(drawdowns[-1]["value"] if drawdowns else None, 1,
                                   {"window": "displayed_daily_history"}, drawdowns),
        "maximum_drawdown": metric(min(row["value"] for row in drawdowns) if drawdowns else None, 1,
                                   {"window": "displayed_daily_history"}),
    }
