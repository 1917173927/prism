from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import time

import pytest

from app.portfolio import PortfolioImportBundle, calculate_exposure
from app.portfolio.health import PortfolioHealthRequest, calculate_portfolio_health
from app.profile import RiskProfile, RiskQuestionnaire
from app.rebalancing.contracts import PortfolioRebalancingRequest
from app.risk import calculate_concentration, assess_risk_budget
from app.service.portfolio_rebalancing import PortfolioRebalancingService, trade_fees
from app.service.session_truth import (
    truth_status, fingerprint, check_session_assertions, SessionAssertionsRequest,
)
from app.store import (
    SQLiteDecisionEventStore, ContextMemoryWriteRequest, build_context_memory_record,
    StoreConflictError, StoreOwnerError,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/api/static/pages-snapshot.json"
TARGET = ROOT / "docs/submission/test-evidence/current-results.json"
D = Decimal
records = []


def check(case_id, title, expected, actual, scope="确定性程序执行"):
    passed = expected == actual
    records.append(dict(id=case_id, title=title, expected=expected, actual=actual,
                        status="PASS" if passed else "FAIL", scope=scope))
    assert passed, f"{case_id}: {actual!r} != {expected!r}"


def q(value):
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def main():
    started = datetime.now(UTC)
    archive = json.loads(SOURCE.read_text(encoding="utf-8"))
    routes = archive["routes"]
    report = json.loads(routes["GET /api/v1/advisor/portfolio/report"]["body"])
    current = json.loads(routes["GET /api/v1/advisor/portfolio/current"]["body"])["data"]
    summary = json.loads(routes["GET /api/v1/advisor/profile/summary"]["body"])
    bundle = PortfolioImportBundle.model_validate(current["portfolio"])
    profile = RiskProfile.model_validate(summary["questionnaire_snapshot"]["profile"])
    owner = profile.owner_id
    at = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))

    # 保存页面快照的历史输入，核验计算过程，不重新声明行情有效性。
    rows = report["positions"]
    products = [str(q(D(row["quantity"]) * D(row["current_price_cny"]))) for row in rows]
    check("NUM-01", "五项市值逐项复算", [row["market_value_cny"] for row in rows], products,
          "历史报告数值复核")
    total = sum(map(D, products)) + D(report["cash_cny"])
    check("NUM-02", "证券和现金金额守恒", report["total_value_cny"], str(total), "历史报告数值复核")
    weights = [q(D(row["market_value_cny"]) / D(report["holdings_value_cny"]) * 100) for row in rows]
    check("NUM-03", "证券权重分母一致", [row["weight_pct"] for row in rows], list(map(str, weights)))
    check("NUM-04", "证券集中度复算", "3692.96", str(q(sum(w * w for w in weights))))
    health = calculate_portfolio_health(PortfolioHealthRequest(
        request_id="report-health", owner_id=owner, calculated_at=at,
        portfolio=bundle, profile=profile,
    ))
    check("NUM-05", "现金比例复核", "1.94", str(health.cash_weight_pct))
    check("NUM-06", "行业集中度复核", "3555.39", str(health.sector_hhi))
    check("NUM-07", "组合问题保留", "REVIEW_REQUIRED", health.status)

    concentration = calculate_concentration(calculate_exposure(bundle, calculated_at=at))
    comparisons = []
    for level, score in [("CONSERVATIVE", "20"), ("BALANCED", "50"), ("GROWTH", "85")]:
        payload = profile.model_dump(mode="json")
        payload.update(risk_level=level, risk_score=score)
        condition = RiskProfile.model_validate(payload)
        assessment = assess_risk_budget(condition, concentration)
        comparisons.append(dict(level=level, score=score, result=assessment.model_dump(mode="json")))
    check("PRO-01", "画像改变单一资产上限", ["20", "35", "50"],
          [item["result"]["budget"]["max_single_asset_weight_pct"] for item in comparisons],
          "历史持仓与明确变更的画像条件")

    # 此处费用属于程序配置规则，金融交易费率的适用性需另行确认。
    check("REB-01", "买入费用计算", "5.04", str(trade_fees(D("4000"), False)["total_fees_cny"]))
    check("REB-02", "卖出费用计算", "7.04", str(trade_fees(D("4000"), True)["total_fees_cny"]))
    targets = {p.asset_id: D("10") for p in bundle.position_snapshot.positions if p.asset_type != "CASH"}
    targets["CASH-CNY"] = D("50")
    request = PortfolioRebalancingRequest(
        request_id="report-rebalancing", owner_id=owner, generated_at=at,
        bundle=bundle, target_weights=targets, minimum_cash_pct=D("5"),
        max_turnover_pct=D("100"), confirmed_profile=profile,
    )
    plan = PortfolioRebalancingService().plan_rebalancing(request)
    check("REB-03", "确定性重复计算", plan.model_dump(mode="json"),
          PortfolioRebalancingService().plan_rebalancing(request).model_dump(mode="json"))
    check("REB-04", "交易费用与现金守恒", str(plan.metrics.cash_after_cny),
          str(q(D(report["cash_cny"]) + plan.metrics.total_sell_cny - plan.metrics.total_buy_cny - plan.metrics.net_turnover_cost)))
    check("REB-05", "整手数量约束", True,
          all(step.shares % 100 == 0 for step in plan.execution_steps if step.shares is not None))
    check("REB-06", "先卖出后买入", sorted(step.liquidity_priority for step in plan.execution_steps),
          [step.liquidity_priority for step in plan.execution_steps])
    check("REB-07", "扣费后现金非负", True, plan.metrics.cash_after_cny >= 0)

    facts = dict(data_mode="LIVE", questionnaire_snapshot_id=summary["questionnaire_snapshot"]["snapshot_id"],
                 profile=profile.model_dump(mode="json"), portfolio=bundle.model_dump(mode="json"))
    check("SES-01", "未确认会话状态", "NOT_LOCKED", truth_status(None, facts)["status"])
    # 使用独立内存数据库，调用实际 SQLite 保存和读取方法。
    store = SQLiteDecisionEventStore(":memory:")
    record = store.save_session_truth(owner, "report-session", facts, 0, started.isoformat())
    check("SES-02", "确认后会话状态", "LOCKED", truth_status(record, facts)["status"])
    changed = deepcopy(facts)
    changed["portfolio"]["position_snapshot"]["positions"][0]["quantity"] = "1100"
    state = truth_status(record, changed)
    check("SES-03", "数量变化触发检测", ["DRIFT_DETECTED", ["portfolio"]], [state["status"], state["changed_fields"]])
    assertions = SessionAssertionsRequest(expected_revision=1, assertions=[
        {"path": "portfolio.positions.quantity", "value": "1000", "position_id": rows[0]["position_id"]},
    ])
    check("SES-04", "已确认数量校验", "PASS", check_session_assertions(record, facts, assertions, owner_id=owner)["status"])
    wrong = assertions.model_copy(update={"expected_revision": 2})
    check("SES-05", "版本不一致拒绝验证", "UNVERIFIED", check_session_assertions(record, facts, wrong, owner_id=owner)["status"])
    check("SES-06", "资料变化拒绝沿用旧前提", "UNVERIFIED", check_session_assertions(record, changed, assertions, owner_id=owner)["status"])
    with pytest.raises(StoreConflictError):
        store.save_session_truth(owner, "report-session", changed, 0, started.isoformat())
    check("SES-07", "并发修订冲突", True, True)
    check("SEC-01", "其他用户不能读取会话", None, store.get_session_truth("report-other-user", "report-session"))
    with pytest.raises(StoreOwnerError):
        check_session_assertions(record, facts, assertions, owner_id="report-other-user")
    check("SEC-02", "其他用户不能校验账户事实", True, True)
    check("SES-08", "指纹与字段顺序无关", fingerprint(facts), fingerprint(dict(reversed(list(facts.items())))))

    questionnaire = RiskQuestionnaire.model_validate(summary["questionnaire_snapshot"]["questionnaire"])
    memory_request = ContextMemoryWriteRequest(owner_id=owner, questionnaire=questionnaire,
                                               profile=profile, portfolio=bundle)
    memory = build_context_memory_record(memory_request, saved_at=started)
    with ThreadPoolExecutor(max_workers=8) as executor:
        saved = list(executor.map(lambda _: store.save_context_memory(memory), range(100)))
    check("MEM-01", "重复保存只创建一条记忆", 1, sum(created for _, created in saved))
    check("MEM-02", "记忆读取完整性", memory.model_dump(mode="json"), store.get_context_memory(owner, memory.memory_id).model_dump(mode="json"))
    check("MEM-03", "其他用户无法读取记忆", None, store.get_context_memory("report-other-user", memory.memory_id))
    check("MEM-04", "其他用户记忆列表为空", 0, len(store.list_context_memory("report-other-user")))
    store.close()

    timings = []
    for _ in range(100):
        start = time.perf_counter()
        PortfolioRebalancingService().plan_rebalancing(request)
        timings.append((time.perf_counter() - start) * 1000)
    ordered = sorted(timings)
    runtime = dict(python=platform.python_version(), os=platform.platform(), processor=platform.processor(),
                   packages={key: version(key) for key in ("pydantic", "fastapi", "pytest")})
    result = dict(
        started_at=started.isoformat(), ended_at=datetime.now(UTC).isoformat(),
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        environment=runtime, source_path=str(SOURCE.relative_to(ROOT)),
        source_sha256=sha256(SOURCE.read_bytes()).hexdigest(), source_captured_at=archive["captured_at"],
        source_generated_at=report["generated_at"], tests=records,
        profile_comparison=comparisons, health=health.model_dump(mode="json"),
        rebalancing=plan.model_dump(mode="json"),
        local_calculation_timing=dict(iterations=100, concurrency=1, raw_ms=timings,
                                     median_ms=(ordered[49]+ordered[50])/2,
                                     p95_ms=ordered[94]+(ordered[95]-ordered[94])*.05,
                                     max_ms=max(timings), scope="本地再平衡函数重复计算，不含 HTTP、LLM 或外部查询"),
        archived_routes=[dict(route=k, status=v["status"]) for k,v in routes.items()],
        boundaries=["历史快照来源和时点由文件记录，本次未重新验证外部行情。", "画像条件比较与再平衡目标为明确指定的测试输入。", "本次未替换任何外部服务响应。"],
    )
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(tests=len(records), passed=sum(r["status"] == "PASS" for r in records),
                         output=str(TARGET), timing=result["local_calculation_timing"]["p95_ms"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
