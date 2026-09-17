(function () {
  "use strict";

  const pageHosts = new Set(["prism.daoyezongzi.org"]);
  const query = new URLSearchParams(window.location.search);
  const enabled = pageHosts.has(window.location.hostname) || query.get("pages") === "1";
  if (!enabled) return;

  const OWNER_ID = "demo-owner";
  const NOW = "2026-09-17T08:00:00.000Z";
  const PAGE_MARK = "Pages Mock";

  const clone = value => JSON.parse(JSON.stringify(value));
  const jsonResponse = (payload, status = 200) => new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });

  function sseResponse(events) {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        events.forEach(event => controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`)));
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      },
    });
    return new Response(stream, { headers: { "Content-Type": "text/event-stream; charset=utf-8" } });
  }

  function addBadge() {
    if (document.getElementById("pages-demo-badge")) return;
    const badge = document.createElement("aside");
    badge.id = "pages-demo-badge";
    badge.setAttribute("role", "note");
    badge.style.cssText = [
      "position:fixed", "right:16px", "bottom:16px", "z-index:10000", "max-width:300px",
      "padding:10px 12px", "border:1px solid rgba(180,83,9,.24)", "border-radius:12px",
      "background:rgba(255,247,237,.96)", "box-shadow:0 8px 24px rgba(15,23,42,.12)",
      "color:#7c2d12", "font:12px/1.5 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    ].join(";");
    const title = document.createElement("strong");
    title.textContent = "GitHub Pages · Mock 演示 · 仅前端";
    const detail = document.createElement("div");
    detail.textContent = "当前使用合成示例数据，不连接后端、账号、真实行情或模型服务。刷新页面后数据恢复为演示状态。";
    badge.append(title, detail);
    document.body.append(badge);
  }

  window.PRISM_PAGES_MOCK = true;
  document.body.classList.add("dev-mode");
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("dev-mode");
    addBadge();
  }, { once: true });
  else addBadge();

  const dateOnly = (offset) => {
    const value = new Date(Date.UTC(2026, 7, 1 + offset));
    return value.toISOString().slice(0, 10);
  };

  const scenarios = [
    { scenario_id: "BASELINE_READY", label: "当前可用数据", description: "两条独立来源链的合成数据已经完成核对。" },
    { scenario_id: "CONTRADICTORY_SOURCE", label: "来源存在差异", description: "展示来源差异的核对路径与人工复核入口。" },
    { scenario_id: "PARTIAL_SOURCE", label: "来源部分可用", description: "展示部分来源可用时仍然保留的证据。" },
    { scenario_id: "TIMEOUT", label: "来源超时", description: "展示来源超时后的结果状态与问题提示。" },
    { scenario_id: "EMPTY", label: "没有可用来源", description: "展示没有形成事实时的结果状态。" },
  ];

  const positions = [
    {
      position_id: "pages-position-600519", owner_id: OWNER_ID, asset_id: "600519.SH", asset_type: "STOCK",
      asset_name: "贵州茅台", quantity: "100", market_value: "168000", market_value_cny: 168000,
      currency: "CNY", as_of: NOW, source: PAGE_MARK, cost_price_cny: 1580, current_price_cny: 1680,
    },
    {
      position_id: "pages-position-300750", owner_id: OWNER_ID, asset_id: "300750.SZ", asset_type: "STOCK",
      asset_name: "宁德时代", quantity: "300", market_value: "69000", market_value_cny: 69000,
      currency: "CNY", as_of: NOW, source: PAGE_MARK, cost_price_cny: 230, current_price_cny: 230,
    },
    {
      position_id: "pages-position-510300", owner_id: OWNER_ID, asset_id: "510300.SH", asset_type: "ETF",
      asset_name: "沪深300ETF", quantity: "20000", market_value: "85000", market_value_cny: 85000,
      currency: "CNY", as_of: NOW, source: PAGE_MARK, cost_price_cny: 4.05, current_price_cny: 4.25,
    },
    {
      position_id: "pages-position-511010", owner_id: OWNER_ID, asset_id: "511010.SH", asset_type: "ETF",
      asset_name: "国债ETF", quantity: "10000", market_value: "103000", market_value_cny: 103000,
      currency: "CNY", as_of: NOW, source: PAGE_MARK, cost_price_cny: 10.1, current_price_cny: 10.3,
    },
  ];

  const fundHoldings = [
    {
      schema_version: "fund-holdings-snapshot.v1", snapshot_id: "pages-holdings-510300", owner_id: OWNER_ID,
      parent_asset_id: "510300.SH", parent_asset_type: "ETF", as_of: NOW, source: PAGE_MARK, coverage_pct: "100",
      holdings: [
        { holding_id: "pages-holding-510300-1", parent_asset_id: "510300.SH", underlying_asset_id: "600036.SH", underlying_name: "招商银行", asset_type: "STOCK", weight_pct: "5.80", sector: "金融", as_of: NOW, source: PAGE_MARK },
        { holding_id: "pages-holding-510300-2", parent_asset_id: "510300.SH", underlying_asset_id: "600519.SH", underlying_name: "贵州茅台", asset_type: "STOCK", weight_pct: "4.20", sector: "消费", as_of: NOW, source: PAGE_MARK },
        { holding_id: "pages-holding-510300-3", parent_asset_id: "510300.SH", underlying_asset_id: "300750.SZ", underlying_name: "宁德时代", asset_type: "STOCK", weight_pct: "3.10", sector: "科技", as_of: NOW, source: PAGE_MARK },
      ],
    },
    {
      schema_version: "fund-holdings-snapshot.v1", snapshot_id: "pages-holdings-511010", owner_id: OWNER_ID,
      parent_asset_id: "511010.SH", parent_asset_type: "ETF", as_of: NOW, source: PAGE_MARK, coverage_pct: "100",
      holdings: [
        { holding_id: "pages-holding-511010-1", parent_asset_id: "511010.SH", underlying_asset_id: "CGB-2028-01", underlying_name: "国债 2028-01", asset_type: "BOND", weight_pct: "57.00", sector: "债券", as_of: NOW, source: PAGE_MARK },
        { holding_id: "pages-holding-511010-2", parent_asset_id: "511010.SH", underlying_asset_id: "CGB-2030-02", underlying_name: "国债 2030-02", asset_type: "BOND", weight_pct: "43.00", sector: "债券", as_of: NOW, source: PAGE_MARK },
      ],
    },
  ];

  const portfolio = {
    schema_version: "portfolio-import-bundle.v1", bundle_id: "pages-demo-bundle-001", owner_id: OWNER_ID,
    created_at: NOW, source: PAGE_MARK, cash_cny: 175000, total_value_cny: 600000,
    position_snapshot: {
      schema_version: "position-snapshot.v1", snapshot_id: "pages-demo-position-snapshot-001", owner_id: OWNER_ID,
      as_of: NOW, base_currency: "CNY", source: PAGE_MARK, positions,
    },
    fund_holdings: fundHoldings,
  };

  const questionnaire = {
    schema_version: "risk-questionnaire.v1", questionnaire_id: "pages-demo-questionnaire-001", owner_id: OWNER_ID,
    answered_at: NOW, loss_tolerance_score: 3, investment_horizon: "MEDIUM", liquidity_need: "MEDIUM",
    experience_level: "INTERMEDIATE", return_expectation: "MODERATE", max_drawdown_tolerance_pct: "15",
    expected_return_range: { minimum_pct: "4", maximum_pct: "12" },
  };

  const question = (question_id, prompt, options, required = true, question_type = "SINGLE") => ({
    question_id, prompt, options, required, question_type,
  });
  const scoreQuestion = (question_id, prompt, minimum_score = 1, maximum_score = 5) => ({
    question_id, prompt, required: true, question_type: "SCORE", minimum_score, maximum_score,
  });
  const opt = (option_id, label) => ({ option_id, label });
  const questions = [
    question("Q1", "当前投资活动的主要状态是什么？", [opt("active", "正在持续投资"), opt("new", "刚开始投资"), opt("pause", "暂时观望")]),
    question("Q2", "计划持有投资的时间范围？", [opt("y1_3", "1 至 3 年"), opt("y3_5", "3 至 5 年"), opt("y5_plus", "5 年以上")]),
    question("Q3", "目前主要关注哪些资产？", [opt("fund", "基金与 ETF"), opt("stock", "股票"), opt("bond", "债券"), opt("mixed", "多类资产")], true, "MULTI"),
    question("Q4", "可用于投资的资产规模？", [opt("k50_200", "5 万至 20 万元"), opt("k200_500", "20 万至 50 万元"), opt("k500_plus", "50 万元以上")]),
    question("Q5", "追加投资的频率？", [opt("monthly", "每月"), opt("quarterly", "每季度"), opt("irregular", "不定期")]),
    question("Q6", "更重视哪一种投资目标？", [opt("balanced_growth", "平衡增长"), opt("income", "稳定收益"), opt("preservation", "资产保值")]),
    question("Q7", "做投资判断时最依赖哪些信息？", [opt("fundamental", "基本面"), opt("market_data", "市场数据"), opt("ai", "AI 辅助"), opt("news", "公开资讯")], true, "MULTI"),
    question("Q8", "你通常可以接受多长时间的价格波动？", [opt("days", "几天到几周"), opt("months", "几个月"), opt("years", "几年")]),
    question("Q9", "你希望单次分析控制在多长时间？", [opt("h1_2", "1 至 2 小时"), opt("h2_4", "2 至 4 小时"), opt("any", "时间不限")]),
    question("Q10", "更希望系统提供哪种提醒？", [opt("regular_review", "定期复盘"), opt("price_alert", "价格提醒"), opt("risk_alert", "风险提醒")], true, "MULTI"),
    question("Q11", "当前最需要解决的问题？", [opt("portfolio", "组合结构"), opt("risk", "风险控制"), opt("research", "研究效率")], true, "MULTI"),
    scoreQuestion("Q12", "短期亏损对你的影响程度？"),
    question("Q13", "希望优先使用哪些功能？", [opt("market", "市场分析"), opt("stock", "个股研究"), opt("portfolio", "组合分析")], false, "MULTI"),
    question("Q14", "你希望系统如何处理风险提示？", [opt("always", "始终展示"), opt("summary", "只看摘要"), opt("on_demand", "需要时查看")]),
    question("Q15", "希望优先看到哪些组合信息？", [opt("holdings", "持仓明细"), opt("risk_level", "风险等级"), opt("goals", "投资目标")], true, "MULTI"),
    question("Q16", "使用智能分析的频率？", [opt("regular", "经常使用"), opt("sometimes", "偶尔使用"), opt("rarely", "很少使用")]),
    scoreQuestion("Q17", "你对自动化建议的参考程度？"),
    question("Q18", "查看分析结果时最重视什么？", [opt("check", "可核验来源"), opt("speed", "响应速度"), opt("simple", "表达简单")]),
    question("Q19", "希望智能分析重点提升哪方面？", [opt("accuracy", "结论准确性"), opt("explainability", "解释完整性"), opt("coverage", "覆盖更多资产")], true, "MULTI"),
  ];

  const sections = [
    { section_id: "basic", title: "基本情况", description: "用于了解投资期限、资产范围与资金安排。", question_ids: ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"] },
    { section_id: "decision", title: "决策方式", description: "用于安排研究内容与结果展示方式。", question_ids: ["Q7", "Q8", "Q9", "Q10"] },
    { section_id: "pain", title: "当前重点", description: "用于确定组合分析与风险提示的重点。", question_ids: ["Q11", "Q12"] },
    { section_id: "scenes", title: "使用场景", description: "可选功能将帮助页面展示更合适的入口。", question_ids: ["Q13"] },
    { section_id: "personal", title: "个人偏好", description: "用于确定风险提示与组合摘要的展示顺序。", question_ids: ["Q14", "Q15"] },
    { section_id: "ai", title: "智能分析", description: "用于确定分析解释、来源与自动化功能的展示重点。", question_ids: ["Q16", "Q17", "Q18", "Q19"] },
  ];

  const answers = [
    ["Q1", ["active"]], ["Q2", ["y3_5"]], ["Q3", ["fund", "stock"]], ["Q4", ["k200_500"]],
    ["Q5", ["monthly"]], ["Q6", ["balanced_growth"]], ["Q7", ["fundamental", "market_data", "ai"]],
    ["Q8", ["days"]], ["Q9", ["h1_2"]], ["Q10", ["regular_review", "risk_alert"]], ["Q11", ["portfolio", "risk"]],
    ["Q12", 3], ["Q13", ["market", "stock", "portfolio"]], ["Q14", ["always"]],
    ["Q15", ["holdings", "risk_level", "goals"]], ["Q16", ["regular"]], ["Q17", 4], ["Q18", ["check"]],
    ["Q19", ["accuracy", "explainability"]],
  ].map(([question_id, value]) => Number.isInteger(value)
    ? { question_id, score: value }
    : { question_id, selected_option_ids: value });

  const profile = {
    profile_id: "pages-demo-profile-001", questionnaire_id: questionnaire.questionnaire_id, owner_id: OWNER_ID,
    profile_version: 1, risk_score: 58, risk_level: "BALANCED", created_at: NOW, suitability_level: "C3",
    max_drawdown_tolerance_pct: "15", equity_weight_pct: "55", equity_minimum_pct: "35", equity_maximum_pct: "70",
    exclusions: [], investment_horizon: "MEDIUM", liquidity_need: "MEDIUM", experience_level: "INTERMEDIATE",
    return_expectation: "MODERATE",
  };

  const behaviorProfile = {
    owner_id: OWNER_ID, profile_version: 1, persona: "稳健成长型", suitability_level: "C3",
    effective_risk_score: 58, behavior_risk_score: 56, evidence_status: "QUESTIONNAIRE_CONFIRMED",
    metrics: { turnover_90d_pct: "18.00", max_drawdown_pct: "8.40" },
    display_policy: { trust_score: 50, mode: "STANDARD" },
  };

  const presentation = {
    persona: "稳健成长型投资者", archetype: "稳健成长型投资者", suitability_label: "C3 平衡型",
    risk_score: 58, persona_fit: 86, tags: ["控制回撤", "关注组合", "重视证据"],
    dimensions: [
      { key: "risk_tolerance", label: "风险承受", score: 58 }, { key: "horizon", label: "投资期限", score: 64 },
      { key: "liquidity", label: "流动性", score: 54 }, { key: "experience", label: "投资经验", score: 62 },
      { key: "return", label: "收益目标", score: 60 }, { key: "decision", label: "决策独立性", score: 72 },
      { key: "discipline", label: "执行纪律", score: 68 }, { key: "evidence", label: "证据偏好", score: 84 },
    ],
    key_profile: [
      { label: "投资期限", value: "3 至 5 年" }, { label: "资金规模", value: "20 万至 50 万元" },
      { label: "流动性需求", value: "中等" }, { label: "决策偏好", value: "基本面与市场数据并重" },
    ],
    service_strategy: ["先展示组合风险边界，再展示研究依据。", "保留来源与计算步骤，便于逐项核验。", "将模拟结果与实际持仓分开显示。"],
    asset_allocation: [
      { key: "cash", label: "现金", target_pct: 20 }, { key: "bonds", label: "债券及防御资产", target_pct: 25 },
      { key: "equity", label: "权益类资产", target_pct: 55 },
    ],
    equity_range: { minimum_pct: 35, maximum_pct: 70 },
    risk_notice: "当前页面使用示例画像，仅用于展示风险约束与解释路径。",
    feats: ["组合健康度", "四类研究", "确定性情景模拟"],
    rule_trace: {
      persona: { gates: ["风险承受分 58", "投资期限为中期", "问卷已确认"], final_fit: 86, conflict_penalty: 0, conflict_reason: "" },
      tags: [
        { label: "控制回撤", evidence: ["最大回撤容忍度为 15%"] },
        { label: "关注组合", evidence: ["优先关注组合结构与风险控制"] },
        { label: "重视证据", evidence: ["优先展示可核验来源"] },
      ],
      service_strategy: [
        { label: "先展示组合风险边界，再展示研究依据。", evidence: ["组合风险控制优先"] },
        { label: "保留来源与计算步骤，便于逐项核验。", evidence: ["Q18 选择可核验来源"] },
        { label: "将模拟结果与实际持仓分开显示。", evidence: ["情景模拟使用覆盖层口径"] },
      ],
    },
  };

  const questionnaireTemplate = {
    schema_version: "risk-questionnaire-template.v1", questionnaire_id: "pages-demo-questionnaire-template-001",
    generated_at: NOW, sections, questions,
  };
  const questionnaireSnapshot = {
    schema_version: "questionnaire-snapshot.v1", snapshot_id: "pages-demo-questionnaire-snapshot-001", snapshot_version: 1,
    owner_id: OWNER_ID, questionnaire, profile, answers,
  };
  const profileSummary = {
    questionnaire_snapshot: questionnaireSnapshot, effective_profile: profile, behavior_profile: behaviorProfile,
    display_policy: { trust_score: 50, mode: "STANDARD" }, presentation, data_gaps: [], next_actions: [],
  };

  const sectorRows = [
    { sector_key: "CONSUMER_HEALTHCARE", name: "消费", weight_pct: "28.00", limit_pct: "45.00", limit_operator: "MAX", difference_pct_points: "-17.00", margin_pct_points: "17.00", verdict: "PASS", top_holdings: ["600519.SH"] },
    { sector_key: "TECHNOLOGY", name: "科技", weight_pct: "11.50", limit_pct: "40.00", limit_operator: "MAX", difference_pct_points: "-28.50", margin_pct_points: "28.50", verdict: "PASS", top_holdings: ["300750.SZ"] },
    { sector_key: "FINANCE_CYCLICAL", name: "金融", weight_pct: "14.17", limit_pct: "45.00", limit_operator: "MAX", difference_pct_points: "-30.83", margin_pct_points: "30.83", verdict: "PASS", top_holdings: ["510300.SH"] },
    { sector_key: "BONDS", name: "债券", weight_pct: "17.17", limit_pct: "50.00", limit_operator: "MAX", difference_pct_points: "-32.83", margin_pct_points: "32.83", verdict: "PASS", top_holdings: ["511010.SH"] },
    { sector_key: "CASH", name: "现金", weight_pct: "29.17", limit_pct: "15.00", limit_operator: "MIN", difference_pct_points: "14.17", margin_pct_points: "14.17", verdict: "PASS", top_holdings: [] },
  ];

  const portfolioHealth = {
    status: "PASS", source_exposure_status: "COMPLETE", total_market_value_cny: "600000.00", sector_hhi: "0.2263",
    hhi_limit: "0.3000", hhi_verdict: "PASS", technology_weight_pct: "11.50", technology_limit_pct: "40.00",
    cash_weight_pct: "29.17", cash_minimum_pct: "15.00", has_breaches: false, evidence_count: 7,
    top_sector_key: "CONSUMER_HEALTHCARE", top_sector_name: "消费", top_sector_weight_pct: "28.00",
    sectors: sectorRows, issues: [],
    calculation_steps: [
      "读取当前确认持仓与现金快照。", "将 ETF 底层持仓按覆盖率纳入行业统计。",
      "按总资产口径计算行业权重与 HHI。", "将各项结果与已确认画像边界逐项比较。",
    ],
  };

  const portfolioRefresh = {
    status: "COMPLETE", data_mode: "MOCK", provider: PAGE_MARK, portfolio,
    positions: positions.map(position => ({ asset_id: position.asset_id, status: "COMPLETE", price_cny: position.current_price_cny, observed_at: NOW, source: PAGE_MARK, staleness_seconds: 0, missing_fields: [] })),
    issues: [],
  };

  const summaryPositions = positions.map(position => {
    const value = Number(position.market_value_cny);
    const cost = Number(position.cost_price_cny) * Number(position.quantity);
    const pnl = value - cost;
    const sector = position.asset_id === "600519.SH" ? "消费" : position.asset_id === "300750.SZ" ? "科技" : position.asset_id === "510300.SH" ? "金融" : "债券";
    return {
      asset_id: position.asset_id, name: position.asset_name, quantity: position.quantity, cost_price: position.cost_price_cny,
      price: position.current_price_cny, market_value_cny: value, pnl_cny: pnl, weight_pct: (value / 600000 * 100).toFixed(2),
      sector, asset_class: position.asset_type === "STOCK" ? "STOCK" : "FUND_ETF",
    };
  });

  const portfolioSummary = {
    data_mode: "MOCK", holdings_value_cny: 425000, cash_cny: 175000, daily_pnl_cny: 2650, pnl_cny: 31300, pnl_pct: "7.95",
    position_count: positions.length, positions: summaryPositions,
  };

  const assetStructure = [
    { group_key: "stock", label: "股票", market_value_cny: 237000, weight_pct: "39.50", position_count: 2 },
    { group_key: "etf", label: "ETF", market_value_cny: 188000, weight_pct: "31.33", position_count: 2 },
    { group_key: "cash", label: "现金", market_value_cny: 175000, weight_pct: "29.17", position_count: 1 },
  ];

  const portfolioReport = {
    data_mode: "MOCK", generated_at: NOW, report_id: "pages-demo-report-001", total_value_cny: 600000,
    headline: "当前示例组合的行业集中度与现金比例均处于设定范围内。", holdings_value_cny: 425000, cash_cny: 175000,
    daily_pnl_cny: 2650, cumulative_pnl_cny: 31300, cumulative_pnl_pct: "7.95", position_count: positions.length,
    observations: ["示例组合包含两项股票、两项 ETF 与现金。", "当前行业 HHI 为 0.2263，低于 0.3000 的展示阈值。", "现金比例为 29.17%，高于画像设定的最低比例。"],
    disclosures: ["本报告使用 GitHub Pages 合成示例数据。", "页面不会连接真实行情、账户或模型服务。", "报告用于展示计算路径，不构成投资建议。"],
    asset_structure: assetStructure,
    positions: summaryPositions.map(item => ({
      ...item, asset_name: item.name, position_id: `pages-report-${item.asset_id}`, asset_type: item.asset_class === "STOCK" ? "STOCK" : "ETF",
      cost_price_cny: item.cost_price, current_price_cny: item.price, pnl_pct: item.cost_price ? ((Number(item.price) / Number(item.cost_price) - 1) * 100).toFixed(2) : null,
      diagnosis_status: "PASS", diagnosis: ["当前示例快照字段完整。", "行业分类来自 Pages Mock 示例数据。"],
    })),
    risk: { status: "PASS", sector_hhi: "0.2263", top_sector_name: "消费", sectors: sectorRows, issues: [], cash_weight_pct: "29.17", cash_minimum_pct: "15.00" },
    concentration: { status: "CALCULATED", top_asset_name: "贵州茅台", top_asset_weight_pct: "39.53", asset_hhi: "0.2380", issues: [], single_asset_limit_pct: "45.00", single_asset_verdict: "PASS" },
    pnl_summary: { loss_position_count: 0, loss_weight_pct: "0.00", note: "示例持仓当前没有浮亏标的。" },
    base_protection: { defensive_market_value_cny: 278000, defensive_weight_pct: "46.33", profile_reference_pct: "25.00", reference_verdict: "PASS", components: ["国债ETF", "现金"], note: "防御性资产按债券 ETF 与现金统计。" },
    configuration_reference: ["权益类参考范围：35.00%–70.00%。", "科技行业上限：40.00%。", "现金最低比例：15.00%。"],
    profile: { suitability_level: "C3", equity_weight_pct: "55.00", equity_minimum_pct: "35.00", equity_maximum_pct: "70.00", equity_verdict: "PASS" },
  };

  const marketCatalog = [
    { market: "CN", index_id: "SSE_COMPOSITE", name: "上证指数", symbol: "000001", currency: "CNY", timezone: "Asia/Shanghai", precision: 2, status: "AVAILABLE" },
    { market: "CN", index_id: "CSI300", name: "沪深300", symbol: "000300", currency: "CNY", timezone: "Asia/Shanghai", precision: 2, status: "AVAILABLE" },
    { market: "CN", index_id: "CHINEXT", name: "创业板指", symbol: "399006", currency: "CNY", timezone: "Asia/Shanghai", precision: 2, status: "AVAILABLE" },
    { market: "HK", index_id: "HANG_SENG", name: "恒生指数", symbol: "HSI", currency: "HKD", timezone: "Asia/Hong_Kong", precision: 2, status: "AVAILABLE" },
    { market: "US", index_id: "SP500", name: "标普500", symbol: "SPX", currency: "USD", timezone: "America/New_York", precision: 2, status: "AVAILABLE" },
  ];

  function makeBars(base, step) {
    return Array.from({ length: 24 }, (_, index) => {
      const open = base + index * step;
      const close = open + (index % 4 === 0 ? -step * 0.4 : step * 0.8);
      const high = Math.max(open, close) + step * 1.7;
      const low = Math.min(open, close) - step * 1.2;
      return { time: dateOnly(index), open: open.toFixed(2), high: high.toFixed(2), low: low.toFixed(2), close: close.toFixed(2), volume: 120000000 + index * 3200000, turnover: 180000000000 + index * 4500000000 };
    });
  }

  function addIndicators(bars) {
    return {
      boll: bars.map((bar, index) => ({ time: bar.time, upper: (Number(bar.close) + 36).toFixed(2), middle: Number(bar.close).toFixed(2), lower: (Number(bar.close) - 36).toFixed(2) })),
      macd: bars.map((bar, index) => ({ time: bar.time, diff: (0.12 + index * 0.01).toFixed(2), dea: (0.08 + index * 0.008).toFixed(2), histogram: (0.04 + index * 0.002).toFixed(2) })),
      kdj: bars.map((bar, index) => ({ time: bar.time, k: (52 + index * 0.4).toFixed(2), d: (48 + index * 0.35).toFixed(2), j: (60 + index * 0.5).toFixed(2) })),
    };
  }

  function marketAnalysis(item) {
    const base = item.market === "US" ? 5480 : item.market === "HK" ? 18000 : item.index_id === "CSI300" ? 3850 : 3100;
    const step = item.market === "US" ? 12 : item.market === "HK" ? 38 : 16;
    const bars = makeBars(base, step);
    const last = bars[bars.length - 1];
    return {
      ...item, interval: "1d", status: "CALCULATED", source: PAGE_MARK, history_status: "LIVE", observed_at: NOW,
      price: Number(last.close), change: 18.42, change_pct: 0.61, bars, indicators: addIndicators(bars),
      volume: last.volume, factors: [
        { factor_id: "pages-rate", name: "无风险利率示例", unit: "%", status: "MOCK", source: PAGE_MARK, observed_at: NOW, latest_value: 1.85, change: -0.03, correlation_20: -0.18, correlation_60: -0.11, sample_size: 60 },
        { factor_id: "pages-usd", name: "美元指数示例", unit: "点", status: "MOCK", source: PAGE_MARK, observed_at: NOW, latest_value: 102.4, change: 0.22, correlation_20: -0.24, correlation_60: -0.16, sample_size: 60 },
        { factor_id: "pages-credit", name: "信用利差示例", unit: "bp", status: "MOCK", source: PAGE_MARK, observed_at: NOW, latest_value: 86, change: 1.4, correlation_20: -0.09, correlation_60: -0.05, sample_size: 60 },
      ],
      risk_notice: "市场数据为合成示例，仅用于展示行情卡片、K 线与指标面板。",
    };
  }

  const marketQuotes = marketCatalog.map(item => ({ ...item, price: item.market === "US" ? 5480.15 : item.market === "HK" ? 18042.8 : item.index_id === "CSI300" ? 3862.12 : 3128.41, change_pct: 0.61, status: "LIVE", source: PAGE_MARK, observed_at: NOW }));

  const stockMetrics = [
    { metric: "accounts_receivable_cny", label: "应收账款", unit: "CNY", expected_value: "8.00" },
    { metric: "debt_ratio_pct", label: "资产负债率", unit: "pct", expected_value: "78.00" },
    { metric: "gross_margin_pct", label: "毛利率", unit: "pct", expected_value: "42.00" },
    { metric: "net_profit_cny", label: "净利润", unit: "CNY", expected_value: "2.00" },
    { metric: "operating_cash_flow_cny", label: "经营活动现金流", unit: "CNY", expected_value: "0.50" },
    { metric: "revenue_cny", label: "营业收入", unit: "CNY", expected_value: "10.00" },
  ];
  const fundMetrics = [
    { metric: "annualized_volatility_pct", label: "年化波动率", unit: "pct", expected_value: "28.00" },
    { metric: "expense_ratio_pct", label: "费率", unit: "pct", expected_value: "1.20" },
    { metric: "max_drawdown_pct", label: "最大回撤", unit: "pct", expected_value: "35.00" },
    { metric: "technology_weight_pct", label: "科技行业权重", unit: "pct", expected_value: "68.00" },
    { metric: "top10_weight_pct", label: "前十大持仓权重", unit: "pct", expected_value: "64.00" },
    { metric: "tracking_error_pct", label: "跟踪误差", unit: "pct", expected_value: "2.10" },
  ];
  const bondMetrics = [
    { metric: "bond_floor", label: "债底", unit: "CNY", expected_value: "76.00" },
    { metric: "bond_price", label: "转债价格", unit: "CNY", expected_value: "170.00" },
    { metric: "conversion_premium_pct", label: "转股溢价率", unit: "pct", expected_value: "36.00", derived: true, formula: "(bond_price / conversion_value - 1) * 100" },
    { metric: "conversion_price", label: "转股价", unit: "CNY", expected_value: "10.00" },
    { metric: "conversion_value", label: "转股价值", unit: "CNY", expected_value: "125.00", derived: true, formula: "underlying_stock_price / conversion_price * bond_par_value" },
    { metric: "credit_rating_rank", label: "信用情况（评级序数）", unit: "rating_rank", expected_value: "4" },
    { metric: "liquidity_score", label: "流动性等级序数", unit: "score", expected_value: "3" },
    { metric: "underlying_stock_price", label: "正股价格", unit: "CNY", expected_value: "12.50" },
    { metric: "yield_to_maturity_pct", label: "到期收益率", unit: "pct", expected_value: "-0.50" },
  ];

  const stockRules = [
    { metric: "cashflow_quality_pct", label: "经营现金流质量", operator: "MIN", threshold: "80.00", unit: "pct" },
    { metric: "receivable_ratio_pct", label: "应收账款占比", operator: "MAX", threshold: "60.00", unit: "pct" },
    { metric: "debt_ratio_pct", label: "资产负债率", operator: "MAX", threshold: "70.00", unit: "pct" },
  ];
  const fundRules = [
    { metric: "technology_weight_pct", label: "科技行业权重", operator: "MAX", threshold: "50.00", unit: "pct" },
    { metric: "top10_weight_pct", label: "前十大持仓权重", operator: "MAX", threshold: "60.00", unit: "pct" },
    { metric: "annualized_volatility_pct", label: "年化波动率", operator: "MAX", threshold: "25.00", unit: "pct" },
    { metric: "max_drawdown_pct", label: "最大回撤", operator: "MAX", threshold: "30.00", unit: "pct" },
    { metric: "expense_ratio_pct", label: "费率", operator: "MAX", threshold: "1.00", unit: "pct" },
  ];
  const bondRules = [
    { metric: "conversion_premium_pct", label: "转股溢价率", operator: "MAX", threshold: "30.00", unit: "pct" },
    { metric: "bond_floor", label: "债底", operator: "MIN", threshold: "80.00", unit: "CNY" },
    { metric: "yield_to_maturity_pct", label: "到期收益率", operator: "MIN", threshold: "0.00", unit: "pct" },
    { metric: "credit_rating_rank", label: "信用评级序数", operator: "MIN", threshold: "4", unit: "rating_rank" },
    { metric: "liquidity_score", label: "流动性等级序数", operator: "MIN", threshold: "3", unit: "score" },
  ];

  function templateFor(kind) {
    const base = { generated_at: NOW, budget_ms: 3000, scenarios: clone(scenarios) };
    if (kind === "stock") return { ...base, manifest_id: "pages-stock-manifest-001", subject: "PRISM_STOCK_DEMO_F", period: "2026-Q2", scope_description: "Pages Mock 个股研究示例", metrics: clone(stockMetrics), risk_rules: clone(stockRules) };
    if (kind === "fund") return { ...base, manifest_id: "pages-fund-manifest-001", subject: "PRISM_FUND_DEMO_G", period: "2026-Q2", scope_description: "Pages Mock ETF 研究示例", metrics: clone(fundMetrics), risk_rules: clone(fundRules) };
    return {
      ...base, manifest_id: "pages-bond-manifest-001", subject: "PRISM_CONVERTIBLE_BOND_DEMO_H", period: "2026-Q2", scope_description: "Pages Mock 可转债研究示例",
      bond_par_value: "100", metrics: clone(bondMetrics), risk_rules: clone(bondRules),
      credit_rating_labels: { "1": "AAA", "2": "AA+", "3": "AA", "4": "AA-", "5": "A+" }, liquidity_labels: { "1": "高", "2": "中", "3": "低" },
    };
  }

  function researchTrace(prefix, metrics, period) {
    const evidence = [];
    const facts = [];
    const findings = [];
    metrics.forEach((metric, index) => {
      const factId = `${prefix}-fact-${index + 1}`;
      const evidenceId = `${prefix}-evidence-${index + 1}`;
      evidence.push({ evidence_id: evidenceId, field: metric.metric, source: `${prefix}-source-a`, provider: PAGE_MARK, period, value: metric.expected_value, unit: metric.unit, quality_status: "VERIFIED", lineage_id: `${prefix}-lineage-a` });
      facts.push({ fact_id: factId, metric: metric.metric, value: metric.expected_value, unit: metric.unit, status: "VERIFIED", evidence_ids: [evidenceId] });
      findings.push({ finding_id: `${prefix}-finding-${index + 1}`, kind: metric.finding_kind || `${prefix.toUpperCase()}_FACT`, severity: metric.finding_severity || "INFO", statement: metric.finding_statement || `两条合成来源对${metric.label}给出一致数值。`, fact_ids: [factId], methodology: metric.formula || "两条独立来源一致性核对" });
    });
    return { evidence, facts, findings };
  }

  function researchRun(kind, scenarioId) {
    const template = templateFor(kind);
    const prefix = kind === "stock" ? "pages-stock" : kind === "fund" ? "pages-fund" : "pages-bond";
    const trace = researchTrace(prefix, template.metrics, template.period);
    const nodes = ["a", "b"].map(sourceSlot => ({
      node_id: `${prefix}-source-${sourceSlot}`, role: kind === "stock" ? "STOCK" : kind === "fund" ? "ETF_FUND" : "CONVERTIBLE_BOND", node_kind: "SOURCE",
      subject: template.subject, status: "COMPLETED", source_slot: sourceSlot, issues: [], missing_fields: [], scope_description: "合成来源节点已返回示例字段。",
    }));
    const validations = template.metrics.map((metric, index) => ({
      subject: template.subject, metric: metric.metric, status: "SUPPORTED", expected_value: metric.expected_value, unit: metric.unit, period: template.period,
      independent_lineage_count: 2, supporting_evidence_ids: [trace.evidence[index].evidence_id], contradicting_evidence_ids: [], unresolved_evidence_ids: [], issues: [],
    }));
    return {
      run_id: `${prefix}-run-001`, request_id: `ui-${prefix}-request-001`, manifest_id: template.manifest_id, owner_id: OWNER_ID,
      subject: template.subject, period: template.period, scenario: scenarios.find(item => item.scenario_id === scenarioId) || scenarios[0],
      run_status: "COMPLETED", pipeline_status: "READY", nodes, validations, facts: trace.facts, findings: trace.findings,
      risk: { status: "WATCH", summary: kind === "stock" ? "示例资产负债率高于展示阈值，建议查看来源与规则。" : kind === "fund" ? "示例 ETF 的波动率、行业权重与费用率需要关注。" : "示例可转债的溢价率与负到期收益率需要关注。", issues: [] },
      issues: [], trace,
    };
  }

  const researchMatrixTemplate = {
    schema_version: "research-specialist-matrix-template.v1", matrix_id: "pages-research-matrix-001", owner_id: OWNER_ID,
    generated_at: NOW, scope_description: "Pages Mock 四类来源研究矩阵", roles: ["ETF_FUND", "INDUSTRY", "MACRO", "STOCK"], node_count: 8, scenarios: clone(scenarios),
  };

  const matrixMetrics = [
    { metric: "technology_weight_pct", label: "科技行业权重", unit: "pct", expected_value: "63.50" },
    { metric: "growth_pct", label: "行业增长率", unit: "pct", expected_value: "8.00" },
    { metric: "policy_rate_pct", label: "政策利率", unit: "pct", expected_value: "2.50" },
    { metric: "revenue_cny", label: "营业收入", unit: "CNY", expected_value: "10.00" },
  ];
  const matrixRoles = [
    ["fund-source-a", "ETF_FUND", "PRISM_FUND_DEMO_G"], ["fund-source-b", "ETF_FUND", "PRISM_FUND_DEMO_G"],
    ["industry-source-a", "INDUSTRY", "PRISM_INDUSTRY_DEMO"], ["industry-source-b", "INDUSTRY", "PRISM_INDUSTRY_DEMO"],
    ["macro-source-a", "MACRO", "PRISM_MACRO_DEMO"], ["macro-source-b", "MACRO", "PRISM_MACRO_DEMO"],
    ["stock-source-a", "STOCK", "PRISM_STOCK_DEMO_F"], ["stock-source-b", "STOCK", "PRISM_STOCK_DEMO_F"],
  ];
  function researchMatrixRun(scenarioId) {
    const trace = researchTrace("pages-matrix", matrixMetrics, "2026-Q2");
    return {
      matrix_id: researchMatrixTemplate.matrix_id, run_id: "pages-matrix-run-001", request_id: "ui-research-001", owner_id: OWNER_ID,
      period: "2026-Q2", scenario: scenarios.find(item => item.scenario_id === scenarioId) || scenarios[0], run_status: "COMPLETED", pipeline_status: "READY",
      nodes: matrixRoles.map(([node_id, role, subject]) => ({ node_id, role, node_kind: "SOURCE", subject, status: "COMPLETED", issues: [] })),
      validations: matrixMetrics.map((metric, index) => ({ subject: metric.metric === "revenue_cny" ? "PRISM_STOCK_DEMO_F" : "PRISM_RESEARCH_DEMO", metric: metric.metric, status: "SUPPORTED", expected_value: metric.expected_value, unit: metric.unit, period: "2026-Q2", independent_lineage_count: 2, supporting_evidence_ids: [trace.evidence[index].evidence_id], contradicting_evidence_ids: [], unresolved_evidence_ids: [], issues: [] })),
      trace, issues: [],
    };
  }

  const optimizationTemplate = {
    schema_version: "portfolio-optimization-template.v1", manifest_id: "pages-optimization-template-001", owner_id: OWNER_ID, generated_at: NOW,
    methodology_version: "CAP_AND_REDISTRIBUTE_V1", scope_description: "Pages Mock 组合目标结构示例", questionnaire: clone(questionnaire), portfolio: clone(portfolio),
    rules: [
      { dimension: "ASSET", label: "单资产上限", description: "每个资产的目标权重不得超过画像对应上限。", limit_by_risk_level: { BALANCED: "35" } },
      { dimension: "SECTOR", label: "行业上限", description: "每个行业的目标权重不得超过画像对应上限。", limit_by_risk_level: { BALANCED: "45" } },
      { dimension: "TECHNOLOGY", label: "科技暴露上限", description: "科技暴露受画像风险预算约束。", limit_by_risk_level: { BALANCED: "40" } },
      { dimension: "CASH", label: "现金最低比例", description: "现金比例不得低于画像参考值。", limit_by_risk_level: { BALANCED: "15" } },
    ], scenarios: [scenarios[0], { scenario_id: "INFEASIBLE", label: "约束无法满足", description: "展示目标约束无法同时满足时的提示。" }, { scenario_id: "SOURCE_PARTIAL", label: "来源部分可用", description: "展示穿透覆盖率不足时的提示。" }],
  };

  const scenarioTemplate = {
    schema_version: "scenario-simulation-template.v1", owner_id: OWNER_ID, generated_at: NOW, methodology_version: "SCENARIO_SIMULATION_V1",
    supported_dimensions: ["SECTOR_RETURN", "VOLATILITY", "CASH_WEIGHT", "EQUITY_TARGET"], scenarios: [scenarios[0], { scenario_id: "RATE_UP", label: "利率上行", description: "假设利率上行 50bp，观察组合差分。" }, { scenario_id: "TECH_DROP", label: "科技行业回撤", description: "假设科技行业下跌 12%，观察组合差分。" }, { scenario_id: "CASH_REDUCED", label: "现金比例下降", description: "假设现金比例下降 5 个百分点，观察配置差分。" }],
  };

  const optimizationTargets = [
    { target_id: "600519.SH", asset_name: "贵州茅台", sector: "消费", current_weight_pct: "28.00", target_weight_pct: "25.00", delta_pct: "-3.00", allowed_max_weight_pct: "35.00", rationale: "降低单一股票权重，保留核心消费暴露。" },
    { target_id: "300750.SZ", asset_name: "宁德时代", sector: "科技", current_weight_pct: "11.50", target_weight_pct: "15.00", delta_pct: "+3.50", allowed_max_weight_pct: "35.00", rationale: "在科技行业上限内保留成长暴露。" },
    { target_id: "510300.SH", asset_name: "沪深300ETF", sector: "金融", current_weight_pct: "14.17", target_weight_pct: "20.00", delta_pct: "+5.83", allowed_max_weight_pct: "35.00", rationale: "增加宽基 ETF 以分散单项持仓。" },
    { target_id: "511010.SH", asset_name: "国债ETF", sector: "债券", current_weight_pct: "17.17", target_weight_pct: "20.00", delta_pct: "+2.83", allowed_max_weight_pct: "35.00", rationale: "保持防御性资产比例。" },
  ];
  const optimizationRun = {
    status: "READY", risk_level: "BALANCED", summary: "示例组合目标权重已按画像边界完成确定性计算。", scenario: scenarios[0], methodology_version: "CAP_AND_REDISTRIBUTE_V1",
    profile_id: profile.profile_id, profile_version: profile.profile_version, portfolio_bundle_id: portfolio.bundle_id, position_snapshot_id: portfolio.position_snapshot.snapshot_id,
    exposure_report_id: "pages-exposure-report-001", assessment_id: "pages-risk-assessment-001", assessment_status: "PASS", issues: [], targets: optimizationTargets,
    constraints: [
      { dimension: "ASSET", label: "单资产上限", disposition: "PASS", current_weight_pct: "39.53", target_weight_pct: "25.00", allowed_max_weight_pct: "45.00", delta_pct: "-14.53", rationale: "最高持仓按总资产口径低于展示上限。" },
      { dimension: "SECTOR", label: "行业上限", disposition: "PASS", current_weight_pct: "28.00", target_weight_pct: "25.00", allowed_max_weight_pct: "45.00", delta_pct: "-3.00", rationale: "主要行业权重低于行业上限。" },
      { dimension: "TECHNOLOGY", label: "科技暴露上限", disposition: "PASS", current_weight_pct: "11.50", target_weight_pct: "15.00", allowed_max_weight_pct: "40.00", delta_pct: "+3.50", rationale: "目标科技暴露仍低于画像上限。" },
      { dimension: "CASH", label: "现金最低比例", disposition: "PASS", current_weight_pct: "29.17", target_weight_pct: "20.00", allowed_max_weight_pct: "15.00", delta_pct: "-9.17", rationale: "目标现金比例保留最低现金边界。" },
    ],
    invalidation_conditions: ["画像版本发生变化。", "持仓快照或行情观察时间发生变化。", "行业穿透覆盖率低于当前计算条件。"],
  };

  const scenarioRun = {
    status: "READY", risk_level: "BALANCED", scenario: scenarioTemplate.scenarios[1], assumption: { description: "示例假设：无风险利率上行 50bp。", parameter_name: "rate_delta", delta: "0.50", unit: "%" },
    methodology_version: "SCENARIO_SIMULATION_V1", profile_id: profile.profile_id, profile_version: 1, simulation_id: "pages-simulation-001",
    trace: { input_fingerprint: "pages-demo-input-fingerprint", baseline_run_id: "pages-optimization-run-001", simulated_run_id: "pages-simulated-run-001" }, issues: [],
    metric_diffs: [
      { label: "组合预期波动率", dimension: "VOLATILITY", baseline_value: "12.40", scenario_value: "14.10", delta: "1.70", unit: "%" },
      { label: "现金比例", dimension: "CASH_WEIGHT", baseline_value: "29.17", scenario_value: "29.17", delta: "0.00", unit: "%" },
      { label: "组合情景收益", dimension: "SECTOR_RETURN", baseline_value: "7.95", scenario_value: "5.80", delta: "-2.15", unit: "%" },
    ],
    target_diffs: [
      { asset_name: "贵州茅台", baseline_value: "25.00", scenario_value: "23.00", delta: "-2.00" },
      { asset_name: "国债ETF", baseline_value: "20.00", scenario_value: "22.00", delta: "+2.00" },
    ],
    invalidation_conditions: ["基线组合发生变化。", "假设参数超出支持范围。", "画像风险边界发生变化。"],
  };

  const workflowDefinition = {
    owner_id: OWNER_ID, budget_ms: 3000, nodes: [
      { node_id: "market-source", x: 80, y: 80, dependencies: [] }, { node_id: "portfolio-health", x: 340, y: 80, dependencies: ["market-source"] },
      { node_id: "research-matrix", x: 600, y: 80, dependencies: ["market-source"] }, { node_id: "decision-output", x: 860, y: 80, dependencies: ["portfolio-health", "research-matrix"] },
    ],
  };

  const mockState = {
    preferences: { owner_id: OWNER_ID, theme: "LIGHT", holdings_data_enabled: false, market_data_enabled: true, trading_enabled: false, updated_at: NOW },
    memories: [{ memory_id: "pages-memory-001", owner_id: OWNER_ID, saved_at: NOW, source: "EXPLICIT_SAVE", profile: clone(profile), questionnaire: clone(questionnaire), portfolio: clone(portfolio), content_hash: "pages-demo-content-hash", references: {} }],
    modeRevision: 1, workflowRevision: 1, workflowDefinition: clone(workflowDefinition), trades: [],
  };

  const queryTemplate = {
    schema_version: "advisor-query-template.v1", fixture_id: "pages-demo-query-template-001", generated_at: NOW,
    owner_id: OWNER_ID, questionnaire: clone(questionnaire), portfolio: clone(portfolio),
  };

  const tradingStyleProfile = {
    status: "CALCULATED", primary_style: "稳健成长", confidence: "0.86",
    metrics: { trades_per_month: "3.2", trade_count: 18, observed_span_days: 180, median_holding_days: "42", matched_sell_coverage: "0.83", median_trade_amount_cny: "18500", symbol_hhi: "0.24", top3_symbol_share_pct: "64.00", turnover_90d_pct: "18.00" },
    data_gaps: [], active_trade_ids: [],
  };

  const evaluationSummary = {
    summary: { case_pass_rate_pct: "92.00", profile_alignment_rate_pct: "96.00", evidence_coverage_rate_pct: "100.00", hallucination_rate_pct: "0.00", risk_detection_rate_pct: "88.00" },
    latency: { p50_ms: 48 },
    cases: [
      { case_id: "pages-eval-001", title: "组合集中度检查", expected_status: "PASS", actual_status: "PASS", latency_ms: 42, passed: true },
      { case_id: "pages-eval-002", title: "来源证据闭合", expected_status: "PASS", actual_status: "PASS", latency_ms: 51, passed: true },
      { case_id: "pages-eval-003", title: "超出风险边界提示", expected_status: "REVIEW_REQUIRED", actual_status: "REVIEW_REQUIRED", latency_ms: 56, passed: true },
    ],
  };

  const recommendationEvent = {
    event_id: "pages-event-001", owner_id: OWNER_ID, status: "PASS", created_at: NOW, query_id: "pages-demo-query-001",
    summary: "示例组合保持当前结构，建议继续关注行业集中度与现金比例。",
    result: {
      receipt: { profile_id: profile.profile_id, profile_version: profile.profile_version, portfolio_bundle_id: portfolio.bundle_id, position_snapshot_id: portfolio.position_snapshot.snapshot_id, risk_assessment_id: "pages-risk-assessment-001", allocation_envelope_id: "pages-allocation-envelope-001", research_run_id: "pages-research-run-001" },
      issues: [],
      trace: {
        evidence: [
          { evidence_id: "pages-advisor-evidence-001", source: "ADVISOR", provider: PAGE_MARK, field: "sector_hhi", period: "2026-Q2", value: "0.2263", unit: "ratio", quality_status: "VERIFIED", lineage_id: "pages-advisor-lineage-001" },
          { evidence_id: "pages-advisor-evidence-002", source: "ADVISOR", provider: PAGE_MARK, field: "cash_weight_pct", period: "2026-Q2", value: "29.17", unit: "pct", quality_status: "VERIFIED", lineage_id: "pages-advisor-lineage-002" },
        ],
        facts: [
          { fact_id: "pages-advisor-fact-001", metric: "sector_hhi", value: "0.2263", unit: "ratio", evidence_ids: ["pages-advisor-evidence-001"] },
          { fact_id: "pages-advisor-fact-002", metric: "cash_weight_pct", value: "29.17", unit: "pct", evidence_ids: ["pages-advisor-evidence-002"] },
        ],
        findings: [{ finding_id: "pages-advisor-finding-001", kind: "PORTFOLIO_HEALTH", statement: "行业集中度低于示例阈值，现金比例高于最低边界。", fact_ids: ["pages-advisor-fact-001", "pages-advisor-fact-002"] }],
        recommendations: [{ recommendation_id: "pages-recommendation-001", asset_id: "PORTFOLIO", action_type: "HOLD", allocation_range: { minimum_pct: "35.00", maximum_pct: "70.00" }, finding_ids: ["pages-advisor-finding-001"], invalidation_conditions: ["画像版本发生变化。", "持仓快照发生变化。"] }],
      },
    },
  };

  function dataModePayload() {
    return {
      status: "SUCCESS", data: {
        data_mode: "MOCK", revision: mockState.modeRevision, live_ready: false, live_configured: false,
        wencai_ready: false, wencai_configured: false, wencai_capability_status: { last_error_code: null }, live_readiness_issues: ["GitHub Pages 仅展示合成数据。"],
        capabilities: {
          MOCK: { stock_quote: true, fund_lookthrough: true, semantic_search: true, portfolio_refresh: true },
          LIVE: { stock_quote: false, fund_lookthrough: false, semantic_search: false, portfolio_refresh: false },
        },
      },
    };
  }

  function sessionTruth() {
    return {
      status: "LOCKED", revision: 1,
      record: { facts: { data_mode: "MOCK", profile: clone(profile), portfolio: clone(portfolio) } },
      current_fingerprint: "pages-demo-fingerprint", current_facts: { data_mode: "MOCK", profile_id: profile.profile_id, portfolio_bundle_id: portfolio.bundle_id },
    };
  }

  function portfolioValidation(payload = {}) {
    const supplied = Array.isArray(payload.positions) && payload.positions.length ? payload.positions : positions;
    return {
      status: "SUCCESS", data_mode: "MOCK", positions: clone(supplied), cash_cny: payload.cash_cny || 175000, total_value_cny: 600000,
      portfolio: clone(portfolio), issues: [],
    };
  }

  function planResult(payload = {}) {
    return {
      plan_id: "pages-plan-001", intent_type: payload.intent_type || "PORTFOLIO_REVIEW", intent_id: payload.intent_id || "pages-intent-001", owner_id: OWNER_ID,
      portfolio_bundle_id: portfolio.bundle_id, position_snapshot_id: portfolio.position_snapshot.snapshot_id, questionnaire_id: questionnaire.questionnaire_id,
      scope_description: "组合健康度、研究矩阵与风险边界示例流程。", node_count: 8, roles: ["ETF_FUND", "INDUSTRY", "MACRO", "STOCK"],
    };
  }

  function devAssistResult() {
    return {
      status: "CALCULATED", conflicts: [], gaps: ["Pages 演示不会将生成内容写入仓库。"], improved_technical_spec: "使用静态页面展示确定性 Mock 接口；真实账户、真实行情与模型服务在公开页面中保持关闭。",
      api_drafts: [{ method: "GET", path: "/api/v1/advisor/portfolio/summary", purpose: "读取组合摘要" }, { method: "POST", path: "/api/v1/advisor/research-runs", purpose: "运行研究矩阵" }],
      skeleton_files: [{ path: "pages-mock.js", content: "只读 Mock API 适配层" }],
    };
  }

  function customStressResult() {
    return {
      status: "CALCULATED", methodology: "确定性行业冲击计算", scenario_return_pct: "-7.80", scenario_pnl_cny: "-46800",
      baseline_volatility_pct: "12.40", stressed_volatility_pct: "18.20", volatility_change_pct_points: "5.80",
      baseline_var_95_1d_cny: "12000", stressed_var_95_1d_cny: "17600", var_change_cny: "5600",
    };
  }

  function stockQuote(symbol) {
    const clean = String(symbol || "600519").replace(/\.(SH|SZ|BJ)$/i, "");
    const known = { "600519": ["贵州茅台", 1680, 1.25], "300750": ["宁德时代", 230, -0.42], "002594": ["比亚迪", 268.5, 0.88], "688256": ["寒武纪", 415.2, 2.31] };
    const item = known[clean] || ["示例证券", 128.6, 0.72];
    return { data: { name: item[0], symbol: clean, price_cny: item[1], change_pct: item[2], pe_ttm: "24.80", pb: "3.20", roe_pct: "14.60", gross_margin_pct: "42.00", debt_ratio_pct: "48.00", observed_at: NOW, financial_report_period: "2026-Q2", financial_report_date: "2026-08-31", source: PAGE_MARK, financial_source: PAGE_MARK, valuation_observed_at: NOW, financial_issues: [] } };
  }

  function stockDeepReport(symbol) {
    const clean = String(symbol || "600519").replace(/\.(SH|SZ|BJ)$/i, "");
    const section = (data, missing_fields = [], issues = []) => ({ status: "READY", data, missing_fields, issues });
    return {
      status: "READY", security: { symbol: clean, name: clean === "300750" ? "宁德时代" : "示例证券", observed_at: NOW },
      observations: { supporting_facts: ["行情与财务指标均来自 Pages Mock。"], risk_facts: ["示例财务指标需要结合期间与来源继续核验。"], watch_items: ["估值与行业景气变化。"] },
      sections: {
        performance: section({ revenue_cny: "10.00", net_profit_cny: "2.00", gross_margin_pct: "42.00" }),
        fundamentals: section({ operating_cash_flow_cny: "0.50", debt_ratio_pct: "78.00", accounts_receivable_cny: "8.00" }),
        valuation: section({ pe_ttm: "24.80", pb: "3.20", roe_pct: "14.60" }),
        evidence: section({ source: PAGE_MARK, period: "2026-Q2", evidence_count: 6 }),
        portfolio_fit: section({ fit: "适合用于展示组合中单项资产的研究入口。", risk_level: "BALANCED" }),
      },
      issues: [],
    };
  }

  function fundQuote(fundCode) {
    const code = String(fundCode || "510300").replace(/\.(SH|SZ|BJ)$/i, "");
    return { data: { fund_name: code === "511010" ? "国债ETF" : "沪深300ETF", fund_code: code, holding_disclosure_as_of: "2026-06-30", observed_at: NOW, source: PAGE_MARK, top_holdings: code === "511010" ? [{ asset_id: "CGB-2028-01", name: "国债 2028-01", weight_pct: "57.00", sector: "债券" }, { asset_id: "CGB-2030-02", name: "国债 2030-02", weight_pct: "43.00", sector: "债券" }] : [{ asset_id: "600036.SH", name: "招商银行", weight_pct: "5.80", sector: "金融" }, { asset_id: "600519.SH", name: "贵州茅台", weight_pct: "4.20", sector: "消费" }, { asset_id: "300750.SZ", name: "宁德时代", weight_pct: "3.10", sector: "科技" }] } };
  }

  function extractionResult() {
    const extraction = { extraction_id: "pages-extraction-001", confidence: "0.94", input_digest: "pages-demo-input", investment_horizon: "MEDIUM", liquidity_need: "MEDIUM", max_drawdown_tolerance_pct: "15" };
    return { status: "REQUIRES_CONFIRMATION", extraction, evidence: [{ field: "investment_horizon", value: "MEDIUM", quote: "希望保持中期投资安排", confidence: "0.94" }, { field: "max_drawdown_tolerance_pct", value: "15", quote: "希望把回撤控制在 15% 以内", confidence: "0.91" }], warnings: ["提取结果只用于生成待确认提案。"] };
  }

  function workflowResult() {
    return { revision: mockState.workflowRevision, definition: clone(mockState.workflowDefinition), catalog: [{ node_id: "market-source", role: "MARKET" }, { node_id: "portfolio-health", role: "PORTFOLIO" }, { node_id: "research-matrix", role: "RESEARCH" }, { node_id: "decision-output", role: "DECISION" }], data_mode: "MOCK", is_synthetic: true, boundary: "Pages Mock 演示" };
  }

  function workflowRunResult() {
    return { data_mode: "MOCK", result: { execution: { state: { status: "COMPLETED", nodes: mockState.workflowDefinition.nodes.map(node => ({ node_id: node.node_id, status: "COMPLETED", attempt: 1 })) } } } };
  }

  function tradePreview() {
    const row = { row_number: 2, status: "PASS", issues: [], raw_values: { traded_at: "2026-08-20 10:00:00", security_code: "600519", security_name: "贵州茅台", side: "买入", quantity: "100", price_cny: "1600", gross_amount_cny: "160000" }, proposed: { traded_at: "2026-08-20T10:00:00Z", security_code: "600519", security_name: "贵州茅台", side: "BUY", quantity: "100", price_cny: "1600", gross_amount_cny: "160000", currency: "CNY" }, confidence: "0.96" };
    return { source_type: "CSV", source_digest: "pages-trade-digest", file_count: 1, sheets: ["交易记录"], selected_sheet: "交易记录", detected_columns: ["traded_at", "security_code", "security_name", "side", "quantity", "price_cny", "gross_amount_cny"], suggested_mapping: { traded_at: "traded_at", security_code: "security_code", security_name: "security_name", side: "side", quantity: "quantity", price_cny: "price_cny", gross_amount_cny: "gross_amount_cny" }, rows: [row], accepted_count: 1, review_count: 0 };
  }

  async function readJson(request) {
    const contentType = request.headers.get("content-type") || "";
    return contentType.includes("application/json") ? request.json() : {};
  }

  async function handleRequest(request, url) {
    const path = url.pathname;
    const method = request.method.toUpperCase();

    if (path === "/api/health") return jsonResponse({ status: "ok", data_mode: "MOCK" });
    if (path === "/api/v1/auth/context") return jsonResponse({ enabled: false, admin: false });
    if (path === "/api/v1/advisor/session-truth" && method === "GET") return jsonResponse(sessionTruth());
    if (path === "/api/v1/advisor/session-truth" && method === "POST") return jsonResponse(sessionTruth());
    if (path === "/api/v1/advisor/session-truth/check") return jsonResponse({ status: "PASS", revision: 1, results: [] });

    if (path === "/api/v1/runtime/data-mode" && method === "GET") return jsonResponse(dataModePayload());
    if (path === "/api/v1/runtime/data-mode" && method === "PUT") return jsonResponse(dataModePayload());
    if (path === "/api/v1/runtime/provider-query") return jsonResponse({ status: "MOCK", data_mode: "MOCK", message: "GitHub Pages 使用合成示例数据。", data: {} });
    if (path === "/api/v1/user/preferences" && method === "GET") return jsonResponse(clone(mockState.preferences));
    if (path === "/api/v1/user/preferences" && method === "PUT") {
      const payload = await readJson(request);
      mockState.preferences = { ...mockState.preferences, ...payload, updated_at: NOW, owner_id: OWNER_ID, holdings_data_enabled: false, market_data_enabled: true, trading_enabled: false };
      return jsonResponse(clone(mockState.preferences));
    }
    if (path === "/api/v1/user/model-settings" && method === "GET") return jsonResponse({ is_configured: false, connection_verified: false, base_url: "https://api.deepseek.com/v1", model: "deepseek-chat", persistence: "SESSION", provider: "deepseek" });
    if (path === "/api/v1/user/model-settings" && (method === "PUT" || method === "DELETE")) return jsonResponse({ is_configured: false, connection_verified: false, base_url: "https://api.deepseek.com/v1", model: "deepseek-chat", persistence: "SESSION", provider: "deepseek" });
    if (path === "/api/v1/user/model-settings/test") return jsonResponse({ status: "SUCCESS", connection_verified: false, message: "Pages Mock 不连接模型服务。" });

    if (path === "/api/v1/advisor/profile/questionnaire-template") return jsonResponse(clone(questionnaireTemplate));
    if (path === "/api/v1/advisor/profile/summary") return jsonResponse(clone(profileSummary));
    if (path === "/api/v1/advisor/profile/questionnaire/preview") return jsonResponse({ status: "PASS", snapshot: clone(questionnaireSnapshot), presentation: clone(presentation) });
    if (path === "/api/v1/advisor/profile/questionnaire/confirm") return jsonResponse({ status: "PASS", snapshot: clone(questionnaireSnapshot), presentation: clone(presentation) });
    if (path === "/api/v1/advisor/behavior/profile") return jsonResponse({ profile: clone(behaviorProfile) });
    if (path === "/api/v1/advisor/behavior/recompute") return jsonResponse({ status: "SUCCESS", profile: clone(behaviorProfile) });
    if (path === "/api/v1/advisor/display-policy") return jsonResponse({ status: "SUCCESS", policy: { trust_score: 50, mode: "STANDARD" } });
    if (path === "/api/v1/advisor/profile-extractions") return jsonResponse(extractionResult());
    if (path === "/api/v1/advisor/profile-proposals") return jsonResponse({ status: "REQUIRES_CONFIRMATION", draft: { draft_id: "pages-profile-draft-001", owner_id: OWNER_ID, status: "REQUIRES_CONFIRMATION", extraction: extractionResult().extraction, conflicts: [] } });
    if (path === "/api/v1/advisor/profile-proposals/confirm") return jsonResponse({ status: "PASS", profile: clone(profile) });

    if (path === "/api/v1/advisor/query-template") return jsonResponse(clone(queryTemplate));
    if (path === "/api/v1/advisor/context/profile") return jsonResponse({ owner_id: OWNER_ID, questionnaire: clone(questionnaire), profile: clone(profile), data_mode: "MOCK" });
    if (path === "/api/v1/advisor/context/portfolio") return jsonResponse({ owner_id: OWNER_ID, portfolio: clone(portfolio), data_mode: "MOCK" });
    if (path === "/api/v1/advisor/plans") return jsonResponse(planResult(await readJson(request)));
    if (path === "/api/v1/advisor/queries") return jsonResponse({ status: "PASS", created: true, event: clone(recommendationEvent) });
    if (path === "/api/v1/decision-events" && method === "GET") return jsonResponse({ items: mockState.lastEvent ? [clone(mockState.lastEvent)] : [] });
    if (path.startsWith("/api/v1/decision-events/") && method === "GET") return jsonResponse(clone(mockState.lastEvent || recommendationEvent));

    if (path === "/api/v1/advisor/context-memory" && method === "GET") return jsonResponse({ owner_id: OWNER_ID, records: clone(mockState.memories) });
    if (path === "/api/v1/advisor/context-memory" && method === "POST") return jsonResponse({ created: true, record: clone(mockState.memories[0]) });
    if (path === "/api/v1/advisor/context-memory/search") return jsonResponse({ mode: "LIMITED_KEYWORD_MATCH", matches: clone(mockState.memories), notice: "Pages Mock 仅展示一条示例记忆。" });

    if (path === "/api/v1/advisor/trading-style/profile") return jsonResponse({ profile: clone(tradingStyleProfile) });
    if (path === "/api/v1/advisor/trading-history/trades") return jsonResponse({ items: clone(mockState.trades), next_cursor: null, total: mockState.trades.length });
    if (path === "/api/v1/advisor/trading-history/import/preview") return jsonResponse(tradePreview());
    if (path === "/api/v1/advisor/trading-history/imports") return jsonResponse({ batch: { duplicate_count: 0 }, style_profile: clone(tradingStyleProfile) });
    if (path.includes("/api/v1/advisor/trading-history/trades/") && method === "PATCH") return jsonResponse({ status: "SUCCESS", style_profile: clone(tradingStyleProfile) });
    if (path.includes("/api/v1/advisor/trading-history/trades/") && (method === "DELETE" || path.endsWith("/restore"))) return jsonResponse({ status: "SUCCESS", style_profile: clone(tradingStyleProfile) });

    if (path === "/api/v1/market/catalog") return jsonResponse(clone(marketCatalog));
    if (path.startsWith("/api/v1/market/quotes/")) {
      const region = path.split("/").pop();
      return jsonResponse(clone(marketQuotes.filter(item => item.market === region)));
    }
    if (path.startsWith("/api/v1/market/analysis/")) {
      const parts = path.split("/");
      const market = parts[5] || "CN";
      const indexId = decodeURIComponent(parts[6] || "SSE_COMPOSITE");
      const item = marketCatalog.find(candidate => candidate.market === market && candidate.index_id === indexId) || marketCatalog[0];
      return jsonResponse(marketAnalysis(item));
    }
    if (path === "/api/v1/market/industries") return jsonResponse({ status: "AVAILABLE", source: PAGE_MARK, message: "行业数据为合成示例。", rows: [{ name: "消费", day_pct: "0.82", five_day_pct: "1.40", twenty_day_pct: "3.26", as_of: NOW.slice(0, 10) }, { name: "科技", day_pct: "-0.35", five_day_pct: "2.10", twenty_day_pct: "5.40", as_of: NOW.slice(0, 10) }, { name: "金融", day_pct: "0.28", five_day_pct: "0.76", twenty_day_pct: "1.84", as_of: NOW.slice(0, 10) }] });

    if (path === "/api/v1/advisor/portfolio/current" && method === "GET") return jsonResponse({ data_mode: "MOCK", data: { positions: clone(positions), cash_cny: 175000, total_value_cny: 600000, portfolio: clone(portfolio) } });
    if (path === "/api/v1/advisor/portfolio/current" && method === "PUT") return jsonResponse({ data_mode: "MOCK", data: { positions: clone(positions), cash_cny: 175000, total_value_cny: 600000, portfolio: clone(portfolio) } });
    if (path === "/api/v1/advisor/portfolio/refresh") return jsonResponse(clone(portfolioRefresh));
    if (path === "/api/v1/advisor/portfolio-health") return jsonResponse(clone(portfolioHealth));
    if (path === "/api/v1/advisor/portfolio/summary") return jsonResponse(clone(portfolioSummary));
    if (path === "/api/v1/advisor/portfolio/report") return jsonResponse(clone(portfolioReport));
    if (path === "/api/v1/advisor/portfolio/ocr") return jsonResponse({ ...portfolioValidation(), status: "SUCCESS" });
    if (path === "/api/v1/advisor/portfolio/ocr/confirm" || path === "/api/v1/copilot/validate-portfolio-ocr") return jsonResponse(portfolioValidation(await readJson(request)));
    if (path === "/api/v1/copilot/parse-portfolio") return jsonResponse({ status: "SUCCESS", positions: clone(positions), cash_cny: 175000, total_value_cny: 600000 });

    if (path === "/api/v1/advisor/research-matrix-template") return jsonResponse(clone(researchMatrixTemplate));
    if (path === "/api/v1/advisor/research-runs") return jsonResponse(researchMatrixRun((await readJson(request)).scenario_id));
    if (path === "/api/v1/advisor/stock-research-template") return jsonResponse(templateFor("stock"));
    if (path === "/api/v1/advisor/stock-research-runs") return jsonResponse(researchRun("stock", (await readJson(request)).scenario_id));
    if (path === "/api/v1/advisor/fund-research-template") return jsonResponse(templateFor("fund"));
    if (path === "/api/v1/advisor/fund-research-runs") return jsonResponse(researchRun("fund", (await readJson(request)).scenario_id));
    if (path === "/api/v1/advisor/convertible-bond-research-template") return jsonResponse(templateFor("bond"));
    if (path === "/api/v1/advisor/convertible-bond-research-runs") return jsonResponse(researchRun("bond", (await readJson(request)).scenario_id));
    if (path === "/api/v1/advisor/portfolio-optimization-template") return jsonResponse(clone(optimizationTemplate));
    if (path === "/api/v1/advisor/portfolio-optimization-runs") return jsonResponse(clone(optimizationRun));
    if (path === "/api/v1/advisor/scenario-simulation-template") return jsonResponse(clone(scenarioTemplate));
    if (path === "/api/v1/advisor/scenario-simulation-runs") return jsonResponse(clone(scenarioRun));
    if (path === "/api/v1/advisor/rebalancing-runs") return jsonResponse({ status: "PASS", metrics: { total_portfolio_value_cny: "600000.00", total_turnover_pct: "8.20", total_buy_cny: "52500.00", total_sell_cny: "18000.00", net_turnover_cost: "96.00", net_turnover_cost_pct: "0.02", turnover_cap_breached: false }, actions: [{ asset_id: "510300.SH", asset_name: "沪深300ETF", current_weight_pct: "14.17", target_weight_pct: "20.00", delta_weight_pct: "5.83", cash_delta_cny: "34980.00", action_type: "BUY", rationale: "提高宽基资产比例。" }, { asset_id: "600519.SH", asset_name: "贵州茅台", current_weight_pct: "28.00", target_weight_pct: "25.00", delta_weight_pct: "-3.00", cash_delta_cny: "-18000.00", action_type: "SELL", rationale: "降低单一标的集中度。" }], execution_steps: [{ step_number: 1, action_type: "SELL", asset_name: "贵州茅台", amount_cny: "18000.00", description: "先卖出超出目标权重的示例持仓。", shares: "10", total_fees_cny: "18.00" }, { step_number: 2, action_type: "BUY", asset_name: "沪深300ETF", amount_cny: "34980.00", description: "再买入宽基 ETF 示例持仓。", shares: "8200", total_fees_cny: "34.98" }], issues: [], post_trade_health: { status: "PASS", cash_weight_pct: "20.00", cash_minimum_pct: "15.00", sector_hhi: "0.2100", hhi_limit: "0.3000" } });
    if (path === "/api/v1/advisor/recommendation-history" && method === "GET") return jsonResponse({ total_count: 1, items: [{ action_type: "HOLD", asset: "组合", status: "PASS", risk_score: 58, recorded_at: NOW, receipt_id: "pages-event-001", content_hash: "pages-history-hash" }] });
    if (path === "/api/v1/advisor/recommendation-history/compare") return jsonResponse({ action_transition: "HOLD → HOLD", summary: "示例版本之间的风险边界保持一致。" });
    if (path === "/api/v1/advisor/evaluation-dashboard-summary") return jsonResponse(clone(evaluationSummary));
    if (path === "/api/v1/advisor/evaluation-dashboard-runs") return jsonResponse({ status: "COMPLETED", ...clone(evaluationSummary) });
    if (path === "/api/v1/advisor/custom-stress-scenarios") return jsonResponse(customStressResult());
    if (path === "/api/v1/dev-assist/runs") return jsonResponse(devAssistResult());

    if (path === "/api/v1/advisor/workflow" && method === "GET") return jsonResponse(workflowResult());
    if (path === "/api/v1/advisor/workflow" && method === "POST") {
      const payload = await readJson(request);
      if (payload.definition) mockState.workflowDefinition = payload.definition;
      mockState.workflowRevision += 1;
      return jsonResponse(workflowResult());
    }
    if (path === "/api/v1/advisor/workflow-runs") return jsonResponse(workflowRunResult());

    if (path === "/api/v1/copilot/live-quote") return jsonResponse(stockQuote(url.searchParams.get("symbol")));
    if (path === "/api/v1/copilot/live-fund") return jsonResponse(fundQuote(url.searchParams.get("fund_code")));
    if (path === "/api/v1/copilot/auto-index-security") return jsonResponse({ status: "SUCCESS", data_mode: "MOCK", security: stockQuote(url.searchParams.get("symbol")).data });
    if (path === "/api/v1/copilot/stock-analysis") return jsonResponse(stockDeepReport(url.searchParams.get("symbol")));
    if (path === "/api/v1/copilot/chat") return sseResponse([
      { type: "analysis_context", display_policy: { trust_score: 50, mode: "STANDARD" }, profile_version: 1, owner_id: OWNER_ID, facts: ["GitHub Pages 使用合成画像与示例持仓"], thresholds: ["仅供演示"], evidence: ["pages-demo-evidence"], warnings: ["当前页面不会连接后端或真实数据源"] },
      { type: "thinking" }, { type: "token", delta: "## Pages 演示回复\n\n当前页面使用 **Mock 数据** 展示组合、行情与研究流程。页面中的数字只用于说明界面与计算路径。" }, { type: "done" },
    ]);

    if (path === "/api/v1/auth/change-password" || path === "/api/v1/auth/logout") return jsonResponse({ status: "SUCCESS" });
    return jsonResponse({ status: "SUCCESS", data_mode: "MOCK", data: {}, message: "Pages Mock 已接收此演示请求。" });
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url, window.location.href);
    if (!url.pathname.startsWith("/api")) return originalFetch(input, init);
    if (url.pathname === "/api/v1/advisor/queries" && request.method === "POST") mockState.lastEvent = clone(recommendationEvent);
    return handleRequest(request, url);
  };
})();
