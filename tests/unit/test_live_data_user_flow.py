"""Regressions for partial live data consumed by existing user workflows."""

from app.llm.agent import CopilotAgent

from pathlib import Path
import re
import shutil
import subprocess

import pytest
import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.runtime.mode import DataMode
from app.llm.ocr_portfolio_parser import recalculate_portfolio_values


def _report(tool, data, *, mode="LIVE"):
    return CopilotAgent()._synthesize_grounded_response(
        "查询行情", {}, [{"tool": tool, "result": {
            "status": "SUCCESS", "data": data,
            "execution_context": {"data_mode": mode, "provider": "fuyao_finance_api"},
        }}], None,
    )


def test_live_quote_without_financials_keeps_price_and_missing_values():
    report = _report("query_stock_quote", {
        "name": "贵州茅台", "symbol": "600519.SH", "price_cny": 1400,
        "change_pct": None, "observed_at": "2026-09-08T15:00:00+08:00",
    })
    assert "1400" in report
    assert "未提供" in report
    assert "LIVE" in report
    assert "MOCK" not in report
    assert "0.00%" not in report


def test_live_fund_without_sector_keeps_disclosure_boundary():
    report = _report("query_fund_lookthrough", {
        "fund_name": "沪深300ETF", "fund_code": "510300.SH",
        "holding_disclosure_as_of": "2026-06-30T00:00:00+08:00",
        "top_holdings": [{"name": "贵州茅台", "asset_id": "600519.SH", "weight_pct": None}],
    })
    assert "定期披露" in report
    assert "2026-06-30" in report
    assert "未提供" in report
    assert "MOCK" not in report
    assert "None" not in report


def test_report_mode_comes_from_result_not_mutable_runtime():
    report = _report("query_stock_quote", {
        "name": "测试", "symbol": "600519.SH", "price_cny": 10,
        "change_pct": 0,
    }, mode="MOCK")
    assert "MOCK" in report
    assert "0.00%" in report


@pytest.mark.parametrize("query,tool,args", [
    ("查询510300基金持仓", "query_fund_lookthrough", {"fund_code": "510300"}),
    ("查询510300.SH", "query_fund_lookthrough", {"fund_code": "510300.SH"}),
    ("查询600036行情", "query_stock_quote", {"symbol": "600036"}),
    ("查询茅台股票", "query_stock_quote", {"symbol": "600519"}),
])
def test_local_chat_routes_the_requested_security(query, tool, args):
    from app.llm.client import AsyncLLMClient
    async def collect():
        return [chunk async for chunk in AsyncLLMClient()._stream_offline_simulation([{"role": "user", "content": query}])]
    call = next(chunk for chunk in asyncio.run(collect()) if chunk["type"] == "tool_call")
    assert call["name"] == tool
    assert call["arguments"] == args


def test_local_chat_does_not_choose_a_default_fund():
    from app.llm.client import AsyncLLMClient
    async def collect():
        return [chunk async for chunk in AsyncLLMClient()._stream_offline_simulation([{"role": "user", "content": "查询基金"}])]
    chunks = asyncio.run(collect())
    assert not any(chunk["type"] == "tool_call" for chunk in chunks)
    assert "证券代码" in chunks[-1]["delta"]


def test_text_holdings_preserve_explicit_live_price_and_cost(monkeypatch):
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    agent = CopilotAgent()
    agent.live_finance_provider = SimpleNamespace(get_quote=AsyncMock(side_effect=AssertionError("unexpected quote")))
    result = asyncio.run(agent.parse_portfolio_from_text("持有100股贵州茅台，现价1400元，买入均价1350元；现金20万元"))
    assert result["status"] == "SUCCESS"
    assert result["total_value_cny"] == 340000
    assert result["positions"][0]["cost_price"] == 1350
    assert result["positions"][0]["price"] == 1400


@pytest.mark.parametrize("grouped", [True, False])
def test_multiline_holdings_with_thousands_separators_confirm_all_values(monkeypatch, grouped):
    from fastapi.testclient import TestClient
    from app.api.main import create_app

    text = """我持有 600股 贵州茅台，买入均价 1,680元；
1,000股 宁德时代，买入均价 225元；
800股 中国平安，买入均价 48元；
2,000股 中芯国际（688981），买入均价 58元；
1,500股 恒瑞医药，买入均价 42元；
以及 28,000元 现金。"""
    if not grouped:
        text = text.replace(",", "")
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    quote = AsyncMock(return_value={"price_cny": 100})
    monkeypatch.setattr("app.providers.fuyao.FuyaoFinanceProvider.get_quote", quote)
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/copilot/parse-portfolio", json={"text": text})
        assert response.status_code == 200
        parsed = response.json()
        assert parsed["status"] == "SUCCESS"
        actual = {p["asset_id"]: (p["quantity"], p["cost_price"]) for p in parsed["positions"]}
        assert actual == {"600519.SH": (600, 1680), "300750.SZ": (1000, 225),
                          "601318.SH": (800, 48), "688981.SH": (2000, 58), "600276.SH": (1500, 42)}
        assert parsed["cash_cny"] == 28000
        assert parsed["total_value_cny"] == 618000
        confirmed = client.post("/api/v1/copilot/validate-portfolio-ocr", headers={"X-Owner-ID": "grouped-test"},
                                json={"owner_id": "grouped-test", "positions": parsed["positions"], "cash_cny": parsed["cash_cny"]})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["total_value_cny"] == 618000


def test_grouped_decimal_prices_and_cash_preserve_sentence_commas(monkeypatch):
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    agent = CopilotAgent()
    agent.live_finance_provider = SimpleNamespace(get_quote=AsyncMock(side_effect=AssertionError("unexpected quote")))
    parsed = asyncio.run(agent.parse_portfolio_from_text(
        "600股贵州茅台,现价1,300.25元,买入均价1,680.50元；现金1,028,000.25元"
    ))
    assert parsed["positions"][0]["quantity"] == 600
    assert parsed["positions"][0]["price"] == 1300.25
    assert parsed["positions"][0]["cost_price"] == 1680.50
    assert parsed["cash_cny"] == 1028000.25
    assert parsed["total_value_cny"] == 1808150.25


def test_live_text_without_price_uses_quote_and_does_not_invent_etf(monkeypatch):
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    agent = CopilotAgent()
    quote = AsyncMock(return_value={"price_cny": 250})
    agent.live_finance_provider = SimpleNamespace(get_quote=quote)
    result = asyncio.run(agent.parse_portfolio_from_text("300750持有100股；现金2万元"))
    assert result["parsed_count"] == 1
    assert result["total_value_cny"] == 45000
    quote.assert_awaited_once_with("300750.SZ")
    quote.return_value = None
    result = asyncio.run(agent.parse_portfolio_from_text("持有100股宁德时代"))
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["positions"] == []
    result = asyncio.run(agent.parse_portfolio_from_text("持有510300基金1.5万份"))
    assert result["status"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("code", ["UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE"])
def test_portfolio_quote_retries_transient_failure_once(monkeypatch, code):
    from app.providers.fuyao import FuyaoProviderError
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    agent = CopilotAgent()
    quote = AsyncMock(side_effect=[FuyaoProviderError(code, "扶摇数据接口响应超时。"), {"price_cny": 1300}])
    agent.live_finance_provider = SimpleNamespace(get_quote=quote)
    result = asyncio.run(agent.parse_portfolio_from_text("600股贵州茅台，买入均价1,680元；现金28,000元"))
    assert result["status"] == "SUCCESS"
    assert result["total_value_cny"] == 808000
    assert result["positions"][0]["cost_price"] == 1680
    assert quote.await_count == 2


@pytest.mark.parametrize("code,attempts", [("UPSTREAM_TIMEOUT", 2), ("FUYAO_2001", 1)])
def test_portfolio_quote_stops_after_bounded_failure_without_fixture(monkeypatch, code, attempts):
    from app.providers.fuyao import FuyaoProviderError
    monkeypatch.setattr("app.llm.agent.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    agent = CopilotAgent()
    quote = AsyncMock(side_effect=FuyaoProviderError(code, "数据请求失败。"))
    agent.live_finance_provider = SimpleNamespace(get_quote=quote)
    result = asyncio.run(agent.parse_portfolio_from_text("600股贵州茅台，买入均价1,680元；现金28,000元"))
    assert result["status"] == "FAILED"
    assert result["positions"] == []
    assert result["error_code"] == code
    assert "贵州茅台（600519.SH）" in result["message"]
    assert "本次持仓未导入" in result["message"]
    assert "现价" in result["message"]
    assert quote.await_count == attempts


def test_live_fund_import_does_not_attach_synthetic_sector_coverage():
    positions = [{"asset_id": "510300.SH", "asset_class": "FUND_ETF", "quantity": 15000, "price": 4}]
    live = recalculate_portfolio_values(positions, Decimal("20000"), "test-owner", allow_synthetic_lookthrough=False)
    mock = recalculate_portfolio_values(positions, Decimal("20000"), "test-owner")
    assert live["total_value_cny"] == 80000
    assert live["portfolio"]["fund_holdings"] == []
    assert mock["portfolio"]["fund_holdings"]


def test_stress_unknown_fund_exposure_returns_actionable_422_not_500():
    from fastapi.testclient import TestClient
    from app.api.main import create_app
    from app.scenarios.custom_stress import SECTORS

    bundle = recalculate_portfolio_values(
        [{"asset_id": "510300.SH", "quantity": 15000, "price": 4}],
        Decimal("20000"), "test-owner", allow_synthetic_lookthrough=False,
    )["portfolio"]
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/advisor/custom-stress-scenarios", headers={"X-Owner-ID": "test-owner"}, json={
            "request_id": "stress-live-fund", "owner_id": "test-owner", "portfolio": bundle,
            "sector_shocks_pct": {sector: -20 for sector in SECTORS},
        })
    assert response.status_code == 422
    assert response.json()["error_code"] == "STRESS_INPUT_INCOMPLETE"
    assert "补齐穿透数据" in response.json()["message"]


@pytest.mark.parametrize("endpoint", ["/api/v1/copilot/validate-portfolio-ocr", "/api/v1/advisor/portfolio/ocr/confirm"])
def test_both_live_import_endpoints_preserve_unknown_fund_exposure(monkeypatch, endpoint):
    from fastapi.testclient import TestClient
    from app.api.main import create_app

    monkeypatch.setattr("app.api.main.get_runtime_mode_controller", lambda: SimpleNamespace(mode=DataMode.LIVE))
    with TestClient(create_app()) as client:
        response = client.post(endpoint, headers={"X-Owner-ID": "test-owner"}, json={
            "owner_id": "test-owner", "image_digest": "a" * 64, "cash_cny": 20000,
            "positions": [{"asset_id": "510300.SH", "name": "沪深300ETF", "asset_class": "FUND_ETF", "quantity": 15000, "price": 4, "cost_price": 4}],
        })
    assert response.status_code == 200, response.text
    assert response.json()["portfolio"]["fund_holdings"] == []


def test_frontend_live_data_flow_handles_missing_context_and_stale_results():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js required for frontend behavior regression")
    source = (Path(__file__).resolve().parents[2] / "app/api/static/app.js").read_text(encoding="utf-8")
    prefix = source.partition("  microStore.subscribe((store) => {")[0]
    names = ["buildCopilotStockCard", "appendReportMetric", "hasFinancialNumber", "buildCopilotFundCard", "runCopilotStockResearch",
             "requirePortfolioAnalysisContext", "renderPortfolioReadiness",
             "ensureDependency", "confirmProfileContext", "renderCompanionRisk",
             "runCopilotHealthCheck", "runCopilotRebalance", "runCopilotScenarioShock",
             "getSectorVerdict", "renderHeroDonutChart", "runPortfolioRebalancing",
             "loadSavedPortfolio", "openPortfolioModal", "buildRebalancingNotice",
             "profileLevelText", "currentProfileTag", "activeProfileTag"]
    functions = []
    for name in names:
        match = re.search(r"  (?:async )?function " + name + r"\([^\n]*\) \{[\s\S]*?\n  \}", source)
        assert match, name
        functions.append(match.group())
    probe = prefix + "\n".join(functions) + r'''
  const assert = require("node:assert/strict");
  class Element {
    constructor() { this.children = []; this.style = {}; this.value = ""; this.classList = {add(){},remove(){},toggle(){}}; }
    set textContent(value) { this.children = [String(value)]; }
    get textContent() { return this.children.map(x => typeof x === "string" ? x : x.textContent).join(" "); }
    append(...children) { this.children.push(...children); }
    appendChild(child) { this.children.push(child); child.parentElement = this; }
    setAttribute() {}
    addEventListener() {}
  }
  const nodes = new Map();
  const byId = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  const document = {body: new Element(), createElement: () => new Element(), createElementNS: () => new Element(), createTextNode: text => String(text)};
  const renderOverviewWorkspace = () => {};
  const updateVisualCompanion = () => {};
  const clear = element => { element.children = []; };
  const createSvgIcon = () => new Element();
  const buildCopilotLoadingCard = () => new Element();
  const buildCopilotDrilldownRow = links => { const e = new Element(); e.textContent = JSON.stringify(links); return e; };
  const PERSONAS = {};
  const DEFAULT_USER_PROFILE = {tag:"C3"};
  const displayLabel = value => value;
  const errors = [];
  const setError = message => errors.push(message);
  const fetchRuntimeDataMode = async () => {};
  const apiError = async response => new Error((await response.json()).message);
  let calls = [];
  let fetch = async url => { calls.push(url); throw new Error("unexpected request"); };
  const output = byId("copilot-decision-output");
  (async () => {
    state.ownerId = "test-owner";
    state.selectedPersona = "custom-user";
    state.dataMode = "LIVE";
    state.templateContext = {portfolio: {synthetic: true}};
    assert.equal(await ensureDependency("PROFILE_CONTEXT"), null);
    assert.equal(await ensureDependency("PORTFOLIO_CONTEXT"), null);
    for (const action of [runCopilotHealthCheck, runCopilotRebalance, runCopilotScenarioShock]) {
      await action();
      assert.match(output.textContent, /请先确认/);
    }
    assert.equal(calls.length, 0, "unconfirmed user must not trigger template/provider requests");
    renderCompanionRisk();
    assert.match(byId("companion-exposure-bars").textContent, /请先完成风险问卷/);
    assert.doesNotMatch(byId("companion-exposure-bars").textContent, /28.5/);
    state.portfolioHealthRun = {status:"REVIEW_REQUIRED",has_breaches:true,hhi_verdict:"OVERBOUND",
      sector_hhi:5200,hhi_limit:3800,sectors:[{name:"现金",pct:60,cap:5,limitOperator:"MIN",
        verdictCode:"PASS",differencePctPoints:55,marginPctPoints:55,topHoldings:"现金"}]};
    renderHeroDonutChart("custom-user");
    assert.match(byId("cf-hero-verdict-badge").textContent, /集中度需要关注.*HHI 5200/);
    assert.match(byId("donut-cause-callout").textContent, /各行业占比仍在设置范围内/);
    state.portfolioHealthRun = null;
    state.portfolio = {position_snapshot:{positions:[{asset_id:"510300.SH"}]}};
    state.portfolioRefreshRun = {status:"COMPLETE"};
    state.portfolioOptimizationRun = {targets:[{target_id:"SECTOR:TECHNOLOGY",target_weight_pct:100}]};
    assert.equal(await runPortfolioRebalancing(), null);
    assert.match(errors.at(-1), /不能直接作为账户持仓下单/);
    assert.equal(calls.length, 0);
    state.portfolio = null;
    for (const value of [null, undefined, "", " ", false, true, NaN, Infinity]) assert.equal(hasFinancialNumber(value), false);
    for (const value of [0, "0", -1, "20.5"]) assert.equal(hasFinancialNumber(value), true);

    fetch = async url => {
      calls.push(url);
      return {ok:true, status:200, json:async()=>({data:{fund_name:"测试ETF",fund_code:"510300.SH",
        holding_disclosure_as_of:"2026-06-30",top_holdings:[{asset_id:"600519.SH",name:"贵州茅台",weight_pct:null}]},
        execution_context:{data_mode:"LIVE",provider:"fuyao_finance_api"}})};
    };
    byId("copilot-stock-input").value = "510300.SH";
    await runCopilotStockResearch();
    assert.equal(calls.at(-1), "/api/v1/copilot/live-fund?fund_code=510300.SH");
    assert.match(output.textContent, /定期披露/);
    assert.match(output.textContent, /2026-06-30/);
    assert.doesNotMatch(output.textContent, /null|undefined|NaN/);

    calls = [];
    byId("copilot-stock-input").value = "600519.SH";
    await runCopilotStockResearch("510300");
    assert.equal(calls.at(-1), "/api/v1/copilot/live-fund?fund_code=510300",
      "quick-tag target must override a stale legacy input value");

    calls = [];
    fetch = async url => { calls.push(url); return {ok:false,status:404,json:async()=>({message:"上游无行情"})}; };
    byId("copilot-stock-input").value = "600999.SH";
    await runCopilotStockResearch();
    assert.equal(calls.length, 1, "live no-result must not auto-index or retry as MOCK");
    assert.match(output.textContent, /上游无行情/);

    let respond;
    fetch = () => new Promise(resolve => { respond = resolve; });
    byId("copilot-stock-input").value = "600519.SZ";
    const pending = runCopilotStockResearch();
    state.dataMode = "MOCK";
    output.textContent = "新的页面状态";
    respond({ok:true,status:200,json:async()=>({data:{}})});
    await pending;
    assert.equal(output.textContent, "新的页面状态", "old request overwrote new mode");

    fetch = async () => ({ok:true,status:200,json:async()=>({data:{name:"测试",symbol:"600519.SH",price_cny:10,
      pe_ttm:null,pb:0,roe_pct:0,valuation_quantile_pct:0},execution_context:{data_mode:"LIVE"}})});
    byId("copilot-stock-input").value = "600519.SH";
    await runCopilotStockResearch();
    assert.match(output.textContent, /部分数据可用/);
    assert.match(output.textContent, /历史估值分位暂未接入/);
    assert.match(output.textContent, /PE（TTM）/);
    assert.match(output.textContent, /0.00%/);
    assert.doesNotMatch(output.textContent, /NaN/);

    state.profile = {profile:{risk_level:"BALANCED",max_drawdown_tolerance_pct:"12"},questionnaire:{loss_tolerance_score:3}};
    state.portfolioHealthRun = {technology_weight_pct:"42.00",technology_limit_pct:"25.00"};
    renderCompanionRisk();
    assert.match(byId("companion-exposure-bars").textContent, /42.00% \(上限 25.00%\)/);
    assert.doesNotMatch(byId("companion-exposure-bars").textContent, /28.5/);
    openPortfolioModal();
    assert.equal(byId("portfolio-modal").parentElement, document.body);
    assert.equal(byId("portfolio-modal").style.display, "flex");
    state.dataMode = "LIVE";
    state.portfolio = null;
    const saved = {data_mode:"LIVE", data:{portfolio:{owner_id:"test-owner"}, positions:[{quantity:600,cost_price:1680}],cash_cny:28000}};
    fetch = async () => ({ok:true,json:async()=>saved});
    await loadSavedPortfolio();
    assert.equal(state.portfolio.owner_id, "test-owner");
    assert.equal(state.ocrPortfolioDraft.cash_cny, 28000);
    assert.match(byId("copilot-hero-portfolio-tag").textContent, /已确认持仓/);
    fetch = () => new Promise(resolve => { respond = resolve; });
    const restoring = loadSavedPortfolio();
    const newer = {owner_id:"test-owner",updated:true};
    state.portfolio = newer;
    respond({ok:true,json:async()=>saved});
    await restoring;
    assert.equal(state.portfolio, newer, "late restore overwrote new confirmation");
    const changedContext = loadSavedPortfolio();
    state.dataMode = "MOCK";
    state.dataMode = "LIVE";
    respond({ok:true,json:async()=>saved});
    await changedContext;
    assert.equal(state.portfolio, newer, "late restore crossed a mode transition");
    state.portfolio = null;
    renderPortfolioReadiness();
    assert.equal(byId("copilot-hero-portfolio-tag").textContent, "待确认持仓");
    const noTrade = buildRebalancingNotice({status:"REVIEW_REQUIRED",execution_steps:[],issues:["取整为 0，目标未达到", "现金风险未解除"]});
    assert.match(noTrade.textContent, /不能据此判断组合无需调整/);
    assert.match(noTrade.textContent, /取整为 0/);
    assert.match(noTrade.textContent, /现金风险未解除/);
    const noDrift = buildRebalancingNotice({status:"PASS",execution_steps:[],issues:[]});
    assert.match(noDrift.textContent, /未触发交易规则/);
    process.stdout.write("PASS");
  })().catch(error => { console.error(error); process.exitCode = 1; });
})();
'''
    result = subprocess.run([node], input=probe, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "PASS"
