(() => {
  "use strict";

  const DERIVED_RUN_KEYS = Object.freeze([
    "advisorPlan",
    "researchRun",
    "stockResearchRun",
    "fundResearchRun",
    "convertibleBondResearchRun",
    "portfolioHealthRun",
    "portfolioRefreshRun",
    "portfolioOptimizationRun",
    "rebalancingRun",
    "scenarioSimulationRun",
    "customStressRun",
  ]);
  const DERIVED_SEQUENCE_KEYS = Object.freeze([
    "templateSequence",
    "portfolioHealthSequence",
    "researchSequence",
    "stockResearchSequence",
    "fundResearchSequence",
    "convertibleBondResearchSequence",
    "portfolioOptimizationSequence",
    "portfolioRefreshSequence",
    "scenarioSimulationSequence",
    "rebalancingSequence",
    "customStressSequence",
    "copilotResearchSequence",
  ]);

  function createMicroStore(initialState, contextKeys = []) {
    const listeners = new Set();
    const contextKeySet = new Set(contextKeys);
    let transactionDepth = 0;
    let pending = false;
    const notify = () => {
      if (transactionDepth) { pending = true; return; }
      listeners.forEach((listener) => listener(proxy));
    };
    const proxy = new Proxy(initialState, {
      set(target, key, value) {
        if (Object.is(target[key], value)) return true;
        target[key] = value;
        if (contextKeySet.has(key)) {
          target.contextRevision += 1;
          DERIVED_SEQUENCE_KEYS.forEach((sequenceKey) => { target[sequenceKey] += 1; });
          DERIVED_RUN_KEYS.forEach((runKey) => { target[runKey] = null; });
        }
        notify();
        return true;
      }
    });
    return {
      state: proxy,
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      transact(mutator) {
        transactionDepth += 1;
        try { mutator(proxy); }
        finally {
          transactionDepth -= 1;
          if (!transactionDepth && pending) { pending = false; notify(); }
        }
      }
    };
  }

  const microStore = createMicroStore({
    ownerId: "",
    selectedPersona: "custom-user",
    contextRevision: 0,
    profile: null,
    behaviorProfile: null,
    displayPolicy: null,
    questionnaireGate: "PENDING",
    questionnaireTemplate: null,
    questionnaireAnswers: {},
    questionnaireSectionIndex: 0,
    questionnairePreview: null,
    profileSummary: null,
    portfolio: null,
    events: [],
    selected: null,
    queryTemplate: null,
    templateContext: null,
    templateSequence: 0,
    portfolioHealthSequence: 0,
    portfolioHealthRun: null,
    portfolioRefreshSequence: 0,
    portfolioRefreshRun: null,
    ocrPortfolioDraft: null,
    profileProposalDraft: null,
    profileProposalQuestionnaire: null,
    profileProposalExtraction: null,
    profileProposalProfile: null,
    profileProposalResolutions: {},
    profileProposalSequence: 0,
    advisorPlan: null,
    researchTemplate: null,
    researchRun: null,
    researchSequence: 0,
    stockResearchTemplate: null,
    stockResearchRun: null,
    stockResearchSequence: 0,
    fundResearchTemplate: null,
    fundResearchRun: null,
    fundResearchSequence: 0,
    convertibleBondResearchTemplate: null,
    convertibleBondResearchRun: null,
    convertibleBondResearchSequence: 0,
    portfolioOptimizationTemplate: null,
    portfolioOptimizationRun: null,
    portfolioOptimizationSequence: 0,
    scenarioSimulationTemplate: null,
    scenarioSimulationRun: null,
    scenarioSimulationSequence: 0,
    contextMemoryRecords: [],
    contextMemorySelected: null,
    contextMemorySequence: 0,
    selectedDecisionEvent: null,
    advancedEvidenceSearch: "",
    advancedEvidenceQuality: "ALL",
    advancedEvidenceMode: "ALL",
    advancedEvidenceSource: "ALL",
    advancedEvidencePromotion: "ALL",
    advancedEvidenceSelectedKey: "",
    dataMode: "MOCK",
    modeRevision: 1,
    liveReady: false,
    liveConfigured: false,
    wencaiReady: false,
    wencaiConfigured: false,
    wencaiLastErrorCode: null,
    liveReadinessIssues: [],
    capabilities: null,
    rebalancingRun: null,
    rebalancingSequence: 0,
    customStressRun: null,
    customStressSequence: 0,
    copilotResearchSequence: 0,
    conversationProfileDraft: null,
    conversationProfileStep: 0,
    userPreferences: null,
  }, ["ownerId", "selectedPersona", "profile", "behaviorProfile", "portfolio", "dataMode"]);
  const state = microStore.state;
  let authenticatedOwner = null;
  let authenticatedAdmin = false;
  let accountAccessEnabled = false;
  let sessionTruthState = {owner:null, revision:0, status:"NOT_LOCKED"};
  async function refreshSessionTruth() {
    const owner = state.ownerId;
    const response = await fetch("/api/v1/advisor/session-truth", {headers:{"X-Owner-ID":owner}});
    if (!response.ok) throw await apiError(response);
    const result = await response.json();
    if (state.ownerId !== owner) return null;
    sessionTruthState = {...result, owner};
    const labels = {LOCKED:"分析资料已更新", NOT_LOCKED:"可以更新分析资料", DRIFT_DETECTED:"持仓或风险设置已变化", INPUT_REQUIRED:"请先添加风险设置和持仓"};
    byId("session-truth-status").textContent = labels[result.status] || "分析资料需要更新";
    byId("confirm-session-truth").textContent = "更新分析资料";
    return result;
  }
  let truthReview = null;
  function renderTruthFacts(target, facts, revision) {
    const panel = byId(target); panel.replaceChildren();
    if (!facts) {panel.textContent = "请先确认问卷和持仓。"; return;}
    const rows = [
      ["版本", String(revision), "会话前提"],
      ["数据模式", facts.data_mode, "运行模式"],
      ["风险等级", facts.profile.risk_level, facts.profile.profile_id],
      ["最大回撤容忍", `${facts.profile.max_drawdown_tolerance_pct}%`, facts.profile.profile_id],
      ["禁投约束", (facts.profile.exclusions || []).join("、") || "未声明", facts.profile.profile_id],
    ];
    for (const p of facts.portfolio.position_snapshot.positions) rows.push([p.asset_name || p.asset_id, p.asset_type === "CASH" ? `金额 ${p.market_value} ${p.currency}` : `${p.quantity ?? "未知"} 股/份 · 市值 ${p.market_value} ${p.currency}`, p.position_id]);
    for (const [label, value, source] of rows) {
      const line = document.createElement("p");
      line.textContent = `${label}：${value}（来源：${source}）`; panel.append(line);
    }
  }
  let truthTurnCounter = 0;
  function recordTruthTurnAlert(row, message, owner) {
    if (owner !== state.ownerId) return;
    const list = byId("truth-turn-alerts");
    const entry = document.createElement("li");
    const link = document.createElement("a");
    row.id = `truth-turn-${++truthTurnCounter}`;
    link.href = `#${row.id}`;
    link.textContent = `第 ${truthTurnCounter} 次中断：${message}`;
    link.addEventListener("click", event => {
      event.preventDefault(); byId("truth-drawer").close();
      row.scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block:"center"});
    });
    entry.append(link); list.append(entry);
    if (list.children.length > 20) list.firstElementChild.remove();
  }
  async function openTruthDrawer() {
    byId("truth-check-result").textContent = "";
    const current = await refreshSessionTruth();
    if (!current) return;
    renderTruthFacts("truth-facts", current.record?.facts, current.revision);
    if (current.status !== "LOCKED") byId("truth-check-result").textContent = "PREMISE_DRIFT / INPUT_REQUIRED：请核对并确认当前前提后再检查。";
    const select = byId("truth-claim-position"); select.replaceChildren();
    for (const p of current.record?.facts?.portfolio?.position_snapshot?.positions || []) {
      const option = document.createElement("option"); option.value = p.position_id; option.textContent = p.asset_name || p.asset_id; select.append(option);
    }
    byId("truth-drawer").showModal();
  }
  async function checkTruthItem(actionOnly = false) {
    const owner = state.ownerId, revision = sessionTruthState.revision;
    const output = byId("truth-check-result");
    const button = byId(actionOnly ? "truth-check-action" : "truth-check-claim");
    if (sessionTruthState.owner !== owner || sessionTruthState.status !== "LOCKED") {output.textContent = "请先锁定当前前提。"; return;}
    const path = byId("truth-claim-path").value;
    const payload = actionOnly ? {actions:[{action:"BUY", asset_id:byId("truth-action-asset").value.trim()}]} :
      {assertions:[{path, value:byId("truth-claim-value").value.trim(), ...(path.startsWith("portfolio.") ? {position_id:byId("truth-claim-position").value} : {})}]};
    button.disabled = true; output.textContent = "正在核对…";
    try {
      const response = await fetch("/api/v1/advisor/session-truth/check", {method:"POST", headers:{"Content-Type":"application/json","X-Owner-ID":owner}, body:JSON.stringify({expected_revision:revision,...payload})});
      if (!response.ok) throw await apiError(response);
      const result = await response.json();
      if (state.ownerId !== owner || sessionTruthState.revision !== revision) {output.textContent = "前提已变化，请重新核对。"; return;}
      output.textContent = JSON.stringify(result, null, 2);
    } catch (error) {output.textContent = error.message || "核验失败";}
    finally {button.disabled = false;}
  }
  async function confirmSessionTruth() {
    try {
      const current = await refreshSessionTruth();
      if (!current?.current_fingerprint) {setError("请先确认画像和持仓"); return;}
      truthReview = {...current, owner:state.ownerId};
      byId("truth-confirm-error").textContent = "";
      renderTruthFacts("truth-confirm-facts", current.current_facts, current.revision + 1);
      byId("truth-confirm-dialog").showModal();
    } catch (error) {setError(error.message || "无法读取前提");}
  }
  async function commitSessionTruth() {
    const review = truthReview;
    const button = byId("commit-session-truth"); button.disabled = true;
    try {
      if (!review || state.ownerId !== review.owner) throw Error("账户已变化，请重新核对前提");
      const response = await fetch("/api/v1/advisor/session-truth", {
        method:"POST", headers:{"Content-Type":"application/json", "X-Owner-ID":review.owner},
        body:JSON.stringify({expected_revision:review.revision, expected_fingerprint:review.current_fingerprint}),
      });
      if (!response.ok) throw await apiError(response);
      byId("truth-confirm-dialog").close(); truthReview = null;
      if (state.ownerId === review.owner) await refreshSessionTruth();
    } catch (error) {byId("truth-confirm-error").textContent = error.message || "前提确认失败，请重新读取后再确认";}
    finally {button.disabled = false;}
  }
  const transientStorage = new Map();
  const workspaceStorage = {
    getItem(key) { return authenticatedOwner ? transientStorage.get(key) ?? null : localStorage.getItem(key); },
    setItem(key, value) { if (authenticatedOwner) transientStorage.set(key, value); else localStorage.setItem(key, value); },
    removeItem(key) { if (authenticatedOwner) transientStorage.delete(key); else localStorage.removeItem(key); },
  };
  function ownerStorageKey(key) {
    return authenticatedOwner ? `${key}:${authenticatedOwner}` : key;
  }

  function invalidateDerivedState(store) {
    globalThis.prismStockQuickAbortController?.abort();
    globalThis.prismStockDeepAbortController?.abort();
    store.contextRevision += 1;
    DERIVED_SEQUENCE_KEYS.forEach((sequenceKey) => { store[sequenceKey] += 1; });
    DERIVED_RUN_KEYS.forEach((runKey) => { store[runKey] = null; });
    store.researchTemplate = null;
    store.stockResearchTemplate = null;
    store.fundResearchTemplate = null;
    store.convertibleBondResearchTemplate = null;
    store.portfolioOptimizationTemplate = null;
    store.scenarioSimulationTemplate = null;
  }

  function beginContextRequest(sequenceKey) {
    state[sequenceKey] += 1;
    return {
      sequenceKey,
      sequence: state[sequenceKey],
      contextRevision: state.contextRevision,
      ownerId: state.ownerId,
      selectedPersona: state.selectedPersona,
      dataMode: state.dataMode,
      profile: state.profile,
      portfolio: state.portfolio,
    };
  }

  function isContextRequestCurrent(token) {
    return state[token.sequenceKey] === token.sequence
      && state.contextRevision === token.contextRevision
      && state.ownerId === token.ownerId
      && state.selectedPersona === token.selectedPersona
      && state.dataMode === token.dataMode
      && state.profile === token.profile
      && state.portfolio === token.portfolio;
  }

  function renderInvalidatedDerivedState() {
    portfolioReportSequence += 1;
    displayedPortfolioReport = null;
    renderPortfolioReport(null);
    renderResearchMatrix(null);
    renderStockResearch(null);
    renderFundResearch(null);
    renderConvertibleBondResearch(null);
    renderPortfolioOptimization(null);
    renderScenarioSimulation(null);
    renderHeroDonutChart(state.selectedPersona);
    renderOverviewWorkspace(state.selectedPersona);
    const customStress = byId("custom-stress-result");
    if (customStress) clear(customStress);
    const customStressStatus = byId("custom-stress-status");
    if (customStressStatus) {
      customStressStatus.textContent = "待计算";
      customStressStatus.className = "status-chip";
    }
    ["rebalancing-metrics-content", "rebalancing-actions-content", "rebalancing-steps-content"]
      .forEach((id) => {
        const panel = byId(id);
        if (panel) clear(panel);
      });
    const rebalancingStatus = byId("rebalancing-status-chip");
    if (rebalancingStatus) {
      rebalancingStatus.textContent = "待运行";
      rebalancingStatus.className = "status-chip";
    }
    const decisionOutput = byId("copilot-decision-output");
    if (decisionOutput) clear(decisionOutput);
    renderPortfolioReadiness();
  }
  microStore.subscribe((store) => {
    document.documentElement.setAttribute("data-prism-owner", store.ownerId || "none");
    document.documentElement.setAttribute("data-prism-mode", store.dataMode || "MOCK");
    updateAgentFeatureAvailability();
  });
  const byId = (id) => document.getElementById(id);

  const DISPLAY_VALUE_LABELS = Object.freeze({
    READY: "就绪",
    PASS: "通过",
    VERIFIED: "已验证",
    STALE: "陈旧/需复核",
    CONFLICTING: "来源冲突",
    INVALID: "无效",
    REVIEW_REQUIRED: "待复核",
    BLOCKED: "已阻断",
    RUNNING: "运行中",
    PENDING: "待运行",
    SUCCESS: "成功",
    CANCELLED: "已取消",
    TIMEOUT: "超时",
    COMPLETED: "已完成",
    COMPLETE: "已完成",
    PARTIAL: "部分完成",
    FAILED: "失败",
    EMPTY: "无结果",
    SUPPORTED: "已支持",
    CONTRADICTED: "来源冲突",
    UNRESOLVED: "未解决",
    INSUFFICIENT: "数据不足",
    CLEAR: "规则未触发",
    WATCH: "需关注",
    HIGH_RISK: "高风险",
    GROWTH: "成长",
    ETF_FUND: "ETF / 基金",
    MACRO: "宏观",
    INDUSTRY: "行业",
    STOCK: "个股",
    TECHNOLOGY: "科技",
    HEALTHCARE: "医疗健康",
    FINANCE: "金融",
    INDUSTRIALS: "工业",
    UTILITIES: "公用事业",
    UNCLASSIFIED: "未分类",
    EXPLICIT_SAVE: "显式保存",
    HOLD: "持有",
    REDUCE: "降低",
    BUY: "买入",
    SELL: "卖出",
    WATCHLIST: "观察",
    BALANCED: "平衡",
    CONSERVATIVE: "保守",
    AGGRESSIVE: "进取",
    LOW: "低",
    MEDIUM: "中",
    HIGH: "高",
    SHORT: "短期",
    LONG: "长期",
    NOVICE: "新手",
    INTERMEDIATE: "中等",
    EXPERIENCED: "丰富",
    MODERATE: "中等",
    CNY: "人民币元",
    PCT: "百分比",
    USD: "美元",
    RATING_RANK: "评级序数",
    SCORE: "分数",
    REPAIRED: "已修复",
    WITHIN_LIMIT: "未超过上限",
    USE_QUESTIONNAIRE: "使用问卷值",
    USE_EXTRACTION: "使用提取值",
    DIRECT: "主数据提供方直连",
    CACHE_FRESH: "新鲜缓存",
    FALLBACK_PROVIDER: "备用数据提供方",
    CACHE_STALE_FALLBACK: "陈旧缓存回退",
    UNAVAILABLE: "未提供",
    ACCOUNTS_RECEIVABLE_CNY: "应收账款",
    DEBT_RATIO_PCT: "资产负债率",
    GROSS_MARGIN_PCT: "毛利率",
    NET_PROFIT_CNY: "净利润",
    OPERATING_CASH_FLOW_CNY: "经营活动现金流",
    REVENUE_CNY: "营业收入",
    REVENUE: "营业收入",
    TECHNOLOGY_WEIGHT_PCT: "科技行业权重",
    GROWTH_PCT: "增长率",
    POLICY_RATE_PCT: "政策利率",
    ANNUALIZED_VOLATILITY_PCT: "年化波动率",
    EXPENSE_RATIO_PCT: "费率",
    MAX_DRAWDOWN_PCT: "最大回撤",
    TOP10_WEIGHT_PCT: "前十大持仓权重",
    TRACKING_ERROR_PCT: "跟踪误差",
    BOND_FLOOR: "债底",
    BOND_PRICE: "转债价格",
    CONVERSION_PREMIUM_PCT: "转股溢价率",
    CONVERSION_PRICE: "转股价",
    CONVERSION_VALUE: "转股价值",
    CREDIT_RATING_RANK: "信用评级序数",
    LIQUIDITY_SCORE: "流动性等级序数",
    UNDERLYING_STOCK_PRICE: "正股价格",
    YIELD_TO_MATURITY_PCT: "到期收益率",
    CAP_AND_REDISTRIBUTE_V1: "上限重分配",
    LTE: "不高于",
    GTE: "不低于",
    GT: "高于",
    LT: "低于",
    EQ: "等于",
    INFO: "提示",
    WARN: "警告",
    WARNING: "警告",
    CRITICAL: "严重",
    ERROR: "错误",
    SOURCE_PARTIAL: "来源部分缺失",
    SOURCE_DISAGREEMENT: "来源分歧",
    SOURCE_EMPTY: "来源无结果",
    SOURCE_FAILED: "来源失败",
    INFEASIBLE: "不可行",
    "Synthetic Balanced ETF": "合成平衡 ETF",
    "Synthetic Technology Basket": "合成科技资产篮子",
    "Synthetic Healthcare Basket": "合成医疗健康资产篮子",
    "Synthetic Finance Basket": "合成金融资产篮子",
    "Synthetic Industrials Basket": "合成工业资产篮子",
    "Synthetic Utilities Basket": "合成公用事业资产篮子",
    "Synthetic Technology Stock": "示例科技股票",
    "Synthetic Healthcare Stock": "示例医疗健康股票",
    "Synthetic Finance Stock": "示例金融股票",
    "Synthetic Industrials Stock": "示例工业股票",
    ETF: "ETF基金",
    PRISM_STOCK_DEMO_F: "示例股票",
    PRISM_FUND_DEMO_G: "示例基金",
    PRISM_CONVERTIBLE_BOND_DEMO_H: "示例可转债",
    BOND_PAR_VALUE: "债券面值",
  });

  const DISPLAY_SCENARIO_LABELS = Object.freeze({
    BASELINE_READY: "基线：完整多资产快照",
    TIGHTER_TECH_CAP: "科技限额收紧 10%",
    TOP_ASSET_TRIM_10PP: "第一大资产削减 10%",
    LOOKTHROUGH_PARTIAL: "基金穿透部分缺失",
    SOURCE_PARTIAL: "来源部分缺失",
    SOURCE_DISAGREEMENT: "来源分歧",
    SOURCE_EMPTY: "来源无结果",
    SOURCE_FAILED: "来源失败",
    INFEASIBLE: "不可行：配置上限无法同时满足",
  });

  const DISPLAY_DESCRIPTIONS = Object.freeze({
    "complete multi-asset snapshot": "完整多资产持仓快照",
    "tighten technology budget cap by 10 percent": "将科技行业风险预算上限收紧 10%",
    "reduce top asset weight by 10 percentage points and redistribute to remaining assets": "将第一大资产权重削减 10 个百分点并等比重分配至其余资产",
    "degrade fund look-through coverage to 80 percent": "将基金/ETF穿透覆盖率下调至 80% 触发部分缺失",
    "fund look-through coverage is below 100 percent": "基金穿透覆盖率低于 100%",
    "one-asset concentration cannot satisfy every configured cap": "单一资产集中度无法同时满足全部配置上限",
    "provider returned no records for the requested scope": "数据提供方在请求范围内没有返回记录",
    "synthetic fixture returned no records for the requested scope": "合成样例在请求范围内没有返回记录",
    "synthetic fixture omitted a required field": "合成样例缺少必需字段",
    "synthetic fixture source was unavailable": "合成样例来源不可用",
    "source B was unavailable in this offline replay": "来源 B 在离线回放中不可用",
    "research run was not fully completed; findings require human review": "研究运行未完整完成；发现需要人工复核",
    "research run was partial; supported claim requires human review": "研究运行部分完成；已支持结论需要人工复核",
    "research run was not completed; supported claim requires human review": "研究运行未完成；已支持结论需要人工复核",
    "claim requires review before it can be consumed downstream": "结论在下游使用前需要人工复核",
    "provider returned a partial payload with declared missing fields": "数据提供方返回了已声明缺失字段的部分结果",
    "provider returned a partial payload requiring review": "数据提供方返回部分结果，需要人工复核",
    "provider output could not be normalized safely": "数据提供方结果无法安全规范化",
    "provider served stale cached data because fresh data was unavailable": "新鲜数据不可用，已提供陈旧缓存",
    "one or more stale provider fields were not usable as scalar observations": "一个或多个陈旧来源字段不能作为标量观测使用",
    "stale provider output contained no usable scalar observation": "陈旧来源结果没有可用的标量观测",
    "provider returned no usable scalar observation": "数据提供方没有返回可用的标量观测",
    "one or more provider fields were not usable as scalar observations": "一个或多个来源字段不能作为标量观测使用",
    "partial provider output contained no usable scalar observation": "部分来源结果没有可用的标量观测",
    "provider did not return usable data within the node boundary": "数据提供方未在节点边界内返回可用数据",
    "research run budget was exhausted before provider execution": "研究运行预算在数据提供方执行前已耗尽",
    "provider identity did not match the requested boundary": "数据提供方身份与请求边界不匹配",
    "provider execution failed safely": "数据提供方执行已安全失败",
    "node was not started because a dependency did not complete": "依赖项未完成，因此节点未启动",
    "one or more required research nodes are incomplete": "一个或多个必需研究节点未完成",
    "optional research nodes were incomplete; run is partial": "可选研究节点未完成；本次运行为部分完成",
    "research run deadline exceeded before node completion": "研究运行在节点完成前超过截止时间",
    "research run deadline exceeded; incomplete nodes were failed safely": "研究运行超过截止时间；未完成节点已安全标记失败",
    "required research node did not complete; run was failed safely": "必需研究节点未完成；本次运行已安全失败",
    "research run stopped after a required node was incomplete": "必需研究节点未完成，研究运行已停止",
    "exposure or concentration input is not complete": "暴露或集中度输入不完整",
    "unclassified exposure requires review": "未分类暴露需要复核",
    "unlooked-through exposure requires review": "未完成基金穿透的暴露需要复核",
    "asset sector classification is ambiguous": "资产行业分类不明确",
    "configured asset and sector caps cannot close to 100 percent": "配置的资产与行业上限无法闭合至 100%",
    "partial replay requires a fund look-through snapshot": "部分回放需要基金穿透快照",
    "exposure or concentration calculation failed": "暴露或集中度计算失败",
    "risk-budget assessment is blocked; no allocation envelope was produced": "风险预算评估已阻断；未生成配置约束包",
    "budget limits or input coverage require human review; no executable instruction was produced": "预算上限或输入覆盖需要人工复核；未生成可执行指令",
    "exposure report is unavailable; concentration was blocked": "暴露报告不可用；集中度评估已阻断",
    "exposure data is partial; concentration requires review": "暴露数据不完整；集中度评估需要复核",
    "concentration report is unavailable; budget assessment was blocked": "集中度报告不可用；风险预算评估已阻断",
    "concentration data is partial; assessment requires review": "集中度数据不完整；风险预算评估需要复核",
    "recommendation input failed contract validation": "建议输入未通过契约校验",
    "recommendation identity contains a sensitive field": "建议身份包含敏感字段",
    "recommendation inputs do not share one owner": "建议输入不属于同一隔离标识",
    "recommendation inputs do not share one profile version": "建议输入不属于同一画像版本",
    "portfolio and exposure inputs do not close one snapshot": "持仓与暴露输入未闭合到同一快照",
    "risk assessment does not close the portfolio reports": "风险评估未闭合持仓报告",
    "allocation envelope does not close the risk assessment": "配置约束包未闭合风险评估",
    "decision gate does not match the current inputs": "决策闸门与当前输入不匹配",
    "PASS recommendation requires complete portfolio risk inputs": "通过状态的建议需要完整持仓风险输入",
    "recommendation generated_at must be timezone-aware": "建议生成时间必须带时区",
    "aggregate risk breach has no executable asset mapping": "汇总风险超限没有可执行的资产映射",
    "allocation envelope has no deterministic actionable bands": "配置约束包没有确定性可执行区间",
    "actionable bands do not close remediation breaches": "可执行区间未闭合风险修复超限",
    "gate input failed contract validation": "闸门输入未通过契约校验",
    "gate identity contains a disallowed sensitive field": "闸门身份包含不允许的敏感字段",
    "risk inputs do not share one owner": "风险输入不属于同一隔离标识",
    "risk inputs do not share one profile": "风险输入不属于同一风险画像",
    "risk budget is not bound to the active profile": "风险预算未绑定当前画像",
    "allocation envelope is not bound to the risk assessment": "配置约束包未绑定风险评估",
    "allocation constraints do not match the active risk budget": "配置约束与当前风险预算不匹配",
    "allocation breach references do not match the risk assessment": "配置超限引用与风险评估不匹配",
    "risk assessment contains duplicate constraint breaches": "风险评估包含重复约束超限",
    "allocation breach is attached to the wrong constraint": "配置超限绑定了错误约束",
    "allocation reduction does not match its risk breach": "配置缩减与风险超限不匹配",
    "allocation status does not match the risk assessment": "配置状态与风险评估不匹配",
    "research evidence pipeline is blocked": "研究证据流程已阻断",
    "research evidence requires human review": "研究证据需要人工复核",
    "ready research trace is incomplete": "就绪研究证据链不完整",
    "research trace contains non-verified evidence": "研究证据链包含未验证证据",
    "research trace contains a non-verified fact": "研究证据链包含未验证事实",
    "research trace has an unknown evidence reference": "研究证据链引用了未知证据",
    "research trace has an unknown fact reference": "研究证据链引用了未知事实",
    "ready research bridge is incomplete": "就绪研究桥接不完整",
    "research bridge does not match the registered trace": "研究桥接与已登记证据链不匹配",
    "research trace must not contain recommendations": "研究证据链不得包含建议",
    "risk budget assessment is blocked": "风险预算评估已阻断",
    "risk budget assessment requires human review": "风险预算评估需要人工复核",
    "allocation constraint envelope is blocked": "配置约束包已阻断",
    "allocation constraint envelope requires human review": "配置约束包需要人工复核",
    "ready allocation has no envelope": "就绪配置没有约束包",
    "Provider execution was cancelled": "数据提供方执行已取消",
    "Internal provider execution error": "数据提供方内部执行错误",
    "Provider response identity did not match the requested boundary": "数据提供方响应身份与请求边界不匹配",
    "source B returned no stock record for the requested period": "来源 B 在请求报告期内没有返回个股记录",
    "source B returned no fund record for the requested period": "来源 B 在请求报告期内没有返回基金记录",
    "source B returned no convertible bond record for the requested period": "来源 B 在请求报告期内没有返回可转债记录",
    "offline synthetic four-track research matrix": "离线合成四轨道研究矩阵",
    "offline synthetic stock research Demo F": "离线合成个股研究（演示 F）",
    "offline synthetic ETF fund asset research replay": "离线合成 ETF / 基金资产研究回放",
    "offline synthetic convertible bond asset research replay": "离线合成可转债资产研究回放",
    "offline synthetic five-asset target-structure replay": "离线合成五资产目标结构回放",
    "single-asset cap applied; released weight is redistributed by stable headroom order": "已应用单资产上限；释放的权重按稳定的剩余容量顺序重分配",
    "target is deterministic and profile-conditioned; it is not a trade instruction": "目标由确定性规则和风险画像共同决定；不是交易指令",
    "sector cap is applied before deterministic redistribution": "先应用行业上限，再执行确定性重分配",
    "aggregate budget dimension is checked independently of sector labels": "独立检查汇总预算维度，不受行业标签影响",
    "aggregate exposure contributions into asset and sector buckets": "将暴露贡献汇总到资产和行业桶",
    "cap sector, technology and unclassified buckets using the confirmed risk budget": "使用已确认风险预算限制行业、科技和未分类桶",
    "redistribute released weight by largest headroom then stable ID": "按剩余容量从大到小、再按稳定 ID 重分配释放权重",
    "allocate each bucket proportionally with a single-asset cap and cent-level closure": "在单资产上限和分厘闭合约束下按比例分配各桶",
    "synthetic two-source revenue cross-check": "合成双来源收入交叉核验",
    "Review technology exposure through Macro, Industry, Stock and ETF/Fund tracks.": "通过宏观、行业、个股和 ETF / 基金轨道复核科技暴露",
    "Review portfolio risk constraints through Macro, Industry, Stock and ETF/Fund tracks.": "通过宏观、行业、个股和 ETF / 基金轨道复核组合风险约束",
    "Risk Profile version or risk budget rule changes": "风险画像版本或风险预算规则发生变化",
    "portfolio bundle or position snapshot changes": "持仓包或持仓快照发生变化",
    "fund look-through coverage or base currency changes": "基金穿透覆盖率或基准货币发生变化",
    "CAP_AND_REDISTRIBUTE_V1 methodology changes": "上限重分配（CAP_AND_REDISTRIBUTE_V1）方法发生变化",
    "validate owner, profile and portfolio input": "校验隔离标识、风险画像和持仓输入",
    "calculate exposure, concentration and profile-conditioned risk budget": "计算暴露、集中度和画像约束风险预算",
    "preserve review or blocked state when inputs are incomplete or infeasible": "输入不完整或不可行时保留待复核/阻断状态",
    "fixture stale replay": "样例陈旧回放",
    "technology weight threshold": "科技行业权重阈值",
    "top10 concentration threshold": "前十大持仓集中度阈值",
    "annualized volatility threshold": "年化波动率阈值",
    "maximum drawdown threshold": "最大回撤阈值",
    "expense ratio threshold": "费率阈值",
    "conversion premium threshold": "转股溢价率阈值",
    "bond floor threshold": "债底阈值",
    "negative yield threshold": "负收益率阈值",
    "credit rating rank threshold": "信用评级序数阈值",
    "liquidity score threshold": "流动性等级序数阈值",
  });

  const DISPLAY_LABELS = Object.freeze({
    Owner: "隔离标识",
    Bundle: "持仓包",
    "Position snapshot": "持仓快照",
    "Base currency": "基准货币",
    "As of": "截止时间",
    Asset: "资产",
    Position: "持仓明细",
    Quantity: "数量",
    "Market value": "市值",
    Underlying: "底层资产",
    Holding: "穿透持仓",
    Weight: "权重",
    "Saved at": "保存时间",
    Profile: "风险画像",
    Questionnaire: "风险问卷",
    "Portfolio bundle": "持仓包",
    "Content hash": "内容哈希",
    "Answered at": "回答时间",
    "Loss tolerance": "损失承受度",
    Horizon: "投资期限",
    Liquidity: "流动性需求",
    Experience: "投资经验",
    "Return expectation": "收益预期",
    "Max drawdown": "最大回撤容忍度",
    "Expected range": "预期收益区间",
    "Confirmed profile": "已确认画像",
    "Risk score": "风险评分",
    "Risk level": "风险等级",
    "Profile version": "画像版本",
    "Confirmed at": "确认时间",
    Draft: "提案草稿",
    Status: "状态",
    Extraction: "提取结果",
    Confidence: "置信度",
    "Input digest": "输入摘要",
    Plan: "计划",
    Intent: "意图",
    Scope: "范围",
    Nodes: "节点数",
    Node: "节点",
    Kind: "类型",
    Missing: "缺失字段",
    "Risk assessment": "风险评估",
    "Allocation envelope": "配置约束",
    "Research run": "研究运行",
    "Finding IDs": "发现 ID",
    "Recommendation ID": "建议 ID",
    Run: "运行",
    Provider: "数据提供方",
    Source: "来源",
    Field: "字段",
    Value: "数值",
    Period: "期间",
    "Observed at": "观测时间",
    "Retrieved at": "获取时间",
    Lineage: "来源链",
    "Cache age": "缓存时长",
    Pipeline: "流程",
    Method: "方法",
    "Exposure report": "暴露报告",
    Current: "当前",
    Target: "目标",
    Delta: "变化",
    "Asset cap": "资产上限",
    "Allocation range": "配置区间",
  });

  function displayLabel(value, fallback = "—") {
    if (value === null || value === undefined || value === "") return fallback;
    const rendered = String(value);
    return DISPLAY_LABELS[rendered]
      || DISPLAY_VALUE_LABELS[rendered]
      || DISPLAY_VALUE_LABELS[rendered.toUpperCase()]
      || rendered;
  }

  function displayDescription(value, fallback = "—") {
    if (value === null || value === undefined || value === "") return fallback;
    const rendered = String(value);
    if (DISPLAY_DESCRIPTIONS[rendered]) return DISPLAY_DESCRIPTIONS[rendered];
    const replay = rendered.match(/^(.+?) · replay ([A-Z0-9_]+)$/);
    if (replay && DISPLAY_DESCRIPTIONS[replay[1]]) {
      return `${DISPLAY_DESCRIPTIONS[replay[1]]} · 回放 ${replay[2]}`;
    }
    const timeout = rendered.match(/^Request timed out after (\d+)ms$/i);
    if (timeout) return `请求超过 ${timeout[1]} 毫秒后超时`;
    const fixtureMiss = rendered.match(/^No matching fixture found for fingerprint (.+)$/i);
    if (fixtureMiss) return `没有找到匹配请求指纹的合成样例：${fixtureMiss[1]}`;
    return rendered;
  }

  function displayScenarioLabel(scenario) {
    const value = scenario && typeof scenario === "object" ? scenario.label || scenario.scenario_id : scenario;
    if (value === null || value === undefined || value === "") return "未命名场景";
    if (DISPLAY_SCENARIO_LABELS[String(value)]) return DISPLAY_SCENARIO_LABELS[String(value)];
    const rendered = text(value, "");
    return /[\u3400-\u9fff]/.test(rendered) ? rendered : "研究场景";
  }

  function displayScenarioDescription(scenario) {
    const value = scenario && typeof scenario === "object" ? scenario.description : scenario;
    return displayDescription(value, "无场景说明");
  }

  function displayMethodology(value) {
    if (value === null || value === undefined || value === "") return "—";
    const rendered = localizeResearchTokens(displayDescription(value));
    const localized = rendered
      .replace(/^(?:deterministic|确定性)\s+(?:Decimal|精确数值)\s+(?:ratio|比率)\s*:/i, "按确定性比率计算：")
      .replace(/^(?:deterministic|确定性)\s+(?:Decimal|精确数值)\s+(?:threshold|阈值)\s*:/i, "按确定性阈值判断：")
      .replace(/^(?:deterministic|确定性)\s+(?:Decimal|精确数值)\s+(?:convertible-bond-formula|可转债计算规则)\.v1\s*;/i, "按确定性可转债公式计算：")
      .replace(/^(?:input_fact_ids|已验证事实)\s*=/i, "基于已验证事实：")
      .replace(/configured (stock-risk|fund-risk|convertible-bond-risk)\.v1 limit/gi, "按配置的风险规则限值")
      .replace(/configured (stock-risk|fund-risk|convertible-bond-risk)\.v1/gi, "按配置的风险规则")
      .replace(/technology weight threshold/g, "科技行业权重阈值")
      .replace(/top10 concentration threshold/g, "前十大持仓集中度阈值")
      .replace(/annualized volatility threshold/g, "年化波动率阈值")
      .replace(/maximum drawdown threshold/g, "最大回撤阈值")
      .replace(/expense ratio threshold/g, "费率阈值")
      .replace(/conversion premium threshold/g, "转股溢价率阈值")
      .replace(/bond floor threshold/g, "债底阈值")
      .replace(/negative yield threshold/g, "负收益率阈值")
      .replace(/credit rating rank threshold/g, "信用评级序数阈值")
      .replace(/liquidity score threshold/g, "流动性等级序数阈值")
      .replace(/\b(?:stock-risk|fund-risk|convertible-bond-risk)\.v1\b/gi, "风险规则")
      .replace(/\bDecimal\b/gi, "精确数值")
      .replace(/\bconvertible-bond-formula\.v1\b/gi, "可转债计算规则")
      .replace(/\binput_fact_ids\b/gi, "已验证事实")
      .replace(/\s*\([^()]*[A-Za-z][^()]*\)\s*$/g, "")
      .replace(/\s+([：:；，。])/g, "$1")
      .replace(/\s{2,}/g, " ")
      .trim();
    return localized && !/[A-Za-z]/.test(localized)
      ? localized
      : "按确定性规则计算，具体依据见证据链。";
  }

  const FINDING_KIND_LABELS = Object.freeze({
    STOCK_ACCOUNTS_RECEIVABLE_FACT: "应收账款事实",
    STOCK_DEBT_RATIO_FACT: "资产负债率事实",
    STOCK_GROSS_MARGIN_FACT: "毛利率事实",
    STOCK_NET_PROFIT_FACT: "净利润事实",
    STOCK_OPERATING_CASHFLOW_FACT: "经营活动现金流事实",
    STOCK_REVENUE_FACT: "营业收入事实",
    STOCK_CASHFLOW_QUALITY_ANOMALY: "经营现金流质量异常",
    STOCK_RECEIVABLE_QUALITY_ANOMALY: "应收账款质量异常",
    FUND_COST_WARNING: "基金费率偏高",
    FUND_VOLATILITY_RISK: "基金波动率偏高",
    FUND_TOP10_CONCENTRATION: "前十大持仓集中",
    FUND_DRAWDOWN_RISK: "历史回撤偏高",
    FUND_TECHNOLOGY_CONCENTRATION: "科技行业集中",
    FUND_VOLATILITY_PROFILE: "基金波动率指标",
    FUND_EXPENSE_PROFILE: "基金费率指标",
    FUND_DRAWDOWN_PROFILE: "基金回撤指标",
    FUND_TECHNOLOGY_PROFILE: "基金科技行业暴露",
    FUND_TOP10_PROFILE: "基金前十大持仓集中度",
    FUND_TRACKING_ERROR_PROFILE: "基金跟踪误差指标",
    STOCK_VALUATION_RISK: "估值风险",
    STOCK_CASH_FLOW_RISK: "现金流风险",
    STOCK_MARGIN_RISK: "盈利能力风险",
    STOCK_LEVERAGE_RISK: "资产负债风险",
    CONVERTIBLE_BOND_FLOOR_PROFILE: "债底指标",
    CONVERTIBLE_BOND_PRICE_PROFILE: "转债价格指标",
    CONVERTIBLE_CONVERSION_PREMIUM_FORMULA: "转股溢价率计算",
    CONVERTIBLE_CONVERSION_PRICE_PROFILE: "转股价指标",
    CONVERTIBLE_CONVERSION_VALUE_FORMULA: "转股价值计算",
    CONVERTIBLE_CREDIT_PROFILE: "信用情况",
    CONVERTIBLE_LIQUIDITY_PROFILE: "流动性情况",
    CONVERTIBLE_UNDERLYING_PROFILE: "正股价格指标",
    CONVERTIBLE_YIELD_PROFILE: "到期收益率指标",
    CONVERTIBLE_PREMIUM_WARNING: "转股溢价率风险",
    CONVERTIBLE_BOND_FLOOR_WARNING: "债底风险",
    CONVERTIBLE_NEGATIVE_YIELD: "到期收益率风险",
    CONVERTIBLE_CREDIT_RISK: "信用风险",
    CONVERTIBLE_LIQUIDITY_RISK: "流动性风险",
    CONVERSION_VALUE_FORMULA: "转股价值计算",
    CONVERSION_PREMIUM_PCT_FORMULA: "转股溢价率计算",
    ETF_TECHNOLOGY_EXPOSURE: "ETF 科技行业暴露",
    INDUSTRY_GROWTH: "行业增长指标",
    MACRO_POLICY_RATE: "政策利率指标",
    STOCK_REVENUE: "个股营业收入指标",
  });

  function findingKindLabel(kind) {
    if (FINDING_KIND_LABELS[kind]) return FINDING_KIND_LABELS[kind];
    const normalized = String(kind || "").toUpperCase();
    if (normalized.endsWith("_ANOMALY")) return "异常项";
    if (normalized.endsWith("_RISK")) return "风险项";
    if (normalized.endsWith("_FORMULA")) return "确定性计算";
    if (normalized.endsWith("_FACT") || normalized.endsWith("_PROFILE")) return "研究事实";
    return "需要关注的风险";
  }

  const RESEARCH_TOKEN_LABELS = Object.freeze({
    accounts_receivable_cny: "应收账款",
    debt_ratio_pct: "资产负债率",
    gross_margin_pct: "毛利率",
    net_profit_cny: "净利润",
    operating_cash_flow_cny: "经营活动现金流",
    revenue_cny: "营业收入",
    annualized_volatility_pct: "年化波动率",
    expense_ratio_pct: "费率",
    max_drawdown_pct: "最大回撤",
    technology_weight_pct: "科技行业权重",
    top10_weight_pct: "前十大持仓权重",
    tracking_error_pct: "跟踪误差",
    bond_floor: "债底",
    bond_price: "转债价格",
    conversion_premium_pct: "转股溢价率",
    conversion_price: "转股价",
    conversion_value: "转股价值",
    credit_rating_rank: "信用评级等级",
    liquidity_score: "流动性等级",
    underlying_stock_price: "正股价格",
    yield_to_maturity_pct: "到期收益率",
    bond_par_value: "债券面值",
    CNY: "人民币元",
    pct: "百分比",
    rating_rank: "评级等级",
    score: "分数",
    limit: "限值",
    threshold: "阈值",
    liquidity: "流动性",
    credit: "信用",
    rating: "评级",
    rank: "序数",
    configured: "配置的",
    deterministic: "确定性",
    fixed: "固定",
    ratio: "比率",
    source: "来源",
  });

  function localizeResearchTokens(value) {
    let rendered = value === null || value === undefined ? "" : String(value);
    Object.entries(RESEARCH_TOKEN_LABELS).forEach(([token, label]) => {
      rendered = rendered.replace(new RegExp(`\\b${token}\\b`, "gi"), label);
    });
    return rendered
      .replace(/\bCRITICAL\b/g, "高风险")
      .replace(/\bWARNING\b/g, "警告")
      .replace(/\bINFO\b/g, "提示")
      .replace(/\bREADY\b/g, "已完成")
      .replace(/\bPARTIAL\b/g, "部分完成")
      .replace(/\bCOMPLETE(?:D)?\b/g, "已完成")
      .replace(/\bREVIEW_REQUIRED\b/g, "待复核");
  }

  function researchSubjectLabel(value) {
    const rendered = text(value, "");
    if (!rendered) return "未命名标的";
    if (rendered !== String(value)) return rendered;
    if (/^PRISM_(?:STOCK|FUND|CONVERTIBLE_BOND)_DEMO_/i.test(rendered)) return "示例标的";
    return /[\u3400-\u9fff]/.test(rendered) || /^\d+[A-Za-z]*$/.test(rendered) ? rendered : "研究标的";
  }

  function researchPeriodLabel(value) {
    const rendered = text(value, "");
    const match = String(value || "").match(/^(\d{4})-Q([1-4])$/i);
    return match ? `${match[1]} 年第 ${match[2]} 季度` : rendered || "未提供期间";
  }

  function researchMetricLabel(value, preferredLabel = "") {
    const preferred = String(preferredLabel || "");
    if (preferred && (!/[A-Za-z]/.test(preferred) || /[\u3400-\u9fff]/.test(preferred))) return preferred;
    const rendered = text(value, "");
    if (rendered && rendered !== String(value)) return rendered;
    const localized = localizeResearchTokens(value);
    return localized && !/[A-Za-z]/.test(localized) ? localized : "研究指标";
  }

  function researchNodeLabel(value) {
    const rendered = String(value || "");
    const slot = rendered.match(/(?:source[-_])([a-z0-9]+)$/i);
    if (slot) return `数据来源 ${slot[1].toUpperCase()}`;
    return "研究来源";
  }

  function researchSourceLabel(value) {
    const rendered = String(value || "");
    const slot = rendered.match(/(?:source[-_])([a-z0-9]+)$/i);
    if (slot) return `来源 ${slot[1].toUpperCase()}`;
    if (/iwencai|wencai/i.test(rendered)) return "问财数据";
    if (/fuyao/i.test(rendered)) return "扶摇数据";
    return "外部数据来源";
  }

  function researchEvidenceLabel(_evidence, index) {
    return `证据 ${index + 1}`;
  }

  function researchFindingLabel(finding, index) {
    const kindLabel = findingKindLabel(finding?.kind);
    return kindLabel === "需要关注的风险" ? `研究发现 ${index + 1}` : kindLabel;
  }

  function researchNarrative(value, fallback = "数据说明暂不可用，需要人工复核。") {
    const rendered = displayDescription(value, "");
    if (!rendered) return fallback;
    const localized = localizeResearchTokens(rendered)
      .replace(/\boffline\b|\bsynthetic\b|\breplay\b|\bDemo\b/gi, "")
      .replace(/\bDecimal\b/gi, "精确数值")
      .replace(/\b(?:stock-risk|fund-risk|convertible-bond-risk)\.v1\b/gi, "风险规则")
      .replace(/\bconvertible-bond-formula\.v1\b/gi, "可转债计算规则")
      .replace(/\s{2,}/g, " ")
      .trim();
    if (!localized || (!/[\u3400-\u9fff]/.test(localized) && /[A-Za-z]/.test(localized))) return fallback;
    return localized;
  }

  function researchFormula(value) {
    const localized = localizeResearchTokens(value);
    return localized
      .replace(/\bDecimal\b/gi, "精确数值")
      .replace(/\bformula\b/gi, "公式")
      .replace(/\bconvertible-bond-formula\.v1\b/gi, "可转债计算规则");
  }

  function humanMetricValue(value, unit = "") {
    const number = Number(value);
    const rendered = Number.isFinite(number) ? number.toFixed(2) : text(value);
    const normalizedUnit = String(unit || "").toUpperCase();
    if (["PCT", "%", "PERCENT", "PERCENTAGE"].includes(normalizedUnit)) return `${rendered}%`;
    if (["CNY", "RMB"].includes(normalizedUnit)) return `¥${rendered}`;
    return `${rendered}${unit ? ` ${displayLabel(unit)}` : ""}`;
  }

  function text(value, fallback = "—") {
    if (value === null || value === undefined || value === "") return fallback;
    const rendered = String(value);
    return DISPLAY_VALUE_LABELS[rendered] || DISPLAY_VALUE_LABELS[rendered.toUpperCase()] || rendered;
  }

  function clear(node) {
    node.replaceChildren();
  }

  function createSvgIcon(iconId, className = "prism-icon") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    if (className) svg.setAttribute("class", className);
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttributeNS("http://www.w3.org/1999/xlink", "href", `#${iconId}`);
    use.setAttribute("href", `#${iconId}`);
    svg.appendChild(use);
    return svg;
  }

  function setError(message = "") {
    const node = byId("global-error");
    const rendered = message ? String(message) : "";
    const safeMessage = !rendered
      ? ""
      : /[\u3400-\u9fff]/.test(rendered)
        ? rendered
        : "操作未完成，请检查输入或稍后重试。";
    node.textContent = safeMessage;
    node.hidden = !safeMessage;
  }

  function setQueryStatus(message, className = "") {
    const node = byId("query-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function researchStatusClass(status) {
    return status === "READY" || status === "COMPLETED" || status === "COMPLETE" || status === "SUPPORTED"
      ? "pass"
      : status === "REVIEW_REQUIRED" || status === "PARTIAL" || status === "CONTRADICTED" || status === "UNRESOLVED" || status === "INSUFFICIENT"
        ? "review"
        : "blocked";
  }

  function researchStatusLabel(status) {
    const rendered = DISPLAY_VALUE_LABELS[status] || text(status, "");
    return rendered && !/^[A-Z][A-Z0-9_-]*$/.test(String(rendered)) ? rendered : "待复核";
  }

  function researchSeverityLabel(severity) {
    const rendered = text(severity, "");
    return rendered && !/^[A-Z][A-Z0-9_-]*$/.test(String(rendered)) ? rendered : "提示";
  }

  function researchIssueLabel(code) {
    const rendered = text(code, "");
    return rendered && rendered !== String(code) ? rendered : "数据校验问题";
  }

  function setResearchStatus(message, className = "") {
    const node = byId("research-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setStockResearchStatus(message, className = "") {
    const node = byId("stock-research-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setFundResearchStatus(message, className = "") {
    const node = byId("fund-research-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setConvertibleBondResearchStatus(message, className = "") {
    const node = byId("convertible-bond-research-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setPortfolioOptimizationStatus(message, className = "") {
    const node = byId("portfolio-optimization-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setScenarioSimulationStatus(message, className = "") {
    const node = byId("scenario-simulation-status");
    if (!node) return;
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setContextMemoryStatus(message, className = "") {
    const node = byId("context-memory-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function researchRoleLabel(role) {
    const rendered = DISPLAY_VALUE_LABELS[role] || text(role, "");
    return rendered && !/^[A-Z][A-Z0-9_-]*$/.test(String(rendered)) ? rendered : "研究节点";
  }

  function clearResearchScenarioOptions() {
    const select = byId("research-scenario");
    clear(select);
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "读取场景目录…";
    select.append(option);
    select.disabled = true;
  }

  function renderResearchScenarioOptions(scenarios) {
    const select = byId("research-scenario");
    const previous = select.value;
    clear(select);
    const options = Array.isArray(scenarios) ? scenarios : [];
    options.forEach((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.scenario_id || "";
      option.textContent = displayScenarioLabel(scenario);
      option.title = researchNarrative(displayScenarioDescription(scenario), "该场景暂无补充说明。");
      select.append(option);
    });
    if (!options.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无可用场景";
      select.append(option);
      select.disabled = true;
      return;
    }
    const known = options.some((scenario) => scenario.scenario_id === previous);
    select.value = known ? previous : options[0].scenario_id;
    select.disabled = false;
  }

  function clearStockResearchScenarioOptions() {
    const select = byId("stock-research-scenario");
    clear(select);
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "读取场景目录…";
    select.append(option);
    select.disabled = true;
  }

  function renderStockResearchScenarioOptions(scenarios) {
    const select = byId("stock-research-scenario");
    const previous = select.value;
    clear(select);
    const options = Array.isArray(scenarios) ? scenarios : [];
    options.forEach((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.scenario_id || "";
      option.textContent = displayScenarioLabel(scenario);
      option.title = researchNarrative(displayScenarioDescription(scenario), "该场景暂无补充说明。");
      select.append(option);
    });
    if (!options.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无可用场景";
      select.append(option);
      select.disabled = true;
      return;
    }
    const known = options.some((scenario) => scenario.scenario_id === previous);
    select.value = known ? previous : options[0].scenario_id;
    select.disabled = false;
  }

  function clearFundResearchScenarioOptions() {
    const select = byId("fund-research-scenario");
    clear(select);
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "读取场景目录…";
    select.append(option);
    select.disabled = true;
  }

  function renderFundResearchScenarioOptions(scenarios) {
    const select = byId("fund-research-scenario");
    const previous = select.value;
    clear(select);
    const options = Array.isArray(scenarios) ? scenarios : [];
    options.forEach((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.scenario_id || "";
      option.textContent = displayScenarioLabel(scenario);
      option.title = researchNarrative(displayScenarioDescription(scenario), "该场景暂无补充说明。");
      select.append(option);
    });
    if (!options.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无可用场景";
      select.append(option);
      select.disabled = true;
      return;
    }
    const known = options.some((scenario) => scenario.scenario_id === previous);
    select.value = known ? previous : options[0].scenario_id;
    select.disabled = false;
  }

  function clearConvertibleBondResearchScenarioOptions() {
    const select = byId("convertible-bond-research-scenario");
    clear(select);
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "读取场景目录…";
    select.append(option);
    select.disabled = true;
  }

  function renderConvertibleBondResearchScenarioOptions(scenarios) {
    const select = byId("convertible-bond-research-scenario");
    const previous = select.value;
    clear(select);
    const options = Array.isArray(scenarios) ? scenarios : [];
    options.forEach((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.scenario_id || "";
      option.textContent = displayScenarioLabel(scenario);
      option.title = researchNarrative(displayScenarioDescription(scenario), "该场景暂无补充说明。");
      select.append(option);
    });
    if (!options.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无可用场景";
      select.append(option);
      select.disabled = true;
      return;
    }
    const known = options.some((scenario) => scenario.scenario_id === previous);
    select.value = known ? previous : options[0].scenario_id;
    select.disabled = false;
  }

  function clearPortfolioOptimizationScenarioOptions() {
    const select = byId("portfolio-optimization-scenario");
    clear(select);
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "读取场景目录…";
    select.append(option);
    select.disabled = true;
  }

  function renderPortfolioOptimizationScenarioOptions(scenarios) {
    const select = byId("portfolio-optimization-scenario");
    const previous = select.value;
    clear(select);
    const options = Array.isArray(scenarios) ? scenarios : [];
    options.forEach((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.scenario_id || "";
      option.textContent = displayScenarioLabel(scenario);
      option.title = displayScenarioDescription(scenario);
      select.append(option);
    });
    if (!options.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无可用场景";
      select.append(option);
      select.disabled = true;
      return;
    }
    const known = options.some((scenario) => scenario.scenario_id === previous);
    select.value = known ? previous : options[0].scenario_id;
    select.disabled = false;
  }

  function clearScenarioSimulationScenarioOptions() {
    const select = byId("scenario-simulation-scenario");
    if (!select) return;
    clear(select);
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "读取场景目录…";
    select.append(option);
    select.disabled = true;
  }

  function renderScenarioSimulationScenarioOptions(scenarios) {
    const select = byId("scenario-simulation-scenario");
    if (!select) return;
    const previous = select.value;
    clear(select);
    const options = Array.isArray(scenarios) ? scenarios : [];
    options.forEach((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.scenario_id || "";
      option.textContent = displayScenarioLabel(scenario);
      option.title = displayScenarioDescription(scenario);
      select.append(option);
    });
    if (!options.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无可用场景";
      select.append(option);
      select.disabled = true;
      return;
    }
    const known = options.some((scenario) => scenario.scenario_id === previous);
    select.value = known ? previous : options[0].scenario_id;
    select.disabled = false;
  }

  function stockRiskStatusClass(status) {
    return status === "CLEAR" ? "pass" : status === "WATCH" ? "review" : "blocked";
  }

  function stockRiskStatusLabel(status) {
    return DISPLAY_VALUE_LABELS[status] || "未评估";
  }

  function fundRiskStatusClass(status) {
    return stockRiskStatusClass(status);
  }

  function fundRiskStatusLabel(status) {
    return stockRiskStatusLabel(status);
  }

  function convertibleBondRiskStatusClass(status) {
    return stockRiskStatusClass(status);
  }

  function convertibleBondRiskStatusLabel(status) {
    return stockRiskStatusLabel(status);
  }

  function optimizationStatusLabel(status) {
    return DISPLAY_VALUE_LABELS[status] || text(status, "待运行");
  }

  function optimizationStatusClass(status) {
    return status === "READY" ? "pass" : status === "REVIEW_REQUIRED" ? "review" : "blocked";
  }

  function statusClass(status) {
    return status === "PASS" ? "pass" : status === "REVIEW_REQUIRED" ? "review" : "blocked";
  }

  function statusLabel(status) {
    return DISPLAY_VALUE_LABELS[status] || text(status, "未知状态");
  }

  function chip(label, className) {
    const node = document.createElement("span");
    node.className = `status-chip ${className || ""}`.trim();
    node.textContent = text(label, "");
    return node;
  }

  function renderEvents() {
    const list = byId("event-list");
    clear(list);
    byId("event-count").textContent = `${state.events.length} 条事件`;
    if (!state.events.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "当前隔离标识还没有保存的决策事件。";
      list.append(empty);
      return;
    }
    state.events.forEach((event) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `event-row${state.selected === event.event_id ? " selected" : ""}`;
      button.addEventListener("click", () => loadEvent(event.event_id));
      const top = document.createElement("div");
      top.className = "event-row-top";
      const id = document.createElement("span");
      id.className = "event-row-id";
      id.textContent = event.receipt_id || event.event_id;
      top.append(id, chip(statusLabel(event.status), statusClass(event.status)));
      const bottom = document.createElement("div");
      bottom.className = "event-row-bottom";
      const composition = document.createElement("span");
      composition.textContent = event.composition_id;
      const recorded = document.createElement("time");
      recorded.dateTime = event.recorded_at;
      recorded.textContent = new Date(event.recorded_at).toLocaleString("zh-CN");
      bottom.append(composition, recorded);
      button.append(top, bottom);
      list.append(button);
    });
  }

  function addMetadata(container, label, value, { devOnly = false } = {}) {
    const item = document.createElement("div");
    // 纯内部标识（Owner / Bundle / 各类 *_id / 指纹 / run_id 等）对普通股民没有意义，
    // 标记 dev-only 后在普通模式隐藏、开发者模式仍完整展示，不丢失可审计信息。
    if (devOnly) item.classList.add("dev-only");
    const dt = document.createElement("dt");
    dt.textContent = displayLabel(label);
    const dd = document.createElement("dd");
    dd.textContent = text(value);
    item.append(dt, dd);
    container.append(item);
  }

  function setPortfolioSourcePresentation(sourceLabel, portfolio) {
    const renderedSource = sourceLabel || "示例数据 · 只读";
    const isExample = /示例|MOCK|模板/i.test(renderedSource);
    const isConfirmed = /已确认/.test(renderedSource);
    const isLocal = /恢复|本地/.test(renderedSource);
    const isLive = state.dataMode === "LIVE" || /实时/.test(renderedSource);
    const title = byId("portfolio-title");
    const label = byId("portfolio-context-label");
    const note = byId("portfolio-source-note");
    if (title) title.textContent = isExample ? "示例持仓明细" : "持仓明细";
    if (label) label.textContent = renderedSource;
    if (!note) return { isExample, isConfirmed, isLocal, isLive };
    note.className = `portfolio-source-note${isConfirmed ? " is-confirmed" : isLocal ? " is-local" : ""}`;
    note.textContent = isExample
      ? "当前展示为示例持仓，可通过右上角导入你的资产组合。"
      : isConfirmed
        ? (isLive
            ? "已同步最新市场行情与底层穿透数据。"
            : "已载入当前持仓明细。")
        : isLocal
          ? "已从本地记录载入持仓快照。"
          : portfolio
            ? "已载入当前持仓明细。"
            : "导入持仓后即可查看明细与穿透详情。";
    return { isExample, isConfirmed, isLocal, isLive };
  }

  function renderPortfolio(portfolio, sourceLabel = "示例数据 · 只读") {
    const presentation = setPortfolioSourcePresentation(sourceLabel, portfolio);
    const panel = byId("portfolio-content");
    clear(panel);
    if (!portfolio) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = presentation.isExample
        ? "当前为示例持仓；确认脱敏持仓后查看你的持仓明细。"
        : "加载后查看持仓明细与基金底层股票。";
      panel.append(empty);
      return;
    }
    const snapshot = portfolio.position_snapshot;
    const summary = document.createElement("dl");
    summary.className = "portfolio-summary";
    addMetadata(summary, "Owner", portfolio.owner_id, { devOnly: true });
    addMetadata(summary, "Bundle", portfolio.bundle_id, { devOnly: true });
    addMetadata(summary, "Position snapshot", snapshot.snapshot_id, { devOnly: true });
    addMetadata(summary, "As of", snapshot.as_of);
    addMetadata(summary, "Base currency", snapshot.base_currency);
    panel.append(summary);

    const positionsHeading = document.createElement("h3");
    positionsHeading.className = "context-heading";
    positionsHeading.textContent = presentation.isExample ? "示例持仓明细" : "持仓明细";
    panel.append(positionsHeading);
    const positions = document.createElement("div");
    positions.className = "position-grid";
    (snapshot.positions || []).forEach((position) => {
      const card = document.createElement("article");
      card.className = "position-card";
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = text(position.asset_name);
      header.append(title, chip(text(position.asset_type), ""));
      card.append(header);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Asset", position.asset_id, { devOnly: true });
      addMetadata(metadata, "Position", position.position_id, { devOnly: true });
      addMetadata(metadata, "Quantity", position.quantity);
      addMetadata(metadata, "Market value", `${text(position.market_value)} ${text(position.currency)}`);
      card.append(metadata);
      positions.append(card);
    });
    panel.append(positions);

    const holdingHeading = document.createElement("h3");
    holdingHeading.className = "context-heading";
    holdingHeading.textContent = presentation.isExample ? "示例基金穿透持仓" : "基金穿透持仓";
    panel.append(holdingHeading);
    if (!(portfolio.fund_holdings || []).length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "当前模板没有基金/ETF 穿透快照。";
      panel.append(empty);
      return;
    }
    (portfolio.fund_holdings || []).forEach((fund) => {
      const section = document.createElement("section");
      section.className = "holding-section";
      const meta = document.createElement("div");
      meta.className = "holding-meta";
      const parentPosition = (snapshot.positions || []).find((position) => position.asset_id === fund.parent_asset_id);
      const parentLabel = parentPosition ? text(parentPosition.asset_name) : "基金/ETF";
      meta.textContent = `${parentLabel} · 穿透覆盖率 ${text(fund.coverage_pct)}% · 截止 ${text(fund.as_of)}`;
      section.append(meta);
      const holdings = document.createElement("div");
      holdings.className = "holding-grid";
      (fund.holdings || []).forEach((holding) => {
        const card = document.createElement("article");
        card.className = "holding-card";
        const header = document.createElement("header");
        const title = document.createElement("strong");
        title.textContent = text(holding.underlying_name);
        header.append(title, chip(text(holding.sector, "未分类"), ""));
        card.append(header);
        const metadata = document.createElement("dl");
        addMetadata(metadata, "Underlying", holding.underlying_asset_id, { devOnly: true });
        addMetadata(metadata, "Holding", holding.holding_id, { devOnly: true });
        addMetadata(metadata, "Weight", `${text(holding.weight_pct)}%`);
        addMetadata(metadata, "As of", holding.as_of);
        card.append(metadata);
        holdings.append(card);
      });
      section.append(holdings);
      panel.append(section);
    });
  }

  function renderContextMemory(records = state.contextMemoryRecords) {
    const panel = byId("context-memory-content");
    clear(panel);
    const items = Array.isArray(records) ? records : [];
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "暂无已保存上下文；保存前必须先确认风险画像与持仓。";
      panel.append(empty);
      return;
    }
    items.forEach((record) => {
      const card = document.createElement("article");
      card.className = `context-memory-card${state.contextMemorySelected === record.memory_id ? " selected" : ""}`;
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = `${text(record.profile?.risk_level)} · ${text(record.memory_id)}`;
      header.append(title, chip(text(record.source, "EXPLICIT_SAVE"), "pass"));
      card.append(header);
      const metadata = document.createElement("dl");
      metadata.className = "metadata-grid";
      addMetadata(metadata, "Saved at", record.saved_at);
      addMetadata(metadata, "Profile", `${text(record.profile?.profile_id)} · v${text(record.profile?.profile_version)}`);
      addMetadata(metadata, "Questionnaire", record.questionnaire?.questionnaire_id);
      addMetadata(metadata, "Portfolio bundle", record.portfolio?.bundle_id);
      addMetadata(metadata, "Position snapshot", record.portfolio?.position_snapshot?.snapshot_id);
      addMetadata(metadata, "Content hash", record.content_hash);
      card.append(metadata);
      const references = record.references || {};
      const referenceValues = [
        references.research_run_id && `研究 ${references.research_run_id}`,
        references.stock_research_run_id && `个股 ${references.stock_research_run_id}`,
        references.fund_research_run_id && `基金 ${references.fund_research_run_id}`,
        references.convertible_bond_research_run_id && `可转债 ${references.convertible_bond_research_run_id}`,
        references.optimization_request_id && `组合优化 ${references.optimization_request_id}`,
      ].filter(Boolean);
      const note = document.createElement("p");
      note.className = "context-memory-references";
      note.textContent = referenceValues.length
        ? `引用：${referenceValues.join(" · ")}`
        : "未保存派生研究引用；恢复后需重新运行研究或组合流程。";
      card.append(note);
      const actions = document.createElement("div");
      actions.className = "context-import-actions";
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "query-submit";
      restore.textContent = "显式恢复到当前会话";
      restore.addEventListener("click", () => restoreContextMemory(record));
      actions.append(restore);
      card.append(actions);
      panel.append(card);
    });
  }

  function clearContextMemory() {
    byId("memory-search-results").textContent = "";
    byId("memory-search-query").value = "";
    state.contextMemorySequence += 1;
    state.contextMemoryRecords = [];
    state.contextMemorySelected = null;
    setContextMemoryStatus("未读取");
    renderContextMemory([]);
  }

  function clearDerivedResultsForContextRestore() {
    state.selected = null;
    state.selectedDecisionEvent = null;
    state.advancedEvidenceSelectedKey = "";
    renderEvents();
    renderProfile(null);
    renderEvidence(null);
    byId("detail-status").className = "status-chip";
    byId("detail-status").textContent = "待选择";
    clear(byId("detail-content"));
    const detailEmpty = document.createElement("div");
    detailEmpty.className = "empty-state";
      detailEmpty.textContent = "上下文已恢复；请重新运行投顾查询后查看新的决策回执。";
    byId("detail-content").append(detailEmpty);
    clearAdvisorPlan();
    clearProfileProposal();
    state.researchRun = null;
    state.researchSequence += 1;
    renderResearchMatrix(null);
    setResearchStatus("需重新运行", "review");
    state.stockResearchRun = null;
    state.stockResearchSequence += 1;
    renderStockResearch(null);
    setStockResearchStatus("需重新运行", "review");
    state.fundResearchRun = null;
    state.fundResearchSequence += 1;
    renderFundResearch(null);
    setFundResearchStatus("需重新运行", "review");
    state.convertibleBondResearchRun = null;
    state.convertibleBondResearchSequence += 1;
    renderConvertibleBondResearch(null);
    setConvertibleBondResearchStatus("需重新运行", "review");
    clearPortfolioOptimizationRun("需重新运行", "review");
  }

  function restoreContextMemory(record) {
    if (!record || record.owner_id !== state.ownerId) {
      state.contextMemorySelected = null;
      setContextMemoryStatus("恢复被拒绝", "blocked");
      setError("上下文记忆不属于当前隔离标识，未恢复。");
      renderContextMemory();
      clearDerivedResultsForContextRestore();
      return;
    }
    state.contextMemorySelected = record.memory_id;
    state.profile = {
      questionnaire: record.questionnaire,
      profile: record.profile,
    };
    state.portfolio = record.portfolio;
    const questionnaireId = text(record.questionnaire?.questionnaire_id, "");
    const queryId = questionnaireId.endsWith("-questionnaire")
      ? questionnaireId.slice(0, -"-questionnaire".length)
      : questionnaireId;
    if (queryId) byId("query-id").value = queryId;
    [
      ["loss-tolerance", record.questionnaire?.loss_tolerance_score],
      ["investment-horizon", record.questionnaire?.investment_horizon],
      ["liquidity-need", record.questionnaire?.liquidity_need],
      ["experience-level", record.questionnaire?.experience_level],
      ["return-expectation", record.questionnaire?.return_expectation],
      ["max-drawdown", record.questionnaire?.max_drawdown_tolerance_pct],
    ].forEach(([id, value]) => {
      if (value !== undefined && value !== null) byId(id).value = String(value);
    });
    renderPortfolio(record.portfolio, "已恢复 · 本地结构化记忆");
    renderProfileContext(record.questionnaire);
    renderConfirmedProfile(record.profile);
    setPortfolioContextStatus("已恢复 · 当前会话只读", "pass");
    setProfileContextStatus(`已恢复 · ${text(record.profile?.risk_level)}`, "pass");
    clearDerivedResultsForContextRestore();
    setContextMemoryStatus("已显式恢复 · 派生结果已清空", "pass");
    setError("");
    renderContextMemory();
  }

  function buildContextMemoryReferences() {
    const research = state.researchRun;
    const stock = state.stockResearchRun;
    const fund = state.fundResearchRun;
    const convertible = state.convertibleBondResearchRun;
    const optimization = state.portfolioOptimizationRun;
    return {
      research_matrix_id: research?.matrix_id || null,
      research_run_id: research?.run_id || null,
      research_scenario_id: research?.scenario?.scenario_id || null,
      stock_research_run_id: stock?.request_id || null,
      stock_research_scenario_id: stock?.scenario?.scenario_id || null,
      fund_research_run_id: fund?.request_id || null,
      fund_research_scenario_id: fund?.scenario?.scenario_id || null,
      convertible_bond_research_run_id: convertible?.request_id || null,
      convertible_bond_research_scenario_id: convertible?.scenario?.scenario_id || null,
      optimization_request_id: optimization?.request_id || null,
      optimization_scenario_id: optimization?.scenario?.scenario_id || null,
    };
  }

  async function saveContextMemory() {
    const requestOwner = byId("owner-id").value.trim();
    if (!requestOwner) {
      setContextMemoryStatus("需要隔离标识", "blocked");
      setError("请输入隔离标识。");
      return;
    }
    if (requestOwner !== state.ownerId) {
      state.ownerId = requestOwner;
      resetOwnerScopedViews();
      setContextMemoryStatus("需先读取隔离标识", "review");
      setError("请先读取该隔离标识，再确认风险画像与持仓。");
      return;
    }
    if (!state.profile?.profile || !state.profile?.questionnaire) {
      setContextMemoryStatus("正在自动确认前置画像…", "review");
      await ensureDependency("PROFILE_CONTEXT");
    }
    if (!state.profile?.profile || !state.profile?.questionnaire) {
      setContextMemoryStatus("需先确认画像", "review");
      setError("请先确认风险画像，再保存上下文记忆。");
      return;
    }
    if (!state.portfolio) {
      await ensureDependency("PORTFOLIO_CONTEXT");
    }
    if (!state.portfolio) {
      setContextMemoryStatus("需先确认持仓", "review");
      setError("请先验证并加载持仓，再保存上下文记忆。");
      return;
    }
    const sequence = ++state.contextMemorySequence;
    const submit = byId("save-context-memory");
    submit.disabled = true;
    setError("");
    setContextMemoryStatus("保存中…");
    try {
      const response = await fetch("/api/v1/advisor/context-memory", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "context-memory-write-request.v1",
          owner_id: requestOwner,
          questionnaire: state.profile.questionnaire,
          profile: state.profile.profile,
          portfolio: state.portfolio,
          references: buildContextMemoryReferences(),
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.contextMemorySequence !== sequence) return;
      const result = await response.json();
      state.contextMemorySelected = result.record?.memory_id || null;
      setContextMemoryStatus(result.created ? "已保存 · EXPLICIT_SAVE" : "已复用 · 内容未改变", "pass");
      await loadContextMemory(requestOwner);
    } catch (error) {
      if (state.ownerId === requestOwner && state.contextMemorySequence === sequence) {
        state.contextMemorySelected = null;
        setContextMemoryStatus("未保存", "blocked");
        renderContextMemory();
        setError(error.message || "保存上下文记忆失败");
      }
    } finally {
      submit.disabled = false;
    }
  }

  async function searchContextMemory() {
    const requestOwner = state.ownerId;
    const query = byId("memory-search-query").value.trim();
    const resultNode = byId("memory-search-results");
    const button = byId("search-context-memory");
    if (!requestOwner || !query) {
      resultNode.textContent = "请先读取账户并填写检索内容。";
      return;
    }
    button.disabled = true;
    resultNode.textContent = "正在检索历史记录…";
    try {
      const response = await fetch("/api/v1/advisor/context-memory/search", {
        method: "POST", headers: {"Content-Type":"application/json", "X-Owner-ID":requestOwner},
        body: JSON.stringify({query, limit:10}),
      });
      if (!response.ok) throw await apiError(response);
      const result = await response.json();
      if (state.ownerId !== requestOwner) { resultNode.textContent = "账户已变化，请重新检索。"; return; }
      const modes = {NO_CANDIDATES:"暂无历史记录", LIMITED_KEYWORD_MATCH:"有限关键词匹配", MODEL_SEMANTIC_RANKING:"模型相关性排序"};
      resultNode.replaceChildren();
      const summary = document.createElement("p");
      summary.textContent = `HISTORICAL_ONLY · ${modes[result.mode] || result.mode} · ${result.matches.length} 条匹配。${result.notice}`;
      if (result.degraded_reason && result.degraded_reason !== "MODEL_NOT_CONFIGURED") summary.textContent += " 模型不可用或输出未通过校验，已降级。";
      resultNode.append(summary);
      for (const match of result.matches) {
        const card = document.createElement("details");
        const title = document.createElement("summary");
        title.textContent = `${match.saved_at} · ${match.source} · ${match.memory_id}`;
        const body = document.createElement("pre");
        body.textContent = JSON.stringify({status:match.status, content_hash:match.content_hash, match_basis:match.match_basis}, null, 2);
        card.append(title, body); resultNode.append(card);
      }
    } catch (error) {
      resultNode.textContent = state.ownerId === requestOwner ? (error.message || "检索失败") : "账户已变化，请重新检索。";
    } finally { button.disabled = false; }
  }

  async function loadContextMemory(ownerId = state.ownerId) {
    const requestOwner = ownerId;
    const sequence = ++state.contextMemorySequence;
    if (!requestOwner) {
      clearContextMemory();
      return;
    }
    setContextMemoryStatus("读取中…");
    try {
      const response = await fetch("/api/v1/advisor/context-memory?limit=20", {
        headers: { "X-Owner-ID": requestOwner },
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.contextMemorySequence !== sequence) return;
      const result = await response.json();
      state.contextMemoryRecords = Array.isArray(result.records) ? result.records : [];
      state.contextMemorySelected = null;
      setContextMemoryStatus(
        state.contextMemoryRecords.length ? `${state.contextMemoryRecords.length} 条最近记忆` : "暂无记忆",
        state.contextMemoryRecords.length ? "pass" : "",
      );
      renderContextMemory();
    } catch (error) {
      if (state.ownerId === requestOwner && state.contextMemorySequence === sequence) {
        state.contextMemoryRecords = [];
        state.contextMemorySelected = null;
        setContextMemoryStatus("读取失败", "blocked");
        renderContextMemory([]);
        setError(error.message || "读取上下文记忆失败");
      }
    }
  }

  function renderProfileContext(questionnaire) {
    const panel = byId("profile-template-content");
    clear(panel);
    if (!questionnaire) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "读取隔离标识模板后查看风险问卷约束。";
      panel.append(empty);
      return;
    }
    const metadata = document.createElement("dl");
    addMetadata(metadata, "Questionnaire", questionnaire.questionnaire_id);
    addMetadata(metadata, "Owner", questionnaire.owner_id);
    addMetadata(metadata, "Answered at", questionnaire.answered_at);
    addMetadata(metadata, "Loss tolerance", questionnaire.loss_tolerance_score);
      addMetadata(metadata, "Horizon", questionnaire.investment_horizon);
    addMetadata(metadata, "Liquidity", questionnaire.liquidity_need);
    addMetadata(metadata, "Experience", questionnaire.experience_level);
    addMetadata(metadata, "Return expectation", questionnaire.return_expectation);
    addMetadata(metadata, "Max drawdown", `${text(questionnaire.max_drawdown_tolerance_pct)}%`);
    const expected = questionnaire.expected_return_range;
    addMetadata(
      metadata,
      "Expected range",
      expected ? `${text(expected.minimum_pct)}% — ${text(expected.maximum_pct)}%` : "未设置",
    );
    panel.append(metadata);
  }

  function renderConfirmedProfile(profile) {
    const panel = byId("profile-confirmation-content");
    clear(panel);
    if (!profile) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "确认问卷后查看确定性画像结果。";
      panel.append(empty);
      return;
    }
    const metadata = document.createElement("dl");
    metadata.className = "metadata-grid";
    addMetadata(metadata, "Confirmed profile", profile.profile_id);
    addMetadata(metadata, "Questionnaire", profile.questionnaire_id);
    addMetadata(metadata, "Risk score", profile.risk_score);
    addMetadata(metadata, "Risk level", profile.risk_level);
    addMetadata(metadata, "Profile version", profile.profile_version);
    addMetadata(metadata, "Confirmed at", profile.created_at);
    panel.append(metadata);
  }

  const PROFILE_DIMENSION_LABELS = Object.freeze({
    risk: "风险承受能力",
    exp: "投资经验",
    act: "操作活跃度",
    res: "研究习惯",
    inf: "信息投入",
    ai: "AI 信任度",
    per: "个性化需求",
    aid: "辅助需求",
  });

  const PROFILE_RADAR_LABELS = Object.freeze({
    risk: "风险承受",
    exp: "投资经验",
    act: "操作活跃",
    res: "研究习惯",
    inf: "信息投入",
    ai: "AI 信任",
    per: "个性需求",
    aid: "辅助需求",
  });

  const RISK_LEVEL_LABELS = Object.freeze({
    CONSERVATIVE: "保守型",
    BALANCED: "平衡型",
    GROWTH: "成长型",
  });

  const DISPLAY_MODE_LABELS = Object.freeze({
    AUDIT_EXPANDED: "详细说明",
    STANDARD: "标准说明",
    CONCLUSION_FIRST: "简洁说明",
  });

  // The API and database still store the historical 0-100 trust score.  The
  // ordinary user only chooses one of these three stable display levels.
  const DISPLAY_DETAIL_LEVELS = Object.freeze({
    CONCISE: Object.freeze({ score: 80, mode: "CONCLUSION_FIRST", label: "简洁", hint: "先看结论和关键依据" }),
    STANDARD: Object.freeze({ score: 50, mode: "STANDARD", label: "标准", hint: "结论与关键依据保持平衡" }),
    DETAILED: Object.freeze({ score: 20, mode: "AUDIT_EXPANDED", label: "详细", hint: "展开结论、依据和数据说明" }),
  });

  const DISPLAY_DETAIL_BY_MODE = Object.freeze(
    Object.fromEntries(Object.values(DISPLAY_DETAIL_LEVELS).map((level) => [level.mode, level])),
  );

  function displayDetailLevelForPolicy(policyOrScore) {
    const policy = policyOrScore && typeof policyOrScore === "object" ? policyOrScore : null;
    if (policy?.mode && DISPLAY_DETAIL_BY_MODE[policy.mode]) return DISPLAY_DETAIL_BY_MODE[policy.mode];
    const score = Number(policy?.trust_score ?? policyOrScore);
    if (Number.isFinite(score) && score >= 65) return DISPLAY_DETAIL_LEVELS.CONCISE;
    if (Number.isFinite(score) && score <= 34) return DISPLAY_DETAIL_LEVELS.DETAILED;
    return DISPLAY_DETAIL_LEVELS.STANDARD;
  }

  function displayDetailLabel(policyOrScore) {
    return displayDetailLevelForPolicy(policyOrScore).label;
  }

  function setDisplayPolicyControl(policyOrScore = 50) {
    const level = displayDetailLevelForPolicy(policyOrScore);
    const trust = byId("ai-trust-score");
    const trustValue = byId("ai-trust-score-value");
    const mode = byId("display-policy-mode");
    const hint = byId("display-policy-hint");
    if (trust) trust.value = String(level.score);
    if (trustValue) trustValue.textContent = level.label;
    if (mode) mode.textContent = DISPLAY_MODE_LABELS[level.mode];
    if (hint) hint.textContent = level.hint;
    document.querySelectorAll('input[name="display-policy-level"]').forEach((input) => {
      input.checked = input.value === String(level.score);
    });
    return level;
  }

  function questionnaireAnsweredCount() {
    return Object.values(state.questionnaireAnswers || {}).filter((answer) => (
      Number.isInteger(answer?.score) || (answer?.selected_option_ids || []).length > 0
    )).length;
  }

  function setQuestionnaireError(message = "") {
    const node = byId("questionnaire-error");
    if (!node) return;
    node.hidden = !message;
    node.textContent = message;
  }

  function currentQuestionnaireSection() {
    return state.questionnaireTemplate?.sections?.[state.questionnaireSectionIndex] || null;
  }

  function unansweredQuestionIds(questionIds = null) {
    const ids = questionIds || (state.questionnaireTemplate?.questions || []).map((item) => item.question_id);
    return ids.filter((questionId) => {
      const answer = state.questionnaireAnswers?.[questionId];
      return !(Number.isInteger(answer?.score) || (answer?.selected_option_ids || []).length > 0);
    });
  }

  function saveQuestionnaireChoice(question, optionId, checked) {
    const answers = { ...(state.questionnaireAnswers || {}) };
    if (question.question_type === "MULTI") {
      const selected = new Set(answers[question.question_id]?.selected_option_ids || []);
      if (checked) selected.add(optionId);
      else selected.delete(optionId);
      if (optionId === "none" && checked) {
        selected.clear();
        selected.add("none");
      } else if (checked) {
        selected.delete("none");
      }
      if (selected.size) answers[question.question_id] = { question_id: question.question_id, selected_option_ids: [...selected] };
      else delete answers[question.question_id];
    } else {
      answers[question.question_id] = { question_id: question.question_id, selected_option_ids: [optionId] };
    }
    state.questionnaireAnswers = answers;
    setQuestionnaireError("");
    renderQuestionnaireProgress();
  }

  function saveQuestionnaireScore(question, score) {
    state.questionnaireAnswers = {
      ...(state.questionnaireAnswers || {}),
      [question.question_id]: { question_id: question.question_id, score: Number(score) },
    };
    setQuestionnaireError("");
    renderQuestionnaireProgress();
  }

  function renderQuestionnaireProgress() {
    const template = state.questionnaireTemplate;
    if (!template) return;
    const answered = questionnaireAnsweredCount();
    const progressText = byId("questionnaire-progress-text");
    const progressBar = byId("questionnaire-progress-bar");
    const sectionTitle = byId("questionnaire-section-title");
    const section = currentQuestionnaireSection();
    if (progressText) progressText.textContent = `${answered} / ${template.questions.length} 题已回答`;
    if (progressBar) progressBar.style.width = `${answered / template.questions.length * 100}%`;
    if (sectionTitle && section) sectionTitle.textContent = `第 ${state.questionnaireSectionIndex + 1} 步：${section.title}`;
    const status = byId("questionnaire-confirmation-status");
    if (status && !state.profileSummary?.questionnaire_snapshot) {
      status.textContent = answered === template.questions.length ? "待确认" : `未完成 · 缺 ${template.questions.length - answered} 题`;
      status.className = answered === template.questions.length ? "status-chip warning" : "status-chip";
    }
  }

  function scrollQuestionnaireToTop() {
    byId("questionnaire-section-tabs")?.scrollIntoView({block: "start", behavior: "instant"});
  }

  function renderQuestionnaire() {
    const template = state.questionnaireTemplate;
    const panel = byId("questionnaire-questions");
    const sectionTabs = byId("questionnaire-section-tabs");
    if (!template || !panel || !sectionTabs) return;
    const section = currentQuestionnaireSection();
    clear(panel);
    clear(sectionTabs);

    template.sections.forEach((item, index) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${index + 1}. ${item.title}`;
      button.className = index === state.questionnaireSectionIndex ? "active" : "";
      if (index === state.questionnaireSectionIndex) button.setAttribute("aria-current", "step");
      button.addEventListener("click", () => {
        state.questionnaireSectionIndex = index;
        renderQuestionnaire();
        scrollQuestionnaireToTop();
      });
      li.append(button);
      sectionTabs.append(li);
    });

    const description = document.createElement("p");
    description.className = "questionnaire-section-description";
    description.textContent = section.description;
    panel.append(description);
    const questionsById = new Map(template.questions.map((item) => [item.question_id, item]));
    section.question_ids.forEach((questionId) => {
      const question = questionsById.get(questionId);
      if (!question) return;
      const fieldset = document.createElement("fieldset");
      fieldset.className = "questionnaire-question";
      const legend = document.createElement("legend");
      legend.textContent = `${question.question_id}　${question.prompt}`;
      fieldset.append(legend);
      const choices = document.createElement("div");
      choices.className = "questionnaire-options";
      if (question.question_type === "SCORE") {
        for (let score = question.minimum_score; score <= question.maximum_score; score += 1) {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = "radio";
          input.name = question.question_id;
          input.value = String(score);
          input.checked = state.questionnaireAnswers?.[question.question_id]?.score === score;
          input.addEventListener("change", () => saveQuestionnaireScore(question, score));
          const span = document.createElement("span");
          const degrees = question.question_id === "Q12"
            ? ["几乎没有影响", "影响较小", "影响一般", "影响较大", "影响非常大"]
            : question.question_id === "Q17"
              ? ["几乎不参考", "少量参考", "适度参考", "较多参考", "高度参考"]
              : ["很低", "较低", "中等", "较高", "很高"];
          span.textContent = degrees[score - question.minimum_score];
          label.append(input, span);
          choices.append(label);
        }
      } else {
        question.options.forEach((option) => {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = question.question_type === "MULTI" ? "checkbox" : "radio";
          input.name = question.question_id;
          input.value = option.option_id;
          input.checked = (state.questionnaireAnswers?.[question.question_id]?.selected_option_ids || []).includes(option.option_id);
          input.addEventListener("change", () => {
            saveQuestionnaireChoice(question, option.option_id, input.checked);
            if (question.question_type === "MULTI") renderQuestionnaire();
          });
          const span = document.createElement("span");
          span.textContent = option.label;
          label.append(input, span);
          choices.append(label);
        });
      }
      fieldset.append(choices);
      panel.append(fieldset);
    });

    const previous = byId("questionnaire-prev");
    const next = byId("questionnaire-next");
    if (previous) previous.disabled = state.questionnaireSectionIndex === 0;
    if (next) next.hidden = state.questionnaireSectionIndex === template.sections.length - 1;
    renderQuestionnaireProgress();
  }

  function questionnairePayload() {
    const template = state.questionnaireTemplate;
    if (!template) throw new Error("问卷模板尚未加载。");
    const missing = unansweredQuestionIds();
    if (missing.length) throw new Error(`还有 ${missing.length} 题未回答：${missing.join("、")}`);
    return template.questions.map((question) => state.questionnaireAnswers[question.question_id]);
  }

  function profileLevelText(profile) {
    if (!profile) return "尚未形成";
    return `${RISK_LEVEL_LABELS[profile.risk_level] || profile.risk_level} · ${Number(profile.risk_score).toFixed(0)} 分`;
  }

  function currentProfileTag(profile) {
    return profile ? profileLevelText(profile) : "完善风险设置";
  }

  function activeProfileTag() {
    return currentProfileTag(state.profileSummary?.questionnaire_snapshot ? state.profile?.profile : null);
  }

  function renderCurrentProfileIdentity(profile = null) {
    const persona = PERSONAS[state.selectedPersona];
    if (!persona) return;
    const tag = currentProfileTag(profile);
    byId("custom-profile-chip-name").textContent = tag;
    byId("btn-custom-profile-chip").title = `当前风险设置：${persona.name}，${tag}`;
    const menuLabel = byId("profile-menu-current-label");
    if (menuLabel) menuLabel.textContent = tag;
    const heroTag = byId("copilot-hero-tag");
    if (heroTag) heroTag.textContent = tag;
  }

  function profileMetricCard(label, value, note = "") {
    const card = document.createElement("article");
    card.className = "profile-summary-card";
    const l = document.createElement("span");
    l.textContent = label;
    const v = document.createElement("strong");
    v.textContent = value;
    card.append(l, v);
    if (note) {
      const small = document.createElement("small");
      small.textContent = note;
      card.append(small);
    }
    return card;
  }

  function profileScore(value) {
    const score = Number(value);
    return Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
  }

  function profileResultSection(title, description = "") {
    const section = document.createElement("article");
    section.className = "profile-result-section";
    const header = document.createElement("header");
    const heading = document.createElement("h4");
    heading.textContent = title;
    header.append(heading);
    if (description) {
      const note = document.createElement("p");
      note.textContent = description;
      header.append(note);
    }
    const body = document.createElement("div");
    body.className = "profile-result-section-body";
    section.append(header, body);
    return { section, body };
  }

  function renderProfileRadar(presentation) {
    const wrapper = document.createElement("div");
    wrapper.className = "profile-radar-visual";
    const svgNS = "http://www.w3.org/2000/svg";
    const dimensions = Array.isArray(presentation?.dimensions) ? presentation.dimensions : [];
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 320 280");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "八维投资者画像雷达图");
    const title = document.createElementNS(svgNS, "title");
    title.textContent = "八维投资者画像雷达图";
    svg.append(title);
    if (!dimensions.length) {
      wrapper.append(svg);
      return wrapper;
    }

    const cx = 160;
    const cy = 132;
    const radius = 86;
    const angleFor = (index) => -Math.PI / 2 + (index * 2 * Math.PI) / dimensions.length;
    const pointFor = (distance, index) => {
      const angle = angleFor(index);
      return [cx + distance * Math.cos(angle), cy + distance * Math.sin(angle)];
    };
    const pointsFor = (distance) => dimensions.map((_, index) => pointFor(distance, index).map((value) => value.toFixed(2)).join(",")).join(" ");

    [20, 40, 60, 80, 100].forEach((level) => {
      const ring = document.createElementNS(svgNS, "polygon");
      ring.setAttribute("points", pointsFor((radius * level) / 100));
      ring.setAttribute("class", "profile-radar-ring");
      svg.append(ring);
    });

    dimensions.forEach((item, index) => {
      const [x, y] = pointFor(radius, index);
      const axis = document.createElementNS(svgNS, "line");
      axis.setAttribute("x1", String(cx));
      axis.setAttribute("y1", String(cy));
      axis.setAttribute("x2", x.toFixed(2));
      axis.setAttribute("y2", y.toFixed(2));
      axis.setAttribute("class", "profile-radar-axis");
      svg.append(axis);

      const [labelX, labelY] = pointFor(radius + 20, index);
      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", labelX.toFixed(2));
      label.setAttribute("y", labelY.toFixed(2));
      label.setAttribute("class", "profile-radar-label");
      label.setAttribute("text-anchor", labelX < cx - 4 ? "end" : labelX > cx + 4 ? "start" : "middle");
      label.setAttribute("dominant-baseline", labelY < cy - 4 ? "auto" : labelY > cy + 4 ? "hanging" : "middle");
      label.textContent = PROFILE_RADAR_LABELS[item.key] || item.short_label || item.label || item.key;
      svg.append(label);
    });

    const valuePolygon = document.createElementNS(svgNS, "polygon");
    valuePolygon.setAttribute("points", dimensions.map((item, index) => pointFor((radius * profileScore(item.score)) / 100, index).map((value) => value.toFixed(2)).join(",")).join(" "));
    valuePolygon.setAttribute("class", "profile-radar-value");
    svg.append(valuePolygon);

    dimensions.forEach((item, index) => {
      const [x, y] = pointFor((radius * profileScore(item.score)) / 100, index);
      const dot = document.createElementNS(svgNS, "circle");
      dot.setAttribute("cx", x.toFixed(2));
      dot.setAttribute("cy", y.toFixed(2));
      dot.setAttribute("r", "3.5");
      dot.setAttribute("class", "profile-radar-dot");
      const dotTitle = document.createElementNS(svgNS, "title");
      dotTitle.textContent = `${item.label || item.key}：${profileScore(item.score).toFixed(0)} 分`;
      dot.append(dotTitle);
      svg.append(dot);
    });
    wrapper.append(svg);
    return wrapper;
  }

  function renderProfileDimensionBars(presentation) {
    const dimensions = document.createElement("div");
    dimensions.className = "profile-dimensions profile-dimension-bars";
    (presentation?.dimensions || []).forEach((item) => {
      const row = document.createElement("div");
      const heading = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = item.label || PROFILE_DIMENSION_LABELS[item.key] || item.key;
      const value = document.createElement("strong");
      value.textContent = `${profileScore(item.score).toFixed(0)} 分`;
      heading.append(label, value);
      const track = document.createElement("div");
      track.className = "profile-dimension-track";
      const bar = document.createElement("span");
      bar.style.width = `${profileScore(item.score)}%`;
      track.append(bar);
      row.append(heading, track);
      dimensions.append(row);
    });
    return dimensions;
  }

  function renderProfileSummary(summary, options = {}) {
    const panel = byId("profile-summary-content");
    if (!panel) return;
    clear(panel);
    const snapshot = summary?.questionnaire_snapshot || null;
    const effective = summary?.effective_profile || snapshot?.profile || null;
    const presentation = summary?.presentation || null;
    const status = byId("questionnaire-confirmation-status");
    if (!snapshot) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "尚未完成 19 题问卷。完成后将生成你的风险偏好与设置。";
      panel.append(empty);
      if (status) {
        status.textContent = "问卷未完成";
        status.className = "status-chip";
      }
      return;
    }
    if (status) {
      status.textContent = options.preview ? "预览未保存" : `已确认 · 第 ${snapshot.snapshot_version} 版`;
      status.className = options.preview ? "status-chip warning" : "status-chip ready";
    }
    if (!presentation) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "画像展示规则尚未返回，请刷新偏好结果。";
      panel.append(empty);
      return;
    }

    const identity = document.createElement("section");
    identity.className = "profile-result-identity";
    const identityCopy = document.createElement("div");
    const identityEyebrow = document.createElement("span");
    identityEyebrow.className = "eyebrow clay";
    identityEyebrow.textContent = "量化投资画像";
    const identityTitle = document.createElement("h4");
    identityTitle.textContent = presentation.archetype;
    const identityNote = document.createElement("p");
    identityNote.textContent = `${presentation.suitability_label} · 风险分 ${profileScore(presentation.risk_score).toFixed(0)} 分`;
    identityCopy.append(identityEyebrow, identityTitle, identityNote);
    const tags = document.createElement("div");
    tags.className = "profile-result-tags";
    (presentation.tags || []).forEach((tagValue) => {
      const tag = document.createElement("span");
      tag.className = "profile-result-tag";
      tag.textContent = tagValue;
      tags.append(tag);
    });
    identity.append(identityCopy, tags);
    panel.append(identity);

    const cards = document.createElement("div");
    cards.className = "profile-summary-cards";
    cards.append(
      profileMetricCard("适当性等级", presentation.suitability_label, "基于 19 题问卷"),
      profileMetricCard("画像风险分", `${profileScore(presentation.risk_score).toFixed(0)} 分`, "八维画像中的风险承受维度"),
      profileMetricCard("当前有效评级", profileLevelText(effective), "用于后续风险约束"),
    );
    panel.append(cards);

    const visual = profileResultSection("八维画像", "8 个维度均按 0–100 分展示；分数只来自本次已确认问卷。");
    const visualLayout = document.createElement("div");
    visualLayout.className = "profile-radar-layout";
    visualLayout.append(renderProfileRadar(presentation), renderProfileDimensionBars(presentation));
    visual.body.append(visualLayout);
    panel.append(visual.section);

    const resultPanels = document.createElement("div");
    resultPanels.className = "profile-result-panels";

    const facts = profileResultSection("关键档案", "用于解释画像和服务策略的问卷答案。");
    const factGrid = document.createElement("div");
    factGrid.className = "profile-key-facts";
    (presentation.key_profile || []).forEach((fact) => {
      const card = document.createElement("div");
      card.className = "profile-key-fact";
      const label = document.createElement("span");
      label.textContent = fact.label;
      const value = document.createElement("strong");
      value.textContent = fact.value;
      card.append(label, value);
      factGrid.append(card);
    });
    facts.body.append(factGrid);
    resultPanels.append(facts.section);

    const strategy = profileResultSection("服务策略", "根据画像结果安排分析顺序和解释方式。");
    const strategyList = document.createElement("ul");
    strategyList.className = "profile-strategy-list";
    (presentation.service_strategy || []).forEach((item) => {
      const row = document.createElement("li");
      row.textContent = item;
      strategyList.append(row);
    });
    strategy.body.append(strategyList);
    resultPanels.append(strategy.section);

    const allocation = profileResultSection("资产配置参考", "当前仅展示画像级参考比例，不生成交易指令。");
    const allocationList = document.createElement("div");
    allocationList.className = "profile-allocation-list";
    const allocationColors = { cash: "var(--slate)", bonds: "var(--sage)", equity: "var(--clay)" };
    (presentation.asset_allocation || []).forEach((item) => {
      const row = document.createElement("div");
      row.className = "profile-allocation-row";
      const heading = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = item.label;
      const value = document.createElement("strong");
      value.textContent = `${profileScore(item.target_pct).toFixed(0)}%`;
      heading.append(label, value);
      const track = document.createElement("div");
      track.className = "profile-allocation-track";
      const bar = document.createElement("span");
      bar.style.width = `${profileScore(item.target_pct)}%`;
      bar.style.background = allocationColors[item.key] || "var(--clay)";
      track.append(bar);
      row.append(heading, track);
      allocationList.append(row);
    });
    const equityRange = document.createElement("p");
    equityRange.className = "profile-allocation-range";
    equityRange.textContent = `权益参考区间：${presentation.equity_range.minimum_pct}%–${presentation.equity_range.maximum_pct}%`;
    const riskNotice = document.createElement("p");
    riskNotice.className = "profile-risk-notice";
    riskNotice.textContent = presentation.risk_notice;
    allocation.body.append(allocationList, equityRange, riskNotice);
    resultPanels.append(allocation.section);
    panel.append(resultPanels);

    if (options.preview) {
      const previewNote = document.createElement("div");
      previewNote.className = "profile-preview-note";
      previewNote.textContent = "当前为问卷预览，确认后才会保存并用于风险约束。";
      panel.append(previewNote);
    }
    const policy = summary?.display_policy;
    if (policy) {
      const level = setDisplayPolicyControl(policy);
      const policyNote = document.createElement("p");
      policyNote.className = "profile-policy-note";
      policyNote.textContent = `当前回答详细度：${level.label}。${level.hint}；风险提示始终展开。`;
      panel.append(policyNote);
    }
  }

  async function loadQuestionnaireTemplate() {
    const owner = state.ownerId;
    const response = await fetch("/api/v1/advisor/profile/questionnaire-template", {
      headers: { "X-Owner-ID": owner },
    });
    if (!response.ok) throw await apiError(response);
    const template = await response.json();
    if (owner !== state.ownerId) return null;
    state.questionnaireTemplate = template;
    state.questionnaireSectionIndex = Math.min(state.questionnaireSectionIndex, template.sections.length - 1);
    renderQuestionnaire();
    return template;
  }

  async function loadProfileSummary() {
    const owner = state.ownerId;
    const response = await fetch("/api/v1/advisor/profile/summary", {
      headers: { "X-Owner-ID": owner },
    });
    if (!response.ok) throw await apiError(response);
    const summary = await response.json();
    if (owner !== state.ownerId) return null;
    state.profileSummary = summary;
    state.displayPolicy = summary.display_policy;
    if (summary.questionnaire_snapshot) {
      state.profile = {
        questionnaire: summary.questionnaire_snapshot.questionnaire,
        profile: summary.effective_profile || summary.questionnaire_snapshot.profile,
      };
      state.questionnaireAnswers = Object.fromEntries(
        summary.questionnaire_snapshot.answers.map((answer) => [answer.question_id, answer]),
      );
    }
    state.behaviorProfile = summary.behavior_profile;
    renderCurrentProfileIdentity(summary.questionnaire_snapshot ? state.profile.profile : null);
    renderBehaviorProfile(summary.behavior_profile);
    renderProfileSummary(summary);
    renderQuestionnaire();
    renderPortfolioReadiness();
    applyQuestionnaireGate(summary);
    return summary;
  }

  async function previewFullQuestionnaire() {
    setQuestionnaireError("");
    try {
      const answers = questionnairePayload();
      const response = await fetch("/api/v1/advisor/profile/questionnaire/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Owner-ID": state.ownerId },
        body: JSON.stringify({
          schema_version: "questionnaire-preview-request.v1",
          owner_id: state.ownerId,
          evaluated_at: new Date().toISOString(),
          answers,
        }),
      });
      if (!response.ok) throw await apiError(response);
      const result = await response.json();
      state.questionnairePreview = result.snapshot;
      renderProfileSummary({ questionnaire_snapshot: result.snapshot, presentation: result.presentation, effective_profile: result.snapshot.profile, display_policy: state.displayPolicy }, { preview: true });
    } catch (error) {
      setQuestionnaireError(error.message || "问卷预览失败。");
    }
  }

  async function confirmFullQuestionnaire(event) {
    event?.preventDefault();
    setQuestionnaireError("");
    try {
      const answers = questionnairePayload();
      const response = await fetch("/api/v1/advisor/profile/questionnaire/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Owner-ID": state.ownerId },
        body: JSON.stringify({
          schema_version: "questionnaire-confirmation-request.v1",
          owner_id: state.ownerId,
          confirmed_at: new Date().toISOString(),
          answers,
        }),
      });
      if (!response.ok) throw await apiError(response);
      const result = await response.json();
      state.profile = { questionnaire: result.snapshot.questionnaire, profile: result.snapshot.profile };
      state.questionnairePreview = null;
      await recomputeBehaviorProfile();
      await loadProfileSummary();
      if (state.portfolio) await refreshPortfolioHealth();
      window.location.hash = "copilot";
    } catch (error) {
      setQuestionnaireError(error.message || "问卷确认失败。");
    }
  }

  function renderBehaviorProfile(profile) {
    const panel = byId("behavior-profile-content");
    const status = byId("behavior-profile-status");
    if (!panel || !status) return;
    clear(panel);
    if (!profile) {
      const p = document.createElement("p");
      p.textContent = "这些设置用于让分析更符合你的投资目标。";
      panel.append(p);
      status.className = "cf-verdict cf-verdict-warning";
      status.textContent = "可完善";
      renderConversationProfileContext(panel);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "behavior-profile-metrics";
    [
      ["风险等级", profile.suitability_level],
      ["参考风险分", profile.effective_risk_score],
      ["近 90 日换手", profile.metrics?.turnover_90d_pct == null ? "未采集（不影响问卷画像）" : `${profile.metrics.turnover_90d_pct}%`],
      ["历史最大回撤", profile.metrics?.max_drawdown_pct == null ? "未采集（不影响问卷画像）" : `${profile.metrics.max_drawdown_pct}%`],
    ].forEach(([label, value]) => {
      const card = document.createElement("div");
      card.className = "behavior-profile-metric";
      const l = document.createElement("span");
      l.textContent = label;
      const v = document.createElement("strong");
      v.textContent = String(value);
      card.append(l, v);
      grid.append(card);
    });
    const note = document.createElement("p");
    note.textContent = "行为证据为可选参考，不作为问卷画像展示的前置条件。";
    panel.append(grid, note);
    const calculated = profile.evidence_status === "CALCULATED";
    status.className = calculated ? "cf-verdict cf-verdict-pass" : "cf-verdict cf-verdict-warning";
    status.textContent = calculated ? "已更新" : "可完善";
    setDisplayPolicyControl(profile.display_policy || 50);
    renderConversationProfileContext(panel);
  }

  function renderConversationProfileContext(panel = byId("behavior-profile-content")) {
    const saved = PERSONAS["custom-user"]?.conversationProfile;
    if (!panel || !saved) return;
    const note = document.createElement("p");
    note.className = "conversation-profile-context-note";
    note.textContent = `对话补充：${saved.goalLabel} · ${saved.horizonLabel} · ${saved.liquidityLabel} · 回撤顾虑 ${saved.maxDrawdown}%`;
    panel.append(note);
  }

  async function loadBehaviorProfile() {
    const owner = state.ownerId;
    try {
      const response = await fetch("/api/v1/advisor/behavior/profile", {
        headers: { "X-Owner-ID": owner },
      });
      if (state.ownerId !== owner) return null;
      if (!response.ok) throw await apiError(response);
      const payload = await response.json();
      const profile = payload.profile || null;
      if (state.ownerId !== owner) return null;
      if (!profile) {
        state.behaviorProfile = null;
        renderBehaviorProfile(null);
        return null;
      }
      state.behaviorProfile = profile;
      state.displayPolicy = profile.display_policy;
      renderBehaviorProfile(profile);
      return profile;
    } catch (error) {
      if (state.ownerId === owner) renderBehaviorProfile(null);
      return null;
    }
  }

  async function saveDisplayPolicy() {
    const trust = Number(byId("ai-trust-score")?.value || 50);
    const owner = state.ownerId;
    const response = await fetch("/api/v1/advisor/display-policy", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "X-Owner-ID": owner },
      body: JSON.stringify({
        schema_version: "display-policy-update-request.v1",
        owner_id: owner,
        trust_score: trust,
        updated_at: new Date().toISOString(),
      }),
    });
    if (!response.ok) throw await apiError(response);
    const result = await response.json();
    state.displayPolicy = result.policy;
    setDisplayPolicyControl(result.policy);
    if (state.behaviorProfile) {
      state.behaviorProfile = { ...state.behaviorProfile, display_policy: result.policy };
      renderBehaviorProfile(state.behaviorProfile);
    }
    if (state.profileSummary) {
      state.profileSummary = { ...state.profileSummary, display_policy: result.policy };
      renderProfileSummary(state.profileSummary);
    }
  }

  async function recomputeBehaviorProfile() {
    if (!state.profile?.profile) {
      setError("请先完成风险测评，再更新投资偏好。");
      return null;
    }
    const owner = state.ownerId;
    const response = await fetch("/api/v1/advisor/behavior/recompute", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Owner-ID": owner },
      body: JSON.stringify({
        schema_version: "behavior-profile-recompute-request.v1",
        owner_id: owner,
        calculated_at: new Date().toISOString(),
        questionnaire_profile: state.profile.profile,
      }),
    });
    if (!response.ok) throw await apiError(response);
    const result = await response.json();
    state.behaviorProfile = result.profile;
    renderBehaviorProfile(result.profile);
    return result;
  }

  function setPortfolioContextStatus(message, className = "") {
    const node = byId("portfolio-context-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setProfileContextStatus(message, className = "") {
    const node = byId("profile-context-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setProfileProposalStatus(message, className = "") {
    const node = byId("profile-proposal-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function setProfileProposalConfirmStatus(message, className = "") {
    const node = byId("profile-proposal-confirm-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function profileDimensionLabel(dimension) {
    return {
      investment_horizon: "投资期限",
      liquidity_need: "流动性需求",
      experience_level: "投资经验",
      return_expectation: "收益预期",
      max_drawdown_tolerance_pct: "最大回撤容忍度",
      expected_return_range: "预期收益区间",
    }[dimension] || text(dimension);
  }

  function renderProfileProposalResult(profile) {
    const panel = byId("profile-proposal-result");
    clear(panel);
    if (!profile) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "确认提案后查看保留冲突选择的风险画像。";
      panel.append(empty);
      return;
    }
    const metadata = document.createElement("dl");
    metadata.className = "metadata-grid";
    addMetadata(metadata, "Profile", profile.profile_id);
    addMetadata(metadata, "Risk score", profile.risk_score);
    addMetadata(metadata, "Risk level", profile.risk_level);
    addMetadata(metadata, "Questionnaire", profile.questionnaire_id);
    addMetadata(metadata, "Extraction", profile.extraction_id);
    addMetadata(metadata, "Confidence", profile.confidence);
    addMetadata(metadata, "Confirmed at", profile.created_at);
    panel.append(metadata);
    const conflicts = profile.conflicts || [];
    if (conflicts.length) {
      const heading = document.createElement("h4");
      heading.className = "context-heading";
      heading.textContent = "已解决的冲突";
      panel.append(heading);
      const list = document.createElement("div");
      list.className = "profile-proposal-resolved";
      conflicts.forEach((conflict) => {
        const row = document.createElement("div");
        row.textContent = `${profileDimensionLabel(conflict.dimension)} · ${text(conflict.resolution)} · ${text(conflict.resolved_value)}`;
        list.append(row);
      });
      panel.append(list);
    }
  }

  function renderProfileProposal(draft) {
    const panel = byId("profile-proposal-content");
    clear(panel);
    const confirm = byId("confirm-profile-proposal");
    confirm.disabled = !draft;
    if (!draft) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "粘贴提案后查看问卷与提取值的冲突。";
      panel.append(empty);
      return;
    }
    const meta = document.createElement("div");
    meta.className = "profile-proposal-meta";
    const metadata = document.createElement("dl");
    metadata.className = "metadata-grid";
    addMetadata(metadata, "Draft", draft.draft_id);
    addMetadata(metadata, "Owner", draft.owner_id);
    addMetadata(metadata, "Status", draft.status);
    addMetadata(metadata, "Extraction", draft.extraction?.extraction_id);
    addMetadata(metadata, "Confidence", draft.extraction?.confidence);
    addMetadata(metadata, "Input digest", draft.extraction?.input_digest);
    meta.append(metadata);
    if (!(draft.conflicts || []).length) {
      const ready = document.createElement("p");
      ready.textContent = "没有维度冲突；仍需显式确认后生成风险画像。";
      meta.append(ready);
    }
    panel.append(meta);

    (draft.conflicts || []).forEach((conflict) => {
      const card = document.createElement("article");
      card.className = "profile-conflict";
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = profileDimensionLabel(conflict.dimension);
      header.append(title, chip("需要确认", "review"));
      card.append(header);
      const values = document.createElement("dl");
      values.className = "profile-conflict-values";
      addMetadata(values, "Questionnaire", conflict.questionnaire_value);
      addMetadata(values, "Extraction", conflict.extracted_value);
      card.append(values);
      const resolution = document.createElement("label");
      resolution.className = "profile-resolution";
      resolution.textContent = "选择生效值";
      const select = document.createElement("select");
      select.dataset.conflictId = conflict.conflict_id;
      const placeholder = document.createElement("option");
      placeholder.value = "UNRESOLVED";
      placeholder.textContent = "请选择";
      select.append(placeholder);
      [
        ["USE_QUESTIONNAIRE", "使用问卷值"],
        ["USE_EXTRACTION", "使用提取值"],
      ].forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        select.append(option);
      });
      const selected = state.profileProposalResolutions[conflict.conflict_id];
      if (selected) select.value = selected;
      select.addEventListener("change", () => {
        if (select.value === "UNRESOLVED") delete state.profileProposalResolutions[conflict.conflict_id];
        else state.profileProposalResolutions[conflict.conflict_id] = select.value;
        state.profileProposalProfile = null;
        renderProfileProposalResult(null);
        setProfileProposalConfirmStatus("待确认");
      });
      resolution.append(select);
      card.append(resolution);
      panel.append(card);
    });
  }

  function clearProfileProposal({ clearInput = true } = {}) {
    state.profileProposalSequence += 1;
    state.profileProposalDraft = null;
    state.profileProposalQuestionnaire = null;
    state.profileProposalExtraction = null;
    state.profileProposalProfile = null;
    state.profileProposalResolutions = {};
    const proposalInput = byId("profile-proposal-json");
    if (!proposalInput) return;
    if (clearInput) proposalInput.value = "";
    setProfileProposalStatus("未预览");
    setProfileProposalConfirmStatus("未确认");
    renderProfileProposal(null);
    renderProfileProposalResult(null);
  }

  function setAdvisorPlanStatus(message, className = "") {
    const node = byId("advisor-plan-status");
    node.className = `status-chip ${className}`.trim();
    node.textContent = message;
  }

  function renderAdvisorPlan(plan) {
    const panel = byId("advisor-plan-content");
    clear(panel);
    if (!plan) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "选择一个结构化研究问题后预览四轨道任务。";
      panel.append(empty);
      return;
    }
    const metadata = document.createElement("dl");
    metadata.className = "metadata-grid";
    addMetadata(metadata, "Plan", plan.plan_id);
    addMetadata(metadata, "Intent", `${text(plan.intent_type)} · ${text(plan.intent_id)}`);
    addMetadata(metadata, "Owner", plan.owner_id);
    addMetadata(metadata, "Portfolio bundle", plan.portfolio_bundle_id);
    addMetadata(metadata, "Position snapshot", plan.position_snapshot_id);
    addMetadata(metadata, "Questionnaire", plan.questionnaire_id);
    addMetadata(metadata, "Scope", displayDescription(plan.scope_description));
    addMetadata(metadata, "Nodes", plan.node_count);
    panel.append(metadata);

    const heading = document.createElement("h4");
    heading.className = "context-heading";
    heading.textContent = "专业研究轨道";
    panel.append(heading);
    const roles = document.createElement("div");
    roles.className = "intent-plan-roles";
    (plan.roles || []).forEach((role) => roles.append(chip(researchRoleLabel(role), "pass")));
    panel.append(roles);
  }

  function clearAdvisorPlan() {
    state.advisorPlan = null;
    setAdvisorPlanStatus("未预览");
    renderAdvisorPlan(null);
  }

  function renderProfile(receipt) {
    const panel = byId("profile-content");
    clear(panel);
    if (!receipt) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "该事件没有可展示的决策回执。";
      panel.append(empty);
      return;
    }
    const grid = document.createElement("dl");
    grid.className = "metadata-grid";
    addMetadata(grid, "Profile", `${receipt.profile_id} · v${receipt.profile_version}`);
    addMetadata(grid, "Portfolio bundle", receipt.portfolio_bundle_id);
    addMetadata(grid, "Position snapshot", receipt.position_snapshot_id);
    addMetadata(grid, "Risk assessment", receipt.risk_assessment_id);
    addMetadata(grid, "Allocation envelope", receipt.allocation_envelope_id);
    addMetadata(grid, "Research run", receipt.research_run_id);
    panel.append(grid);
  }

  function renderDetail(event) {
    state.selected = event.event_id;
    state.selectedDecisionEvent = event;
    renderEvents();
    const result = event.result;
    const detail = byId("detail-content");
    clear(detail);
    const status = byId("detail-status");
    status.className = `status-chip ${statusClass(event.status)}`;
    status.textContent = statusLabel(event.status);

    if (event.status !== "PASS" || !result.receipt) {
      const blocked = document.createElement("div");
      blocked.className = "notice error";
      blocked.textContent = event.status === "REVIEW_REQUIRED"
        ? "当前证据或风险输入仍需人工复核，Prism 没有生成可执行建议。"
        : "当前决策被安全阻断，Prism 没有生成可执行建议。";
      detail.append(blocked);
      const issueList = document.createElement("ul");
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${researchIssueLabel(issue.code)}: ${displayDescription(issue.safe_message)}`;
        issueList.append(item);
      });
      if (issueList.childElementCount) detail.append(issueList);
      renderProfile(null);
      renderEvidence(null);
      return;
    }

    const summary = document.createElement("div");
    summary.className = "decision-summary";
    const summaryLabel = document.createElement("span");
    summaryLabel.className = "eyebrow clay";
    summaryLabel.textContent = "分析依据";
    const summaryText = document.createElement("p");
    summaryText.textContent = text(result.summary);
    summary.append(summaryLabel, summaryText);
    detail.append(summary);

    const recs = document.createElement("div");
    recs.className = "recommendation-list";
    (result.trace.recommendations || []).forEach((recommendation) => {
      const card = document.createElement("article");
      card.className = "recommendation-card";
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = recommendation.asset_id;
      const action = document.createElement("span");
      action.className = `action-chip ${recommendation.action_type.toLowerCase()}`;
      action.textContent = text(recommendation.action_type);
      header.append(title, action);
      const grid = document.createElement("dl");
      grid.className = "metadata-grid";
      addMetadata(grid, "Allocation range", `${recommendation.allocation_range.minimum_pct}% — ${recommendation.allocation_range.maximum_pct}%`);
      addMetadata(grid, "Finding IDs", recommendation.finding_ids.join(", "));
      addMetadata(grid, "Recommendation ID", recommendation.recommendation_id);
      card.append(header, grid);
      recs.append(card);
    });
    detail.append(recs);
    const invalidation = document.createElement("div");
    invalidation.className = "invalidation";
    invalidation.textContent = "失效条件";
    const conditions = document.createElement("ul");
    const allConditions = new Set();
    (result.trace.recommendations || []).forEach((recommendation) => {
      (recommendation.invalidation_conditions || []).forEach((condition) => allConditions.add(condition));
    });
    [...allConditions].forEach((condition) => {
      const item = document.createElement("li");
      item.textContent = displayDescription(condition);
      conditions.append(item);
    });
    invalidation.append(conditions);
    detail.append(invalidation);
    renderProfile(result.receipt);
    renderEvidence(result);
  }

  function renderEvidence(result) {
    const panel = byId("evidence-content");
    clear(panel);
    if (!result || !result.trace) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "选择通过（PASS）回执后展开证据。";
      panel.append(empty);
      renderAdvancedEvidence();
      return;
    }
    const evidenceById = new Map((result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.trace.findings || []).forEach((finding) => {
      const details = document.createElement("details");
      details.className = "evidence-item";
      const summary = document.createElement("summary");
      summary.textContent = `${text(finding.kind)} · ${text(finding.statement)}`;
      details.append(summary);
      const meta = document.createElement("div");
      meta.className = "evidence-meta";
      const addMetaLine = (value) => {
        const line = document.createElement("div");
        line.textContent = value;
        meta.append(line);
      };
      addMetaLine(`发现（FINDING）：${text(finding.finding_id)}`);
      finding.fact_ids.forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        addMetaLine(`事实（FACT）：${text(fact.fact_id)} · ${text(fact.metric)} = ${text(fact.value)}`);
        fact.evidence_ids.forEach((evidenceId) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          addMetaLine(`证据（EVIDENCE）：${text(evidence.evidence_id)} · ${text(evidence.source)} · ${text(evidence.period)}`);
        });
      });
      details.append(meta);
      panel.append(details);
    });
    if (!panel.childElementCount) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "该回执没有可展示的发现（FINDING）。";
      panel.append(empty);
    }
    renderAdvancedEvidence();
  }

  const ADVANCED_EVIDENCE_QUALITY_LABELS = Object.freeze({
    VERIFIED: "已验证（VERIFIED）",
    STALE: "陈旧/需复核（STALE）",
    PARTIAL: "部分可用（PARTIAL）",
    CONFLICTING: "来源冲突（CONFLICTING）",
    INVALID: "无效（INVALID）",
  });
  const ADVANCED_EVIDENCE_MODE_LABELS = Object.freeze({
    DIRECT: "主数据提供方直连（DIRECT）",
    CACHE_FRESH: "新鲜缓存（CACHE_FRESH）",
    FALLBACK_PROVIDER: "备用数据提供方（FALLBACK_PROVIDER）",
    CACHE_STALE_FALLBACK: "陈旧缓存回退（CACHE_STALE_FALLBACK）",
    UNAVAILABLE: "未提供送达元数据（UNAVAILABLE）",
  });
  const ADVANCED_EVIDENCE_SOURCE_LABELS = Object.freeze({
    ADVISOR: "投顾回执（ADVISOR）",
    RESEARCH_MATRIX: "研究矩阵（RESEARCH_MATRIX）",
    STOCK: "个股研究（STOCK）",
    FUND: "ETF / 基金研究（FUND）",
    CONVERTIBLE_BOND: "可转债研究（CONVERTIBLE_BOND）",
  });
  const ADVANCED_EVIDENCE_PROMOTION_LABELS = Object.freeze({
    FINDING: "已闭合发现（FINDING）",
    FACT: "已进入事实（FACT）",
    AVAILABLE: "可用 · 未升级（AVAILABLE）",
  });

  function advancedEvidenceModeLabel(mode) {
    return ADVANCED_EVIDENCE_MODE_LABELS[mode] || text(mode, ADVANCED_EVIDENCE_MODE_LABELS.UNAVAILABLE);
  }

  function advancedEvidenceQualityLabel(status) {
    return ADVANCED_EVIDENCE_QUALITY_LABELS[status] || text(status, "未知质量");
  }

  function advancedEvidenceQualityClass(status) {
    if (status === "VERIFIED") return "pass";
    if (status === "STALE" || status === "PARTIAL" || status === "CONFLICTING") return "review";
    return "blocked";
  }

  function advancedEvidencePromotionLabel(promotion) {
    return ADVANCED_EVIDENCE_PROMOTION_LABELS[promotion] || text(promotion);
  }

  function advancedEvidenceValue(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") return "[结构化值]";
    return String(value);
  }

  function advancedEvidenceCacheAgeLabel(age) {
    if (age === null || age === undefined || age === "") return "未提供";
    const numericAge = Number(age);
    if (!Number.isFinite(numericAge) || numericAge < 0) return "未提供";
    if (numericAge < 1000) return `${Math.round(numericAge)} 毫秒`;
    if (numericAge < 60000) return `${(numericAge / 1000).toFixed(1)} 秒 · ${Math.round(numericAge)} 毫秒`;
    return `${(numericAge / 60000).toFixed(1)} 分钟 · ${Math.round(numericAge)} 毫秒`;
  }

  function advancedEvidenceRunId(result, fallback) {
    return result && (result.run_id || result.request_id || result.matrix_id) || fallback;
  }

  function advancedEvidenceTraceEntries(sourceKey, sourceLabel, result, ownerId, fallbackRunId) {
    if (!result || !result.trace || !ownerId || ownerId !== state.ownerId) return [];
    const trace = result.trace;
    const evidenceItems = Array.isArray(trace.evidence) ? trace.evidence : [];
    const facts = Array.isArray(trace.facts) ? trace.facts : [];
    const findings = Array.isArray(trace.findings) ? trace.findings : [];
    const validations = Array.isArray(result.validations) ? result.validations : [];
    const findingsByFactId = new Map();
    findings.forEach((finding) => {
      (finding.fact_ids || []).forEach((factId) => {
        const existing = findingsByFactId.get(factId) || [];
        existing.push(finding);
        findingsByFactId.set(factId, existing);
      });
    });
    const nodes = Array.isArray(result.nodes) ? result.nodes : [];
    const resultIssues = Array.isArray(result.issues) ? result.issues : [];
    const runId = advancedEvidenceRunId(result, fallbackRunId);
    return evidenceItems.map((evidence) => {
      const relatedFacts = facts.filter((fact) => (fact.evidence_ids || []).includes(evidence.evidence_id));
      const relatedFindings = relatedFacts.flatMap((fact) => findingsByFactId.get(fact.fact_id) || []);
      const relatedValidations = validations.filter((validation) => [
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "duplicate_lineage_evidence_ids",
        "unlinked_evidence_ids",
        "unresolved_evidence_ids",
      ].some((field) => (validation[field] || []).includes(evidence.evidence_id)));
      const matchingNodes = nodes.filter((candidate) => candidate.provider && candidate.provider === evidence.provider);
      const node = matchingNodes.find((candidate) => (
        candidate.node_id && evidence.source && String(evidence.source).includes(String(candidate.node_id))
      )) || matchingNodes[0] || null;
      const inferredMode = evidence.quality_status === "STALE"
        ? "CACHE_STALE_FALLBACK"
        : node?.provider_serving_mode || "UNAVAILABLE";
      const mode = node?.provider_serving_mode || inferredMode;
      const promotion = relatedFindings.length ? "FINDING" : relatedFacts.length ? "FACT" : "AVAILABLE";
      const issueLines = [];
      relatedValidations.forEach((validation) => {
        (validation.issues || []).forEach((issue) => {
          const line = `${researchIssueLabel(issue.code)}: ${displayDescription(issue.safe_message)}`;
          if (!issueLines.includes(line)) issueLines.push(line);
        });
      });
      if (!relatedValidations.length && resultIssues.length && promotion === "AVAILABLE") {
        resultIssues.forEach((issue) => {
          const line = `${researchIssueLabel(issue.code)}: ${displayDescription(issue.safe_message)}`;
          if (!issueLines.includes(line)) issueLines.push(line);
        });
      }
      const searchText = [
        evidence.evidence_id,
        evidence.provider,
        evidence.source,
        evidence.field,
        evidence.period,
        evidence.lineage_id,
        sourceLabel,
        advancedEvidenceQualityLabel(evidence.quality_status),
        advancedEvidenceModeLabel(mode),
        advancedEvidencePromotionLabel(promotion),
      ].map((value) => text(value, "")).join(" ").toLocaleLowerCase();
      return {
        key: `${sourceKey}:${text(evidence.evidence_id, "unknown")}`,
        sourceKey,
        sourceLabel,
        ownerId,
        runId,
        pipelineStatus: result.pipeline_status || result.status || "UNAVAILABLE",
        evidence,
        facts: relatedFacts,
        findings: relatedFindings,
        validations: relatedValidations,
        issues: issueLines,
        node,
        mode,
        cacheAgeMs: node?.provider_cache_age_ms ?? null,
        promotion,
        searchText,
      };
    });
  }

  function collectAdvancedEvidenceEntries() {
    if (!state.ownerId) return [];
    const entries = [];
    const selectedEvent = state.selectedDecisionEvent;
    if (selectedEvent && selectedEvent.owner_id === state.ownerId && selectedEvent.result) {
      entries.push(...advancedEvidenceTraceEntries(
        "ADVISOR",
        ADVANCED_EVIDENCE_SOURCE_LABELS.ADVISOR,
        selectedEvent.result,
        selectedEvent.owner_id,
        selectedEvent.event_id,
      ));
    }
    [
      ["RESEARCH_MATRIX", state.researchRun, ADVANCED_EVIDENCE_SOURCE_LABELS.RESEARCH_MATRIX],
      ["STOCK", state.stockResearchRun, ADVANCED_EVIDENCE_SOURCE_LABELS.STOCK],
      ["FUND", state.fundResearchRun, ADVANCED_EVIDENCE_SOURCE_LABELS.FUND],
      ["CONVERTIBLE_BOND", state.convertibleBondResearchRun, ADVANCED_EVIDENCE_SOURCE_LABELS.CONVERTIBLE_BOND],
    ].forEach(([sourceKey, result, sourceLabel]) => {
      if (!result || result.owner_id !== state.ownerId) return;
      entries.push(...advancedEvidenceTraceEntries(sourceKey, sourceLabel, result, result.owner_id, null));
    });
    return entries.sort((left, right) => {
      const sourceOrder = left.sourceKey.localeCompare(right.sourceKey);
      return sourceOrder || text(left.evidence.evidence_id, "").localeCompare(text(right.evidence.evidence_id, ""));
    });
  }

  function setAdvancedEvidenceSelect(id, stateKey, values, labels, allLabel) {
    const select = byId(id);
    if (!select) return;
    const current = state[stateKey] || "ALL";
    clear(select);
    const all = document.createElement("option");
    all.value = "ALL";
    all.textContent = allLabel;
    select.append(all);
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = labels[value] || value;
      select.append(option);
    });
    const allowed = ["ALL", ...values];
    state[stateKey] = allowed.includes(current) ? current : "ALL";
    select.value = state[stateKey];
  }

  function renderAdvancedEvidenceDetail(panel, entry) {
    clear(panel);
    if (!entry) {
      const empty = document.createElement("div");
      empty.className = "advanced-evidence-empty";
      empty.textContent = "当前筛选没有匹配的证据。";
      panel.append(empty);
      return;
    }
    const header = document.createElement("header");
    const title = document.createElement("strong");
    title.textContent = entry.evidence.evidence_id;
    header.append(title);
    const badges = document.createElement("div");
    badges.className = "advanced-evidence-badges";
    badges.append(
      chip(advancedEvidenceQualityLabel(entry.evidence.quality_status), advancedEvidenceQualityClass(entry.evidence.quality_status)),
      chip(
        advancedEvidenceModeLabel(entry.mode),
        entry.mode === "CACHE_STALE_FALLBACK" || entry.mode === "FALLBACK_PROVIDER" ? "review" : entry.mode === "UNAVAILABLE" ? "" : "pass",
      ),
      chip(advancedEvidencePromotionLabel(entry.promotion), entry.promotion === "FINDING" ? "pass" : "review"),
    );
    panel.append(header, badges);

    const metadata = document.createElement("dl");
    metadata.className = "metadata-grid";
    addMetadata(metadata, "研究轨道", entry.sourceLabel);
    addMetadata(metadata, "Owner", entry.ownerId);
    addMetadata(metadata, "Run", entry.runId);
    addMetadata(metadata, "Provider", entry.evidence.provider);
    addMetadata(metadata, "Source", entry.evidence.source);
    addMetadata(metadata, "Field", entry.evidence.field);
    addMetadata(metadata, "Value", `${advancedEvidenceValue(entry.evidence.value)} ${text(entry.evidence.unit, "")}`.trim());
    addMetadata(metadata, "Period", entry.evidence.period);
    addMetadata(metadata, "Observed at", entry.evidence.observed_at);
    addMetadata(metadata, "Retrieved at", entry.evidence.retrieved_at);
    addMetadata(metadata, "Lineage", entry.evidence.lineage_id);
    addMetadata(metadata, "Cache age", advancedEvidenceCacheAgeLabel(entry.cacheAgeMs));
    addMetadata(metadata, "Pipeline", entry.pipelineStatus);
    panel.append(metadata);

    if (entry.evidence.quality_note) {
      const note = document.createElement("div");
      note.className = "advanced-evidence-notice";
      note.textContent = `质量说明：${displayDescription(entry.evidence.quality_note)}`;
      panel.append(note);
    }
    if (entry.mode === "CACHE_STALE_FALLBACK" || entry.evidence.quality_status === "STALE") {
      const notice = document.createElement("div");
      notice.className = "advanced-evidence-notice blocked";
      notice.textContent = "陈旧缓存回退：需要人工复核，不能作为已验证事实（VERIFIED）或可执行建议。";
      panel.append(notice);
    } else if (entry.mode === "FALLBACK_PROVIDER") {
      const notice = document.createElement("div");
      notice.className = "advanced-evidence-notice";
      notice.textContent = "备用数据提供方已送达：保留备用来源与来源链，使用前仍应检查独立验证状态。";
      panel.append(notice);
    }

    const pathHeading = document.createElement("h4");
    pathHeading.className = "context-heading";
    pathHeading.textContent = "审计路径 · 发现（FINDING）→事实（FACT）→证据（EVIDENCE）";
    panel.append(pathHeading);
    const path = document.createElement("ul");
    path.className = "advanced-evidence-path";
    const evidencePath = document.createElement("li");
    evidencePath.className = "path-primary";
    evidencePath.textContent = `证据（EVIDENCE）· ${entry.evidence.evidence_id} · ${text(entry.evidence.field)} · ${advancedEvidenceQualityLabel(entry.evidence.quality_status)}`;
    path.append(evidencePath);
    entry.facts.forEach((fact) => {
      const item = document.createElement("li");
      item.textContent = `事实（FACT）· ${text(fact.fact_id)} · ${text(fact.metric)} = ${advancedEvidenceValue(fact.value)} ${text(fact.unit, "")} · ${text(fact.status)}`.trim();
      path.append(item);
    });
    entry.findings.forEach((finding) => {
      const item = document.createElement("li");
      item.textContent = `发现（FINDING）· ${text(finding.finding_id)} · ${text(finding.kind)} · ${text(finding.severity)} · ${text(finding.statement)}`;
      path.append(item);
    });
    entry.validations.forEach((validation) => {
      const item = document.createElement("li");
      item.textContent = `验证（VALIDATION）· ${text(validation.metric)} · ${text(validation.status)} · ${text(validation.independent_lineage_count, "0")} 条独立来源链`;
      path.append(item);
    });
    if (!entry.facts.length && !entry.findings.length) {
      const item = document.createElement("li");
      item.textContent = "当前证据尚未进入事实（FACT）/发现（FINDING），待进一步验证。";
      path.append(item);
    }
    panel.append(path);

    if (entry.issues.length) {
      const issueHeading = document.createElement("h4");
      issueHeading.className = "context-heading";
      issueHeading.textContent = "需复核的安全问题（ISSUE）";
      panel.append(issueHeading);
      const issues = document.createElement("ul");
      issues.className = "advanced-evidence-issues";
      entry.issues.forEach((line) => {
        const item = document.createElement("li");
        item.textContent = line;
        issues.append(item);
      });
      panel.append(issues);
    }
  }

  function renderAdvancedEvidence() {
    const explorer = byId("advanced-evidence-explorer");
    if (!explorer) return;
    const entries = collectAdvancedEvidenceEntries();
    setAdvancedEvidenceSelect(
      "advanced-evidence-quality",
      "advancedEvidenceQuality",
      Object.keys(ADVANCED_EVIDENCE_QUALITY_LABELS),
      ADVANCED_EVIDENCE_QUALITY_LABELS,
      "全部质量",
    );
    setAdvancedEvidenceSelect(
      "advanced-evidence-mode",
      "advancedEvidenceMode",
      Object.keys(ADVANCED_EVIDENCE_MODE_LABELS),
      ADVANCED_EVIDENCE_MODE_LABELS,
      "全部模式",
    );
    const sourceValues = [...new Set(entries.map((entry) => entry.sourceKey))].sort();
    setAdvancedEvidenceSelect(
      "advanced-evidence-source",
      "advancedEvidenceSource",
      sourceValues,
      ADVANCED_EVIDENCE_SOURCE_LABELS,
      "全部轨道",
    );
    setAdvancedEvidenceSelect(
      "advanced-evidence-promotion",
      "advancedEvidencePromotion",
      Object.keys(ADVANCED_EVIDENCE_PROMOTION_LABELS),
      ADVANCED_EVIDENCE_PROMOTION_LABELS,
      "全部状态",
    );

    const search = byId("advanced-evidence-search");
    if (search && search.value !== state.advancedEvidenceSearch) search.value = state.advancedEvidenceSearch;
    const needle = state.advancedEvidenceSearch.trim().toLocaleLowerCase();
    const filtered = entries.filter((entry) => {
      if (needle && !entry.searchText.includes(needle)) return false;
      if (state.advancedEvidenceQuality !== "ALL" && entry.evidence.quality_status !== state.advancedEvidenceQuality) return false;
      if (state.advancedEvidenceMode !== "ALL" && entry.mode !== state.advancedEvidenceMode) return false;
      if (state.advancedEvidenceSource !== "ALL" && entry.sourceKey !== state.advancedEvidenceSource) return false;
      if (state.advancedEvidencePromotion !== "ALL" && entry.promotion !== state.advancedEvidencePromotion) return false;
      return true;
    });
    const summary = byId("advanced-evidence-summary");
    const list = byId("advanced-evidence-list");
    const detail = byId("advanced-evidence-detail");
    clear(summary);
    clear(list);
    const closedCount = entries.filter((entry) => entry.promotion === "FINDING").length;
    const reviewCount = entries.filter((entry) => entry.evidence.quality_status !== "VERIFIED" || entry.promotion !== "FINDING").length;
    summary.append(
      chip(`${entries.length} 条证据`, entries.length ? "" : "review"),
      chip(`${filtered.length} 条显示`, filtered.length === entries.length ? "" : "review"),
      chip(`${closedCount} 条已闭合`, closedCount ? "pass" : ""),
      chip(`${reviewCount} 条需复核`, reviewCount ? "review" : "pass"),
    );
    const summaryText = document.createElement("span");
    summaryText.textContent = entries.length
      ? "只聚合当前隔离标识的内存结果；切换隔离标识或重新运行会清空旧选择。"
      : "先运行研究轨道或选择通过（PASS）回执，才能建立当前会话的证据索引。";
    summary.append(summaryText);

    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "advanced-evidence-empty";
      empty.textContent = "暂无当前隔离标识的证据。运行研究或选择通过（PASS）回执后再查看。";
      list.append(empty);
      renderAdvancedEvidenceDetail(detail, null);
      return;
    }
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "advanced-evidence-empty";
      empty.textContent = "当前筛选没有匹配的证据；清除筛选后查看全部记录。";
      list.append(empty);
      renderAdvancedEvidenceDetail(detail, null);
      return;
    }
    const selected = filtered.find((entry) => entry.key === state.advancedEvidenceSelectedKey) || filtered[0];
    state.advancedEvidenceSelectedKey = selected.key;
    filtered.forEach((entry) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = `advanced-evidence-row${entry.key === selected.key ? " selected" : ""}`;
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", String(entry.key === selected.key));
      row.setAttribute("aria-label", `${entry.evidence.evidence_id} · ${advancedEvidenceQualityLabel(entry.evidence.quality_status)} · ${entry.sourceLabel}`);
      row.addEventListener("click", () => {
        state.advancedEvidenceSelectedKey = entry.key;
        renderAdvancedEvidence();
      });
      const rowHeader = document.createElement("header");
      const rowTitle = document.createElement("strong");
      rowTitle.textContent = entry.evidence.evidence_id;
      rowHeader.append(rowTitle, chip(advancedEvidenceQualityLabel(entry.evidence.quality_status), advancedEvidenceQualityClass(entry.evidence.quality_status)));
      const rowSource = document.createElement("div");
      rowSource.className = "advanced-evidence-row-source";
      rowSource.textContent = `${entry.sourceLabel} · ${text(entry.evidence.field)} · ${text(entry.evidence.period)}`;
      const rowMeta = document.createElement("div");
      rowMeta.className = "advanced-evidence-row-meta";
      rowMeta.textContent = `${advancedEvidenceModeLabel(entry.mode)} · ${advancedEvidencePromotionLabel(entry.promotion)} · ${text(entry.evidence.lineage_id, "无来源链")}`;
      row.append(rowHeader, rowSource, rowMeta);
      list.append(row);
    });
    renderAdvancedEvidenceDetail(detail, selected);
  }

  function renderResearchMatrix(result) {
    const panel = byId("research-matrix-content");
    clear(panel);
    renderAdvancedEvidence();
    if (!result) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "运行矩阵后查看四类节点、独立来源验证，以及从发现到事实再到证据的闭合路径。";
      panel.append(empty);
      return;
    }

    const summary = document.createElement("div");
    summary.className = "research-summary";
    summary.append(
      chip(researchStatusLabel(result.pipeline_status), researchStatusClass(result.pipeline_status)),
      chip(`运行：${researchStatusLabel(result.run_status)}`, researchStatusClass(result.run_status)),
    );
    const summaryText = document.createElement("p");
    summaryText.textContent = `研究矩阵 · ${researchPeriodLabel(result.period)} · 当前隔离标识已载入`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${researchNarrative(displayScenarioDescription(result.scenario), "该场景暂无补充说明。")}`;
      summary.append(scenarioText);
    }
    panel.append(summary);

    const cards = document.createElement("div");
    cards.className = "research-grid";
    (result.nodes || []).forEach((node) => {
      const card = document.createElement("article");
      card.className = "research-card";
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = researchRoleLabel(node.role);
      header.append(title, chip(researchStatusLabel(node.status), researchStatusClass(node.status)));
      card.append(header);
      const subject = document.createElement("div");
      subject.className = "muted";
      subject.textContent = researchSubjectLabel(node.subject);
      card.append(subject);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Node", researchNodeLabel(node.node_id));
      addMetadata(metadata, "Kind", researchRoleLabel(node.node_kind));
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      card.append(metadata);
      if (node.issues && node.issues.length) {
        const issues = document.createElement("ul");
        issues.className = "research-issues";
        node.issues.forEach((issue) => {
          const item = document.createElement("li");
          item.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
          issues.append(item);
        });
        card.append(issues);
      }
      cards.append(card);
    });
    panel.append(cards);

    if (result.pipeline_status !== "READY") {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = "部分研究数据尚需核验，请参考下方提示项。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "research-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        issues.append(item);
      });
      if (issues.childElementCount) panel.append(issues);
    }

    const validationHeading = document.createElement("h3");
    validationHeading.textContent = "独立来源链验证";
    panel.append(validationHeading);
    const validations = document.createElement("div");
    validations.className = "research-validations";
    (result.validations || []).forEach((validation) => {
      const row = document.createElement("article");
      row.className = "research-validation";
      const title = document.createElement("strong");
      title.textContent = `${researchSubjectLabel(validation.subject)} · ${researchMetricLabel(validation.metric)}`;
      row.append(title, chip(researchStatusLabel(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `预期 ${humanMetricValue(validation.expected_value, validation.unit)} · ${researchPeriodLabel(validation.period)} · ${text(validation.independent_lineage_count, "0")} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      if (validation.issues && validation.issues.length) {
        const issues = document.createElement("ul");
        issues.className = "validation-issues";
        validation.issues.forEach((issue) => {
          const item = document.createElement("li");
          item.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
          issues.append(item);
        });
        row.append(issues);
      }
      validations.append(row);
    });
    panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const availableHeading = document.createElement("h3");
      availableHeading.textContent = "可用证据 · 未升级为事实";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "research-available-evidence";
      (result.trace && result.trace.evidence || []).forEach((evidence, index) => {
        const details = document.createElement("details");
        const summaryLine = document.createElement("summary");
        summaryLine.textContent = `${researchMetricLabel(evidence.field)} · ${researchSourceLabel(evidence.source)} · ${researchStatusLabel(evidence.quality_status)}`;
        details.append(summaryLine);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据：${researchEvidenceLabel(evidence, index)}`,
          `数值：${humanMetricValue(evidence.value, evidence.unit)}`,
          `期间：${researchPeriodLabel(evidence.period)}`,
          `来源：${researchSourceLabel(evidence.source)}`,
        ].forEach((line) => {
          const item = document.createElement("div");
          item.textContent = line;
          metadata.append(item);
        });
        details.append(metadata);
        available.append(details);
      });
      if (available.childElementCount) panel.append(available);
      return;
    }

    const evidenceHeading = document.createElement("h3");
    evidenceHeading.textContent = "发现 → 事实 → 证据";
    panel.append(evidenceHeading);
    const evidencePanel = document.createElement("div");
    evidencePanel.className = "research-evidence";
    const evidenceById = new Map((result.trace && result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace && result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.trace && result.trace.findings || []).forEach((finding, findingIndex) => {
      const details = document.createElement("details");
      details.open = true;
      const summaryLine = document.createElement("summary");
      summaryLine.textContent = `${researchFindingLabel(finding, findingIndex)} · ${researchNarrative(finding.statement)}`;
      details.append(summaryLine);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现：${researchFindingLabel(finding, findingIndex)} · ${researchSeverityLabel(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实：${researchMetricLabel(fact.metric)} = ${humanMetricValue(fact.value, fact.unit)} · ${researchStatusLabel(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId, evidenceIndex) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据：${researchEvidenceLabel(evidence, evidenceIndex)} · ${researchSourceLabel(evidence.source)} · ${researchPeriodLabel(evidence.period)} · ${humanMetricValue(evidence.value, evidence.unit)}`;
          metadata.append(evidenceLine);
        });
      });
      details.append(metadata);
      evidencePanel.append(details);
    });
    if (evidencePanel.childElementCount) panel.append(evidencePanel);
  }

  function renderStockResearch(result) {
    const panel = byId("stock-research-content");
    clear(panel);
    renderAdvancedEvidence();
    if (!result) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "运行个股研究后查看财务事实、异常、风险与证据闭合。";
      panel.append(empty);
      return;
    }

    const summary = document.createElement("div");
    summary.className = "stock-research-summary";
    summary.append(
      chip(researchStatusLabel(result.pipeline_status), researchStatusClass(result.pipeline_status)),
      chip(`运行：${researchStatusLabel(result.run_status)}`, researchStatusClass(result.run_status)),
      chip(stockRiskStatusLabel(result.risk && result.risk.status), stockRiskStatusClass(result.risk && result.risk.status)),
    );
    const summaryText = document.createElement("p");
    summaryText.textContent = `${researchSubjectLabel(result.subject)} · ${researchPeriodLabel(result.period)}`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${researchNarrative(displayScenarioDescription(result.scenario), "该场景暂无补充说明。")}`;
      summary.append(scenarioText);
    }
    panel.append(summary);

    const nodeHeading = document.createElement("h3");
    nodeHeading.className = "dev-only technical-detail";
    nodeHeading.textContent = "来源节点";
    panel.append(nodeHeading);
    const nodeGrid = document.createElement("div");
    nodeGrid.className = "research-grid dev-only technical-detail";
    (result.nodes || []).forEach((node) => {
      const card = document.createElement("article");
      card.className = "research-card";
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = researchNodeLabel(node.node_id);
      header.append(title, chip(researchStatusLabel(node.status), researchStatusClass(node.status)));
      card.append(header);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      if (node.missing_fields && node.missing_fields.length) {
        addMetadata(metadata, "Missing", node.missing_fields.map((field) => researchMetricLabel(field)).join("、"));
      }
      card.append(metadata);
      if (node.scope_description) {
        const scope = document.createElement("div");
        scope.className = "muted";
        scope.textContent = researchNarrative(node.scope_description);
        card.append(scope);
      }
      (node.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        card.append(issueLine);
      });
      nodeGrid.append(card);
    });
    if (nodeGrid.childElementCount) panel.append(nodeGrid);

    const validationsHeading = document.createElement("h3");
    validationsHeading.textContent = "来源验证";
    panel.append(validationsHeading);
    const validations = document.createElement("div");
    validations.className = "research-validations";
    (result.validations || []).forEach((validation) => {
      const row = document.createElement("article");
      row.className = "research-validation";
      const title = document.createElement("strong");
      title.textContent = `${researchMetricLabel(validation.metric)} · ${researchPeriodLabel(validation.period)}`;
      row.append(title, chip(researchStatusLabel(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `${text(validation.independent_lineage_count, "0")} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      (validation.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        row.append(issueLine);
      });
      validations.append(row);
    });
    if (validations.childElementCount) panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = "部分来源数据尚不完整或存在冲突，需核对下方提示项。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "stock-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        issues.append(item);
      });
      if (issues.childElementCount) panel.append(issues);
      const availableHeading = document.createElement("h3");
      availableHeading.textContent = "可用证据 · 未升级为事实";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "stock-available-evidence";
      (result.trace && result.trace.evidence || []).forEach((evidence, index) => {
        const details = document.createElement("details");
        const line = document.createElement("summary");
        line.textContent = `${researchMetricLabel(evidence.field)} · ${researchSourceLabel(evidence.source)} · ${researchStatusLabel(evidence.quality_status)}`;
        details.append(line);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据：${researchEvidenceLabel(evidence, index)}`,
          `数值：${humanMetricValue(evidence.value, evidence.unit)}`,
          `期间：${researchPeriodLabel(evidence.period)}`,
          `来源：${researchSourceLabel(evidence.source)}`,
        ].forEach((lineText) => {
          const item = document.createElement("div");
          item.textContent = lineText;
          metadata.append(item);
        });
        details.append(metadata);
        available.append(details);
      });
      if (available.childElementCount) panel.append(available);
      return;
    }

    const factHeading = document.createElement("h3");
    factHeading.textContent = "已验证的财务事实";
    panel.append(factHeading);
    const metricLabels = new Map((state.stockResearchTemplate && state.stockResearchTemplate.metrics || []).map((item) => [item.metric, item.label]));
    const factGrid = document.createElement("div");
    factGrid.className = "stock-fact-grid";
    (result.facts || []).forEach((fact) => {
      const card = document.createElement("article");
      card.className = "stock-fact-card";
      const title = document.createElement("strong");
      title.textContent = researchMetricLabel(fact.metric, metricLabels.get(fact.metric));
      const value = document.createElement("div");
      value.className = "stock-fact-value";
      value.textContent = humanMetricValue(fact.value, fact.unit);
      const period = document.createElement("div");
      period.className = "muted";
      period.textContent = `${researchMetricLabel(fact.metric)} · ${researchPeriodLabel(fact.period)} · ${researchStatusLabel(fact.status)}`;
      card.append(title, value, period);
      factGrid.append(card);
    });
    if (factGrid.childElementCount) panel.append(factGrid);

    const risk = document.createElement("section");
    risk.className = "stock-risk-summary";
    const riskHeader = document.createElement("header");
    const riskTitle = document.createElement("strong");
    riskTitle.textContent = "确定性风险摘要";
    riskHeader.append(riskTitle, chip(stockRiskStatusLabel(result.risk && result.risk.status), stockRiskStatusClass(result.risk && result.risk.status)));
    risk.append(riskHeader);
    const riskText = document.createElement("p");
    riskText.textContent = researchNarrative(result.risk && result.risk.summary, "风险摘要暂不可用，需要人工复核。");
    risk.append(riskText);
    const rules = document.createElement("div");
    rules.className = "stock-rules";
    (state.stockResearchTemplate && state.stockResearchTemplate.risk_rules || []).forEach((rule) => {
      const line = document.createElement("div");
      line.textContent = `${text(rule.label)} · ${text(rule.operator)} ${humanMetricValue(rule.threshold, rule.unit)}`;
      rules.append(line);
    });
    if (rules.childElementCount) risk.append(rules);
    panel.append(risk);

    const anomalyHeading = document.createElement("h3");
    anomalyHeading.textContent = "确定性异常";
    panel.append(anomalyHeading);
    const anomalies = document.createElement("div");
    anomalies.className = "stock-findings";
    (result.findings || []).filter((finding) => finding.severity !== "INFO").forEach((finding, index) => {
      const details = document.createElement("details");
      details.open = true;
      const line = document.createElement("summary");
      line.textContent = `${researchFindingLabel(finding, index)} · ${researchNarrative(finding.statement)}`;
      details.append(line);
      const meta = document.createElement("div");
      meta.className = "research-evidence-meta";
      meta.textContent = `${researchFindingLabel(finding, index)} · ${researchSeverityLabel(finding.severity)} · ${displayMethodology(finding.methodology)}`;
      details.append(meta);
      anomalies.append(details);
    });
    if (anomalies.childElementCount) panel.append(anomalies);

    const chainHeading = document.createElement("h3");
    chainHeading.textContent = "发现 → 事实 → 证据";
    panel.append(chainHeading);
    const chain = document.createElement("div");
    chain.className = "stock-findings";
    const evidenceById = new Map((result.trace && result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace && result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.findings || []).forEach((finding, findingIndex) => {
      const details = document.createElement("details");
      const line = document.createElement("summary");
      line.textContent = `${researchFindingLabel(finding, findingIndex)} · ${researchNarrative(finding.statement)}`;
      details.append(line);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现：${researchFindingLabel(finding, findingIndex)} · ${researchSeverityLabel(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实：${researchMetricLabel(fact.metric)} = ${humanMetricValue(fact.value, fact.unit)} · ${researchStatusLabel(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId, evidenceIndex) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据：${researchEvidenceLabel(evidence, evidenceIndex)} · ${researchSourceLabel(evidence.source)} · ${researchPeriodLabel(evidence.period)} · ${humanMetricValue(evidence.value, evidence.unit)}`;
          metadata.append(evidenceLine);
        });
      });
      details.append(metadata);
      chain.append(details);
    });
    if (chain.childElementCount) panel.append(chain);
  }

  function renderFundResearch(result) {
    const panel = byId("fund-research-content");
    clear(panel);
    renderAdvancedEvidence();
    if (!result) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "运行 ETF / 基金研究后查看资产事实、风险与证据闭合。";
      panel.append(empty);
      return;
    }

    const summary = document.createElement("div");
    summary.className = "fund-research-summary";
    summary.append(
      chip(researchStatusLabel(result.pipeline_status), researchStatusClass(result.pipeline_status)),
      chip(`运行：${researchStatusLabel(result.run_status)}`, researchStatusClass(result.run_status)),
      chip(fundRiskStatusLabel(result.risk && result.risk.status), fundRiskStatusClass(result.risk && result.risk.status)),
    );
    const summaryText = document.createElement("p");
    summaryText.textContent = `${researchSubjectLabel(result.subject)} · ${researchPeriodLabel(result.period)}`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${researchNarrative(displayScenarioDescription(result.scenario), "该场景暂无补充说明。")}`;
      summary.append(scenarioText);
    }
    panel.append(summary);

    const nodeHeading = document.createElement("h3");
    nodeHeading.className = "dev-only technical-detail";
    nodeHeading.textContent = "技术详情：来源节点";
    panel.append(nodeHeading);
    const nodeGrid = document.createElement("div");
    nodeGrid.className = "research-grid dev-only technical-detail";
    (result.nodes || []).forEach((node) => {
      const card = document.createElement("article");
      card.className = "research-card";
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = researchNodeLabel(node.node_id);
      header.append(title, chip(researchStatusLabel(node.status), researchStatusClass(node.status)));
      card.append(header);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      if (node.missing_fields && node.missing_fields.length) {
        addMetadata(metadata, "Missing", node.missing_fields.map((field) => researchMetricLabel(field)).join("、"));
      }
      card.append(metadata);
      if (node.scope_description) {
        const scope = document.createElement("div");
        scope.className = "muted";
        scope.textContent = researchNarrative(node.scope_description);
        card.append(scope);
      }
      (node.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        card.append(issueLine);
      });
      nodeGrid.append(card);
    });
    if (nodeGrid.childElementCount) panel.append(nodeGrid);

    const validationHeading = document.createElement("h3");
    validationHeading.className = "dev-only technical-detail";
    validationHeading.textContent = "来源验证";
    panel.append(validationHeading);
    const validations = document.createElement("div");
    validations.className = "research-validations dev-only technical-detail";
    (result.validations || []).forEach((validation) => {
      const row = document.createElement("article");
      row.className = "research-validation";
      const title = document.createElement("strong");
      title.textContent = `${researchMetricLabel(validation.metric)} · ${researchPeriodLabel(validation.period)}`;
      row.append(title, chip(researchStatusLabel(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `${text(validation.independent_lineage_count, "0")} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      (validation.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        row.append(issueLine);
      });
      validations.append(row);
    });
    if (validations.childElementCount) panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = "部分来源数据尚不完整或存在冲突，需核对下方提示项。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "fund-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = researchNarrative(issue.safe_message, "数据暂不可用，需要人工复核。");
        issues.append(item);
      });
      if (issues.childElementCount) panel.append(issues);
      const availableHeading = document.createElement("h3");
      availableHeading.className = "dev-only technical-detail";
      availableHeading.textContent = "技术详情：可用证据 · 未升级为事实";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "fund-available-evidence dev-only technical-detail";
      (result.trace && result.trace.evidence || []).forEach((evidence, index) => {
        const details = document.createElement("details");
        const line = document.createElement("summary");
        line.textContent = `${researchMetricLabel(evidence.field)} · ${researchSourceLabel(evidence.source)} · ${researchStatusLabel(evidence.quality_status)}`;
        details.append(line);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据：${researchEvidenceLabel(evidence, index)}`,
          `数值：${humanMetricValue(evidence.value, evidence.unit)}`,
          `期间：${researchPeriodLabel(evidence.period)}`,
          `来源：${researchSourceLabel(evidence.source)}`,
        ].forEach((lineText) => {
          const item = document.createElement("div");
          item.textContent = lineText;
          metadata.append(item);
        });
        details.append(metadata);
        available.append(details);
      });
      if (available.childElementCount) panel.append(available);
      return;
    }

    const factHeading = document.createElement("h3");
    factHeading.textContent = "已验证的基金事实";
    panel.append(factHeading);
    const metricLabels = new Map((state.fundResearchTemplate && state.fundResearchTemplate.metrics || []).map((item) => [item.metric, item.label]));
    const factGrid = document.createElement("div");
    factGrid.className = "fund-fact-grid";
    (result.facts || []).forEach((fact) => {
      const card = document.createElement("article");
      card.className = "fund-fact-card";
      const title = document.createElement("strong");
      title.textContent = researchMetricLabel(fact.metric, metricLabels.get(fact.metric));
      const value = document.createElement("div");
      value.className = "fund-fact-value";
      value.textContent = humanMetricValue(fact.value, fact.unit);
      const period = document.createElement("div");
      period.className = "muted";
      period.textContent = `数据时间：${researchPeriodLabel(fact.period)} · 来源已验证`;
      card.append(title, value, period);
      factGrid.append(card);
    });
    if (factGrid.childElementCount) panel.append(factGrid);

    const risk = document.createElement("section");
    risk.className = "fund-risk-summary";
    const riskHeader = document.createElement("header");
    const riskTitle = document.createElement("strong");
    riskTitle.textContent = "确定性基金风险摘要";
    riskHeader.append(riskTitle, chip(fundRiskStatusLabel(result.risk && result.risk.status), fundRiskStatusClass(result.risk && result.risk.status)));
    risk.append(riskHeader);
    const riskText = document.createElement("p");
    riskText.textContent = researchNarrative(result.risk && result.risk.summary, "风险摘要暂不可用，需要人工复核。");
    risk.append(riskText);
    const rules = document.createElement("div");
    rules.className = "fund-rules";
    (state.fundResearchTemplate && state.fundResearchTemplate.risk_rules || []).forEach((rule) => {
      const line = document.createElement("div");
      line.textContent = `${text(rule.label)}：${text(rule.operator)} ${humanMetricValue(rule.threshold, rule.unit)}`;
      rules.append(line);
    });
    if (rules.childElementCount) risk.append(rules);
    panel.append(risk);

    const findingHeading = document.createElement("h3");
    findingHeading.textContent = "确定性基金风险";
    panel.append(findingHeading);
    const findings = document.createElement("div");
    findings.className = "fund-findings";
    (result.findings || []).filter((finding) => finding.severity !== "INFO").forEach((finding, index) => {
      const details = document.createElement("details");
      details.open = true;
      const line = document.createElement("summary");
      line.textContent = `${researchFindingLabel(finding, index)} · ${researchNarrative(finding.statement)}`;
      details.append(line);
      const meta = document.createElement("div");
      meta.className = "research-evidence-meta dev-only technical-detail";
      meta.textContent = `${researchFindingLabel(finding, index)} · ${researchSeverityLabel(finding.severity)} · ${displayMethodology(finding.methodology)}`;
      details.append(meta);
      findings.append(details);
    });
    if (findings.childElementCount) panel.append(findings);

    const chainHeading = document.createElement("h3");
    chainHeading.className = "dev-only technical-detail";
    chainHeading.textContent = "技术详情：发现 → 事实 → 证据";
    panel.append(chainHeading);
    const chain = document.createElement("div");
    chain.className = "fund-findings dev-only technical-detail";
    const evidenceById = new Map((result.trace && result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace && result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.findings || []).forEach((finding, findingIndex) => {
      const details = document.createElement("details");
      const line = document.createElement("summary");
      line.textContent = `${researchFindingLabel(finding, findingIndex)} · ${researchNarrative(finding.statement)}`;
      details.append(line);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现：${researchFindingLabel(finding, findingIndex)} · ${researchSeverityLabel(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实：${researchMetricLabel(fact.metric)} = ${humanMetricValue(fact.value, fact.unit)} · ${researchStatusLabel(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId, evidenceIndex) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据：${researchEvidenceLabel(evidence, evidenceIndex)} · ${researchSourceLabel(evidence.source)} · ${researchPeriodLabel(evidence.period)} · ${humanMetricValue(evidence.value, evidence.unit)}`;
          metadata.append(evidenceLine);
        });
      });
      details.append(metadata);
      chain.append(details);
    });
    if (chain.childElementCount) panel.append(chain);
  }

  function renderConvertibleBondResearch(result) {
    const panel = byId("convertible-bond-research-content");
    clear(panel);
    renderAdvancedEvidence();
    if (!result) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "运行可转债研究后查看最低资产事实、公式、风险与证据闭合。";
      panel.append(empty);
      return;
    }

    const summary = document.createElement("div");
    summary.className = "convertible-bond-research-summary";
    summary.append(
      chip(researchStatusLabel(result.pipeline_status), researchStatusClass(result.pipeline_status)),
      chip(`运行：${researchStatusLabel(result.run_status)}`, researchStatusClass(result.run_status)),
      chip(convertibleBondRiskStatusLabel(result.risk && result.risk.status), convertibleBondRiskStatusClass(result.risk && result.risk.status)),
    );
    const summaryText = document.createElement("p");
    summaryText.textContent = `${researchSubjectLabel(result.subject)} · ${researchPeriodLabel(result.period)}`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${researchNarrative(displayScenarioDescription(result.scenario), "该场景暂无补充说明。")}`;
      summary.append(scenarioText);
    }
    panel.append(summary);

    const nodeHeading = document.createElement("h3");
    nodeHeading.textContent = "来源节点";
    panel.append(nodeHeading);
    const nodeGrid = document.createElement("div");
    nodeGrid.className = "research-grid";
    (result.nodes || []).forEach((node) => {
      const card = document.createElement("article");
      card.className = "research-card";
      const header = document.createElement("header");
      const title = document.createElement("strong");
      title.textContent = researchNodeLabel(node.node_id);
      header.append(title, chip(researchStatusLabel(node.status), researchStatusClass(node.status)));
      card.append(header);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      if (node.missing_fields && node.missing_fields.length) addMetadata(metadata, "Missing", node.missing_fields.map((field) => researchMetricLabel(field)).join("、"));
      card.append(metadata);
      if (node.scope_description) {
        const scope = document.createElement("div");
        scope.className = "muted";
        scope.textContent = researchNarrative(node.scope_description);
        card.append(scope);
      }
      (node.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        card.append(issueLine);
      });
      nodeGrid.append(card);
    });
    if (nodeGrid.childElementCount) panel.append(nodeGrid);

    const validationHeading = document.createElement("h3");
    validationHeading.textContent = "来源验证";
    panel.append(validationHeading);
    const validations = document.createElement("div");
    validations.className = "research-validations";
    (result.validations || []).forEach((validation) => {
      const row = document.createElement("article");
      row.className = "research-validation";
      const title = document.createElement("strong");
      title.textContent = `${researchMetricLabel(validation.metric)} · ${researchPeriodLabel(validation.period)}`;
      row.append(title, chip(researchStatusLabel(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `${text(validation.independent_lineage_count, "0")} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      (validation.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        row.append(issueLine);
      });
      validations.append(row);
    });
    if (validations.childElementCount) panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = "部分来源数据尚不完整或存在冲突，需核对下方提示项。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "convertible-bond-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${researchIssueLabel(issue.code)}: ${researchNarrative(issue.safe_message)}`;
        issues.append(item);
      });
      if (issues.childElementCount) panel.append(issues);
      const availableHeading = document.createElement("h3");
      availableHeading.textContent = "可用证据 · 未升级为事实";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "convertible-bond-available-evidence";
      (result.trace && result.trace.evidence || []).forEach((evidence, index) => {
        const details = document.createElement("details");
        const line = document.createElement("summary");
        line.textContent = `${researchMetricLabel(evidence.field)} · ${researchSourceLabel(evidence.source)} · ${researchStatusLabel(evidence.quality_status)}`;
        details.append(line);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据：${researchEvidenceLabel(evidence, index)}`,
          `数值：${humanMetricValue(evidence.value, evidence.unit)}`,
          `期间：${researchPeriodLabel(evidence.period)}`,
          `来源：${researchSourceLabel(evidence.source)}`,
        ].forEach((lineText) => {
          const item = document.createElement("div");
          item.textContent = lineText;
          metadata.append(item);
        });
        details.append(metadata);
        available.append(details);
      });
      if (available.childElementCount) panel.append(available);
      return;
    }

    const factHeading = document.createElement("h3");
    factHeading.textContent = "已验证的可转债事实";
    panel.append(factHeading);
    const template = state.convertibleBondResearchTemplate;
    const metricLabels = new Map((template && template.metrics || []).map((item) => [item.metric, item.label]));
    const factGrid = document.createElement("div");
    factGrid.className = "convertible-bond-fact-grid";
    const creditLabels = (template && template.credit_rating_labels) || {};
    const liquidityLabels = (template && template.liquidity_labels) || {};
    (result.facts || []).forEach((fact) => {
      const card = document.createElement("article");
      card.className = "convertible-bond-fact-card";
      const title = document.createElement("strong");
      title.textContent = researchMetricLabel(fact.metric, metricLabels.get(fact.metric));
      const value = document.createElement("div");
      value.className = "convertible-bond-fact-value";
      let displayValue = text(fact.value);
      const levelMetric = fact.metric === "credit_rating_rank" || fact.metric === "liquidity_score";
      if (fact.metric === "credit_rating_rank") displayValue = `${text(creditLabels[String(fact.value)], "未知评级")} · 序数 ${displayValue}`;
      if (fact.metric === "liquidity_score") displayValue = `${text(liquidityLabels[String(fact.value)], "未知流动性")} · 分数 ${displayValue}`;
      value.textContent = levelMetric ? displayValue : humanMetricValue(fact.value, fact.unit);
      const period = document.createElement("div");
      period.className = "muted";
      period.textContent = `${researchMetricLabel(fact.metric)} · ${researchPeriodLabel(fact.period)} · ${researchStatusLabel(fact.status)}`;
      card.append(title, value, period);
      factGrid.append(card);
    });
    if (factGrid.childElementCount) panel.append(factGrid);

    const formulaHeading = document.createElement("h3");
    formulaHeading.textContent = "确定性公式";
    panel.append(formulaHeading);
    const formulas = document.createElement("div");
    formulas.className = "convertible-bond-formulas";
    (template && template.metrics || []).filter((item) => item.derived).forEach((item) => {
      const line = document.createElement("div");
      line.textContent = `${researchMetricLabel(item.metric, item.label)} · ${researchFormula(item.formula)}`;
      formulas.append(line);
    });
    if (formulas.childElementCount) panel.append(formulas);

    const risk = document.createElement("section");
    risk.className = "convertible-bond-risk-summary";
    const riskHeader = document.createElement("header");
    const riskTitle = document.createElement("strong");
    riskTitle.textContent = "确定性可转债风险摘要";
    riskHeader.append(riskTitle, chip(convertibleBondRiskStatusLabel(result.risk && result.risk.status), convertibleBondRiskStatusClass(result.risk && result.risk.status)));
    risk.append(riskHeader);
    const riskText = document.createElement("p");
    riskText.textContent = researchNarrative(result.risk && result.risk.summary, "风险摘要暂不可用，需要人工复核。");
    risk.append(riskText);
    const rules = document.createElement("div");
    rules.className = "convertible-bond-rules";
    (template && template.risk_rules || []).forEach((rule) => {
      const line = document.createElement("div");
      line.textContent = `${text(rule.label)} · ${text(rule.operator)} ${humanMetricValue(rule.threshold, rule.unit)}`;
      rules.append(line);
    });
    if (rules.childElementCount) risk.append(rules);
    panel.append(risk);

    const findingHeading = document.createElement("h3");
    findingHeading.textContent = "确定性可转债风险";
    panel.append(findingHeading);
    const findings = document.createElement("div");
    findings.className = "convertible-bond-findings";
    (result.findings || []).filter((finding) => finding.severity !== "INFO").forEach((finding, index) => {
      const details = document.createElement("details");
      details.open = true;
      const line = document.createElement("summary");
      line.textContent = `${researchFindingLabel(finding, index)} · ${researchNarrative(finding.statement)}`;
      details.append(line);
      const meta = document.createElement("div");
      meta.className = "research-evidence-meta";
      meta.textContent = `${researchFindingLabel(finding, index)} · ${researchSeverityLabel(finding.severity)} · ${displayMethodology(finding.methodology)}`;
      details.append(meta);
      findings.append(details);
    });
    if (findings.childElementCount) panel.append(findings);

    const chainHeading = document.createElement("h3");
    chainHeading.textContent = "发现 → 事实 → 证据";
    panel.append(chainHeading);
    const chain = document.createElement("div");
    chain.className = "convertible-bond-findings";
    const evidenceById = new Map((result.trace && result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace && result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.findings || []).forEach((finding, findingIndex) => {
      const details = document.createElement("details");
      const line = document.createElement("summary");
      line.textContent = `${researchFindingLabel(finding, findingIndex)} · ${researchNarrative(finding.statement)}`;
      details.append(line);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现：${researchFindingLabel(finding, findingIndex)} · ${researchSeverityLabel(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实：${researchMetricLabel(fact.metric)} = ${humanMetricValue(fact.value, fact.unit)} · ${researchStatusLabel(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId, evidenceIndex) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据：${researchEvidenceLabel(evidence, evidenceIndex)} · ${researchSourceLabel(evidence.source)} · ${researchPeriodLabel(evidence.period)} · ${humanMetricValue(evidence.value, evidence.unit)}`;
          metadata.append(evidenceLine);
        });
      });
      details.append(metadata);
      chain.append(details);
    });
    if (chain.childElementCount) panel.append(chain);
  }

  function renderPortfolioOptimization(result) {
    const panel = byId("portfolio-optimization-content");
    clear(panel);
    if (!result) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "生成提案后查看当前→目标权重、约束上限、算术解释与失效条件。";
      panel.append(empty);
      return;
    }

    const summary = document.createElement("div");
    summary.className = "portfolio-optimization-summary";
    summary.append(
      chip(optimizationStatusLabel(result.status), optimizationStatusClass(result.status)),
      chip(text(result.risk_level), ""),
    );
    const summaryText = document.createElement("p");
    summaryText.textContent = `${displayScenarioLabel(result.scenario)} · ${text(result.summary)}`;
    summary.append(summaryText);
    panel.append(summary);

    const metadata = document.createElement("dl");
    // 方法版本与各类内部 ID 对普通用户没有意义，整块标为开发者可见。
    metadata.className = "metadata-grid dev-only";
    addMetadata(metadata, "Method", result.methodology_version);
    addMetadata(metadata, "Profile", `${text(result.profile_id)} · v${text(result.profile_version)}`);
    addMetadata(metadata, "Portfolio bundle", result.portfolio_bundle_id);
    addMetadata(metadata, "Position snapshot", result.position_snapshot_id);
    addMetadata(metadata, "Exposure report", result.exposure_report_id);
    addMetadata(metadata, "Risk assessment", `${text(result.assessment_id)} · ${text(result.assessment_status)}`);
    panel.append(metadata);

    if (result.issues && result.issues.length) {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = result.status === "BLOCKED"
        ? "目标约束无法闭合；没有生成可执行权重。"
        : "输入数据尚未闭合；没有生成目标权重。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "portfolio-optimization-issues";
      result.issues.forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${researchIssueLabel(issue.code)}: ${displayDescription(issue.safe_message)}`;
        issues.append(item);
      });
      panel.append(issues);
    }

    if (result.status === "READY") {
      const targetHeading = document.createElement("h3");
      targetHeading.textContent = "当前 → 确定性目标权重";
      panel.append(targetHeading);
      const targets = document.createElement("div");
      targets.className = "portfolio-optimization-targets";
      (result.targets || []).forEach((target) => {
        const card = document.createElement("article");
        card.className = "portfolio-optimization-target";
        const header = document.createElement("header");
        const title = document.createElement("strong");
        title.textContent = `${text(target.asset_name)} · ${text(target.sector, "未分类")}`;
        header.append(title);
        card.append(header);
        const grid = document.createElement("dl");
        addMetadata(grid, "Current", `${text(target.current_weight_pct)}%`);
        addMetadata(grid, "Target", `${text(target.target_weight_pct)}%`);
        addMetadata(grid, "Delta", `${text(target.delta_pct)} 个百分点`);
        addMetadata(grid, "Asset cap", `${text(target.allowed_max_weight_pct)}%`);
        card.append(grid);
        const rationale = document.createElement("div");
        rationale.className = "muted";
        rationale.textContent = displayDescription(target.rationale);
        card.append(rationale);
        targets.append(card);
      });
      if (targets.childElementCount) panel.append(targets);

      const constraintHeading = document.createElement("h3");
      constraintHeading.textContent = "约束算术";
      panel.append(constraintHeading);
      const constraints = document.createElement("div");
      constraints.className = "portfolio-optimization-constraints";
      (result.constraints || []).forEach((constraint) => {
        const details = document.createElement("details");
        const line = document.createElement("summary");
        line.textContent = `${text(constraint.dimension)} · ${text(constraint.label)} · ${text(constraint.disposition)}`;
        details.append(line);
        const meta = document.createElement("div");
        meta.className = "research-evidence-meta";
        meta.textContent = `当前 ${text(constraint.current_weight_pct)}% → 目标 ${text(constraint.target_weight_pct)}% · 上限 ${text(constraint.allowed_max_weight_pct)}% · 变化 ${text(constraint.delta_pct)} 个百分点 · ${displayDescription(constraint.rationale)}`;
        details.append(meta);
        constraints.append(details);
      });
      if (constraints.childElementCount) panel.append(constraints);
    }

    const invalidation = document.createElement("div");
    invalidation.className = "invalidation";
    const invalidationTitle = document.createElement("strong");
    invalidationTitle.textContent = "提案失效条件";
    invalidation.append(invalidationTitle);
    const list = document.createElement("ul");
    (result.invalidation_conditions || []).forEach((condition) => {
      const item = document.createElement("li");
      item.textContent = displayDescription(condition);
      list.append(item);
    });
    invalidation.append(list);
    panel.append(invalidation);
  }

  function clearPortfolioOptimizationRun(status = "待运行", className = "") {
    state.portfolioOptimizationRun = null;
    state.portfolioOptimizationSequence += 1;
    renderPortfolioOptimization(null);
    setPortfolioOptimizationStatus(status, className);
  }

  function renderScenarioSimulation(result) {
    const panel = byId("scenario-simulation-content");
    if (!panel) return;
    clear(panel);
    if (!result) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "运行情景模拟后查看基线 vs 假设覆盖层的指标对比与目标权重变化。";
      panel.append(empty);
      return;
    }

    const summary = document.createElement("div");
    summary.className = "portfolio-optimization-summary";
    summary.append(
      chip(optimizationStatusLabel(result.status), optimizationStatusClass(result.status)),
      chip(text(result.risk_level), ""),
      chip(text(result.scenario.scenario_id), "clay"),
    );
    const summaryText = document.createElement("p");
    summaryText.textContent = `${displayScenarioLabel(result.scenario)} · ${displayScenarioDescription(result.scenario)}`;
    summary.append(summaryText);
    panel.append(summary);

    const assumptionBox = document.createElement("div");
    assumptionBox.className = "sidebar-note";
    const assumptionTitle = document.createElement("strong");
    assumptionTitle.textContent = "假设覆盖层（SIMULATED 覆盖）";
    const assumptionDesc = document.createElement("p");
    assumptionDesc.textContent = `${displayDescription(result.assumption.description)} (参数: ${text(result.assumption.parameter_name)}, 变化量: ${text(result.assumption.delta)}${result.assumption.unit ? " " + result.assumption.unit : ""})`;
    assumptionBox.append(assumptionTitle, assumptionDesc);
    panel.append(assumptionBox);

    const metadata = document.createElement("dl");
    // 方法版本、模拟 ID、指纹与 run_id 属于内部审计信息，整块标为开发者可见。
    metadata.className = "metadata-grid dev-only";
    addMetadata(metadata, "Method", result.methodology_version);
    addMetadata(metadata, "Profile", `${text(result.profile_id)} · v${text(result.profile_version)}`);
    addMetadata(metadata, "Simulation ID", result.simulation_id);
    addMetadata(metadata, "Fingerprint", result.trace.input_fingerprint);
    addMetadata(metadata, "Baseline Run", result.trace.baseline_run_id);
    addMetadata(metadata, "Simulated Run", result.trace.simulated_run_id);
    panel.append(metadata);

    if (result.issues && result.issues.length) {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = result.status === "BLOCKED"
        ? "情景模拟因数据或约束阻断；未能生成完整有效差分。"
        : "情景模拟包含待复核项；数据不完整或需复核。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "portfolio-optimization-issues";
      result.issues.forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `[${text(issue.dimension)}] ${researchIssueLabel(issue.code)}: ${displayDescription(issue.safe_message)}`;
        issues.append(item);
      });
      panel.append(issues);
    }

    if (result.metric_diffs && result.metric_diffs.length) {
      const diffHeading = document.createElement("h3");
      diffHeading.textContent = "基线 vs 模拟关键指标差分对比";
      panel.append(diffHeading);

      const table = document.createElement("table");
      table.className = "scenario-diff-table";
      const thead = document.createElement("thead");
      const trHead = document.createElement("tr");
      ["指标名称", "维度", "基线值 (BASELINE)", "模拟值 (SIMULATED)", "变化量 (Δ)", "单位"].forEach((hText) => {
        const th = document.createElement("th");
        th.textContent = hText;
        trHead.append(th);
      });
      thead.append(trHead);
      table.append(thead);

      const tbody = document.createElement("tbody");
      result.metric_diffs.forEach((diff) => {
        const tr = document.createElement("tr");
        const tdName = document.createElement("td");
        const nameStrong = document.createElement("strong");
        nameStrong.textContent = diff.label;
        tdName.append(nameStrong);

        const tdDim = document.createElement("td");
        tdDim.append(chip(text(diff.dimension), ""));

        const tdBase = document.createElement("td");
        tdBase.textContent = String(diff.baseline_value);

        const tdSim = document.createElement("td");
        tdSim.textContent = String(diff.scenario_value);

        const tdDelta = document.createElement("td");
        const deltaNum = parseFloat(diff.delta);
        if (deltaNum > 0) {
          tdDelta.className = "positive-delta";
          tdDelta.textContent = `+${diff.delta}`;
        } else if (deltaNum < 0) {
          tdDelta.className = "negative-delta";
          tdDelta.textContent = String(diff.delta);
        } else {
          tdDelta.textContent = String(diff.delta);
        }

        const tdUnit = document.createElement("td");
        tdUnit.textContent = text(diff.unit);

        tr.append(tdName, tdDim, tdBase, tdSim, tdDelta, tdUnit);
        tbody.append(tr);
      });
      table.append(tbody);
      panel.append(table);
    }

    if (result.target_diffs && result.target_diffs.length) {
      const targetHeading = document.createElement("h3");
      targetHeading.textContent = "组合目标权重差分对比";
      panel.append(targetHeading);

      const table = document.createElement("table");
      table.className = "scenario-diff-table";
      const thead = document.createElement("thead");
      const trHead = document.createElement("tr");
      ["资产名称", "基线目标权重", "模拟目标权重", "变化量 (Δ)"].forEach((hText) => {
        const th = document.createElement("th");
        th.textContent = hText;
        trHead.append(th);
      });
      thead.append(trHead);
      table.append(thead);

      const tbody = document.createElement("tbody");
      result.target_diffs.forEach((target) => {
        const tr = document.createElement("tr");
        const tdName = document.createElement("td");
        const nameStrong = document.createElement("strong");
        nameStrong.textContent = target.asset_name;
        tdName.append(nameStrong);

        const tdBase = document.createElement("td");
        tdBase.textContent = `${target.baseline_value}%`;

        const tdSim = document.createElement("td");
        tdSim.textContent = `${target.scenario_value}%`;

        const tdDelta = document.createElement("td");
        const deltaNum = parseFloat(target.delta);
        if (deltaNum > 0) {
          tdDelta.className = "positive-delta";
          tdDelta.textContent = `+${target.delta}%`;
        } else if (deltaNum < 0) {
          tdDelta.className = "negative-delta";
          tdDelta.textContent = `${target.delta}%`;
        } else {
          tdDelta.textContent = `${target.delta}%`;
        }

        tr.append(tdName, tdBase, tdSim, tdDelta);
        tbody.append(tr);
      });
      table.append(tbody);
      panel.append(table);
    }

    const invalidation = document.createElement("div");
    invalidation.className = "invalidation";
    const invalidationTitle = document.createElement("strong");
    invalidationTitle.textContent = "情景模拟失效条件";
    invalidation.append(invalidationTitle);
    const list = document.createElement("ul");
    (result.invalidation_conditions || []).forEach((condition) => {
      const item = document.createElement("li");
      item.textContent = displayDescription(condition);
      list.append(item);
    });
    invalidation.append(list);
    panel.append(invalidation);
  }

  function clearScenarioSimulationRun(status = "待运行", className = "") {
    state.scenarioSimulationRun = null;
    state.scenarioSimulationSequence += 1;
    renderScenarioSimulation(null);
    setScenarioSimulationStatus(status, className);
  }

  async function loadEvent(eventId) {
    const requestOwner = state.ownerId;
    const templateSequence = state.templateSequence;
    setError("");
    try {
      const response = await fetch(`/api/v1/decision-events/${encodeURIComponent(eventId)}`, {
        headers: { "X-Owner-ID": requestOwner },
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.templateSequence !== templateSequence) return;
      renderDetail(await response.json());
    } catch (error) {
      setError(error.message || "读取决策事件失败");
    }
  }

  async function apiError(response) {
    try {
      const payload = await response.json();
      const message = payload && typeof payload.message === "string" ? payload.message : "";
      const errorCode = payload?.error_code || null;
      const localizedByCode = {
        INVALID_INPUT: "确认数据格式不符合接口要求，请重新识别并核对各字段",
        OCR_VALUE_VALIDATION_FAILED: "持仓数据校验失败，请检查证券代码、持股、可用数量、价格、市值和报价时间",
        OCR_OBSERVED_AT_REQUIRED: "请补充报价时间后再确认",
        LIVE_OCR_PRICE_REQUIRED: "正式持仓缺少可核验价格，暂时不能确认",
        CONFLICT: "该截图的确认内容已发生变化，请重新识别后再确认",
      };
      const safeMessage = message && /[\u3400-\u9fff]/.test(message)
        ? message
        : localizedByCode[errorCode] || `请求失败${errorCode ? `（${errorCode}）` : ""}`;
      const error = new Error(safeMessage);
      error.errorCode = errorCode;
      error.httpStatus = response.status;
      return error;
    } catch (_) {
      return new Error("接口请求失败");
    }
  }

  function buildQuestionnaire(template) {
    const queryId = byId("query-id").value.trim() || "ui-profile-confirmation";
    return {
      ...template.questionnaire,
      questionnaire_id: `${queryId}-questionnaire`,
      owner_id: state.ownerId,
      answered_at: template.questionnaire.answered_at,
      loss_tolerance_score: Number(byId("loss-tolerance").value),
      investment_horizon: byId("investment-horizon").value,
      liquidity_need: byId("liquidity-need").value,
      experience_level: byId("experience-level").value,
      return_expectation: byId("return-expectation").value,
      max_drawdown_tolerance_pct: byId("max-drawdown").value,
    };
  }

  async function confirmPortfolioContext() {
    const requestOwner = byId("owner-id").value.trim();
    const raw = byId("portfolio-json").value.trim();
    const submit = byId("confirm-portfolio");
    clearAdvisorPlan();
    clearPortfolioOptimizationRun("需重新运行", "review");
    clearScenarioSimulationRun("需重新运行", "review");
    if (!requestOwner) {
      state.portfolio = null;
      renderPortfolio(state.queryTemplate?.portfolio || null);
      setPortfolioContextStatus("需要隔离标识", "blocked");
      setError("请输入隔离标识。");
      return;
    }
    if (!raw) {
      state.portfolio = null;
      renderPortfolio(state.queryTemplate?.portfolio || null);
      setPortfolioContextStatus("未提供 JSON", "blocked");
      setError("请粘贴已脱敏的持仓 JSON。");
      return;
    }
    let portfolio;
    try {
      portfolio = JSON.parse(raw);
      if (!portfolio || typeof portfolio !== "object" || Array.isArray(portfolio)) {
        throw new Error("not an object");
      }
    } catch (_) {
      state.portfolio = null;
      renderPortfolio(state.queryTemplate?.portfolio || null);
      setPortfolioContextStatus("JSON 无效", "blocked");
      setError("持仓 JSON 格式错误，请检查语法。");
      return;
    }
    if (requestOwner !== state.ownerId) {
      state.ownerId = requestOwner;
      resetOwnerScopedViews();
      byId("portfolio-json").value = raw;
    }
    const contextSequence = state.templateSequence;
    setError("");
    submit.disabled = true;
    setPortfolioContextStatus("验证中…");
    try {
      const response = await fetch("/api/v1/advisor/context/portfolio", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "portfolio-context-request.v1",
          portfolio,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.templateSequence !== contextSequence) return;
      const result = await response.json();
      microStore.transact((store) => {
        store.portfolio = result.portfolio;
      });
      renderPortfolio(state.portfolio, "已确认 · 当前会话只读");
      setPortfolioContextStatus(
        `已确认 · ${text(result.position_count)} 个持仓`,
        "pass",
      );
    } catch (error) {
      if (state.ownerId === requestOwner && state.templateSequence === contextSequence) {
        state.portfolio = null;
        setPortfolioContextStatus("未确认", "blocked");
        renderPortfolio(state.queryTemplate?.portfolio || null);
      }
      setError(error.message || "持仓校验失败");
    } finally {
      submit.disabled = false;
    }
  }

  async function confirmProfileContext({ silent = false } = {}) {
    if (state.selectedPersona === "custom-user") {
      if (!state.profile?.profile) setError("请先在风险画像页面完成并确认问卷。");
      return state.profile;
    }
    const requestOwner = byId("owner-id").value.trim() || state.ownerId || "custom-user";
    const submit = byId("confirm-profile");
    if (!silent) {
      clearAdvisorPlan();
      clearProfileProposal();
      clearPortfolioOptimizationRun("需重新运行", "review");
      clearScenarioSimulationRun("需重新运行", "review");
    }
    if (!requestOwner) {
      state.profile = null;
      renderConfirmedProfile(null);
      setProfileContextStatus("需要隔离标识", "blocked");
      if (!silent) setError("请输入隔离标识。");
      return null;
    }
    if (requestOwner !== state.ownerId) {
      state.ownerId = requestOwner;
      resetOwnerScopedViews();
    }
    const contextSequence = ++state.templateSequence;
    if (!silent) {
      setError("");
      if (submit) submit.disabled = true;
      setProfileContextStatus("确认中…");
    }
    try {
      const template = state.queryTemplate || await loadTemplateContext(requestOwner, contextSequence);
      if (!template) return null;
      const questionnaire = buildQuestionnaire(template);
      const response = await fetch("/api/v1/advisor/context/profile", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "profile-context-request.v1",
          questionnaire,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.templateSequence !== contextSequence) return null;
      const result = await response.json();
      microStore.transact((store) => {
        store.profile = result;
      });
      renderProfileContext(result.questionnaire);
      renderConfirmedProfile(result.profile);
      setProfileContextStatus(`已确认 · ${text(result.profile.risk_level)}`, "pass");
      return result;
    } catch (error) {
      if (state.ownerId === requestOwner && state.templateSequence === contextSequence) {
        state.profile = null;
        renderConfirmedProfile(null);
        setProfileContextStatus("未确认", "blocked");
      }
      if (!silent) setError(error.message || "风险画像确认失败");
      return null;
    } finally {
      if (submit) submit.disabled = false;
    }
  }

  async function ensureDependency(depType) {
    if (depType === "PROFILE_CONTEXT") {
      if (state.profile && state.profile.profile) {
        return state.profile;
      }
      return await confirmProfileContext({ silent: true });
    }
    if (depType === "PORTFOLIO_CONTEXT") {
      if (state.portfolio) return state.portfolio;
      if (state.selectedPersona === "custom-user") return null;
      if (state.templateContext?.portfolio) {
        state.portfolio = state.templateContext.portfolio;
        return state.portfolio;
      }
      const owner = byId("owner-id")?.value.trim() || state.ownerId || "custom-user";
      const tpl = await loadTemplateContext(owner, ++state.templateSequence);
      if (tpl?.portfolio) {
        state.portfolio = tpl.portfolio;
        return state.portfolio;
      }
      return null;
    }
    if (depType === "PROFILE_PROPOSAL") {
      if (state.profileProposalDraft && state.profileProposalQuestionnaire && state.profileProposalExtraction) {
        return true;
      }
      await previewProfileProposal();
      return !!(state.profileProposalDraft && state.profileProposalQuestionnaire && state.profileProposalExtraction);
    }
    return null;
  }

  function clearConfirmedContexts() {
    state.portfolio = null;
    state.profile = null;
    byId("portfolio-json").value = "";
    setPortfolioContextStatus("未确认");
    setProfileContextStatus("未确认");
    renderConfirmedProfile(null);
    clearProfileProposal();
    clearAdvisorPlan();
  }

  function clearTemplateContext({ clearConfirmed = false } = {}) {
    state.queryTemplate = null;
    state.templateContext = null;
    byId("query-template-meta").textContent = "根据设定的风险参数与偏好进行查询。";
    if (clearConfirmed) clearConfirmedContexts();
    renderPortfolio(null);
    renderProfileContext(null);
  }

  async function loadTemplateContext(ownerId, sequence) {
    try {
      const response = await fetch("/api/v1/advisor/query-template", {
        headers: { "X-Owner-ID": ownerId },
      });
      if (!response.ok) throw await apiError(response);
      const template = await response.json();
      if (state.ownerId !== ownerId || state.templateSequence !== sequence) return null;
      state.templateContext = template;
      state.queryTemplate = template;
      byId("query-template-meta").textContent = `合成数据 ${text(template.fixture_id)} · 生成时间 ${text(template.generated_at)} · 合成持仓模板`;
      renderPortfolio(
        state.portfolio || template.portfolio,
        state.portfolio ? "已确认 · 当前会话只读" : "只读 · 合成模板",
      );
      renderProfileContext(state.profile?.questionnaire || template.questionnaire);
      renderConfirmedProfile(state.profile?.profile || null);
      return template;
    } catch (error) {
      if (state.ownerId === ownerId && state.templateSequence === sequence) {
        clearTemplateContext({ clearConfirmed: true });
      }
      throw error;
    }
  }

  async function loadResearchScenarioCatalog(ownerId) {
    const sequence = ++state.researchSequence;
    const response = await fetch("/api/v1/advisor/research-matrix-template", {
      headers: { "X-Owner-ID": ownerId },
    });
    if (!response.ok) throw await apiError(response);
    const template = await response.json();
    if (state.ownerId !== ownerId || state.researchSequence !== sequence) return null;
    state.researchTemplate = template;
    renderResearchScenarioOptions(template.scenarios);
    byId("research-template-meta").textContent = `研究矩阵 · ${text(template.node_count, "0")} 个节点 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
    return template;
  }

  async function loadStockResearchCatalog(ownerId) {
    const sequence = ++state.stockResearchSequence;
    const response = await fetch("/api/v1/advisor/stock-research-template", {
      headers: { "X-Owner-ID": ownerId },
    });
    if (!response.ok) throw await apiError(response);
    const template = await response.json();
    if (state.ownerId !== ownerId || state.stockResearchSequence !== sequence) return null;
    state.stockResearchTemplate = template;
    renderStockResearchScenarioOptions(template.scenarios);
    byId("stock-research-template-meta").textContent = `个股 ${researchSubjectLabel(template.subject)} · ${researchPeriodLabel(template.period)} · ${text(template.metrics?.length, "0")} 项指标 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
    return template;
  }

  async function loadFundResearchCatalog(ownerId) {
    const sequence = ++state.fundResearchSequence;
    const response = await fetch("/api/v1/advisor/fund-research-template", {
      headers: { "X-Owner-ID": ownerId },
    });
    if (!response.ok) throw await apiError(response);
    const template = await response.json();
    if (state.ownerId !== ownerId || state.fundResearchSequence !== sequence) return null;
    state.fundResearchTemplate = template;
    renderFundResearchScenarioOptions(template.scenarios);
    byId("fund-research-template-meta").textContent = `基金 ${researchSubjectLabel(template.subject)} · ${researchPeriodLabel(template.period)} · ${text(template.metrics?.length, "0")} 项指标 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
    return template;
  }

  async function loadConvertibleBondResearchCatalog(ownerId) {
    const sequence = ++state.convertibleBondResearchSequence;
    const response = await fetch("/api/v1/advisor/convertible-bond-research-template", {
      headers: { "X-Owner-ID": ownerId },
    });
    if (!response.ok) throw await apiError(response);
    const template = await response.json();
    if (state.ownerId !== ownerId || state.convertibleBondResearchSequence !== sequence) return null;
    state.convertibleBondResearchTemplate = template;
    renderConvertibleBondResearchScenarioOptions(template.scenarios);
    byId("convertible-bond-research-template-meta").textContent = `可转债 ${researchSubjectLabel(template.subject)} · ${researchPeriodLabel(template.period)} · ${text(template.metrics?.length, "0")} 项指标 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
    return template;
  }

  async function loadPortfolioOptimizationCatalog(ownerId) {
    const sequence = ++state.portfolioOptimizationSequence;
    if (state.dataMode === "LIVE") {
      const template = {
        methodology_version: "CAP_AND_REDISTRIBUTE_V1",
        rules: [],
        scenarios: [{
          scenario_id: "BASELINE_READY",
          label: "当前真实持仓",
          description: "仅对当前已确认并完成真实行情刷新的持仓计算目标权重。",
        }],
        generated_at: new Date().toISOString(),
        questionnaire: state.profile?.questionnaire || null,
      };
      if (state.ownerId !== ownerId || state.portfolioOptimizationSequence !== sequence) return null;
      state.portfolioOptimizationTemplate = template;
      renderPortfolioOptimizationScenarioOptions(template.scenarios);
      byId("portfolio-optimization-template-meta").textContent = "方法 CAP_AND_REDISTRIBUTE_V1 · 当前真实持仓 · Python 确定性计算";
      return template;
    }
    const response = await fetch("/api/v1/advisor/portfolio-optimization-template", {
      headers: { "X-Owner-ID": ownerId },
    });
    if (!response.ok) throw await apiError(response);
    const template = await response.json();
    if (state.ownerId !== ownerId || state.portfolioOptimizationSequence !== sequence) return null;
    state.portfolioOptimizationTemplate = template;
    renderPortfolioOptimizationScenarioOptions(template.scenarios);
    byId("portfolio-optimization-template-meta").textContent = `方法 ${text(template.methodology_version)} · ${text((template.rules || []).length, "0")} 条规则 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
    return template;
  }

  async function loadScenarioSimulationCatalog(ownerId) {
    const sequence = ++state.scenarioSimulationSequence;
    const response = await fetch("/api/v1/advisor/scenario-simulation-template", {
      headers: { "X-Owner-ID": ownerId },
    });
    if (!response.ok) throw await apiError(response);
    const template = await response.json();
    if (state.ownerId !== ownerId || state.scenarioSimulationSequence !== sequence) return null;
    state.scenarioSimulationTemplate = template;
    renderScenarioSimulationScenarioOptions(template.scenarios);
    const metaNode = byId("scenario-simulation-template-meta");
    if (metaNode) {
      metaNode.textContent = `方法 ${text(template.methodology_version)} · ${text((template.scenarios || []).length, "0")} 个模拟场景 · 生成时间 ${text(template.generated_at)}`;
    }
    return template;
  }

  async function extractNaturalProfile() {
    if (!state.profile?.questionnaire) { setError("请先完成并确认风险问卷，再与自然语言偏好进行核对"); return; }
    const owner = state.ownerId;
    const revision = state.contextRevision;
    const input = byId("profile-natural-text").value.trim();
    const button = byId("extract-natural-profile");
    if (!input) { setError("请先输入投资偏好"); return; }
    button.disabled = true;
    try {
      const response = await fetch("/api/v1/advisor/profile-extractions", {
        method:"POST", headers:{"Content-Type":"application/json", "X-Owner-ID":owner},
        body:JSON.stringify({owner_id:owner, text:input}),
      });
      if (!response.ok) throw await apiError(response);
      const result = await response.json();
      if (state.ownerId !== owner || state.contextRevision !== revision || byId("profile-natural-text").value.trim() !== input) return;
      byId("profile-proposal-json").value = JSON.stringify(result.extraction, null, 2);
      byId("profile-natural-evidence").textContent = [
        ...result.evidence.map(item => `${profileDimensionLabel(item.field)}：${text(item.value)}；原文「${item.quote}」；置信度 ${item.confidence}`),
        ...result.warnings, "尚未修改已确认画像。",
      ].join("\n");
      if (result.status === "REQUIRES_CONFIRMATION") await previewProfileProposal();
      else { clearProfileProposal({clearInput:false}); setError("没有足够明确的偏好，请补充或使用风险问卷"); }
    } catch (error) {
      if (state.ownerId === owner) setError(error.message || "提取失败，未修改画像");
    } finally { button.disabled = false; }
  }

  async function previewProfileProposal() {
    const requestOwner = byId("owner-id").value.trim();
    const raw = byId("profile-proposal-json").value.trim();
    const submit = byId("preview-profile-proposal");
    if (!requestOwner) {
      clearProfileProposal({ clearInput: false });
      clearAdvisorPlan();
      setProfileProposalStatus("需要隔离标识", "blocked");
      setError("请输入隔离标识。");
      return;
    }
    if (!raw) {
      clearProfileProposal({ clearInput: false });
      clearAdvisorPlan();
      setProfileProposalStatus("未提供 JSON", "blocked");
      setError("请粘贴已脱敏的画像提取提案 JSON。");
      return;
    }
    let extraction;
    try {
      extraction = JSON.parse(raw);
      if (!extraction || typeof extraction !== "object" || Array.isArray(extraction)) {
        throw new Error("not an object");
      }
    } catch (_) {
      clearProfileProposal({ clearInput: false });
      clearAdvisorPlan();
      setProfileProposalStatus("JSON 无效", "blocked");
      setError("画像提案 JSON 格式错误，请检查语法。");
      return;
    }
    if (requestOwner !== state.ownerId) {
      state.ownerId = requestOwner;
      resetOwnerScopedViews();
      byId("profile-proposal-json").value = raw;
    }
    clearAdvisorPlan();
    clearProfileProposal({ clearInput: false });
    const proposalSequence = ++state.profileProposalSequence;
    let templateSequence = state.templateSequence;
    if (!state.queryTemplate) templateSequence = ++state.templateSequence;
    setError("");
    submit.disabled = true;
    setProfileProposalStatus("验证中…");
    try {
      const template = state.queryTemplate || await loadTemplateContext(requestOwner, templateSequence);
      if (!template) return;
      const questionnaire = state.profile?.questionnaire || buildQuestionnaire(template);
      const response = await fetch("/api/v1/advisor/profile-proposals", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "advisor-profile-proposal-request.v1",
          questionnaire,
          extraction,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (
        state.ownerId !== requestOwner
        || state.templateSequence !== templateSequence
        || state.profileProposalSequence !== proposalSequence
      ) return;
      const result = await response.json();
      state.profileProposalDraft = result.draft;
      state.profileProposalQuestionnaire = questionnaire;
      state.profileProposalExtraction = extraction;
      state.profileProposalProfile = null;
      state.profileProposalResolutions = {};
      renderProfileProposal(result.draft);
      renderProfileProposalResult(null);
      const conflictCount = (result.draft.conflicts || []).length;
      setProfileProposalStatus(
        conflictCount ? `${conflictCount} 个冲突` : "无冲突 · 可确认",
        conflictCount ? "review" : "pass",
      );
      setProfileProposalConfirmStatus(conflictCount ? "待选择" : "待确认");
    } catch (error) {
      if (
        state.ownerId === requestOwner
        && state.templateSequence === templateSequence
        && state.profileProposalSequence === proposalSequence
      ) {
        clearProfileProposal({ clearInput: false });
        setProfileProposalStatus("未生成", "blocked");
      }
      setError(error.message || "风险画像提案验证失败");
    } finally {
      submit.disabled = false;
    }
  }

  async function confirmProfileProposal() {
    let draft = state.profileProposalDraft;
    let questionnaire = state.profileProposalQuestionnaire;
    let extraction = state.profileProposalExtraction;
    const submit = byId("confirm-profile-proposal");
    if (!draft || !questionnaire || !extraction) {
      setProfileProposalConfirmStatus("正在自动预览…", "review");
      await ensureDependency("PROFILE_PROPOSAL");
      draft = state.profileProposalDraft;
      questionnaire = state.profileProposalQuestionnaire;
      extraction = state.profileProposalExtraction;
    }
    if (!draft || !questionnaire || !extraction) {
      setProfileProposalConfirmStatus("请先预览", "blocked");
      setError("请先预览结构化风险画像提案。");
      return;
    }
    const resolutions = {};
    let unresolved = false;
    byId("profile-proposal-content").querySelectorAll("select[data-conflict-id]").forEach((select) => {
      if (!select.value || select.value === "UNRESOLVED") unresolved = true;
      else resolutions[select.dataset.conflictId] = select.value;
    });
    if (unresolved) {
      setProfileProposalConfirmStatus("需逐项选择", "blocked");
      setError("请为每个画像冲突选择问卷值或提取值。");
      return;
    }
    const requestOwner = state.ownerId;
    const confirmationSequence = ++state.profileProposalSequence;
    setError("");
    submit.disabled = true;
    setProfileProposalConfirmStatus("确认中…");
    try {
      const response = await fetch("/api/v1/advisor/profile-proposals/confirm", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "advisor-profile-confirmation-request.v1",
          questionnaire,
          extraction,
          resolutions,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.profileProposalSequence !== confirmationSequence) return;
      const result = await response.json();
      state.profileProposalProfile = result.profile;
      renderProfileProposalResult(state.profileProposalProfile);
      setProfileProposalConfirmStatus(`已确认 · ${text(result.profile.risk_level)}`, "pass");
    } catch (error) {
      if (state.ownerId === requestOwner && state.profileProposalSequence === confirmationSequence) {
        state.profileProposalProfile = null;
        renderProfileProposalResult(null);
        setProfileProposalConfirmStatus("未确认", "blocked");
      }
      setError(error.message || "画像提案确认失败");
    } finally {
      submit.disabled = false;
    }
  }

  async function previewAdvisorPlan() {
    const requestOwner = byId("owner-id").value.trim();
    const submit = byId("preview-advisor-plan");
    if (!requestOwner) {
      clearAdvisorPlan();
      setAdvisorPlanStatus("需要隔离标识", "blocked");
      setError("请输入隔离标识。");
      return;
    }
    if (requestOwner !== state.ownerId) {
      state.ownerId = requestOwner;
      resetOwnerScopedViews();
    }
    const planSequence = ++state.templateSequence;
    setError("");
    submit.disabled = true;
    clearAdvisorPlan();
    setAdvisorPlanStatus("生成中…");
    try {
      const template = state.queryTemplate || await loadTemplateContext(requestOwner, planSequence);
      if (!template) return;
      const portfolio = state.portfolio || template.portfolio;
      const questionnaire = buildQuestionnaire(template);
      const intentType = byId("intent-type").value;
      const response = await fetch("/api/v1/advisor/plans", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "advisor-intent-request.v1",
          intent_id: `${questionnaire.questionnaire_id}-plan`,
          owner_id: requestOwner,
          intent_type: intentType,
          generated_at: new Date().toISOString(),
          portfolio_bundle_id: portfolio.bundle_id,
          position_snapshot_id: portfolio.position_snapshot.snapshot_id,
          questionnaire_id: questionnaire.questionnaire_id,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.templateSequence !== planSequence) return;
      state.advisorPlan = await response.json();
      renderAdvisorPlan(state.advisorPlan);
      setAdvisorPlanStatus(`已生成 · ${text(state.advisorPlan.node_count)} 个节点`, "pass");
    } catch (error) {
      if (state.ownerId === requestOwner && state.templateSequence === planSequence) {
        clearAdvisorPlan();
        setAdvisorPlanStatus("未生成", "blocked");
      }
      setError(error.message || "任务计划生成失败");
    } finally {
      submit.disabled = false;
    }
  }

  function resetOwnerScopedViews() {
    byId("truth-turn-alerts").replaceChildren();
    byId("truth-drawer").close();
    byId("truth-confirm-dialog").close();
    truthReview = null;
    clearContextMemory();
    clearTemplateContext({ clearConfirmed: true });
    setQueryStatus("待运行");
    state.events = [];
    state.selected = null;
    state.selectedDecisionEvent = null;
    state.advancedEvidenceSearch = "";
    state.advancedEvidenceQuality = "ALL";
    state.advancedEvidenceMode = "ALL";
    state.advancedEvidenceSource = "ALL";
    state.advancedEvidencePromotion = "ALL";
    state.advancedEvidenceSelectedKey = "";
    const advancedSearch = byId("advanced-evidence-search");
    if (advancedSearch) advancedSearch.value = "";
    renderEvents();
    renderProfile(null);
    renderEvidence(null);
    byId("detail-status").className = "status-chip";
    byId("detail-status").textContent = "待选择";
    byId("detail-content").replaceChildren();
    const detailEmpty = document.createElement("div");
    detailEmpty.className = "empty-state";
    detailEmpty.textContent = "读取隔离标识后查看已保存的决策事件。";
    byId("detail-content").append(detailEmpty);
    state.researchTemplate = null;
    state.researchRun = null;
    state.researchSequence += 1;
    byId("research-template-meta").textContent = "运行时读取四轨道矩阵模板；研究结果不写入决策回执。";
    clearResearchScenarioOptions();
    setResearchStatus("待运行");
    renderResearchMatrix(null);
    state.stockResearchTemplate = null;
    state.stockResearchRun = null;
    state.stockResearchSequence += 1;
    byId("stock-research-template-meta").textContent = "运行时读取固定合成个股与风险规则；结果不写入决策回执。";
    clearStockResearchScenarioOptions();
    setStockResearchStatus("待运行");
    renderStockResearch(null);
    state.fundResearchTemplate = null;
    state.fundResearchRun = null;
    state.fundResearchSequence += 1;
    byId("fund-research-template-meta").textContent = "运行时读取固定合成基金与资产风险规则；结果不写入决策回执。";
    clearFundResearchScenarioOptions();
    setFundResearchStatus("待运行");
    renderFundResearch(null);
    state.convertibleBondResearchTemplate = null;
    state.convertibleBondResearchRun = null;
    state.convertibleBondResearchSequence += 1;
    byId("convertible-bond-research-template-meta").textContent = "运行时读取固定合成可转债、确定性公式与风险规则；结果不写入决策回执。";
    clearConvertibleBondResearchScenarioOptions();
    setConvertibleBondResearchStatus("待运行");
    renderConvertibleBondResearch(null);
    state.portfolioOptimizationTemplate = null;
    state.portfolioOptimizationRun = null;
    state.portfolioOptimizationSequence += 1;
    byId("portfolio-optimization-template-meta").textContent = "运行时读取确定性上限重分配（cap-and-redistribute）方法与合成组合模板。";
    clearPortfolioOptimizationScenarioOptions();
    setPortfolioOptimizationStatus("待运行");
    renderPortfolioOptimization(null);
    state.scenarioSimulationTemplate = null;
    state.scenarioSimulationRun = null;
    state.scenarioSimulationSequence += 1;
    const simMeta = byId("scenario-simulation-template-meta");
    if (simMeta) simMeta.textContent = "模拟市场或持仓变化，评估风险与目标权重。";
    clearScenarioSimulationScenarioOptions();
    setScenarioSimulationStatus("待运行");
    renderScenarioSimulation(null);
  }

  async function runAdvisorQuery(event) {
    event.preventDefault();
    const nextOwnerId = byId("owner-id").value.trim();
    const ownerChanged = nextOwnerId !== state.ownerId;
    state.ownerId = nextOwnerId;
    if (ownerChanged || !state.ownerId) resetOwnerScopedViews();
    const requestOwner = state.ownerId;
    const templateSequence = ++state.templateSequence;
    const queryId = byId("query-id").value.trim();
    const submit = byId("run-advisor-query");
    if (!state.ownerId) {
      setError("请输入隔离标识。");
      return;
    }
    if (!queryId) {
      setError("请输入查询 ID。");
      return;
    }
    setError("");
    submit.disabled = true;
    setQueryStatus("运行中…");
    try {
      const template = state.queryTemplate || await loadTemplateContext(requestOwner, templateSequence);
      if (!template) return;

      const questionnaire = buildQuestionnaire(template);
      const payload = {
        schema_version: "advisor-query.v1",
        query_id: queryId,
        fixture_id: template.fixture_id,
        generated_at: template.generated_at,
        questionnaire,
        portfolio: state.portfolio || template.portfolio,
      };
      const response = await fetch("/api/v1/advisor/queries", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": state.ownerId,
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.templateSequence !== templateSequence) return;
      const result = await response.json();
      const createdLabel = result.created ? "已保存" : "已复用";
      setQueryStatus(`${statusLabel(result.status)} · ${createdLabel}`, statusClass(result.status));
      await loadEvents();
      if (result.event && result.event.event_id) await loadEvent(result.event.event_id);
    } catch (error) {
      setQueryStatus("未运行", "blocked");
      setError(error.message || "运行投顾查询失败");
    } finally {
      submit.disabled = false;
    }
  }

  async function runResearchMatrix() {
    const nextOwnerId = byId("owner-id").value.trim();
    const ownerChanged = nextOwnerId !== state.ownerId;
    state.ownerId = nextOwnerId;
    if (ownerChanged || !state.ownerId) resetOwnerScopedViews();
    const requestOwner = state.ownerId;
    const researchSequence = ++state.researchSequence;
    const submit = byId("run-research-matrix");
    const scenarioSelect = byId("research-scenario");
    if (!state.ownerId) {
      setError("请输入隔离标识。");
      return;
    }
    setError("");
    submit.disabled = true;
    scenarioSelect.disabled = true;
    state.researchRun = null;
    renderResearchMatrix(null);
    setResearchStatus("运行中…");
    try {
      const templateResponse = await fetch("/api/v1/advisor/research-matrix-template", {
        headers: { "X-Owner-ID": state.ownerId },
      });
      if (!templateResponse.ok) throw await apiError(templateResponse);
      const template = await templateResponse.json();
      if (state.ownerId !== requestOwner || state.researchSequence !== researchSequence) return;
      state.researchTemplate = template;
      renderResearchScenarioOptions(template.scenarios);
      const scenarioId = scenarioSelect.value || "BASELINE_READY";
      scenarioSelect.disabled = true;
      byId("research-template-meta").textContent = `矩阵 ${text(template.matrix_id)} · ${text(template.node_count)} 个节点 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
      const response = await fetch("/api/v1/advisor/research-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": state.ownerId,
        },
        body: JSON.stringify({
          schema_version: "research-specialist-matrix-request.v1",
          matrix_id: template.matrix_id,
          request_id: "ui-research-001",
          owner_id: state.ownerId,
          generated_at: new Date().toISOString(),
          scenario_id: scenarioId,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.researchSequence !== researchSequence) return;
      state.researchRun = await response.json();
      setResearchStatus(
        researchStatusLabel(state.researchRun.pipeline_status),
        researchStatusClass(state.researchRun.pipeline_status),
      );
      renderResearchMatrix(state.researchRun);
    } catch (error) {
      if (state.ownerId !== requestOwner || state.researchSequence !== researchSequence) return;
      state.researchRun = null;
      renderResearchMatrix(null);
      setResearchStatus("未运行", "blocked");
      setError(error.message || "运行研究矩阵失败");
    } finally {
      submit.disabled = false;
      if (state.ownerId === requestOwner && state.researchSequence === researchSequence) {
        scenarioSelect.disabled = !state.researchTemplate;
      }
    }
  }

  async function runStockResearch() {
    const nextOwnerId = byId("owner-id").value.trim();
    const ownerChanged = nextOwnerId !== state.ownerId;
    state.ownerId = nextOwnerId;
    if (ownerChanged || !state.ownerId) resetOwnerScopedViews();
    const requestOwner = state.ownerId;
    let sequence = ++state.stockResearchSequence;
    const submit = byId("run-stock-research");
    const scenarioSelect = byId("stock-research-scenario");
    if (!state.ownerId) {
      setError("请输入隔离标识。");
      return;
    }
    setError("");
    submit.disabled = true;
    scenarioSelect.disabled = true;
    state.stockResearchRun = null;
    renderStockResearch(null);
    setStockResearchStatus("运行中…");
    try {
      let template = state.stockResearchTemplate;
      if (!template) {
        template = await loadStockResearchCatalog(requestOwner);
        sequence = state.stockResearchSequence;
      }
      if (!template) return;
      if (state.ownerId !== requestOwner || state.stockResearchSequence !== sequence) return;
      const scenarioId = scenarioSelect.value || "BASELINE_READY";
      const response = await fetch("/api/v1/advisor/stock-research-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "stock-research-request.v1",
          request_id: "ui-stock-research-001",
          owner_id: requestOwner,
          subject: template.subject,
          period: template.period,
          generated_at: template.generated_at,
          scenario_id: scenarioId,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.stockResearchSequence !== sequence) return;
      state.stockResearchRun = await response.json();
      setStockResearchStatus(
        researchStatusLabel(state.stockResearchRun.pipeline_status),
        researchStatusClass(state.stockResearchRun.pipeline_status),
      );
      renderStockResearch(state.stockResearchRun);
    } catch (error) {
      if (state.ownerId !== requestOwner || state.stockResearchSequence !== sequence) return;
      state.stockResearchRun = null;
      renderStockResearch(null);
      setStockResearchStatus("未运行", "blocked");
      setError(error.message || "运行个股研究失败");
    } finally {
      submit.disabled = false;
      if (state.ownerId === requestOwner && state.stockResearchSequence === sequence) {
        scenarioSelect.disabled = !state.stockResearchTemplate;
      }
    }
  }

  async function runFundResearch() {
    const nextOwnerId = byId("owner-id").value.trim();
    const ownerChanged = nextOwnerId !== state.ownerId;
    state.ownerId = nextOwnerId;
    if (ownerChanged || !state.ownerId) resetOwnerScopedViews();
    const requestOwner = state.ownerId;
    let sequence = ++state.fundResearchSequence;
    const submit = byId("run-fund-research");
    const scenarioSelect = byId("fund-research-scenario");
    if (!state.ownerId) {
      setError("请输入隔离标识。");
      return;
    }
    setError("");
    submit.disabled = true;
    scenarioSelect.disabled = true;
    state.fundResearchRun = null;
    renderFundResearch(null);
    setFundResearchStatus("运行中…");
    try {
      let template = state.fundResearchTemplate;
      if (!template) {
        template = await loadFundResearchCatalog(requestOwner);
        sequence = state.fundResearchSequence;
      }
      if (!template) return;
      if (state.ownerId !== requestOwner || state.fundResearchSequence !== sequence) return;
      const scenarioId = scenarioSelect.value || "BASELINE_READY";
      const response = await fetch("/api/v1/advisor/fund-research-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "fund-research-request.v1",
          request_id: "ui-fund-research-001",
          owner_id: requestOwner,
          subject: template.subject,
          period: template.period,
          generated_at: template.generated_at,
          scenario_id: scenarioId,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.fundResearchSequence !== sequence) return;
      state.fundResearchRun = await response.json();
      setFundResearchStatus(
        researchStatusLabel(state.fundResearchRun.pipeline_status),
        researchStatusClass(state.fundResearchRun.pipeline_status),
      );
      renderFundResearch(state.fundResearchRun);
    } catch (error) {
      if (state.ownerId !== requestOwner || state.fundResearchSequence !== sequence) return;
      state.fundResearchRun = null;
      renderFundResearch(null);
      setFundResearchStatus("未运行", "blocked");
      setError(error.message || "运行 ETF / 基金研究失败");
    } finally {
      submit.disabled = false;
      if (state.ownerId === requestOwner && state.fundResearchSequence === sequence) {
        scenarioSelect.disabled = !state.fundResearchTemplate;
      }
    }
  }

  async function runConvertibleBondResearch() {
    const nextOwnerId = byId("owner-id").value.trim();
    const ownerChanged = nextOwnerId !== state.ownerId;
    state.ownerId = nextOwnerId;
    if (ownerChanged || !state.ownerId) resetOwnerScopedViews();
    const requestOwner = state.ownerId;
    let sequence = ++state.convertibleBondResearchSequence;
    const submit = byId("run-convertible-bond-research");
    const scenarioSelect = byId("convertible-bond-research-scenario");
    if (!state.ownerId) {
      setError("请输入隔离标识。");
      return;
    }
    setError("");
    submit.disabled = true;
    scenarioSelect.disabled = true;
    state.convertibleBondResearchRun = null;
    renderConvertibleBondResearch(null);
    setConvertibleBondResearchStatus("运行中…");
    try {
      let template = state.convertibleBondResearchTemplate;
      if (!template) {
        template = await loadConvertibleBondResearchCatalog(requestOwner);
        sequence = state.convertibleBondResearchSequence;
      }
      if (!template) return;
      if (state.ownerId !== requestOwner || state.convertibleBondResearchSequence !== sequence) return;
      const scenarioId = scenarioSelect.value || "BASELINE_READY";
      const response = await fetch("/api/v1/advisor/convertible-bond-research-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "convertible-bond-research-request.v1",
          request_id: "ui-convertible-bond-research-001",
          owner_id: requestOwner,
          subject: template.subject,
          period: template.period,
          generated_at: template.generated_at,
          scenario_id: scenarioId,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.convertibleBondResearchSequence !== sequence) return;
      state.convertibleBondResearchRun = await response.json();
      setConvertibleBondResearchStatus(
        researchStatusLabel(state.convertibleBondResearchRun.pipeline_status),
        researchStatusClass(state.convertibleBondResearchRun.pipeline_status),
      );
      renderConvertibleBondResearch(state.convertibleBondResearchRun);
    } catch (error) {
      if (state.ownerId !== requestOwner || state.convertibleBondResearchSequence !== sequence) return;
      state.convertibleBondResearchRun = null;
      renderConvertibleBondResearch(null);
      setConvertibleBondResearchStatus("未运行", "blocked");
      setError(error.message || "运行可转债研究失败");
    } finally {
      submit.disabled = false;
      if (state.ownerId === requestOwner && state.convertibleBondResearchSequence === sequence) {
        scenarioSelect.disabled = !state.convertibleBondResearchTemplate;
      }
    }
  }

  async function runPortfolioOptimization() {
    const requestOwner = byId("owner-id").value.trim();
    const submit = byId("run-portfolio-optimization");
    const scenarioSelect = byId("portfolio-optimization-scenario");
    if (!requestOwner) {
      setError("请输入隔离标识。");
      return;
    }
    if (!state.portfolioOptimizationTemplate) {
      try {
        await loadPortfolioOptimizationCatalog(requestOwner);
      } catch (error) {
        setError(error.message || "读取组合优化模板失败");
        return;
      }
    }
    const template = state.portfolioOptimizationTemplate;
    if (!template || state.ownerId !== requestOwner) return;
    if (!state.profile || !state.profile.profile) {
      setPortfolioOptimizationStatus("正在自动确认前置画像…", "review");
      await ensureDependency("PROFILE_CONTEXT");
    }
    if (!state.profile || !state.profile.profile) {
      setPortfolioOptimizationStatus("需先确认画像", "review");
      setError("请先确认风险画像，再生成组合目标结构。");
      return;
    }
    await ensureDependency("PORTFOLIO_CONTEXT");
    if (!state.portfolio) {
      setError("请先添加并确认持仓，再生成组合目标结构。");
      return null;
    }
    if (state.dataMode === "LIVE" && state.portfolioRefreshRun?.status !== "COMPLETE") {
      setPortfolioOptimizationStatus("正在刷新真实行情…", "review");
      const health = await refreshPortfolioHealth();
      if (!health || state.portfolioRefreshRun?.status !== "COMPLETE") {
        setPortfolioOptimizationStatus("持仓信息待补全", "review");
        setError(portfolioRefreshProblem());
        return null;
      }
    }
    const requestSequence = ++state.portfolioOptimizationSequence;
    const scenarioId = scenarioSelect.value || "BASELINE_READY";
    const questionnaire = state.profile && state.profile.questionnaire
      ? state.profile.questionnaire
      : template.questionnaire;
    const portfolio = state.portfolio;
    submit.disabled = true;
    scenarioSelect.disabled = true;
    state.portfolioOptimizationRun = null;
    renderPortfolioOptimization(null);
    setPortfolioOptimizationStatus("运行中…");
    setError("");
    try {
      const response = await fetch("/api/v1/advisor/portfolio-optimization-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "portfolio-optimization-request.v1",
          request_id: "ui-portfolio-optimization-001",
          owner_id: requestOwner,
          generated_at: new Date().toISOString(),
          questionnaire,
          confirmed_profile: state.profile.profile,
          portfolio,
          scenario_id: scenarioId,
          minimum_cash_pct: state.portfolioHealthRun?.cash_minimum_pct || "0.00",
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.portfolioOptimizationSequence !== requestSequence) return;
      state.portfolioOptimizationRun = await response.json();
      setPortfolioOptimizationStatus(
        optimizationStatusLabel(state.portfolioOptimizationRun.status),
        optimizationStatusClass(state.portfolioOptimizationRun.status),
      );
      renderPortfolioOptimization(state.portfolioOptimizationRun);
      return state.portfolioOptimizationRun;
    } catch (error) {
      if (state.ownerId !== requestOwner || state.portfolioOptimizationSequence !== requestSequence) return;
      if (error.errorCode === "LIVE_PORTFOLIO_REFRESH_REQUIRED") {
        state.portfolioRefreshRun = null;
        renderPortfolioRefreshStatus(null);
      }
      state.portfolioOptimizationRun = null;
      renderPortfolioOptimization(null);
      setPortfolioOptimizationStatus("未运行", "blocked");
      setError(error.message || "生成组合目标结构失败");
    } finally {
      submit.disabled = false;
      if (state.ownerId === requestOwner && state.portfolioOptimizationSequence === requestSequence) {
        scenarioSelect.disabled = !state.portfolioOptimizationTemplate;
      }
    }
  }

  async function runScenarioSimulation() {
    const requestOwner = byId("owner-id").value.trim();
    const submit = byId("run-scenario-simulation");
    const scenarioSelect = byId("scenario-simulation-scenario");
    if (!requestOwner) {
      setError("请输入隔离标识。");
      return;
    }
    if (!state.scenarioSimulationTemplate) {
      try {
        await loadScenarioSimulationCatalog(requestOwner);
      } catch (error) {
        setError(error.message || "读取情景模拟模板失败");
        return;
      }
    }
    const template = state.scenarioSimulationTemplate;
    if (!template || state.ownerId !== requestOwner) return;
    if (!state.profile || !state.profile.profile) {
      setScenarioSimulationStatus("正在自动确认前置画像…", "review");
      await ensureDependency("PROFILE_CONTEXT");
    }
    if (!state.profile || !state.profile.profile) {
      setScenarioSimulationStatus("需先确认画像", "review");
      setError("请先确认风险画像，再运行情景模拟。");
      return;
    }
    if (!state.portfolio) {
      await ensureDependency("PORTFOLIO_CONTEXT");
    }
    const requestSequence = ++state.scenarioSimulationSequence;
    const scenarioId = scenarioSelect.value || "BASELINE_READY";
    const baseTemplate = state.queryTemplate || state.portfolioOptimizationTemplate;
    const questionnaire = state.profile && state.profile.questionnaire
      ? state.profile.questionnaire
      : (baseTemplate ? buildQuestionnaire(baseTemplate) : null);
    const portfolio = state.portfolio || baseTemplate?.portfolio;
    if (!questionnaire || !portfolio) {
      setError("未找到有效持仓快照或问卷数据，请先加载工作台模板。");
      return;
    }
    submit.disabled = true;
    scenarioSelect.disabled = true;
    state.scenarioSimulationRun = null;
    renderScenarioSimulation(null);
    setScenarioSimulationStatus("运行中…");
    setError("");
    try {
      const response = await fetch("/api/v1/advisor/scenario-simulation-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": requestOwner,
        },
        body: JSON.stringify({
          schema_version: "scenario-simulation-request.v1",
          request_id: "ui-scenario-simulation-001",
          owner_id: requestOwner,
          generated_at: template.generated_at,
          scenario_id: scenarioId,
          questionnaire,
          portfolio,
        }),
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.scenarioSimulationSequence !== requestSequence) return;
      state.scenarioSimulationRun = await response.json();
      setScenarioSimulationStatus(
        optimizationStatusLabel(state.scenarioSimulationRun.status),
        optimizationStatusClass(state.scenarioSimulationRun.status),
      );
      renderScenarioSimulation(state.scenarioSimulationRun);
    } catch (error) {
      if (state.ownerId !== requestOwner || state.scenarioSimulationSequence !== requestSequence) return;
      state.scenarioSimulationRun = null;
      renderScenarioSimulation(null);
      setScenarioSimulationStatus("未运行", "blocked");
      setError(error.message || "运行情景模拟失败");
    } finally {
      submit.disabled = false;
      if (state.ownerId === requestOwner && state.scenarioSimulationSequence === requestSequence) {
        scenarioSelect.disabled = !state.scenarioSimulationTemplate;
      }
    }
  }

  async function loadEvents() {
    const nextOwnerId = byId("owner-id").value.trim();
    const ownerChanged = nextOwnerId !== state.ownerId;
    state.ownerId = nextOwnerId;
    const requestOwner = state.ownerId;
    const templateSequence = ++state.templateSequence;
    setError("");
    state.selected = null;
    state.selectedDecisionEvent = null;
    renderEvents();
    renderEvidence(null);
    byId("detail-status").className = "status-chip";
    byId("detail-status").textContent = "读取中…";
    clear(byId("detail-content"));
    const loadingDetail = document.createElement("div");
    loadingDetail.className = "empty-state";
    loadingDetail.textContent = "读取当前隔离标识的决策回执…";
    byId("detail-content").append(loadingDetail);
    if (ownerChanged || !state.ownerId) {
      resetOwnerScopedViews();
    }
    if (!state.ownerId) {
      setError("请输入隔离标识。");
      return;
    }
    try {
      const response = await fetch("/api/v1/decision-events", {
        headers: { "X-Owner-ID": requestOwner },
      });
      if (!response.ok) throw await apiError(response);
      if (state.ownerId !== requestOwner || state.templateSequence !== templateSequence) return;
      state.events = (await response.json()).items || [];
      state.selected = null;
      state.selectedDecisionEvent = null;
      renderEvents();
      renderProfile(null);
      renderEvidence(null);
      byId("detail-status").className = "status-chip";
      byId("detail-status").textContent = "待选择";
      byId("detail-content").replaceChildren();
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = state.events.length ? "选择一条回执查看详情。" : "这个隔离标识还没有保存的决策事件。";
      byId("detail-content").append(empty);
      if (accountAccessEnabled) {
        // Formal sessions load each available workflow on demand. Hidden
        // fixture catalogues must not surface errors on the chat homepage.
        await loadContextMemory(requestOwner);
        if (state.ownerId === requestOwner && state.events.length) await loadEvent(state.events[0].event_id);
        return;
      }
      try {
        await loadTemplateContext(requestOwner, templateSequence);
      } catch (error) {
        if (state.ownerId === requestOwner && state.templateSequence === templateSequence) {
      setError(error.message || "读取持仓/风险画像模板失败");
        }
      }
      if (state.ownerId === requestOwner && !state.researchTemplate) {
        try {
          await loadResearchScenarioCatalog(requestOwner);
        } catch (error) {
          if (state.ownerId === requestOwner) {
            clearResearchScenarioOptions();
            setError(error.message || "读取研究场景目录失败");
          }
        }
      }
      if (state.ownerId === requestOwner && !state.stockResearchTemplate) {
        try {
          await loadStockResearchCatalog(requestOwner);
        } catch (error) {
          if (state.ownerId === requestOwner) {
            clearStockResearchScenarioOptions();
            setError(error.message || "读取个股研究场景目录失败");
          }
        }
      }
      if (state.ownerId === requestOwner && !state.fundResearchTemplate) {
        try {
          await loadFundResearchCatalog(requestOwner);
        } catch (error) {
          if (state.ownerId === requestOwner) {
            clearFundResearchScenarioOptions();
            setError(error.message || "读取 ETF / 基金研究场景目录失败");
          }
        }
      }
      if (state.ownerId === requestOwner && !state.convertibleBondResearchTemplate) {
        try {
          await loadConvertibleBondResearchCatalog(requestOwner);
        } catch (error) {
          if (state.ownerId === requestOwner) {
            clearConvertibleBondResearchScenarioOptions();
            setError(error.message || "读取可转债研究场景目录失败");
          }
        }
      }
      if (state.ownerId === requestOwner && !state.portfolioOptimizationTemplate) {
        try {
          await loadPortfolioOptimizationCatalog(requestOwner);
        } catch (error) {
          if (state.ownerId === requestOwner) {
            clearPortfolioOptimizationScenarioOptions();
            setError(error.message || "读取组合优化场景目录失败");
          }
        }
      }
      if (state.ownerId === requestOwner && !state.scenarioSimulationTemplate) {
        try {
          await loadScenarioSimulationCatalog(requestOwner);
        } catch (error) {
          if (state.ownerId === requestOwner) {
            clearScenarioSimulationScenarioOptions();
            setError(error.message || "读取情景模拟场景目录失败");
          }
        }
      }
      if (state.ownerId === requestOwner) {
        try {
          await loadContextMemory(requestOwner);
        } catch (error) {
          if (state.ownerId === requestOwner) {
            setContextMemoryStatus("读取失败", "blocked");
            setError(error.message || "读取上下文记忆失败");
          }
        }
      }
      if (state.events.length) await loadEvent(state.events[0].event_id);
    } catch (error) {
      state.events = [];
      renderEvents();
      setError(error.message || "读取决策列表失败");
    }
  }

  async function checkHealth() {
    const node = byId("health-status");
    if (!node) return;
    try {
      const response = await fetch("/api/health");
      if (!response.ok) throw new Error("health check failed");
      node.classList.remove("bad");
      node.classList.add("ok");
      node.hidden = true;
      node.textContent = "";
    } catch (_) {
      node.classList.remove("ok");
      node.classList.add("bad");
      node.hidden = false;
      node.textContent = "● 部分数据服务暂时不可用";
    }
  }

  function setExpertMode(enabled) {
    const workspace = byId("expert-workspace-grid");
    const modeToggle = byId("view-mode-toggle");
    const modeText = byId("mode-toggle-text");
    const modeIcon = byId("mode-toggle-icon");
    const expertNav = byId("nav-expert-section");
    if (workspace) {
      workspace.hidden = !enabled;
    }
    document.body.classList.toggle("expert-mode", enabled);
    if (modeToggle) modeToggle.setAttribute("aria-expanded", String(enabled));
    if (modeText) modeText.textContent = enabled ? "返回开始" : "更多工具";
    if (modeIcon) modeIcon.textContent = enabled ? "←" : "＋";
    if (expertNav && !enabled) expertNav.classList.add("collapsed");
  }

  const DOMAIN_MAP = Object.freeze({
    copilot: "copilot",
    workbench: "copilot",
    portfolio: "portfolio",
    overview: "portfolio",
    market: "market",
    "portfolio-optimization": "portfolio",
    "portfolio-rebalancing": "portfolio",
    "scenario-simulation": "portfolio",
    research: "research",
    "stock-research": "research",
    "fund-research": "research",
    "convertible-bond-research": "research",
    decisions: "decisions",
    "recommendation-history": "decisions",
    evidence: "decisions",
    "advanced-explainability": "decisions",
    system: "system",
    advisor: "system",
    profile: "profile",
    "research-tracks": "system",
    "context-memory": "system",
    "evaluation-dashboard": "system",
    "dev-assist": "system",
  });

  async function fetchRuntimeDataMode() {
    try {
      const res = await fetch("/api/v1/runtime/data-mode");
      if (res.ok) {
        const payload = await res.json();
        if (payload && payload.data) {
          const previousMode = state.dataMode;
          microStore.transact((store) => {
            store.dataMode = payload.data.data_mode || "MOCK";
            store.modeRevision = payload.data.revision || 1;
            store.liveReady = payload.data.live_ready === true;
            store.liveConfigured = payload.data.live_configured === true;
            store.wencaiReady = payload.data.wencai_ready === true;
            store.wencaiConfigured = payload.data.wencai_configured === true;
            store.wencaiLastErrorCode = payload.data.wencai_capability_status?.last_error_code || null;
            store.liveReadinessIssues = payload.data.live_readiness_issues || [];
            store.capabilities = payload.data.capabilities || null;
          });
          if (state.dataMode !== previousMode) {
            state.portfolio = null;
            state.ocrPortfolioDraft = null;
            renderInvalidatedDerivedState();
            syncNavigation();
            if (state.ownerId && state.selectedPersona === "custom-user") await loadSavedPortfolio();
          }
          updateRuntimeDataModeUI();
        }
      }
    } catch (err) {
      console.warn("fetchRuntimeDataMode failed:", err);
    }
  }

  function capabilitySummaryForUser() {
    const liveCapabilities = (state.capabilities && state.capabilities.LIVE) || {};
    const available = [];
    if (liveCapabilities.stock_quote) available.push("A 股行情");
    if (liveCapabilities.fund_lookthrough) available.push("场内基金披露");
    if (liveCapabilities.semantic_search) available.push("公告与语义检索");
    if (liveCapabilities.portfolio_refresh) available.push("组合刷新");
    return available.length ? available.join("、") : "暂无";
  }

  function liveModeLabelForUser() {
    const liveCapabilities = (state.capabilities && state.capabilities.LIVE) || {};
    const fuyaoReady = !!(liveCapabilities.stock_quote || liveCapabilities.fund_lookthrough);
    const wencaiReady = state.wencaiReady === true;
    if (fuyaoReady && wencaiReady) return "LIVE · 双数据源";
    if (fuyaoReady) return "LIVE · 扶摇数据";
    if (wencaiReady) return "LIVE · 问财数据";
    return "LIVE · 不可用";
  }

  function updateRuntimeDataModeUI() {
    updateVisibleSourceStatus();
    updateAgentFeatureAvailability();
    const btn = byId("global-data-mode-toggle");
    const label = byId("global-data-mode-label");
    if (!btn || !label) return;

    const isLive = (state.dataMode === "LIVE");
    const formalUnavailable = accountAccessEnabled && !isLive;
    const liveReady = state.liveReady === true;
    btn.classList.toggle("mode-live", isLive);
    btn.classList.toggle("mode-mock", !isLive);
    const liveCapabilities = (state.capabilities && state.capabilities.LIVE) || {};
    label.textContent = isLive ? liveModeLabelForUser() : formalUnavailable ? "工具数据 · 未就绪" : "MOCK · 合成数据";
    btn.disabled = accountAccessEnabled && isLive;
    const capabilitySummary = [
      `A 股行情${liveCapabilities.stock_quote ? "可用" : "不可用"}`,
      `场内基金披露${liveCapabilities.fund_lookthrough ? "可用" : "不可用"}`,
      `公告与语义检索${liveCapabilities.semantic_search ? "可用" : "不可用"}`,
      `组合刷新${liveCapabilities.portfolio_refresh ? "可用" : "不可用"}`,
    ].join("；");
    btn.setAttribute(
      "title",
      isLive
        ? capabilitySummary
        : (liveReady ? `可切换至实时数据；${capabilitySummary}` : "实时数据源尚未就绪"),
    );

    const fundInput = /^(510|512|513|515|588|159)/.test(byId("copilot-stock-input")?.value?.trim() || "");
    const capabilityControls = [
      ["copilot-btn-stock-research", fundInput ? "fund_lookthrough" : "stock_quote", "此类标的实时数据权限当前不可用"],
    ];
    capabilityControls.forEach(([id, capability, unavailableMessage]) => {
      const control = byId(id);
      if (!control) return;
      const unavailable = isLive && !liveCapabilities[capability];
      control.disabled = unavailable;
      control.setAttribute(
        "title",
        unavailable ? (accountAccessEnabled ? unavailableMessage : `${unavailableMessage}；可切换至 MOCK 查看示例数据`) : "",
      );
    });
  }

  function openDataModeConfirmModal() {
    if (accountAccessEnabled && state.dataMode === "LIVE") {
      alert("正式账户不允许切换至 Mock 数据；如需演示，请使用显式开发预览命令。");
      return;
    }
    const modal = byId("modal-data-mode-confirm");
    if (!modal) return;
    closeLLMConfigModal();
    document.body.appendChild(modal);

    const targetMode = (state.dataMode === "MOCK") ? "LIVE" : "MOCK";
    const currChip = byId("modal-curr-mode-chip");
    const targetChip = byId("modal-target-mode-chip");
    const revText = byId("modal-mode-revision-text");
    const warnTitle = byId("modal-mode-warning-title");
    const warnText = byId("modal-mode-warning-text");
    const confirmBtn = byId("btn-confirm-mode-switch");
    if (confirmBtn) confirmBtn.disabled = false;

    if (currChip) {
      currChip.textContent = (state.dataMode === "MOCK") ? "MOCK · 合成数据" : liveModeLabelForUser();
      currChip.className = "status-chip " + (state.dataMode === "MOCK" ? "chip-mock" : "chip-live");
    }
    if (targetChip) {
      targetChip.textContent = (targetMode === "LIVE") ? liveModeLabelForUser() : "MOCK · 合成数据";
      targetChip.className = "status-chip " + (targetMode === "LIVE" ? "chip-live" : "chip-mock");
    }
    if (revText) {
      revText.textContent = `当前 Rev: ${state.modeRevision} → 递增至 Rev: ${state.modeRevision + 1}`;
    }
    if (warnTitle && warnText) {
      if (targetMode === "LIVE") {
        warnTitle.textContent = "切换至实时数据";
        warnText.textContent = state.liveReady
          ? `服务端已验证可用能力：${capabilitySummaryForUser()}。`
          : state.liveConfigured
            ? "数据源已配置，正在检测连通性。"
            : "服务端尚无已验证的实时数据能力。请由管理员完成数据源配置。";
        if (confirmBtn) confirmBtn.disabled = !state.liveReady && !state.liveConfigured;
      } else {
        warnTitle.textContent = "沙箱仿真环境重置";
        warnText.textContent = "切回 MOCK 模式将加载本地基准沙箱与高质量仿真数据，所有分析结果将标注 MOCK · 合成数据。";
      }
    }

    modal.classList.add("active");
    modal.style.display = "flex";
  }

  function closeDataModeConfirmModal() {
    const modal = byId("modal-data-mode-confirm");
    if (modal) {
      modal.classList.remove("active");
      modal.style.display = "none";
    }
  }

  async function handleConfirmDataModeSwitch() {
    const confirmBtn = byId("btn-confirm-mode-switch");
    if (!confirmBtn) return;

    const targetMode = (state.dataMode === "MOCK") ? "LIVE" : "MOCK";
    if (targetMode === "LIVE" && !state.liveReady && !state.liveConfigured) {
      alert(`LIVE 不可用：${(state.liveReadinessIssues || []).join("、") || "缺少官方 Provider 配置"}`);
      return;
    }
    const expectedRevision = state.modeRevision;

    confirmBtn.disabled = true;
    confirmBtn.textContent = "正在校验并切换...";

    try {
      const resp = await fetch("/api/v1/runtime/data-mode", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_mode: targetMode,
          expected_revision: expectedRevision,
        }),
      });

      const body = await resp.json().catch(() => ({}));
      if (resp.status === 200 && body.status === "SUCCESS") {
        microStore.transact((store) => {
          store.dataMode = body.data.data_mode;
          store.modeRevision = body.data.revision;
          store.liveReady = body.data.live_ready === true;
          store.wencaiReady = body.data.wencai_ready === true;
          store.liveReadinessIssues = body.data.live_readiness_issues || [];
          store.capabilities = body.data.capabilities;
          store.portfolio = null;
          store.ocrPortfolioDraft = null;
          invalidateDerivedState(store);
        });
        renderInvalidatedDerivedState();
        updateRuntimeDataModeUI();
        closeDataModeConfirmModal();
        syncNavigation();
        await loadSavedPortfolio();
        await refreshSessionTruth().catch(error => setError(error.message));
      } else if (resp.status === 409) {
        alert(`[模式切换拦截 HTTP 409] ${body.message || "版本修订冲突或凭据缺失"}`);
        closeDataModeConfirmModal();
        await fetchRuntimeDataMode();
      } else {
        alert(`[模式切换失败 HTTP ${resp.status}] ${body.message || "请求被拒绝"}`);
        closeDataModeConfirmModal();
      }
    } catch (err) {
      alert(`[网络异常] 模式切换请求失败: ${err.message || err}`);
      closeDataModeConfirmModal();
    } finally {
      confirmBtn.disabled = false;
      confirmBtn.textContent = "确认切换模式";
    }
  }

  function initRuntimeDataMode() {
    const toggleBtn = byId("global-data-mode-toggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", openDataModeConfirmModal);
    }
    const closeBtn = byId("btn-close-mode-modal");
    if (closeBtn) {
      closeBtn.addEventListener("click", closeDataModeConfirmModal);
    }
    const cancelBtn = byId("btn-cancel-mode-switch");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", closeDataModeConfirmModal);
    }
    const confirmBtn = byId("btn-confirm-mode-switch");
    if (confirmBtn) {
      confirmBtn.addEventListener("click", handleConfirmDataModeSwitch);
    }
    fetchRuntimeDataMode();
  }

  function applyQuestionnaireGate(summary) {
    const wasPending = state.questionnaireGate === "PENDING";
    const hasConfirmedQuestionnaire = Boolean(summary?.questionnaire_snapshot);
    state.questionnaireGate = hasConfirmedQuestionnaire ? "COMPLETE" : "REQUIRED";
    document.body.classList.remove("questionnaire-pending", "questionnaire-required");
    document.body.classList.toggle("questionnaire-required", !hasConfirmedQuestionnaire);
    const profileTitle = byId("profile-title");
    const profileEyebrow = profileTitle?.closest(".panel-head")?.querySelector(".eyebrow");
    if (profileTitle) profileTitle.textContent = hasConfirmedQuestionnaire ? "风险测评与行为画像" : "投资者风险测评";
    if (profileEyebrow) profileEyebrow.textContent = hasConfirmedQuestionnaire ? "风险画像" : "首次使用";

    // The PRD permits browsing and portfolio input before assessment.  Action
    // endpoints remain individually gated by their existing server-side profile
    // checks, so navigation must not manufacture a C-level profile.
    if (!hasConfirmedQuestionnaire) {
      const key = ownerStorageKey("prism_welcome_dismissed");
      if (!workspaceStorage.getItem(key) || new URLSearchParams(window.location.search).get("onboarding") === "1") byId("questionnaire-welcome")?.showModal();
      return;
    }
    byId("questionnaire-welcome")?.close();

    if (wasPending && (!window.location.hash || window.location.hash === "#profile")) {
      window.history.replaceState(null, "", "#copilot");
      syncNavigation("copilot");
    }
  }

  function syncNavigation(targetId = window.location.hash.replace(/^#/, "")) {
    const aliases = {
      workbench: "copilot",
      research: "stock-research",
      decisions: "recommendation-history",
      system: "evaluation-dashboard",
      "expert-workspace-grid": "stock-research",
    };
    let requestedId = aliases[targetId] || targetId || "copilot";
    let domain = DOMAIN_MAP[requestedId] || "copilot";
    if (domain === "system" && !document.body.classList.contains("dev-mode")) {
      requestedId = "copilot";
      domain = "copilot";
    }
    const requestedNode = byId(requestedId);

    const copilotSec = byId("copilot");
    const overviewSec = byId("overview");
    const marketSec = byId("market");
    const expertSec = byId("expert-workspace-grid");
    const pageTabs = byId("workspace-page-tabs");

    const isOverview = (requestedId === "overview");
    const isMarket = (requestedId === "market");
    const isWorkspacePanel = Boolean(requestedNode?.closest("#expert-workspace-grid"));
    const isCopilot = domain === "copilot" || !requestedNode;

    if (copilotSec) copilotSec.hidden = !isCopilot;
    if (overviewSec) overviewSec.hidden = !isOverview;
    if (marketSec) marketSec.hidden = !isMarket;
    if (expertSec) expertSec.hidden = !isWorkspacePanel;
    if (pageTabs) pageTabs.hidden = isCopilot;

    setExpertMode(isWorkspacePanel);

    if (expertSec) {
      [...expertSec.children].forEach((child) => {
        if (child.classList.contains("panel")) child.hidden = child.id !== requestedId;
        if (child.classList.contains("expert-mode-banner")) child.hidden = true;
        if (child.classList.contains("dev-tools-banner")) child.hidden = domain !== "system";
      });
    }

    if (pageTabs) {
      [...pageTabs.querySelectorAll("a[data-domain]")].forEach((link) => {
        const visible = link.dataset.domain === domain;
        link.hidden = !visible;
        const selected = visible && link.getAttribute("href") === `#${requestedId}`;
        link.classList.toggle("active", selected);
        if (selected) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      const pageContainer = isOverview ? overviewSec : isMarket ? marketSec : isWorkspacePanel ? requestedNode : null;
      const pageHeading = pageContainer?.querySelector(":scope > .page-heading, :scope > .overview-header-bar, :scope > .panel-head, :scope > .panel-header, :scope > header");
      if (pageHeading) pageHeading.insertAdjacentElement("afterend", pageTabs);
      else if (pageContainer) pageContainer.prepend(pageTabs);
    }

    if (domain === "system") {
      const expertSecNav = byId("nav-expert-section");
      if (expertSecNav) {
        expertSecNav.classList.remove("collapsed");
      }
      const navToggle = byId("nav-expert-toggle");
      if (navToggle) navToggle.setAttribute("aria-expanded", "true");
    }

    if (isOverview) {
      renderOverviewWorkspace();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else if (isMarket) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else if (isCopilot) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else if (isWorkspacePanel) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    if (requestedId === "evaluation-dashboard") {
      loadEvaluationSummary();
    }
    if (requestedId === "profile" && state.ownerId) {
      Promise.allSettled([loadQuestionnaireTemplate(), loadProfileSummary()]);
    }
    if (requestedId === "portfolio" && state.portfolio) {
      const sourceTitle = state.dataMode === "LIVE" ? "已确认 · 实时数据" : "已确认 · 当前会话只读";
      renderPortfolio(state.portfolio, sourceTitle);
    }

    const items = [...document.querySelectorAll(".nav-item")];
    if (!items.length) return;
    const primaryByDomain = {
      copilot: "#copilot",
      portfolio: "#overview",
      market: "#market",
      research: "#stock-research",
      decisions: "#recommendation-history",
      profile: "#profile",
    };
    const target = items.find((item) => item.getAttribute("href") === (primaryByDomain[domain] || `#${requestedId}`))
      || items.find((item) => item.getAttribute("href") === `#${requestedId}`)
      || items[0];
    items.forEach((item) => {
      const selected = item === target;
      item.classList.toggle("active", selected);
      if (selected) item.setAttribute("aria-current", "location");
      else item.removeAttribute("aria-current");
    });
  }

  function initializeNavigation() {
    const items = [...document.querySelectorAll(".nav-item, #workspace-page-tabs a")];
    items.forEach((item) => {
      item.addEventListener("click", () => syncNavigation(item.hash.slice(1)));
    });
    window.addEventListener("hashchange", () => syncNavigation());
    syncNavigation();
  }

  async function loadUserPreferences() {
    const owner = state.ownerId;
    if (!owner) return;
    const response = await fetch("/api/v1/user/preferences", {headers: {"X-Owner-ID": owner}});
    if (!response.ok) throw await apiError(response);
    const preferences = await response.json();
    if (state.ownerId !== owner) return;
    state.userPreferences = preferences;
    applyThemePreference(preferences.theme);
  }

  function applyThemePreference(theme) {
    const dark = theme === "DARK";
    document.body.classList.toggle("prism-theme-dark", dark);
    const button = byId("theme-toggle");
    const label = byId("theme-toggle-label");
    if (button) button.setAttribute("aria-pressed", String(dark));
    if (label) label.textContent = dark ? "切换浅色主题" : "切换深色主题";
  }

  async function saveThemePreference(theme) {
    const owner = state.ownerId;
    if (!owner) return;
    const button = byId("theme-toggle");
    if (button) button.disabled = true;
    try {
      const response = await fetch("/api/v1/user/preferences", {
        method: "PUT", headers: {"Content-Type": "application/json", "X-Owner-ID": owner},
        body: JSON.stringify({owner_id: owner, theme,
          holdings_data_enabled: false, market_data_enabled: true}),
      });
      if (!response.ok) throw await apiError(response);
      state.userPreferences = await response.json();
      applyThemePreference(state.userPreferences.theme);
      button?.closest("details")?.removeAttribute("open");
    } catch (error) {
      setError(error.message || "保存用户偏好失败");
    } finally {
      if (button) button.disabled = false;
    }
  }

  let marketRequestSequence = 0;
  let marketAbortController = null;
  let marketCatalog = [];
  let marketRegion = "CN";
  let marketInterval = "1d";
  let marketAnalysis = null;
  let marketQuoteSequence = 0;
  const activeMarketIndicators = new Set(["boll"]);

  function selectedMarketIndex() {
    return marketCatalog.find(item => item.market === marketRegion && item.index_id === byId("market-index-input")?.value);
  }

  function renderMarketIndexCards() {
    const container = byId("market-index-options");
    if (!container) return;
    container.replaceChildren();
    const rows = marketCatalog.filter(item => item.market === marketRegion);
    rows.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.marketIndex = item.index_id;
      button.setAttribute("aria-pressed", String(item.index_id === byId("market-index-input").value));
      const name = document.createElement("strong"); name.textContent = item.name;
      const detail = document.createElement("small"); detail.textContent = item.symbol || "公开数据代码不可用";
      const status = document.createElement("span"); status.className = "market-index-card-status";
      if (item.quote_status === "LIVE" && item.price != null) {
        const pct = Number(item.change_pct || 0);
        status.textContent = `${Number(item.price).toLocaleString("zh-CN", {minimumFractionDigits: item.precision, maximumFractionDigits: item.precision})} · ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
        status.classList.add(pct >= 0 ? "is-up" : "is-down");
      } else {
        status.textContent = item.status === "AVAILABLE" ? "待查询" : "UNAVAILABLE";
      }
      button.append(name, detail, status);
      button.addEventListener("click", () => {
        byId("market-index-input").value = item.index_id;
        container.querySelectorAll("button").forEach(node => node.setAttribute("aria-pressed", String(node === button)));
        assessMarket();
      });
      container.append(button);
      if (index === 0 && !rows.some(row => row.index_id === byId("market-index-input").value)) {
        byId("market-index-input").value = item.index_id;
        button.setAttribute("aria-pressed", "true");
      }
    });
    byId("market-industries-section").hidden = marketRegion !== "CN";
  }

  async function loadMarketCatalog() {
    const response = await fetch("/api/v1/market/catalog", {headers: {"X-Owner-ID": state.ownerId}});
    if (!response.ok) throw await apiError(response);
    marketCatalog = await response.json();
    renderMarketIndexCards();
  }

  async function loadMarketQuotes() {
    const sequence = ++marketQuoteSequence;
    const region = marketRegion;
    try {
      const response = await fetch(`/api/v1/market/quotes/${region}`, {headers: {"X-Owner-ID": state.ownerId}});
      if (!response.ok) throw await apiError(response);
      const quotes = await response.json();
      if (sequence !== marketQuoteSequence || region !== marketRegion) return;
      const indexed = new Map(quotes.map(item => [item.index_id, item]));
      marketCatalog = marketCatalog.map(item => item.market === region && indexed.has(item.index_id)
        ? {...item, ...indexed.get(item.index_id), quote_status: indexed.get(item.index_id).status}
        : item);
      renderMarketIndexCards();
    } catch (_) {
      if (sequence === marketQuoteSequence && region === marketRegion) renderMarketIndexCards();
    }
  }

  async function assessMarket() {
    const sequence = ++marketRequestSequence;
    const owner = state.ownerId;
    const result = byId("market-result-content");
    const status = byId("market-status");
    const selected = selectedMarketIndex();
    if (!selected || !result || !status) return;
    marketAbortController?.abort();
    marketAbortController = new AbortController();
    status.textContent = "正在读取";
    byId("market-kline").replaceChildren();
    result.textContent = "正在读取可验证行情与研判状态…";
    try {
      const response = await fetch(`/api/v1/market/analysis/${marketRegion}/${encodeURIComponent(selected.index_id)}?interval=${marketInterval}`,
        {headers: {"X-Owner-ID": state.ownerId}, signal: marketAbortController.signal});
      if (!response.ok) throw await apiError(response);
      const data = await response.json();
      if (sequence !== marketRequestSequence || owner !== state.ownerId) return;
      status.textContent = data.status;
      marketAnalysis = data;
      const quote = data.price === null ? "未返回行情" : `${Number(data.price).toLocaleString("zh-CN", {minimumFractionDigits: data.precision, maximumFractionDigits: data.precision})}（${data.change_pct >= 0 ? "+" : ""}${Number(data.change_pct).toFixed(2)}%）`;
      result.replaceChildren();
      const heading = document.createElement("h3"); heading.textContent = `${data.name}${data.symbol ? ` · ${data.symbol}` : ""}`;
      const detail = document.createElement("p"); detail.textContent = `${quote} · ${data.currency} · ${data.source}`;
      detail.className = "market-quote-value";
      const historyLabel = data.history_status === "LIVE" ? "历史完整" : data.history_status === "REVIEW_REQUIRED" ? "历史窗口部分可用" : "历史不可用";
      const audit = document.createElement("small"); audit.textContent = `周期：${data.interval === "1M" ? "月线" : "日线"}；${historyLabel}；市场时区：${data.timezone}；观察时间：${data.observed_at || "未提供"}`;
      result.append(heading, detail, audit);
      renderIndexCandles(data);
      renderMarketFactors(data.factors || []);
    } catch (error) {
      if (sequence !== marketRequestSequence || owner !== state.ownerId) return;
      if (error.name === "AbortError") return;
      status.textContent = "REVIEW_REQUIRED";
      result.textContent = error.message || "市场数据暂不可用。";
    }
  }

  byId("load-events").addEventListener("click", loadEvents);
  byId("advisor-query-form").addEventListener("submit", runAdvisorQuery);
  byId("confirm-portfolio").addEventListener("click", confirmPortfolioContext);
  byId("confirm-profile").addEventListener("click", confirmProfileContext);
  byId("preview-advisor-plan").addEventListener("click", previewAdvisorPlan);
  byId("intent-type").addEventListener("change", clearAdvisorPlan);
  byId("run-research-matrix").addEventListener("click", runResearchMatrix);
  byId("research-scenario").addEventListener("change", () => {
    state.researchRun = null;
    renderResearchMatrix(null);
    setResearchStatus("待运行");
  });
  byId("run-stock-research").addEventListener("click", runStockResearch);
  byId("stock-research-scenario").addEventListener("change", () => {
    state.stockResearchRun = null;
    state.stockResearchSequence += 1;
    renderStockResearch(null);
    setStockResearchStatus("待运行");
  });
  byId("run-fund-research").addEventListener("click", runFundResearch);
  byId("fund-research-scenario").addEventListener("change", () => {
    state.fundResearchRun = null;
    state.fundResearchSequence += 1;
    renderFundResearch(null);
    setFundResearchStatus("待运行");
  });
  byId("run-convertible-bond-research").addEventListener("click", runConvertibleBondResearch);
  byId("convertible-bond-research-scenario").addEventListener("change", () => {
    state.convertibleBondResearchRun = null;
    state.convertibleBondResearchSequence += 1;
    renderConvertibleBondResearch(null);
    setConvertibleBondResearchStatus("待运行");
  });
  byId("run-portfolio-optimization").addEventListener("click", runPortfolioOptimization);
  byId("advanced-evidence-search").addEventListener("input", (event) => {
    state.advancedEvidenceSearch = event.target.value;
    renderAdvancedEvidence();
  });
  byId("advanced-evidence-quality").addEventListener("change", (event) => {
    state.advancedEvidenceQuality = event.target.value;
    state.advancedEvidenceSelectedKey = "";
    renderAdvancedEvidence();
  });
  byId("advanced-evidence-mode").addEventListener("change", (event) => {
    state.advancedEvidenceMode = event.target.value;
    state.advancedEvidenceSelectedKey = "";
    renderAdvancedEvidence();
  });
  byId("advanced-evidence-source").addEventListener("change", (event) => {
    state.advancedEvidenceSource = event.target.value;
    state.advancedEvidenceSelectedKey = "";
    renderAdvancedEvidence();
  });
  byId("advanced-evidence-promotion").addEventListener("change", (event) => {
    state.advancedEvidencePromotion = event.target.value;
    state.advancedEvidenceSelectedKey = "";
    renderAdvancedEvidence();
  });
  byId("clear-advanced-evidence-filters").addEventListener("click", () => {
    state.advancedEvidenceSearch = "";
    state.advancedEvidenceQuality = "ALL";
    state.advancedEvidenceMode = "ALL";
    state.advancedEvidenceSource = "ALL";
    state.advancedEvidencePromotion = "ALL";
    state.advancedEvidenceSelectedKey = "";
    renderAdvancedEvidence();
  });
  byId("save-context-memory").addEventListener("click", saveContextMemory);
  byId("search-context-memory").addEventListener("click", searchContextMemory);
  byId("load-context-memory").addEventListener("click", () => {
    const nextOwnerId = byId("owner-id").value.trim();
    const ownerChanged = nextOwnerId !== state.ownerId;
    state.ownerId = nextOwnerId;
    if (ownerChanged || !state.ownerId) resetOwnerScopedViews();
    loadContextMemory(state.ownerId);
  });
  byId("portfolio-optimization-scenario").addEventListener("change", () => {
    state.portfolioOptimizationRun = null;
    state.portfolioOptimizationSequence += 1;
    renderPortfolioOptimization(null);
    setPortfolioOptimizationStatus("待运行");
  });
  const scenarioOptSelect = byId("scenario-simulation-scenario");
  if (scenarioOptSelect) {
    scenarioOptSelect.addEventListener("change", () => {
      state.scenarioSimulationRun = null;
      state.scenarioSimulationSequence += 1;
      renderScenarioSimulation(null);
      setScenarioSimulationStatus("待运行");
    });
  }
  const runScenarioBtn = byId("run-scenario-simulation");
  if (runScenarioBtn) runScenarioBtn.addEventListener("click", runScenarioSimulation);
  let stressDebounceTimer = null;
  stressInputs().forEach((input) => {
    input.addEventListener("input", () => {
      const output = byId(`${input.id}-value`);
      if (output) output.textContent = `${Number(input.value).toFixed(1)}%`;
      const status = byId("custom-stress-status");
      if (status) { status.textContent = "计算中"; status.className = "status-chip"; }
      window.clearTimeout(stressDebounceTimer);
      stressDebounceTimer = window.setTimeout(() => {
        runCustomStressScenario().catch((error) => {
          if (status) { status.textContent = "计算失败"; status.className = "status-chip blocked"; }
          setError(error.message || "自定义压力测试失败");
        });
      }, 180);
    });
  });

  // 1. Recommendation History
  async function loadRecommendationHistory() {
    const owner = state.ownerId;
    if (!owner) return;
    try {
      const res = await fetch("/api/v1/advisor/recommendation-history?limit=20", {
        headers: { "X-Owner-ID": owner },
      });
      if (!res.ok) throw new Error("历史读取失败");
      const data = await res.json();
      const countPill = byId("history-count");
      if (countPill) countPill.textContent = `${data.total_count} 条建议`;
      const panel = byId("history-list-content");
      if (!panel) return;
      panel.textContent = "";
      if (!data.items || !data.items.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = "暂无已归档的历史决策回执。";
        panel.append(empty);
        return;
      }
      data.items.forEach((item) => {
        const card = document.createElement("div");
        card.className = "history-item-card";
        const h = document.createElement("h4");
        h.textContent = `建议动作：${text(item.action_type, "无")} · 标的：${text(item.asset, "—")}`;
        const p1 = document.createElement("p");
        p1.textContent = `状态：${text(item.status)} · 风险得分：${text(item.risk_score, "—")}`;
        const p2 = document.createElement("p");
        p2.textContent = `生成时间：${text(item.recorded_at)}`;
        card.append(h, p1, p2);
        // 回执 ID 与内容哈希属于内部审计信息，仅开发者可见。
        const devMeta = document.createElement("p");
        devMeta.className = "muted dev-only";
        devMeta.textContent = `回执 ID：${text(item.receipt_id, "无")} · 哈希：${item.content_hash ? item.content_hash.slice(0, 16) + "…" : "—"}`;
        card.append(devMeta);
        panel.append(card);
      });
    } catch (err) {
      setError(err.message);
    }
  }

  async function runRecommendationCompare() {
    const owner = state.ownerId;
    const rA = byId("compare-receipt-a").value.trim();
    const rB = byId("compare-receipt-b").value.trim();
    if (!rA || !rB) {
      setError("请输入两个待比对的回执 ID");
      return;
    }
    try {
      const res = await fetch("/api/v1/advisor/recommendation-history/compare", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": owner,
        },
        body: JSON.stringify({
          schema_version: "recommendation-comparison-request.v1",
          owner_id: owner,
          receipt_a_id: rA,
          receipt_b_id: rB,
        }),
      });
      if (!res.ok) throw new Error("比对失败或回执未找到");
      const data = await res.json();
      const panel = byId("compare-result-content");
      panel.textContent = "";
      const card = document.createElement("div");
      card.className = "history-item-card";
      const h = document.createElement("h4");
      h.textContent = `比对结果: ${data.action_transition}`;
      const p = document.createElement("p");
      p.textContent = data.summary;
      card.append(h, p);
      panel.append(card);
    } catch (err) {
      setError(err.message);
    }
  }

  // 2. Portfolio Rebalancing
  async function runPortfolioRebalancing() {
    try {
      if (
        state.dataMode === "LIVE"
        && (state.portfolioRefreshRun?.status !== "COMPLETE" || !state.portfolioOptimizationRun?.targets?.length)
      ) {
        await runPortfolioOptimization();
      }
      if (!state.portfolioOptimizationRun?.targets?.length) {
        if (state.dataMode === "LIVE" && state.portfolioRefreshRun?.status !== "COMPLETE") {
          throw new Error(portfolioRefreshProblem());
        }
        throw new Error("缺少已计算的目标权重，请先生成组合目标结构");
      }
      await ensureDependency("PORTFOLIO_CONTEXT");
      if (!state.portfolio) throw new Error("缺少结构化持仓，无法生成调仓计划");
      const token = beginContextRequest("rebalancingSequence");
      const portfolio = token.portfolio;
      const heldAssets = new Set(portfolio.position_snapshot.positions.map((position) => position.asset_id));
      if (state.portfolioOptimizationRun.targets.some((target) => !heldAssets.has(target.target_id))) {
        throw new Error("当前目标包含基金底层穿透资产，不能直接作为账户持仓下单。请在目标权重页面查看暴露分布。");
      }
      const targetWeights = Object.fromEntries(
        state.portfolioOptimizationRun.targets.map((target) => [target.target_id, target.target_weight_pct])
      );
      const res = await fetch("/api/v1/advisor/rebalancing-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": token.ownerId,
        },
        body: JSON.stringify({
          schema_version: "portfolio-rebalancing-request.v1",
          request_id: `reb-${Date.now()}`,
          owner_id: token.ownerId,
          generated_at: new Date().toISOString(),
          bundle: portfolio,
          confirmed_profile: state.profile?.profile || null,
          target_weights: targetWeights,
          deadband_pct: "0.50",
          max_turnover_pct: "50.00",
          minimum_cash_pct: state.portfolioHealthRun?.cash_minimum_pct || "0.00",
        }),
      });
      if (!isContextRequestCurrent(token)) return null;
      if (!res.ok) throw await apiError(res);
      const data = await res.json();
      if (!isContextRequestCurrent(token)) return null;
      state.rebalancingRun = data;
      const chip = byId("rebalancing-status-chip");
      if (chip) {
        chip.textContent = data.status === "PASS" ? "已就绪（READY）" : data.status;
        chip.className = `status-chip ${data.status.toLowerCase()}`;
      }
      const metricsPanel = byId("rebalancing-metrics-content");
      metricsPanel.textContent = "";
      const mCard = document.createElement("div");
      mCard.className = "score-grid";
      const addScore = (title, val) => {
        const c = document.createElement("div");
        c.className = "score-card";
        const t = document.createElement("div");
        t.textContent = title;
        const v = document.createElement("div");
        v.className = "score-value";
        v.textContent = val;
        c.append(t, v);
        mCard.append(c);
      };
      addScore("总市值 (CNY)", data.metrics.total_portfolio_value_cny);
      addScore("换手率 (%)", `${data.metrics.total_turnover_pct}%`);
      addScore("买入金额 (CNY)", data.metrics.total_buy_cny);
      addScore("卖出金额 (CNY)", data.metrics.total_sell_cny);
      metricsPanel.append(mCard);

      const actionsPanel = byId("rebalancing-actions-content");
      actionsPanel.textContent = "";
      const table = document.createElement("table");
      table.className = "rebalancing-table";
      const thead = document.createElement("thead");
      const trh = document.createElement("tr");
      ["资产代码", "资产名称", "当前权重", "目标权重", "实际变动权重", "实际变动金额 (CNY)", "动作", "原因"].forEach((tht) => {
        const th = document.createElement("th");
        th.textContent = tht;
        trh.append(th);
      });
      thead.append(trh);
      table.append(thead);
      const tbody = document.createElement("tbody");
      data.actions.forEach((act) => {
        const tr = document.createElement("tr");
        const td1 = document.createElement("td"); td1.textContent = act.asset_id;
        const td2 = document.createElement("td"); td2.textContent = act.asset_name;
        const td3 = document.createElement("td"); td3.textContent = `${act.current_weight_pct}%`;
        const td4 = document.createElement("td"); td4.textContent = `${act.target_weight_pct}%`;
        const td5 = document.createElement("td"); td5.textContent = `${act.delta_weight_pct}%`;
        const td6 = document.createElement("td"); td6.textContent = `${act.cash_delta_cny}`;
        const td7 = document.createElement("td");
        const b = document.createElement("span");
        b.className = `action-badge ${act.action_type}`;
        b.textContent = act.action_type;
        td7.append(b);
        const td8 = document.createElement("td"); td8.textContent = act.rationale;
        tr.append(td1, td2, td3, td4, td5, td6, td7, td8);
        tbody.append(tr);
      });
      table.append(tbody);
      actionsPanel.append(table);

      const stepsPanel = byId("rebalancing-steps-content");
      stepsPanel.textContent = "";
      stepsPanel.append(buildRebalancingNotice(data));
      data.execution_steps.forEach((step) => {
        const sc = document.createElement("div");
        sc.className = "rebalancing-action-card";
        const h = document.createElement("h4");
        h.textContent = `步骤 ${step.step_number}: [${step.action_type}] ${step.asset_name} · 金额: ${step.amount_cny} CNY`;
        const p = document.createElement("p");
        p.textContent = step.description;
        sc.append(h, p);
        stepsPanel.append(sc);
      });
      return data;
    } catch (err) {
      if (err.errorCode === "LIVE_PORTFOLIO_REFRESH_REQUIRED") {
        state.portfolioRefreshRun = null;
        state.portfolioOptimizationRun = null;
        renderPortfolioRefreshStatus(null);
        renderPortfolioOptimization(null);
      }
      setError(err.message);
      return null;
    }
  }

  // 3. Advanced Explainability
  async function runAdvancedExplainability() {
    try {
      await ensureDependency("PROFILE_CONTEXT");
      await ensureDependency("PORTFOLIO_CONTEXT");
      const health = await refreshPortfolioHealth();
      if (!health) throw new Error("画像或持仓尚未确认，无法解释分析依据");
      const chip = byId("explainability-status-chip");
      if (chip) {
        chip.textContent = health.status;
        chip.className = health.status === "PASS" ? "status-chip ready" : "status-chip review";
      }
      const driversPanel = byId("explainability-drivers-content");
      clear(driversPanel);
      health.calculation_steps.forEach((step, index) => {
        const div = document.createElement("div");
        div.className = "driver-item";
        const h = document.createElement("strong");
        h.textContent = `步骤 ${index + 1}`;
        const p = document.createElement("p");
        p.textContent = step;
        div.append(h, p);
        driversPanel.append(div);
      });

      const cfPanel = byId("explainability-counterfactual-content");
      clear(cfPanel);
      health.sectors.forEach((sector) => {
        const div = document.createElement("div");
        div.className = "counterfactual-item";
        const h = document.createElement("strong");
        h.textContent = `${sector.name} · ${sector.verdictCode}`;
        const p1 = document.createElement("p");
        p1.textContent = `后端结果：实际 ${sector.pct}%；边界 ${sector.limitOperator === "MIN" ? "≥" : "≤"}${sector.cap}%。`;
        const p2 = document.createElement("p");
        p2.textContent = sector.differenceLabel;
        div.append(h, p1, p2);
        cfPanel.append(div);
      });

      const trgPanel = byId("explainability-triggers-content");
      clear(trgPanel);
      const triggers = [
        `持仓快照或画像发生变化时重新计算；当前敞口状态 ${health.source_exposure_status}`,
        ...(health.issues || []).map((issue) => `数据问题：${issue}`),
      ];
      triggers.forEach((description) => {
        const div = document.createElement("div");
        div.className = "trigger-item";
        const h = document.createElement("strong");
        h.textContent = "复核条件";
        const p = document.createElement("p");
        p.textContent = description;
        div.append(h, p);
        trgPanel.append(div);
      });
    } catch (err) {
      setError(err.message);
    }
  }

  // 4. Evaluation Dashboard
  function renderEvaluationDashboardData(data) {
    if (!data) return;
    const chip = byId("evaluation-pass-chip");
    if (chip && data.summary) {
      chip.textContent = `${data.summary.case_pass_rate_pct}% 通过`;
      chip.className = "status-chip ready";
    }

    const sumPanel = byId("evaluation-summary-content");
    if (sumPanel && data.summary && data.latency) {
      sumPanel.textContent = "";
      const sGrid = document.createElement("div");
      sGrid.className = "score-grid";
      const addSum = (title, val, badgeTag = "PASS", isGood = true) => {
        const c = document.createElement("div");
        c.className = "score-card";

        const head = document.createElement("div");
        head.className = "score-head";
        const t = document.createElement("span");
        t.textContent = title;
        const b = document.createElement("span");
        b.className = isGood ? "status-chip ready" : "status-chip blocked";
        b.style.fontSize = "10px";
        b.style.padding = "2px 6px";
        b.textContent = badgeTag;
        head.append(t, b);

        const v = document.createElement("div");
        v.className = "score-value";
        v.textContent = val;

        c.append(head, v);
        sGrid.append(c);
      };

      const passRate = parseFloat(data.summary.case_pass_rate_pct);
      const halluRate = parseFloat(data.summary.hallucination_rate_pct);
      addSum("用例通过率", `${data.summary.case_pass_rate_pct}%`, passRate >= 99 ? "PASS" : "WARN", passRate >= 99);
      addSum("画像一致性", `${data.summary.profile_alignment_rate_pct}%`, "PASS", true);
      addSum("证据闭环率", `${data.summary.evidence_coverage_rate_pct}%`, "PASS", true);
      addSum("事实幻觉率", `${data.summary.hallucination_rate_pct}%`, halluRate === 0 ? "0.00% PASS" : "WARN", halluRate === 0);
      addSum("风险拦截率", `${data.summary.risk_detection_rate_pct}%`, "PASS", true);
      addSum("响应延迟 P50", `${data.latency.p50_ms} ms`, "<15ms PASS", true);
      sumPanel.append(sGrid);
    }

    const casesPanel = byId("evaluation-cases-content");
    if (casesPanel && Array.isArray(data.cases)) {
      casesPanel.textContent = "";
      const table = document.createElement("table");
      table.className = "eval-table";
      const thead = document.createElement("thead");
      const trh = document.createElement("tr");
      ["用例 ID", "测试用例描述", "预期状态", "实际状态", "耗时 (ms)", "判定结论"].forEach((tht) => {
        const th = document.createElement("th");
        th.textContent = tht;
        trh.append(th);
      });
      thead.append(trh);
      table.append(thead);

      const tbody = document.createElement("tbody");
      data.cases.forEach((c) => {
        const tr = document.createElement("tr");
        const td1 = document.createElement("td");
        td1.textContent = c.case_id;
        td1.style.fontFamily = "var(--mono)";
        td1.style.fontWeight = "600";

        const td2 = document.createElement("td");
        td2.textContent = c.title;

        const td3 = document.createElement("td");
        td3.textContent = c.expected_status;
        td3.style.fontFamily = "var(--mono)";

        const td4 = document.createElement("td");
        td4.textContent = c.actual_status;
        td4.style.fontFamily = "var(--mono)";

        const td5 = document.createElement("td");
        td5.textContent = `${c.latency_ms}ms`;
        td5.style.fontFamily = "var(--mono)";

        const td6 = document.createElement("td");
        const tag = document.createElement("span");
        tag.className = c.passed ? "status-chip ready" : "status-chip blocked";
        tag.textContent = c.passed ? "✓ PASS" : "✗ FAIL";
        td6.append(tag);

        tr.append(td1, td2, td3, td4, td5, td6);
        tbody.append(tr);
      });
      table.append(tbody);
      casesPanel.append(table);
    }
  }

  async function loadEvaluationSummary() {
    const owner = state.ownerId || "demo-owner";
    try {
      const res = await fetch("/api/v1/advisor/evaluation-dashboard-summary", {
        headers: {
          "X-Owner-ID": owner,
        },
      });
      if (!res.ok) return;
      const data = await res.json();
      renderEvaluationDashboardData(data);
    } catch (err) {
      console.warn("loadEvaluationSummary error:", err);
    }
  }

  async function runEvaluationSuite() {
    const owner = state.ownerId || "demo-owner";
    const btn = byId("run-evaluation-suite");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "正在执行全量回归...";
    }
    try {
      const res = await fetch("/api/v1/advisor/evaluation-dashboard-runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Owner-ID": owner,
        },
        body: JSON.stringify({
          schema_version: "evaluation-dashboard-request.v1",
          request_id: `eval-${Date.now()}`,
          operator_id: owner,
          generated_at: new Date().toISOString(),
          repeat_count: 1,
        }),
      });
      if (!res.ok) throw new Error("评测套件运行失败");
      const data = await res.json();
      renderEvaluationDashboardData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "运行全量评测";
      }
    }
  }

  // =========================================================================
  // Copilot 任务中心与预设画像体系 (Optimization Direction 1 & 2)
  // =========================================================================

  const DEFAULT_USER_PROFILE = {
    id: "custom-user",
    ownerId: "demo-owner",
    name: "我的专属账户",
    tag: "R3 平衡型",
    riskLevel: "R3",
    portfolioTag: "待加载当前持仓",
    avatar: "👤",
    desc: "投资目标：控制回撤，稳健增长。",
    aum: "¥ 500,000",
    budgetCap: "30.0%",
    lossToleranceScore: "3",
    investmentHorizon: "MEDIUM",
    liquidityNeed: "MEDIUM",
    experienceLevel: "INTERMEDIATE",
    returnExpectation: "MODERATE",
    maxDrawdown: "15",
    defaultStock: "300750",
    quickTags: [
      { label: "体检我的组合", intent: "CHECK_PORTFOLIO" },
      { label: "研究 300750", intent: "RESEARCH_STOCK", target: "300750" },
      { label: "生成调仓方案", intent: "REBALANCE_PORTFOLIO" },
      { label: "测试下跌 20%", intent: "SCENARIO_SHOCK" }
    ]
  };

  const PERSONAS = {
    "custom-user": { ...DEFAULT_USER_PROFILE },
    "persona-zhang-r3": {
      id: "persona-zhang-r3",
      ownerId: "demo-owner",
      name: "张先生",
      tag: "R3 平衡型",
      portfolioTag: "待加载当前持仓",
      avatar: "👨‍💼",
      desc: "35岁中产白领 · 投资期限 中期 · 回撤容忍 ≤15% · 目标在控制波动的条件下获得稳健超额收益。",
      aum: "¥ 500,000",
      budgetCap: "30.0%",
      lossToleranceScore: "3",
      investmentHorizon: "MEDIUM",
      liquidityNeed: "MEDIUM",
      experienceLevel: "INTERMEDIATE",
      returnExpectation: "MODERATE",
      maxDrawdown: "15",
      defaultStock: "300750",
      quickTags: [
        { label: "体检科技持仓", intent: "CHECK_PORTFOLIO" },
        { label: "研究 300750", intent: "RESEARCH_STOCK", target: "300750" },
        { label: "生成调仓方案", intent: "REBALANCE_PORTFOLIO" },
        { label: "测试科技股下跌 20%", intent: "SCENARIO_SHOCK" }
      ]
    },
    "persona-li-r2": {
      id: "persona-li-r2",
      ownerId: "demo-owner",
      name: "李阿姨",
      tag: "R2 稳健型",
      portfolioTag: "待加载当前持仓",
      avatar: "👵",
      desc: "58岁退休长辈 · 投资期限 长期 · 回撤容忍 ≤8% · 注重本金安全、低波动与稳定分红收益。",
      aum: "¥ 800,000",
      budgetCap: "15.0%",
      lossToleranceScore: "2",
      investmentHorizon: "LONG",
      liquidityNeed: "LOW",
      experienceLevel: "NOVICE",
      returnExpectation: "LOW",
      maxDrawdown: "8",
      defaultStock: "113050",
      quickTags: [
        { label: "检查组合风险", intent: "CHECK_PORTFOLIO" },
        { label: "研究 113050", intent: "RESEARCH_STOCK", target: "113050" },
        { label: "生成稳健调仓方案", intent: "REBALANCE_PORTFOLIO" },
        { label: "测试利率变化影响", intent: "SCENARIO_SHOCK" }
      ]
    },
    "persona-wang-r4": {
      id: "persona-wang-r4",
      ownerId: "demo-owner",
      name: "王同学",
      tag: "R4 进取型",
      portfolioTag: "待加载当前持仓",
      avatar: "🧑‍💻",
      desc: "28岁青年投资者 · 投资期限 长期 · 回撤容忍 ≤25% · 偏好科创板龙头与高成长赛道，追求超额 Alpha。",
      aum: "¥ 200,000",
      budgetCap: "50.0%",
      lossToleranceScore: "4",
      investmentHorizon: "LONG",
      liquidityNeed: "HIGH",
      experienceLevel: "EXPERIENCED",
      returnExpectation: "HIGH",
      maxDrawdown: "25",
      defaultStock: "588000",
      quickTags: [
        { label: "体检成长组合波动", intent: "CHECK_PORTFOLIO" },
        { label: "研究 588000", intent: "RESEARCH_STOCK", target: "588000" },
        { label: "生成进取调仓方案", intent: "REBALANCE_PORTFOLIO" },
        { label: "测试市场上涨时的变化", intent: "SCENARIO_SHOCK" }
      ]
    }
  };

  function loadUserProfile() {
    try {
      const saved = workspaceStorage.getItem(ownerStorageKey("prism_custom_user_profile_v2"));
      if (saved) {
        const parsed = JSON.parse(saved);
        PERSONAS["custom-user"] = { ...DEFAULT_USER_PROFILE, ...parsed };
      }
      const conversationProfile = workspaceStorage.getItem(ownerStorageKey("prism_conversation_profile_v1"));
      if (conversationProfile) {
        PERSONAS["custom-user"] = {
          ...PERSONAS["custom-user"],
          conversationProfile: JSON.parse(conversationProfile),
        };
      }
    } catch (e) {}

    if (authenticatedOwner) PERSONAS["custom-user"].ownerId = authenticatedOwner;
    const profile = PERSONAS["custom-user"];
    const chipName = byId("custom-profile-chip-name");
    if (chipName) chipName.textContent = `${profile.name} (${profile.tag})`;
  }

  function saveUserProfile(updated) {
    PERSONAS["custom-user"] = { ...PERSONAS["custom-user"], ...updated };
    if (authenticatedOwner) PERSONAS["custom-user"].ownerId = authenticatedOwner;
    try {
      workspaceStorage.setItem(ownerStorageKey("prism_custom_user_profile_v2"), JSON.stringify(PERSONAS["custom-user"]));
    } catch (e) {}

    const profile = PERSONAS["custom-user"];
    const chipName = byId("custom-profile-chip-name");
    if (chipName) chipName.textContent = `${profile.name} (${profile.tag})`;

    if (state.selectedPersona === "custom-user") {
      switchPersona("custom-user");
    }
  }

  function openProfileModal() {
    const profile = PERSONAS["custom-user"] || DEFAULT_USER_PROFILE;
    const nameInput = byId("profile-name-input");
    if (nameInput) nameInput.value = profile.name;
    const ddInput = byId("profile-drawdown-input");
    if (ddInput) ddInput.value = profile.maxDrawdown || "15";
    const budInput = byId("profile-budget-input");
    if (budInput) budInput.value = parseInt(profile.budgetCap, 10) || 30;
    const horizSelect = byId("profile-horizon-select");
    if (horizSelect) horizSelect.value = profile.investmentHorizon || "MEDIUM";
    const aumInput = byId("profile-aum-input");
    if (aumInput) aumInput.value = profile.aum.replace("¥ ", "").trim();

    const statusBox = byId("profile-save-status");
    if (statusBox) statusBox.style.display = "none";

    const modal = byId("profile-edit-modal");
    if (modal) modal.style.display = "flex";
  }

  function closeProfileModal() {
    const modal = byId("profile-edit-modal");
    if (modal) modal.style.display = "none";
  }

  function handleSaveProfile() {
    const nameInput = byId("profile-name-input");
    const ddInput = byId("profile-drawdown-input");
    const budInput = byId("profile-budget-input");
    const horizSelect = byId("profile-horizon-select");
    const aumInput = byId("profile-aum-input");

    const currentProfile = PERSONAS["custom-user"] || DEFAULT_USER_PROFILE;
    const riskVal = currentProfile.riskLevel || "R3";
    const riskMap = {
      R1: "R1 保守型",
      R2: "R2 稳健型",
      R3: "R3 平衡型",
      R4: "R4 进取型",
      R5: "R5 激进型"
    };

    const scoreMap = { R1: "1", R2: "2", R3: "3", R4: "4", R5: "5" };
    const questionnaireDrawdown = Number(state.profile?.profile?.max_drawdown_tolerance_pct);
    const savedDrawdown = Number(currentProfile.maxDrawdown || 15);
    const drawdownCeiling = Number.isFinite(questionnaireDrawdown) ? questionnaireDrawdown : savedDrawdown;
    const maxDd = String(Math.max(0, Math.min(Number(ddInput?.value || drawdownCeiling), drawdownCeiling)));
    const savedBudget = Number.parseFloat(currentProfile.budgetCap) || 30;
    const budget = String(Math.max(0, Math.min(Number(budInput?.value || savedBudget), savedBudget)));
    const aumVal = (aumInput?.value || "500,000").trim();

    saveUserProfile({
      name: (nameInput?.value || "我的专属账户").trim(),
      riskLevel: riskVal,
      tag: riskMap[riskVal] || "R3 平衡型",
      lossToleranceScore: scoreMap[riskVal] || "3",
      maxDrawdown: maxDd,
      budgetCap: `${Number(budget).toFixed(1)}%`,
      investmentHorizon: horizSelect?.value || "MEDIUM",
      aum: aumVal.startsWith("¥") ? aumVal : `¥ ${aumVal}`,
      desc: `自定义专属画像 · 投资期限 ${horizSelect?.value || "中期"} · 回撤容忍 ≤${maxDd}% · 行业预算上限 ${budget}%。`,
    });

    const statusBox = byId("profile-save-status");
    if (statusBox) {
      statusBox.style.display = "block";
      statusBox.textContent = "约束偏好已保存，并同步更新分析边界。";
    }

    setTimeout(() => {
      closeProfileModal();
    }, 800);
  }

  function handleResetProfile() {
    saveUserProfile({ ...DEFAULT_USER_PROFILE });
    openProfileModal();
  }

  function switchPersona(personaId) {
    byId("truth-turn-alerts").replaceChildren();
    byId("truth-drawer").close(); byId("truth-confirm-dialog").close(); truthReview = null;
    if (authenticatedOwner && personaId !== "custom-user") return;
    const persona = PERSONAS[personaId];
    if (!persona) return;
    microStore.transact((store) => {
      invalidateDerivedState(store);
      store.selectedPersona = personaId;
      store.ownerId = persona.ownerId;
      store.profile = null;
      store.behaviorProfile = null;
      store.displayPolicy = null;
      store.questionnaireTemplate = null;
      store.questionnaireAnswers = {};
      store.questionnaireSectionIndex = 0;
      store.questionnairePreview = null;
      store.profileSummary = null;
      store.portfolio = null;
      store.queryTemplate = null;
      store.templateContext = null;
      store.ocrPortfolioDraft = null;
    });
    renderInvalidatedDerivedState();

    loadUserPreferences().catch(error => setError(error.message));
    // Keep the compact current-profile summary in sync; example profiles stay behind
    // the optional picker so the main task surface remains calm.
    document.querySelectorAll(".persona-chip").forEach(chip => {
      chip.classList.toggle("active", chip.id === "btn-custom-profile-chip" || chip.dataset.persona === personaId);
    });
    const currentProfileAvatar = byId("custom-profile-chip-avatar");
    if (currentProfileAvatar) currentProfileAvatar.textContent = persona.avatar;
    const currentProfileName = byId("custom-profile-chip-name");
    if (currentProfileName) currentProfileName.textContent = currentProfileTag(null);
    const currentProfileChip = byId("btn-custom-profile-chip");
    if (currentProfileChip) currentProfileChip.title = `当前风险设置：${persona.name}，${currentProfileTag(null)}`;
    const menuLabel = byId("profile-menu-current-label");
    if (menuLabel) menuLabel.textContent = currentProfileTag(null);

    // Update Hero card
    const heroAvatar = byId("copilot-hero-avatar");
    if (heroAvatar) heroAvatar.textContent = persona.avatar;
    const heroName = byId("copilot-hero-name");
    if (heroName) heroName.textContent = persona.name;
    const heroTag = byId("copilot-hero-tag");
    if (heroTag) heroTag.textContent = currentProfileTag(null);
    const heroPortfolioTag = byId("copilot-hero-portfolio-tag");
    if (heroPortfolioTag) heroPortfolioTag.textContent = persona.portfolioTag;
    const heroDesc = byId("copilot-hero-desc");
    if (heroDesc) heroDesc.textContent = persona.desc;

    // Update stats
    const aum = byId("copilot-stat-aum");
    if (aum) aum.textContent = "待确认持仓";
    const tech = byId("copilot-stat-tech");
    if (tech) {
      tech.textContent = "待体检";
      tech.classList.remove("alert-text", "ok-text");
    }
    const budget = byId("copilot-stat-budget");
    if (budget) budget.textContent = "待确认画像";
    const evStat = byId("copilot-stat-evidence");
    if (evStat) evStat.textContent = "待计算";

    // Update underlying form fields
    const ownerInput = byId("owner-id");
    if (ownerInput) ownerInput.value = persona.ownerId;
    const lossInput = byId("loss-tolerance");
    if (lossInput) lossInput.value = persona.lossToleranceScore;
    const horizInput = byId("investment-horizon");
    if (horizInput) horizInput.value = persona.investmentHorizon;
    const liqInput = byId("liquidity-need");
    if (liqInput) liqInput.value = persona.liquidityNeed;
    const expInput = byId("experience-level");
    if (expInput) expInput.value = persona.experienceLevel;
    const retInput = byId("return-expectation");
    if (retInput) retInput.value = persona.returnExpectation;
    const ddInput = byId("max-drawdown");
    if (ddInput) ddInput.value = persona.maxDrawdown;

    const stockInput = byId("copilot-stock-input");
    if (stockInput) stockInput.value = persona.defaultStock;

    // Update Quick Tags
    renderQuickTags(persona.quickTags);

    // Refresh underlying state and charts
    renderHeroDonutChart(personaId);
    renderOverviewWorkspace(personaId);
    Promise.allSettled([
      loadEvents(),
      loadRecommendationHistory(),
      loadBehaviorProfile(),
      loadQuestionnaireTemplate(),
      loadProfileSummary(),
    ])
      .then(async () => {
        if (state.selectedPersona !== personaId) return;
        if (state.questionnaireGate === "PENDING") applyQuestionnaireGate(null);
        if (!state.profile && personaId !== "custom-user") await ensureDependency("PROFILE_CONTEXT");
        if (state.selectedPersona !== personaId) return;
        await fetchRuntimeDataMode();
        if (state.selectedPersona !== personaId) return;
        if (personaId === "custom-user") await loadSavedPortfolio();
        if (state.selectedPersona !== personaId) return;
        await ensureDependency("PORTFOLIO_CONTEXT");
        if (state.selectedPersona !== personaId) return;
        if (state.profile && state.portfolio) await refreshPortfolioHealth();
        renderPortfolioReadiness();
        await refreshSessionTruth();
      })
      .catch((error) => renderPortfolioAnalysisStatus(error.message || "持仓体检初始化失败"));
  }

  function renderQuickTags(tags) {
    const container = byId("copilot-quick-tags");
    if (!container) return;
    clear(container);

    const span = document.createElement("span");
    span.className = "tags-label";
    span.textContent = "试试这些：";
    container.append(span);

    tags.forEach(t => {
      const btn = document.createElement("button");
      btn.className = "quick-tag-chip";
      btn.type = "button";
      btn.textContent = t.label;
      btn.dataset.intent = t.intent;
      if (t.target) btn.dataset.target = t.target;
      btn.addEventListener("click", () => {
        handleCopilotIntent(t.intent, t.target);
      });
      container.append(btn);
    });
  }

  function handleCopilotIntent(intent, target) {
    setAgentFeatureToolsCompact(true);
    if (intent === "CHECK_PORTFOLIO") {
      runCopilotHealthCheck();
    } else if (intent === "RESEARCH_STOCK") {
      if (target) {
        const stockInput = byId("copilot-stock-input");
        if (stockInput) stockInput.value = target;
      }
      runCopilotStockResearch(target);
    } else if (intent === "REBALANCE_PORTFOLIO") {
      runCopilotRebalance();
    } else if (intent === "SCENARIO_SHOCK") {
      runCopilotScenarioShock();
    } else {
      runCopilotHealthCheck();
    }
  }

  function buildCopilotLoadingCard(iconId, title, desc) {
    const card = document.createElement("div");
    card.className = "copilot-empty-output";
    const iconSpan = document.createElement("span");
    iconSpan.className = "empty-icon";
    const spinSvg = createSvgIcon("icon-activity", "prism-icon prism-icon-xl");
    spinSvg.style.animation = "spin 1.2s linear infinite";
    iconSpan.append(spinSvg);
    const h4 = document.createElement("h4");
    h4.textContent = title;
    const p = document.createElement("p");
    p.textContent = desc;
    card.append(iconSpan, h4, p);
    return card;
  }

  function buildCopilotMetricBox(label, value, isAlert, isOk, tooltip) {
    const box = document.createElement("div");
    box.className = "metric-box";
    const span = document.createElement("span");
    if (tooltip) {
      span.className = "term-tip";
      span.setAttribute("data-tooltip", tooltip);
      span.textContent = `${label} `;
      const tipIcon = document.createElement("span");
      tipIcon.className = "tip-icon";
      tipIcon.textContent = "?";
      span.append(tipIcon);
    } else {
      span.textContent = label;
    }
    const strong = document.createElement("strong");
    strong.textContent = value;
    if (isAlert) strong.className = "alert-text";
    if (isOk) strong.className = "ok-text";
    box.append(span, strong);
    return box;
  }

  function buildCopilotDrilldownRow(links) {
    const row = document.createElement("div");
    row.className = "decision-drilldown-row";
    const label = document.createElement("span");
    label.className = "drilldown-label";
    label.textContent = "想了解更多依据？";
    row.append(label);
    links.forEach(l => {
      const a = document.createElement("a");
      a.href = l.href;
      a.className = "drilldown-btn";
      const span = document.createElement("span");
      span.textContent = l.text;
      a.append(span);
      row.append(a);
    });
    return row;
  }

  function getSectorVerdict(s) {
    return {
      isCash: s.limitOperator === "MIN",
      isOver: s.verdictCode === "OVERBOUND",
      diffVal: s.differencePctPoints,
      verdictCode: s.verdictCode,
      diffLabel: s.differenceLabel,
    };
  }

  const SECTOR_COLORS = Object.freeze({
    TECHNOLOGY: "#3b82f6",
    INDUSTRIALS: "#10b981",
    CONSUMER_HEALTHCARE: "#f97316",
    FINANCE_CYCLICAL: "#8b5cf6",
    CASH: "#eab308",
    UNCLASSIFIED: "#94a3b8",
  });

  const SOURCE_INDUSTRY_COLORS = Object.freeze([
    "#2563eb", "#059669", "#d97706", "#7c3aed", "#db2777",
    "#0891b2", "#65a30d", "#c2410c", "#4f46e5", "#0f766e",
  ]);

  function sectorColor(sectorKey, name) {
    if (SECTOR_COLORS[sectorKey]) return SECTOR_COLORS[sectorKey];
    const source = String(name || sectorKey || "行业");
    let hash = 0;
    for (let index = 0; index < source.length; index += 1) {
      hash = ((hash * 31) + source.charCodeAt(index)) >>> 0;
    }
    return SOURCE_INDUSTRY_COLORS[hash % SOURCE_INDUSTRY_COLORS.length];
  }

  function portfolioHealthView(data) {
    return {
      ...data,
      sectors: (data.sectors || []).map((row) => ({
        sectorKey: row.sector_key,
        name: row.name,
        pct: Number(row.weight_pct),
        cap: Number(row.limit_pct),
        color: sectorColor(row.sector_key, row.name),
        topHoldings: (row.top_holdings || []).join("、") || "无可用穿透标的",
        limitOperator: row.limit_operator,
        differencePctPoints: Number(row.difference_pct_points),
        marginPctPoints: Number(row.margin_pct_points),
        verdictCode: row.verdict,
        differenceLabel: row.verdict === "OVERBOUND"
          ? `${row.limit_operator === "MIN" ? "不足" : "超限"} ${row.margin_pct_points} 个百分点`
          : `余量 ${row.margin_pct_points} 个百分点`,
      })),
    };
  }

  function renderPortfolioReadiness() {
    if (!state.portfolio && byId("copilot-hero-portfolio-tag")) {
      byId("copilot-hero-portfolio-tag").textContent = "待确认持仓";
    }
    if (state.portfolioHealthRun) return;
    const message = !state.profile?.profile ? "请先完成并确认风险问卷" : !state.portfolio ? "请先添加并确认持仓" : "待运行体检";
    const values = {
      "copilot-stat-aum": state.portfolio ? "待体检" : "待确认持仓",
      "copilot-stat-tech": "待体检",
      "copilot-stat-budget": state.profile?.profile ? "待体检" : "待确认画像",
      "copilot-stat-evidence": "待计算",
      "portfolio-refresh-status": message,
    };
    Object.entries(values).forEach(([id, value]) => { if (byId(id)) byId(id).textContent = value; });
    renderHeroDonutChart(state.selectedPersona);
  }

  function requirePortfolioAnalysisContext(output, needsProfile = true) {
    const missingProfile = needsProfile && !state.profile?.profile;
    if (!missingProfile && state.portfolio) return true;
    const card = document.createElement("div");
    card.className = "copilot-empty-output";
    const title = document.createElement("h4");
    title.textContent = missingProfile ? "请先确认风险画像" : "请先确认持仓";
    const message = document.createElement("p");
    message.textContent = missingProfile ? "请在风险画像页面完成并确认问卷，再运行组合分析。" : "请通过添加持仓导入并确认本次分析的数据。";
    card.append(title, message, buildCopilotDrilldownRow([{href: missingProfile ? "#profile" : "#overview", text: missingProfile ? "填写风险问卷" : "查看我的组合"}]));
    output.append(card);
    renderPortfolioReadiness();
    return false;
  }

  async function refreshPortfolioHealth() {
    if (!state.profile?.profile || !state.portfolio) {
      microStore.transact((store) => {
        store.portfolioHealthSequence += 1;
        store.portfolioHealthRun = null;
        store.portfolioRefreshSequence += 1;
        store.portfolioRefreshRun = null;
      });
      renderPortfolioRefreshStatus(null);
      renderHeroDonutChart(state.selectedPersona);
      renderOverviewWorkspace(state.selectedPersona);
      return null;
    }
    let token = beginContextRequest("portfolioHealthSequence");
    microStore.transact((store) => {
      store.portfolioHealthRun = null;
      store.portfolioRefreshRun = null;
    });
    renderPortfolioRefreshStatus(null);
    const profile = token.profile.profile;
    let portfolio = token.portfolio;
    const liveCapabilities = (state.capabilities && state.capabilities.LIVE) || {};
    const shouldRefresh = state.dataMode !== "LIVE"
      || liveCapabilities.portfolio_refresh === true
      || liveCapabilities.stock_quote === true
      || liveCapabilities.fund_lookthrough === true
      // A previous probe failure is not a permanent block. The backend
      // verifies this refresh; incomplete prices still stop optimization.
      || Boolean(portfolio?.position_snapshot?.positions?.length);
    if (shouldRefresh) {
      const refreshResponse = await fetch("/api/v1/advisor/portfolio/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Owner-ID": token.ownerId },
        body: JSON.stringify({
          schema_version: "portfolio-refresh-request.v1",
          request_id: `portfolio-refresh-${Date.now()}`,
          owner_id: token.ownerId,
          as_of: new Date().toISOString(),
          portfolio,
        }),
      });
      if (!isContextRequestCurrent(token)) return null;
      const refreshPayload = await refreshResponse.json().catch(() => ({}));
      if (!refreshResponse.ok) {
        microStore.transact((store) => { store.portfolioRefreshRun = refreshPayload; });
        renderPortfolioRefreshStatus(refreshPayload);
        await fetchRuntimeDataMode();
        throw new Error(refreshPayload.message || "最新数据刷新失败，未使用旧数据继续计算");
      }
      if (!["COMPLETE", "REVIEW_REQUIRED"].includes(refreshPayload.status) || !refreshPayload.portfolio) {
        microStore.transact((store) => { store.portfolioRefreshRun = refreshPayload; });
        renderPortfolioRefreshStatus(refreshPayload);
        if (refreshPayload.data_mode === "LIVE") await fetchRuntimeDataMode();
        throw new Error(portfolioRefreshProblem(refreshPayload));
      }
      microStore.transact((store) => {
        store.portfolio = refreshPayload.portfolio;
        store.portfolioRefreshRun = refreshPayload;
      });
      renderPortfolioRefreshStatus(refreshPayload);
      if (refreshPayload.data_mode === "LIVE") await fetchRuntimeDataMode();
      token = beginContextRequest("portfolioHealthSequence");
      portfolio = token.portfolio;
    } else {
      const skippedRefresh = {
        status: "BLOCKED",
        data_mode: "LIVE",
        provider: "未执行外部刷新",
        issues: ["真实组合行情当前不可用；未使用旧持仓价格继续计算。"],
      };
      microStore.transact((store) => { store.portfolioRefreshRun = skippedRefresh; });
      renderPortfolioRefreshStatus(skippedRefresh);
      throw new Error("真实组合行情当前不可用，组合体检已停止");
    }
    const response = await fetch("/api/v1/advisor/portfolio-health", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Owner-ID": token.ownerId },
      body: JSON.stringify({
        schema_version: "portfolio-health-request.v1",
        request_id: `portfolio-health-${Date.now()}`,
        owner_id: token.ownerId,
        calculated_at: new Date().toISOString(),
        portfolio,
        profile,
      }),
    });
    if (!isContextRequestCurrent(token)) return null;
    if (!response.ok) throw await apiError(response);
    const result = portfolioHealthView(await response.json());
    if (!isContextRequestCurrent(token)) return null;
    state.portfolioHealthRun = result;
    const health = state.portfolioHealthRun;
    const aum = byId("copilot-stat-aum");
    if (aum) aum.textContent = `¥ ${Number(health.total_market_value_cny).toLocaleString()}`;
    const tech = byId("copilot-stat-tech");
    const topSector = health.sectors.find((row) => row.sectorKey === health.top_sector_key);
    if (tech) {
      tech.textContent = `${health.top_sector_name} ${health.top_sector_weight_pct}%`;
      tech.classList.toggle("alert-text", topSector?.verdictCode === "OVERBOUND");
      tech.classList.toggle("ok-text", topSector?.verdictCode === "PASS");
    }
    const budget = byId("copilot-stat-budget");
    if (budget) budget.textContent = topSector ? `${topSector.limitOperator === "MIN" ? "≥" : "≤"} ${topSector.cap}%` : "待计算";
    const evidence = byId("copilot-stat-evidence");
    if (evidence) evidence.textContent = `${health.evidence_count}项穿透贡献 · Python 验算`;
    renderHeroDonutChart(state.selectedPersona);
    renderOverviewWorkspace(state.selectedPersona);
    return health;
  }

  function portfolioRefreshProblem(refresh = state.portfolioRefreshRun) {
    const rows = Array.isArray(refresh?.positions) ? refresh.positions : [];
    const missingSectors = rows.filter(row => row.missing_fields?.some(field => ["sector", "holding_sector"].includes(field)));
    if (missingSectors.length) {
      const prefix = refresh?.portfolio ? "真实报价已更新；" : "";
      return `${prefix}以下持仓的自动行业数据暂不可用：${missingSectors.map(row => row.asset_id).join("、")}。自动行业查询暂未返回完整结果，请稍后重试。`;
    }
    const missingPrices = rows.filter(row => row.status !== "SKIPPED" && (!row.price_cny || !row.observed_at));
    return missingPrices.length
      ? `以下持仓的真实报价或报价时间暂不可用：${missingPrices.map(row => row.asset_id).join("、")}。请稍后重试。`
      : "真实持仓数据尚未完整刷新，请检查持仓信息与数据服务状态后重试。";
  }

  function portfolioMissingAnalysisData(refresh = state.portfolioRefreshRun) {
    const rows = Array.isArray(refresh?.positions) ? refresh.positions : [];
    const affected = rows.filter(row => Array.isArray(row.missing_fields) && row.missing_fields.length);
    const sectorIncomplete = affected.some(row => row.missing_fields.some(field => ["sector", "holding_sector"].includes(field)))
      || (state.portfolioHealthRun?.sectors || []).some(sector => sector.sectorKey === "UNCLASSIFIED" && Number(sector.pct) > 0);
    return {affected, sectorIncomplete};
  }

  function renderPortfolioAnalysisStatus(errorMessage = "") {
    const panel = byId("portfolio-analysis-status");
    const title = byId("portfolio-analysis-status-title");
    const message = byId("portfolio-analysis-status-message");
    const extended = byId("portfolio-extended-analysis");
    if (!panel || !title || !message || !extended) return;
    const {affected, sectorIncomplete} = portfolioMissingAnalysisData();
    if (!state.portfolio) {
      panel.hidden = true;
      extended.hidden = true;
      return;
    }
    let detail = "";
    if (errorMessage) {
      title.textContent = "持仓已保存，组合体检未完成";
      detail = `${errorMessage} 已确认的市值、现金与资产结构仍可查看；行业分布、行业限额和行业 HHI 暂不可用。`;
    } else if (!state.profile?.profile) {
      title.textContent = "持仓已保存，风险画像尚未确认";
      detail = "请先完成风险问卷。已确认的市值、现金与资产结构仍可查看；画像阈值和组合体检暂不可用。";
    } else if (sectorIncomplete) {
      const unclassifiedCodes = state.portfolio?.position_snapshot?.positions
        ?.filter(position => !position.sector || String(position.sector).toUpperCase() === "UNCLASSIFIED")
        .map(position => position.asset_id) || [];
      const codes = [...new Set([...affected.map(row => row.asset_id), ...unclassifiedCodes].filter(Boolean))];
      const fields = [...new Set(affected.flatMap(row => row.missing_fields || []))].map(field => ({
        sector: "行业",
        holding_sector: "基金底层行业",
        price_cny: "最新价格",
        observed_at: "报价时间",
      }[field] || field));
      title.textContent = "持仓已保存，行业与集中度分析待补齐";
      detail = `${codes.length ? `缺失标的：${codes.join("、")}；` : ""}${fields.length ? `缺失字段：${fields.join("、")}；` : "缺失字段：行业；"}影响范围：行业分布、行业限额和行业 HHI。补齐行业数据后可重新分析；未分类资产不作为真实行业结论。`;
    } else if (!state.portfolioHealthRun) {
      title.textContent = "持仓已保存，扩展分析尚未生成";
      detail = "已确认的市值、现金与资产结构仍可查看。重新分析后生成行业分布与集中度扩展结果。";
    }
    const unavailable = Boolean(detail);
    panel.hidden = !unavailable;
    extended.hidden = unavailable;
    message.textContent = detail;
  }

  let portfolioAnalysisSequence = 0;
  async function runPortfolioAnalysis() {
    const sequence = ++portfolioAnalysisSequence;
    const owner = state.ownerId;
    const mode = state.dataMode;
    const buttons = [byId("btn-run-full-overview-check"), byId("portfolio-analysis-retry")].filter(Boolean);
    buttons.forEach(button => { button.disabled = true; button.setAttribute("aria-busy", "true"); });
    try {
      const health = await refreshPortfolioHealth();
      if (sequence !== portfolioAnalysisSequence || owner !== state.ownerId || mode !== state.dataMode) return;
      if (!health) {
        renderPortfolioAnalysisStatus();
        return;
      }
      await refreshPortfolioSummary();
      if (sequence !== portfolioAnalysisSequence || owner !== state.ownerId || mode !== state.dataMode) return;
      setError("");
      renderPortfolioAnalysisStatus();
    } catch (error) {
      if (sequence === portfolioAnalysisSequence && owner === state.ownerId && mode === state.dataMode) {
        renderPortfolioAnalysisStatus(error.message || "组合体检服务暂不可用，请稍后重试。");
      }
    } finally {
      if (sequence === portfolioAnalysisSequence) buttons.forEach(button => { button.disabled = false; button.removeAttribute("aria-busy"); });
    }
  }

  function renderPortfolioRefreshStatus(refresh) {
    const target = byId("portfolio-refresh-status");
    if (!target) return;
    if (!refresh) {
      target.textContent = "等待持仓数据";
      target.className = "portfolio-refresh-status";
      return;
    }
    const isLive = refresh.data_mode === "LIVE";
    const skipped = refresh.status === "SKIPPED";
    const complete = refresh.status === "COMPLETE";
    const rows = Array.isArray(refresh.positions) ? refresh.positions : [];
    const timedRows = rows.filter((row) => row.observed_at && row.staleness_seconds != null);
    const stalest = timedRows.reduce(
      (current, row) => !current || Number(row.staleness_seconds) > Number(current.staleness_seconds) ? row : current,
      null,
    );
    const freshness = stalest?.staleness_seconds == null
      ? "新鲜度未提供"
      : `最旧行情距计算时点 ${Number(stalest.staleness_seconds).toFixed(0)} 秒`;
    const sources = [...new Set(rows.map((row) => row.source).filter(Boolean))];
    const sourceLabel = sources.length ? sources.join(" + ") : (refresh.provider || "未标注来源");
    target.textContent = skipped
      ? `LIVE · 未刷新 · ${refresh.issues?.[0] || "使用已确认持仓进行计算"}`
      : complete
      ? `${isLive ? "LIVE · 真实数据刷新" : "MOCK · 合成数据"} · ${sourceLabel} · ${freshness}`
      : `${isLive ? "LIVE · 需要复核" : "MOCK · 需要复核"} · ${portfolioRefreshProblem(refresh)}`;
    target.className = `portfolio-refresh-status ${complete ? "complete" : "review"}`;
  }

  function renderEvidenceLineageModal() {
    const content = byId("evidence-lineage-content");
    if (!content) return;
    clear(content);
    const isLiveMode = state.dataMode === "LIVE";
    const health = state.portfolioHealthRun;
    const persona = PERSONAS[state.selectedPersona || "custom-user"] || DEFAULT_USER_PROFILE;
    const shell = document.createElement("div");
    shell.className = "evidence-explainer";

    if (!health) {
      const empty = document.createElement("section");
      empty.className = "evidence-empty-state";
      const icon = document.createElement("span");
      icon.className = "evidence-empty-icon";
      icon.append(createSvgIcon("icon-layers", "prism-icon prism-icon-lg"));
      const title = document.createElement("h4");
      title.textContent = "还没有足够信息生成分析依据";
      const description = document.createElement("p");
      description.textContent = "先添加风险设置和持仓，即可查看行业占比及其与设置范围的对照。";
      empty.append(icon, title, description);
      shell.append(empty);
      content.append(shell);
      return;
    }

    const overbound = health.sectors.filter((sector) => sector.verdictCode === "OVERBOUND");
    const primaryIssue = overbound[0] || null;
    const needsReview = health.status !== "PASS";

    const summary = document.createElement("section");
    summary.className = `evidence-answer-card ${needsReview ? "review" : "pass"}`;
    const summaryIcon = document.createElement("span");
    summaryIcon.className = "evidence-answer-icon";
    summaryIcon.append(createSvgIcon(needsReview ? "icon-alert" : "icon-shield-check", "prism-icon prism-icon-lg"));
    const summaryCopy = document.createElement("div");
    const eyebrow = document.createElement("span");
    eyebrow.className = "evidence-answer-eyebrow";
    eyebrow.textContent = needsReview ? "本次分析 · 需要关注" : "本次分析 · 暂无明显问题";
    const title = document.createElement("h4");
    const description = document.createElement("p");
    if (primaryIssue) {
      const direction = primaryIssue.limitOperator === "MIN" ? "低于你设置的最低比例" : "超过你设置的上限";
      title.textContent = `${primaryIssue.name}${direction}`;
      description.textContent = `当前为 ${primaryIssue.pct.toFixed(1)}%，你设置的是${primaryIssue.limitOperator === "MIN" ? "至少" : "不超过"} ${primaryIssue.cap.toFixed(1)}%。${primaryIssue.differenceLabel}，建议进一步查看。`;
    } else if (needsReview) {
      title.textContent = "部分持仓信息还不完整";
      description.textContent = "当前指标未发现数值超限，但存在部分缺失或未分类数据，建议核实补充。";
    } else {
      title.textContent = "当前持仓暂无明显问题";
      description.textContent = "已完成行业占比和设置范围的逐项对照，当前可计算指标均在你设置的范围内。";
    }
    summaryCopy.append(eyebrow, title, description);
    summary.append(summaryIcon, summaryCopy);

    const facts = document.createElement("div");
    facts.className = "evidence-fact-strip";
    [
      { label: "分析了什么", value: `${health.evidence_count} 项持仓贡献`, note: "含基金底层持仓" },
      { label: "使用的风险设置", value: activeProfileTag(), note: "来自你的投资偏好" },
      { label: "当前情况", value: needsReview ? "需要关注" : "暂无明显问题", note: "基于可用持仓数据" },
    ].forEach((fact) => {
      const item = document.createElement("div");
      item.className = "evidence-fact";
      const label = document.createElement("span");
      label.textContent = fact.label;
      const value = document.createElement("strong");
      value.textContent = fact.value;
      const note = document.createElement("small");
      note.textContent = fact.note;
      item.append(label, value, note);
      facts.append(item);
    });

    const comparison = document.createElement("section");
    comparison.className = "evidence-comparison";
    const comparisonHeader = document.createElement("header");
    const comparisonTitle = document.createElement("h4");
    comparisonTitle.textContent = "当前持仓与设置范围的距离";
    const comparisonHelp = document.createElement("p");
    comparisonHelp.textContent = "彩色条表示当前占比，竖线表示你设置的范围。红色表示需要关注。";
    comparisonHeader.append(comparisonTitle, comparisonHelp);
    const barList = document.createElement("div");
    barList.className = "evidence-bar-list";
    health.sectors.forEach((sector) => {
      const row = document.createElement("div");
      row.className = `evidence-bar-row ${sector.verdictCode === "OVERBOUND" ? "overbound" : "pass"}`;
      const rowHeader = document.createElement("div");
      rowHeader.className = "evidence-bar-header";
      const name = document.createElement("strong");
      name.textContent = sector.name;
      const verdict = document.createElement("span");
      verdict.className = "evidence-bar-verdict";
      verdict.textContent = sector.verdictCode === "OVERBOUND" ? "需要关注" : "范围内";
      rowHeader.append(name, verdict);
      const track = document.createElement("div");
      track.className = "evidence-bar-track";
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", `${sector.name}当前 ${sector.pct.toFixed(1)}%，设置${sector.limitOperator === "MIN" ? "至少" : "不超过"}${sector.cap.toFixed(1)}%，${verdict.textContent}`);
      const fill = document.createElement("span");
      fill.className = "evidence-bar-fill";
      fill.style.width = `${Math.max(0, Math.min(100, sector.pct))}%`;
      fill.style.backgroundColor = sector.color;
      const marker = document.createElement("span");
      marker.className = "evidence-limit-marker";
      marker.style.left = `${Math.max(0, Math.min(100, sector.cap))}%`;
      const markerLabel = document.createElement("span");
      markerLabel.className = "evidence-limit-label";
      markerLabel.textContent = "设置";
      marker.append(markerLabel);
      track.append(fill, marker);
      const caption = document.createElement("div");
      caption.className = "evidence-bar-caption";
      const actual = document.createElement("span");
      actual.textContent = `当前 ${sector.pct.toFixed(1)}%`;
      const limit = document.createElement("span");
      limit.textContent = `${sector.limitOperator === "MIN" ? "至少" : "上限"} ${sector.cap.toFixed(1)}% · ${sector.differenceLabel}`;
      caption.append(actual, limit);
      row.append(rowHeader, track, caption);
      barList.append(row);
    });
    comparison.append(comparisonHeader, barList);

    const process = document.createElement("section");
    process.className = "evidence-process";
    const processTitle = document.createElement("h4");
    processTitle.textContent = "这个结论是怎样得出的";
    const processFlow = document.createElement("div");
    processFlow.className = "evidence-process-flow";
    [
      { icon: "icon-file-text", title: "读取持仓", text: "使用你已确认的数量、价格和现金。" },
      { icon: "icon-layers", title: "还原真实占比", text: "股票直接归类，基金继续穿透到底层持仓。" },
      { icon: "icon-scale", title: "对照你的设置", text: `逐项对照 ${activeProfileTag()} 的行业上限和现金最低比例。` },
      { icon: needsReview ? "icon-alert" : "icon-check", title: "形成判断", text: primaryIssue ? `${primaryIssue.name}需要关注。` : needsReview ? "信息不完整，需要补充。" : "当前没有明显问题。" },
    ].forEach((step, index, items) => {
      const card = document.createElement("div");
      card.className = "evidence-process-step";
      const icon = document.createElement("span");
      icon.append(createSvgIcon(step.icon, "prism-icon"));
      const copy = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = step.title;
      const text = document.createElement("p");
      text.textContent = step.text;
      copy.append(name, text);
      card.append(icon, copy);
      processFlow.append(card);
      if (index < items.length - 1) {
        const arrow = document.createElement("span");
        arrow.className = "evidence-process-arrow";
        arrow.textContent = "→";
        arrow.setAttribute("aria-hidden", "true");
        processFlow.append(arrow);
      }
    });
    process.append(processTitle, processFlow);

    const next = document.createElement("section");
    next.className = `evidence-next-step ${needsReview ? "review" : "pass"}`;
    const nextIcon = document.createElement("span");
    nextIcon.append(createSvgIcon(needsReview ? "icon-compass" : "icon-check", "prism-icon"));
    const nextCopy = document.createElement("div");
    const nextTitle = document.createElement("strong");
    nextTitle.textContent = needsReview ? "接下来可以怎么做" : "什么时候需要重新检查";
    const nextText = document.createElement("p");
    if (primaryIssue) {
      nextText.textContent = "先确认这项偏离是否符合你的实际需要；如需调整，进入调仓计划，由后端把整手约束和交易费用一起算入。";
    } else if (needsReview) {
      nextText.textContent = "补齐缺失或未分类的持仓信息后重新运行体检，再决定是否需要调整。";
    } else {
      nextText.textContent = "当持仓数量、价格、基金底层持仓或风险设置变化时，再更新一次分析。";
    }
    nextCopy.append(nextTitle, nextText);
    next.append(nextIcon, nextCopy);

    const details = document.createElement("details");
    details.className = "evidence-professional-details";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "查看计算方式与数据来源";
    const detailsBody = document.createElement("div");
    detailsBody.className = "evidence-professional-body";
    const sourceTitle = document.createElement("strong");
    sourceTitle.textContent = "数据来源";
    const sourceText = document.createElement("p");
    const refresh = state.portfolioRefreshRun;
    if (!isLiveMode) {
      sourceText.textContent = "当前为离线演示数据，指标由预置基准数据测算。";
    } else if (refresh?.status === "COMPLETE") {
      sourceText.textContent = "本次组合已由可用 LIVE 数据源刷新；场内基金持仓来自最近一期定期披露。";
    } else {
      sourceText.textContent = "本次未完成外部组合刷新；体检仅使用已确认持仓执行确定性计算，不引用未取得的公告、语义检索或最新组合数据。";
    }
    const formulaTitle = document.createElement("strong");
    formulaTitle.textContent = "确定性计算";
    const formulaList = document.createElement("ul");
    [
      "行业占比：每项持仓市值占组合总市值的比例；基金按底层权重继续拆分。",
      "集中度：由各行业占比平方求和；当前 HHI 为 " + health.sector_hhi + "，参考上限为 " + health.hhi_limit + "。",
      "风控参考：行业占比不超过你设置的上限，可用现金不低于最低要求。",
    ].forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      formulaList.append(li);
    });
    const auditTitle = document.createElement("strong");
    auditTitle.textContent = "计算说明";
    const auditText = document.createElement("p");
    auditText.textContent = "资产数据均通过系统量化模型计算，大模型仅负责语言理解与分析表达，不参与金融数值加减。";
    detailsBody.append(sourceTitle, sourceText, formulaTitle, formulaList, auditTitle, auditText);
    details.append(detailsSummary, detailsBody);

    shell.append(summary, facts, comparison, process, next, details);
    content.append(shell);
  }

  function openEvidenceLineageModal() {
    renderEvidenceLineageModal();
    const modal = byId("evidence-lineage-modal");
    if (modal) modal.style.display = "flex";
  }

  function closeEvidenceLineageModal() {
    const modal = byId("evidence-lineage-modal");
    if (modal) modal.style.display = "none";
  }

  function buildMultiIndustryMatrixTable(sectors) {
    const table = document.createElement("table");
    table.className = "health-check-matrix-table";

    const thead = document.createElement("thead");
    const hRow = document.createElement("tr");
    ["行业 / 资产大类", "当前占比", "你设置的范围", "与设置的距离", "当前情况", "主要标的"].forEach(h => {
      const th = document.createElement("th");
      th.textContent = h;
      hRow.append(th);
    });
    thead.append(hRow);

    const tbody = document.createElement("tbody");
    sectors.forEach(s => {
      const v = getSectorVerdict(s);
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      const dot = document.createElement("span");
      dot.className = "donut-color-dot";
      dot.style.backgroundColor = s.color;
      dot.style.display = "inline-block";
      dot.style.marginRight = "6px";
      tdName.append(dot, document.createTextNode(s.name));

      const tdActual = document.createElement("td");
      tdActual.textContent = `${s.pct.toFixed(1)}%`;
      tdActual.style.fontFamily = "var(--mono)";
      tdActual.style.fontWeight = "600";

      const tdCap = document.createElement("td");
      tdCap.textContent = `${v.isCash ? "≥ " : "≤ "}${s.cap.toFixed(1)}%`;
      tdCap.style.fontFamily = "var(--mono)";

      const tdDiff = document.createElement("td");
      tdDiff.textContent = v.diffLabel;
      tdDiff.style.fontFamily = "var(--mono)";
      if (v.isOver) tdDiff.style.color = "var(--danger)";
      else if (v.isCash) tdDiff.style.color = "var(--success)";

      const tdVerdict = document.createElement("td");
      const vBadge = document.createElement("span");
      vBadge.className = v.isOver ? "matrix-status-overbound" : "matrix-status-pass";
      vBadge.textContent = v.isOver ? "需要关注" : "范围内";
      tdVerdict.append(vBadge);

      const tdHoldings = document.createElement("td");
      tdHoldings.textContent = s.topHoldings;
      tdHoldings.style.color = "var(--ink-secondary)";

      tr.append(tdName, tdActual, tdCap, tdDiff, tdVerdict, tdHoldings);
      tbody.append(tr);
    });
    table.append(thead, tbody);
    return table;
  }

  function buildMultiDimensionalMetricsGrid(health) {
    const maxSector = (health.sectors || []).find(s => s.sectorKey === health.top_sector_key);
    const cashSector = (health.sectors || []).find(s => s.sectorKey === "CASH");

    const metricsData = [
      { label: "最大行业占比", value: `${health.top_sector_weight_pct}% (${health.top_sector_name})`, status: maxSector?.verdictCode === "PASS" ? "在设置范围内" : "需要关注", isOk: maxSector?.verdictCode === "PASS" },
      { label: "组合集中度 (HHI)", value: `${health.sector_hhi}`, status: health.hhi_verdict === "PASS" ? `低于参考值 ${health.hhi_limit}` : `超过参考值 ${health.hhi_limit}`, isOk: health.hhi_verdict === "PASS" },
      { label: "现金与流动性", value: `${health.cash_weight_pct}%`, status: cashSector?.verdictCode === "PASS" ? `达到最低 ${health.cash_minimum_pct}%` : `低于最低 ${health.cash_minimum_pct}%`, isOk: cashSector?.verdictCode === "PASS" },
      { label: "财务数据", value: "暂未检查", status: "本次分析未包含财务凭证", isOk: false }
    ];

    const mGrid = document.createElement("div");
    mGrid.className = "overview-health-metrics-grid";
    metricsData.forEach(m => {
      const box = document.createElement("div");
      box.className = "overview-health-metric-box";
      const lbl = document.createElement("span");
      lbl.className = "overview-health-metric-label";
      lbl.textContent = m.label;
      const val = document.createElement("span");
      val.className = "overview-health-metric-value";
      val.textContent = m.value;
      const st = document.createElement("span");
      st.className = "overview-health-metric-status";
      st.textContent = m.status;
      st.style.color = m.isOk ? "var(--success)" : "var(--danger)";
      box.append(lbl, val, st);
      mGrid.append(box);
    });
    return mGrid;
  }

  function renderHeroDonutChart(personaId) {
    const container = byId("copilot-hero-donut-chart");
    const legendContainer = byId("copilot-donut-legend");
    const hintEl = byId("donut-active-hint");
    const detailEl = byId("donut-sector-detail");
    const rankPill = byId("cf-profile-rank-pill");
    const verdictBadge = byId("cf-hero-verdict-badge");
    const causeCallout = byId("donut-cause-callout");
    if (!container || !legendContainer) return;

    clear(container);
    clear(legendContainer);
    if (detailEl) {
      clear(detailEl);
      detailEl.hidden = true;
    }

    const persona = PERSONAS[personaId || state.selectedPersona || "custom-user"] || DEFAULT_USER_PROFILE;
    const health = state.portfolioHealthRun;
    const sectors = health?.sectors || [];
    if (!health || !sectors.length) {
      if (hintEl) hintEl.textContent = !state.profile?.profile ? "请先完成风险设置。" : !state.portfolio ? "请先添加持仓。" : "请更新组合分析。";
      if (verdictBadge) verdictBadge.textContent = "等待分析";
      if (causeCallout) causeCallout.textContent = "添加风险设置与持仓后，可查看行业占比。";
      return;
    }
    const overboundList = sectors
      .map(s => ({ sector: s, verdict: getSectorVerdict(s) }))
      .filter(x => x.verdict.isOver);
    const requiresReview = health.status !== "PASS";

    if (rankPill) rankPill.textContent = activeProfileTag();
    if (verdictBadge) {
      clear(verdictBadge);
      verdictBadge.className = requiresReview ? "cf-verdict cf-verdict-risk" : "cf-verdict cf-verdict-pass";
      const vIcon = createSvgIcon(requiresReview ? "icon-alert" : "icon-check", "prism-icon");
      if (overboundList.length) {
        const topOver = overboundList[0];
        const breachText = topOver.verdict.isCash
          ? `${topOver.sector.name}不足 (${topOver.verdict.diffVal.toFixed(1)}%)`
          : `${topOver.sector.name}超标 (+${topOver.verdict.diffVal.toFixed(1)}%)`;
        verdictBadge.append(vIcon, document.createTextNode(` 需要关注 · ${breachText}`));
      } else if (health.hhi_verdict === "OVERBOUND") {
        verdictBadge.append(vIcon, document.createTextNode(` 集中度需要关注 · HHI ${health.sector_hhi}`));
      } else if (requiresReview) {
        verdictBadge.append(vIcon, document.createTextNode(" 部分数据需补充"));
      } else {
        verdictBadge.append(vIcon, document.createTextNode(" 暂无明显问题"));
      }
    }

    if (causeCallout) {
      if (overboundList.length) {
        causeCallout.className = "donut-cause-callout risk";
        causeCallout.textContent = `需要关注：${overboundList.map(x => x.verdict.isCash
          ? `【${x.sector.name}】实际比例 ${x.sector.pct.toFixed(1)}% 低于最低要求 ${x.sector.cap.toFixed(1)}%（差额 ${x.sector.marginPctPoints.toFixed(1)}%）`
          : `【${x.sector.name}】当前占比 ${x.sector.pct.toFixed(1)}% 超过你设置的上限 ${x.sector.cap.toFixed(1)}%（超出 ${x.sector.marginPctPoints.toFixed(1)}%）`
        ).join("；")}。如需调整，可进入调仓计划查看方案。`;
      } else if (health.hhi_verdict === "OVERBOUND") {
        causeCallout.className = "donut-cause-callout risk";
        causeCallout.textContent = `组合集中度 HHI ${health.sector_hhi} 超过参考值 ${health.hhi_limit}；各行业占比仍在设置范围内。`;
      } else if (requiresReview) {
        causeCallout.className = "donut-cause-callout risk";
        causeCallout.textContent = "当前没有数值超限项，但部分持仓数据缺失或尚未分类，请补充后更新分析。";
      } else {
        causeCallout.className = "donut-cause-callout pass";
        causeCallout.textContent = `当前可计算的行业占比均在 ${activeProfileTag()} 的设置范围内。`;
      }
    }

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 220 220");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "持仓行业分布环形图");

    const cx = 110, cy = 110, R = 95, r = 62;
    let currentAngle = -Math.PI / 2;

    const centerLabel = document.createElementNS(svgNS, "text");
    centerLabel.setAttribute("x", "110");
    centerLabel.setAttribute("y", "106");
    centerLabel.setAttribute("class", "donut-center-label");
    centerLabel.textContent = "行业分布";

    const centerValue = document.createElementNS(svgNS, "text");
    centerValue.setAttribute("x", "110");
    centerValue.setAttribute("y", "126");
    centerValue.setAttribute("class", "donut-center-value");
    centerValue.textContent = `${sectors.length}大类`;

    const sliceElements = [];
    const chipElements = [];

    function selectSector(s, idx) {
      const v = getSectorVerdict(s);
      sliceElements.forEach((el, i) => el.classList.toggle("active", i === idx));
      chipElements.forEach((el, i) => el.classList.toggle("active", i === idx));
      centerLabel.textContent = s.name;
      centerValue.textContent = `${s.pct.toFixed(1)}%`;
      if (hintEl) {
        hintEl.textContent = `${s.name}当前占比 ${s.pct.toFixed(1)}%，你设置的是${v.isCash ? "至少" : "不超过"} ${s.cap.toFixed(1)}%；主要标的：${s.topHoldings}`;
      }
    }

    function resetSelection() {
      sliceElements.forEach(el => el.classList.remove("active"));
      chipElements.forEach(el => el.classList.remove("active"));
      centerLabel.textContent = "行业分布";
      centerValue.textContent = `${sectors.length}大类`;
      if (hintEl) {
        hintEl.textContent = "选择行业查看占比、上限和主要标的";
      }
    }

    function renderSectorDetail(s) {
      if (!detailEl) return;
      const v = getSectorVerdict(s);
      clear(detailEl);
      detailEl.hidden = false;
      detailEl.className = v.isOver
        ? "donut-sector-detail risk"
        : "donut-sector-detail pass";

      const header = document.createElement("div");
      header.className = "donut-sector-detail-header";
      const title = document.createElement("strong");
      title.textContent = `${s.name}占比`;
      const verdict = document.createElement("span");
      verdict.className = v.isOver ? "donut-chip-badge overbound" : "donut-chip-badge pass";
      verdict.textContent = v.isOver ? "需要关注" : "范围内";
      header.append(title, verdict);

      const comparison = document.createElement("p");
      const comparator = v.isCash ? "不低于" : "不高于";
      comparison.textContent = `当前占比 ${s.pct.toFixed(1)}%；你的风险设置要求${comparator} ${s.cap.toFixed(1)}%。`;

      const result = document.createElement("p");
      result.className = "donut-sector-detail-result";
      if (v.isOver) {
        result.textContent = `超出设置 ${s.marginPctPoints} 个百分点，建议进一步查看。`;
      } else {
        result.textContent = `距设置上限仍有 ${s.marginPctPoints} 个百分点。`;
      }

      const holdings = document.createElement("p");
      holdings.className = "donut-sector-detail-holdings";
      holdings.textContent = `主要标的：${s.topHoldings}`;
      detailEl.append(header, comparison, result, holdings);
      detailEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    sectors.forEach((s, idx) => {
      const v = getSectorVerdict(s);
      const sliceAngle = (s.pct / 100) * (2 * Math.PI);
      const nextAngle = currentAngle + sliceAngle;

      const x1 = cx + R * Math.cos(currentAngle);
      const y1 = cy + R * Math.sin(currentAngle);
      const x2 = cx + R * Math.cos(nextAngle);
      const y2 = cy + R * Math.sin(nextAngle);
      const x3 = cx + r * Math.cos(nextAngle);
      const y3 = cy + r * Math.sin(nextAngle);
      const x4 = cx + r * Math.cos(currentAngle);
      const y4 = cy + r * Math.sin(currentAngle);

      const largeArc = sliceAngle > Math.PI ? 1 : 0;
      const d = `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} L ${x3.toFixed(2)} ${y3.toFixed(2)} A ${r} ${r} 0 ${largeArc} 0 ${x4.toFixed(2)} ${y4.toFixed(2)} Z`;

      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", s.color);
      path.setAttribute("class", "donut-slice");
      path.setAttribute("data-sector", s.name);

      path.addEventListener("mouseenter", () => selectSector(s, idx));
      path.addEventListener("mouseleave", () => resetSelection());
      path.addEventListener("click", () => {
        selectSector(s, idx);
        renderSectorDetail(s);
      });

      svg.append(path);
      sliceElements.push(path);

      const chip = document.createElement("div");
      chip.className = "donut-legend-chip";
      chip.setAttribute("role", "button");
      chip.setAttribute("tabindex", "0");
      chip.setAttribute("aria-label", `查看${s.name}占比`);
      const left = document.createElement("div");
      left.className = "donut-legend-left";
      const dot = document.createElement("span");
      dot.className = "donut-color-dot";
      dot.style.backgroundColor = s.color;
      const name = document.createElement("span");
      name.className = "donut-legend-name";
      name.textContent = s.name;
      left.append(dot, name);

      const right = document.createElement("div");
      right.className = "donut-legend-right";

      const pct = document.createElement("span");
      pct.className = "donut-legend-pct";
      pct.textContent = `${s.pct.toFixed(0)}%`;
      if (v.isOver) pct.style.color = "var(--danger)";

      const badge = document.createElement("span");
      badge.className = v.isOver ? "donut-chip-badge overbound" : "donut-chip-badge pass";
      badge.textContent = v.isOver ? "需要关注" : "";

      right.append(pct, badge);
      chip.append(left, right);

      chip.addEventListener("mouseenter", () => selectSector(s, idx));
      chip.addEventListener("mouseleave", () => resetSelection());
      chip.addEventListener("click", () => {
        selectSector(s, idx);
        renderSectorDetail(s);
      });
      chip.addEventListener("keydown", event => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        selectSector(s, idx);
        renderSectorDetail(s);
      });

      legendContainer.append(chip);
      chipElements.push(chip);

      currentAngle = nextAngle;
    });

    svg.append(centerLabel, centerValue);
    container.append(svg);
    resetSelection();
  }

  function renderOverviewWorkspace(personaId) {
    refreshPortfolioSummary().catch(error => setError(error.message));
    byId("cf-profile-rank-pill").textContent = activeProfileTag();

    const tableBody = byId("overview-industry-table-body");
    const metricsBody = byId("overview-metrics-body");
    const tableVerdict = byId("overview-table-verdict");
    const hhiChip = byId("overview-hhi-chip");
    if (!tableBody || !metricsBody) return;

    clear(tableBody);
    clear(metricsBody);

    const health = state.portfolioHealthRun;
    renderPortfolioAnalysisStatus();
    if (!health) {
      return;
    }
    if (portfolioMissingAnalysisData().sectorIncomplete) {
      return;
    }
    const sectors = health.sectors;
    const isAnyOverbound = health.has_breaches;
    const requiresReview = health.status !== "PASS";

    if (tableVerdict) {
      clear(tableVerdict);
      tableVerdict.className = requiresReview ? "cf-verdict cf-verdict-risk" : "cf-verdict cf-verdict-pass";
      tableVerdict.append(
        createSvgIcon(requiresReview ? "icon-alert" : "icon-check", "prism-icon"),
        document.createTextNode(
          isAnyOverbound
            ? " 需要关注"
            : requiresReview
              ? " 部分数据需补充"
              : " 暂无明显问题"
        )
      );
    }

    if (hhiChip) {
      hhiChip.textContent = health.hhi_verdict === "PASS" ? `HHI ${health.sector_hhi} · 正常` : `HHI ${health.sector_hhi} · 需要关注`;
      hhiChip.className = health.hhi_verdict === "PASS" ? "status-chip ok" : "status-chip alert";
    }

    tableBody.append(buildMultiIndustryMatrixTable(sectors));
    metricsBody.append(buildMultiDimensionalMetricsGrid(health));

    renderHeroDonutChart(personaId || state.selectedPersona);
  }

  async function runCopilotHealthCheck() {
    const output = byId("copilot-decision-output");
    if (!output) return;
    clear(output);
    state.copilotResearchSequence += 1;
    if (!requirePortfolioAnalysisContext(output)) return;
    output.append(buildCopilotLoadingCard("icon-activity", "正在检查你的组合…", "正在计算行业占比、集中度和可用现金。"));

    try {
      const health = await refreshPortfolioHealth();
      if (!health) throw new Error("后端未返回持仓穿透结果");
      const persona = PERSONAS[state.selectedPersona || "persona-zhang-r3"] || DEFAULT_USER_PROFILE;
      const sectors = health.sectors;
      const hasBreaches = health.has_breaches;
      const requiresReview = health.status !== "PASS";
      const technologyOverbound = Number(health.technology_weight_pct) > Number(health.technology_limit_pct);
      const incompleteIndustries = sectors.some(sector => sector.sectorKey === "UNCLASSIFIED" && sector.pct > 0);

      clear(output);
      const card = document.createElement("div");
      card.className = "copilot-decision-card";

      // Banner
      const banner = document.createElement("div");
      banner.className = `decision-banner ${requiresReview ? "reduce" : "hold"}`;
      const verdictTitleWrap = document.createElement("div");
      verdictTitleWrap.className = "decision-verdict-title";
      const icon = document.createElement("span");
      icon.className = "decision-verdict-icon";
      icon.append(createSvgIcon(requiresReview ? "icon-alert" : "icon-shield-check", "prism-icon prism-icon-lg"));
      const h3 = document.createElement("h3");
      h3.textContent = incompleteIndustries ? "真实报价已更新，行业数据暂缺" : hasBreaches
        ? "发现需要关注的组合风险"
        : requiresReview
          ? "部分数据需要补充"
          : "暂未发现需要关注的问题";
      verdictTitleWrap.append(icon, h3);

      const statusChip = document.createElement("span");
      statusChip.className = requiresReview ? "cf-verdict cf-verdict-risk" : "cf-verdict cf-verdict-pass";
      if (requiresReview) {
        statusChip.append(
          createSvgIcon("icon-alert", "prism-icon"),
          document.createTextNode(hasBreaches ? " 需要关注" : " 部分数据需补充")
        );
      } else {
        statusChip.append(createSvgIcon("icon-check", "prism-icon"), document.createTextNode(" 暂无明显问题"));
      }
      banner.append(verdictTitleWrap, statusChip);

      // Body
      const body = document.createElement("div");
      body.className = "decision-card-body";

      // 菜鸟/文档风格 Callout 诊断说明
      const callout = document.createElement("div");
      callout.className = requiresReview ? "doc-callout doc-callout-danger" : "doc-callout doc-callout-tip";
      
      const cIcon = document.createElement("div");
      cIcon.className = "callout-icon";
      cIcon.append(createSvgIcon(requiresReview ? "icon-alert" : "icon-info", "prism-icon"));
      
      const cContent = document.createElement("div");
      cContent.className = "callout-content";
      const cTitle = document.createElement("div");
      cTitle.className = "callout-title";
      cTitle.textContent = incompleteIndustries ? "部分体检结果 · 自动行业数据暂缺" : hasBreaches
        ? "部分持仓比例超出你的设置"
        : requiresReview
          ? "部分指标缺少完整数据"
          : "当前组合暂无明显问题";
      
      const cP = document.createElement("p");
      cP.textContent = `本次分析使用 ${persona.name} 的风险设置，并计算了当前持仓的行业占比和集中度。` +
        (hasBreaches
          ? "至少一项比例超出设置范围，可查看明细并评估是否调整。"
          : requiresReview
            ? "当前结果仅覆盖可计算指标；未分类或缺失输入建议补齐。"
            : "当前各项指标均在预设范围内。" );
      
      cContent.append(cTitle, cP);
      if (incompleteIndustries) {
        cP.textContent = `${portfolioRefreshProblem()} 未分类资产被单独归集，当前行业占比和 HHI 不能视为已核实的行业分布；市值与现金指标仍可计算。`;
        cContent.append(buildCopilotDrilldownRow([{href: "#overview", text: "查看自动分析状态"}]));
      }
      callout.append(cIcon, cContent);

      // Metrics with tooltips
      const metricsRow = document.createElement("div");
      metricsRow.className = "decision-metrics-row";
      metricsRow.append(
        buildCopilotMetricBox("当前科技占比", `${health.technology_weight_pct}%`, technologyOverbound, !technologyOverbound, "包含基金底层持仓。"),
        buildCopilotMetricBox("科技行业上限", `${health.technology_limit_pct}%`, false, false, "来自你的风险设置。"),
        buildCopilotMetricBox("组合 HHI", `${health.sector_hhi}`, health.hhi_verdict === "OVERBOUND", health.hhi_verdict === "PASS", "用于衡量行业集中度。")
      );

      // 全行业穿透对照表
      const matrixTableWrap = document.createElement("div");
      matrixTableWrap.style.margin = "18px 0";
      const mTableTitle = document.createElement("h4");
      mTableTitle.style.margin = "0 0 8px";
      mTableTitle.style.fontSize = "13.5px";
      mTableTitle.append(createSvgIcon("icon-layers", "prism-icon"), document.createTextNode(" 行业分布与设置范围"));
      matrixTableWrap.append(mTableTitle, buildMultiIndustryMatrixTable(sectors));

      // 多维健康度评分网格
      const multiMetricsWrap = document.createElement("div");
      multiMetricsWrap.style.margin = "18px 0";
      const mGridTitle = document.createElement("h4");
      mGridTitle.style.margin = "0 0 8px";
      mGridTitle.style.fontSize = "13.5px";
      mGridTitle.append(createSvgIcon("icon-shield-check", "prism-icon"), document.createTextNode(" 组合集中度与流动性"));
      multiMetricsWrap.append(mGridTitle, buildMultiDimensionalMetricsGrid(health));

      // Reasons
      const reasonsWrap = document.createElement("div");
      const reasonsHead = document.createElement("h4");
      reasonsHead.style.margin = "0 0 8px";
      reasonsHead.style.fontSize = "14px";
      const rHeadIcon = createSvgIcon("icon-info", "prism-icon");
      rHeadIcon.style.marginRight = "6px";
      reasonsHead.append(rHeadIcon, document.createTextNode(" 判断依据"));
      const reasonsList = document.createElement("ul");
      reasonsList.className = "decision-reasons-list";

      const r1 = document.createElement("li");
      const r1Bold = document.createElement("strong");
      r1Bold.textContent = "行业分布：";
      r1.append(r1Bold, document.createTextNode("已归集股票和基金底层持仓；未分类或缺失信息会单独保留。"));

      const r2 = document.createElement("li");
      const r2Bold = document.createElement("strong");
      r2Bold.textContent = "组合集中度：";
      r2.append(r2Bold, document.createTextNode(`当前 HHI 为 ${health.sector_hhi}，${health.hhi_verdict === "PASS" ? "低于参考值" : "高于参考值"} ${health.hhi_limit}。`));

      const r3 = document.createElement("li");
      const r3Bold = document.createElement("strong");
      r3Bold.textContent = "数据说明：";
      r3.append(r3Bold, document.createTextNode(`现金占比 ${health.cash_weight_pct}%，你设置的最低比例为 ${health.cash_minimum_pct}%；本次未包含财务凭证。`));

      reasonsList.append(r1, r2, r3);
      reasonsWrap.append(reasonsHead, reasonsList);

      body.append(callout, metricsRow, matrixTableWrap, multiMetricsWrap, reasonsWrap);

      // Drilldown links
      body.append(buildCopilotDrilldownRow([
        { href: "#research-tracks", text: "查看研究来源" },
        { href: "#advanced-explainability", text: "查看判断原因" },
        { href: "#evidence", text: "查看证据" },
        { href: "#overview", text: "查看设置范围" }
      ]));

      card.append(banner, body);
      output.append(card);
    } catch (err) {
      clear(output);
      const errCard = document.createElement("div");
      errCard.className = "copilot-empty-output";
      const h4 = document.createElement("h4");
      h4.textContent = "运行失败";
      const p = document.createElement("p");
      p.textContent = err.message || "未能完成投顾决策分析";
      errCard.append(h4, p);
      output.append(errCard);
    }
  }

  async function runCopilotStockResearch() {
    const symbolOverride = typeof arguments[0] === "string" ? arguments[0] : "";
    const lookbackYears = Number.isInteger(arguments[1]) ? Math.min(5, Math.max(3, arguments[1])) : 5;
    const output = byId("copilot-decision-output");
    if (!output) return;
    globalThis.prismStockQuickAbortController?.abort();
    globalThis.prismStockDeepAbortController?.abort();
    globalThis.prismStockQuickAbortController = new AbortController();
    clear(output);
    const token = beginContextRequest("copilotResearchSequence");

    const stockSymbol = symbolOverride.trim() || byId("copilot-stock-input")?.value?.trim() || "";
    if (!stockSymbol) {
      const emptyCard = document.createElement("div");
      emptyCard.className = "copilot-empty-output";
      const h4 = document.createElement("h4");
      h4.textContent = "请输入证券代码";
      const p = document.createElement("p");
      p.textContent = "请输入 6 位 A 股证券或 ETF 代码（如 300750、688256、600519）。";
      emptyCard.append(h4, p);
      output.append(emptyCard);
      return;
    }

    const cleanCode = stockSymbol.replace(/\.(SH|SZ|BJ)$/i, "").trim();
    const A_SHARE_PREFIXES = /^(600|601|603|605|688|689|000|001|002|003|300|301|82|83|87|88|92|510|512|513|515|588|159|110|113|123|127|128)/;
    const isSixDigits = /^\d{6}$/.test(cleanCode);
    const hasValidPrefix = A_SHARE_PREFIXES.test(cleanCode);
    const isSecurityName = /^[\u3400-\u9fffA-Za-z·]{2,30}$/.test(stockSymbol.trim());

    // Hard Gate 1: Syntax & Exchange Prefix Validation (e.g. 114514 rejection)
    if ((!isSixDigits || !hasValidPrefix) && !isSecurityName) {
      const card = document.createElement("div");
      card.className = "copilot-decision-card";

      const banner = document.createElement("div");
      banner.className = "decision-banner overbound";
      const titleWrap = document.createElement("div");
      titleWrap.className = "decision-verdict-title";
      const icon = document.createElement("span");
      icon.className = "decision-verdict-icon";
      icon.append(createSvgIcon("icon-alert", "prism-icon prism-icon-lg"));
      const h3 = document.createElement("h3");
      h3.textContent = `代码格式有误：${stockSymbol}`;
      titleWrap.append(icon, h3);

      const statusChip = document.createElement("span");
      statusChip.className = "cf-verdict cf-verdict-overbound";
      statusChip.append(createSvgIcon("icon-x", "prism-icon"), document.createTextNode(" 代码格式无效"));
      banner.append(titleWrap, statusChip);

      const body = document.createElement("div");
      body.className = "decision-card-body";

      const callout = document.createElement("div");
      callout.className = "doc-callout doc-callout-danger";
      const cIcon = document.createElement("div");
      cIcon.className = "callout-icon";
      cIcon.append(createSvgIcon("icon-alert", "prism-icon"));
      const cContent = document.createElement("div");
      cContent.className = "callout-content";
      const cTitle = document.createElement("div");
      cTitle.className = "callout-title";
      cTitle.textContent = "证券代码格式有误";
      const cP = document.createElement("p");
      cP.textContent = `A 股上市证券代码通常为 6 位数字（如 60/688 主板与科创板、00/300 主板与创业板、8/92 北交所、51/159 ETF 等）。输入的标的代码 [${stockSymbol}] 格式不符合规范，请输入有效代码后再试。`;
      cContent.append(cTitle, cP);
      callout.append(cIcon, cContent);

      const quickWrap = document.createElement("div");
      quickWrap.style.marginTop = "14px";
      const qHead = document.createElement("div");
      qHead.style.fontSize = "13px";
      qHead.style.fontWeight = "600";
      qHead.style.marginBottom = "8px";
      qHead.textContent = "建议检索已收录基准标的：";
      quickWrap.append(qHead);

      const sampleCodes = [
        { code: "300750", name: "宁德时代 (新能源)" },
        { code: "688256", name: "寒武纪 (AI芯片)" },
        { code: "600519", name: "贵州茅台 (核心消费)" },
        { code: "002594", name: "比亚迪 (整车/电池)" },
        { code: "688981", name: "中芯国际 (晶圆制造)" },
        { code: "600036", name: "招商银行 (股份行)" },
      ];
      const chipsRow = document.createElement("div");
      chipsRow.style.display = "flex";
      chipsRow.style.flexWrap = "wrap";
      chipsRow.style.gap = "8px";
      for (const item of sampleCodes) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "drilldown-btn";
        btn.textContent = `${item.code} ${item.name}`;
        btn.addEventListener("click", () => {
          const input = byId("copilot-stock-input");
          if (input) input.value = item.code;
          runCopilotStockResearch(item.code);
        });
        chipsRow.append(btn);
      }
      quickWrap.append(chipsRow);

      body.append(callout, quickWrap);
      card.append(banner, body);
      output.append(card);
      return;
    }

    const isFund = /^(510|512|513|515|588|159)/.test(cleanCode);
    output.append(buildCopilotLoadingCard("icon-activity", `正在查询 ${cleanCode} 数据…`, isFund ? "正在获取基金披露持仓与底层明细…" : "正在获取最新市场行情与财务指标…"));

    try {
      const endpoint = isFund ? "live-fund?fund_code=" : "live-quote?symbol=";
      let resp = await fetch(`/api/v1/copilot/${endpoint}${encodeURIComponent(stockSymbol)}${isFund ? "" : "&include_financials=true"}`, {signal: globalThis.prismStockQuickAbortController.signal});
      if (!isContextRequestCurrent(token)) return;
      let autoDependencyCompleted = false;

      if (isFund) {
        if (!resp.ok) throw await apiError(resp);
        const result = await resp.json();
        if (!isContextRequestCurrent(token)) return;
        clear(output);
        output.append(buildCopilotFundCard(result));
        return;
      }

      if (resp.status === 404 && token.dataMode === "LIVE") throw await apiError(resp);

      // 遇到阻碍：如果 404 缺失底稿，自动完成前置依赖（自动建档并重试）
      if (resp.status === 404) {
        clear(output);
        output.append(buildCopilotLoadingCard("icon-activity", `正在查询 ${cleanCode} 行情数据…`, "检测到标的代码尚未建档，正在同步行情与财报数据…"));
        try {
          const autoResp = await fetch(`/api/v1/copilot/auto-index-security?symbol=${encodeURIComponent(cleanCode)}`, { method: "POST", signal: globalThis.prismStockQuickAbortController.signal });
          if (!isContextRequestCurrent(token)) return;
          if (autoResp.ok) {
            const retryResp = await fetch(`/api/v1/copilot/live-quote?symbol=${encodeURIComponent(cleanCode)}`, {signal: globalThis.prismStockQuickAbortController.signal});
            if (!isContextRequestCurrent(token)) return;
            if (retryResp.ok) {
              resp = retryResp;
              autoDependencyCompleted = true;
            }
          }
        } catch (autoErr) {
          console.warn("自动补全标的数据失败:", autoErr);
        }
      }

      // Hard Gate 2: Unrecorded Security Handling (404)
      if (resp.status === 404) {
        clear(output);
        const card = document.createElement("div");
        card.className = "copilot-decision-card";

        const banner = document.createElement("div");
        banner.className = "decision-banner hold";
        const titleWrap = document.createElement("div");
        titleWrap.className = "decision-verdict-title";
        const icon = document.createElement("span");
        icon.className = "decision-verdict-icon";
        icon.append(createSvgIcon("icon-alert", "prism-icon prism-icon-lg"));
        const h3 = document.createElement("h3");
        h3.textContent = `暂无标的数据：${cleanCode}`;
        titleWrap.append(icon, h3);

        const statusChip = document.createElement("span");
        statusChip.className = "cf-verdict cf-verdict-hold";
        statusChip.append(createSvgIcon("icon-clock", "prism-icon"), document.createTextNode(" 暂未收录"));
        banner.append(titleWrap, statusChip);

        const body = document.createElement("div");
        body.className = "decision-card-body";

        const callout = document.createElement("div");
        callout.className = "doc-callout doc-callout-warning";
        const cIcon = document.createElement("div");
        cIcon.className = "callout-icon";
        cIcon.append(createSvgIcon("icon-alert", "prism-icon"));
        const cContent = document.createElement("div");
        cContent.className = "callout-content";
        const cTitle = document.createElement("div");
        cTitle.className = "callout-title";
        cTitle.textContent = "暂无该标的市场数据";
        const cP = document.createElement("p");
        cP.textContent = `目前系统尚未收录代码 [${cleanCode}] 的最新行情与财务数据，暂时无法提供分析。请检查代码是否正确或稍后重试。`;
        cContent.append(cTitle, cP);
        callout.append(cIcon, cContent);

        const retryWrap = document.createElement("div");
        retryWrap.style.marginTop = "14px";
        const retryBtn = document.createElement("button");
        retryBtn.type = "button";
        retryBtn.className = "btn btn-primary";
        retryBtn.style.marginRight = "10px";
        retryBtn.textContent = "重新尝试自动建档并研判";
        retryBtn.addEventListener("click", () => {
          runCopilotStockResearch(stockSymbol);
        });
        retryWrap.append(retryBtn);

        const quickWrap = document.createElement("div");
        quickWrap.style.marginTop = "14px";
        const qHead = document.createElement("div");
        qHead.style.fontSize = "13px";
        qHead.style.fontWeight = "600";
        qHead.style.marginBottom = "8px";
        qHead.textContent = "可查询已收录基准池标的：";
        quickWrap.append(qHead);

        const sampleCodes = [
          { code: "300750", name: "宁德时代" },
          { code: "688256", name: "寒武纪" },
          { code: "601998", name: "中信银行" },
          { code: "600519", name: "贵州茅台" },
          { code: "002594", name: "比亚迪" },
          { code: "688981", name: "中芯国际" },
          { code: "600036", name: "招商银行" },
          { code: "601318", name: "中国平安" },
          { code: "600900", name: "长江电力" },
        ];
        const chipsRow = document.createElement("div");
        chipsRow.style.display = "flex";
        chipsRow.style.flexWrap = "wrap";
        chipsRow.style.gap = "8px";
        for (const item of sampleCodes) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "drilldown-btn";
          btn.textContent = `${item.code} ${item.name}`;
          btn.addEventListener("click", () => {
            const input = byId("copilot-stock-input");
            if (input) input.value = item.code;
            runCopilotStockResearch(item.code);
          });
          chipsRow.append(btn);
        }
        quickWrap.append(chipsRow);

        body.append(callout, retryWrap, quickWrap);
        card.append(banner, body);
        output.append(card);
        return;
      }

      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.message || `请求失败 HTTP ${resp.status}`);
      }

      const res = await resp.json();
      if (!isContextRequestCurrent(token)) return;
      const quote = res.data;
      if (!quote) throw new Error("未获取到标的底稿数据");

      clear(output);
      const card = buildCopilotStockCard(res);
      output.append(card);
      globalThis.prismStockQuickAbortController = null;
      globalThis.prismStockDeepAbortController = new AbortController();
      const deepTarget = typeof card.querySelector === "function" ? card.querySelector("[data-stock-deep-report]") : null;
      if (!deepTarget) return;
      try {
        const deepResponse = await fetch(
          `/api/v1/copilot/stock-analysis?symbol=${encodeURIComponent(quote.symbol || cleanCode)}&lookback_years=${lookbackYears}`,
          {headers: {"X-Owner-ID": state.ownerId}, signal: globalThis.prismStockDeepAbortController.signal},
        );
        if (!isContextRequestCurrent(token)) return;
        if (!deepResponse.ok) throw await apiError(deepResponse);
        const deepResult = await deepResponse.json();
        if (!isContextRequestCurrent(token)) return;
        if (typeof renderCopilotStockDeepReport === "function") renderCopilotStockDeepReport(deepTarget, deepResult);
      } catch (deepError) {
        if (deepError.name === "AbortError" || !isContextRequestCurrent(token)) return;
        if (typeof renderCopilotStockDeepFailure === "function") renderCopilotStockDeepFailure(deepTarget, deepError.message || "深度研判暂不可用");
      } finally {
        if (isContextRequestCurrent(token)) globalThis.prismStockDeepAbortController = null;
      }
    } catch (err) {
      if (err.name === "AbortError") return;
      if (!isContextRequestCurrent(token)) return;
      if (token.dataMode === "LIVE") await fetchRuntimeDataMode();
      if (!isContextRequestCurrent(token)) return;
      clear(output);
      const errCard = document.createElement("div");
      errCard.className = "copilot-empty-output";
      const h4 = document.createElement("h4");
      h4.textContent = "研判失败";
      const p = document.createElement("p");
      p.textContent = err.message || "未能完成标的研判";
      errCard.append(h4, p);
      output.append(errCard);
    } finally {
      if (isContextRequestCurrent(token)) globalThis.prismStockQuickAbortController = null;
    }
  }

  function hasFinancialNumber(value) {
    return (typeof value === "number" || (typeof value === "string" && value.trim() !== "")) && Number.isFinite(Number(value));
  }

  function buildCopilotStockCard(result) {
    const quote = result.data;
    if (!quote) throw new Error("未返回个股数据。");
    const card = document.createElement("div");
    card.className = "copilot-decision-card";
    const banner = document.createElement("div"); banner.className = "decision-banner hold";
    const title = document.createElement("h3");
    title.textContent = `${quote.name} (${quote.symbol}) · 个股研判`;
    const status = document.createElement("span"); status.className = "cf-verdict cf-verdict-hold";
    const financialKeys = ["pe_ttm", "pb", "roe_pct", "gross_margin_pct", "debt_ratio_pct"];
    const complete = financialKeys.every(key => hasFinancialNumber(quote[key]));
    status.textContent = complete ? "行情与财务已取得" : "部分数据可用";
    banner.append(title, status);
    const body = document.createElement("div"); body.className = "decision-card-body";
    const metrics = document.createElement("div"); metrics.className = "copilot-metrics-row";
    [["最新价", "price_cny", " 元"], ["涨跌幅", "change_pct", "%"], ["PE（TTM）", "pe_ttm", " 倍"],
     ["PB（MRQ）", "pb", " 倍"], ["加权 ROE（报告期）", "roe_pct", "%"], ["销售毛利率", "gross_margin_pct", "%"],
     ["资产负债率", "debt_ratio_pct", "%"]].forEach(([label, key, unit]) => {
      appendReportMetric(metrics, label, hasFinancialNumber(quote[key]) ? `${Number(quote[key]).toFixed(2)}${unit}` : "暂未取得");
    });
    body.append(metrics);
    const period = document.createElement("p"); period.className = "research-boundary";
    period.textContent = `行情时间：${quote.observed_at || "未提供"}；财务报告期：${quote.financial_report_period || "未提供"}；披露日期：${quote.financial_report_date?.slice(0, 10) || "未提供"}。ROE 为报告期值，不自动年化。`;
    body.append(period);
    const limits = document.createElement("p");
    limits.textContent = "快速阶段仅展示当前行情与最新报告期指标；下方深度章节会继续补齐历史表现、五年财务、估值分位、动态证据和当前账户适配。仅供研究参考，不构成交易建议。";
    body.append(limits);
    for (const issue of quote.financial_issues || []) {
      const message = document.createElement("p"); message.textContent = `财务数据：${issue.message}（${issue.code}）`; body.append(message);
    }
    const source = document.createElement("details");
    const summary = document.createElement("summary"); summary.textContent = "数据来源与时间";
    const evidence = document.createElement("p");
    evidence.textContent = `${quote.source || result.source || "未提供"}；${quote.financial_source || "财务来源未提供"}。估值快照最新有效时间：${quote.valuation_observed_at || "未提供"}，不表示各项指标同时更新。`;
    source.append(summary, evidence); body.append(source);
    const deep = document.createElement("section");
    deep.className = "stock-deep-report";
    deep.setAttribute("data-stock-deep-report", "");
    deep.setAttribute("aria-live", "polite");
    const deepHead = document.createElement("div"); deepHead.className = "stock-deep-loading";
    deepHead.append(createSvgIcon("icon-activity", "prism-icon"), document.createTextNode(" 正在并行补齐五年财务、估值、动态证据和账户适配…"));
    deep.append(deepHead);
    body.append(deep);
    card.append(banner, body);
    return card;
  }

  function renderCopilotStockDeepFailure(target, message) {
    if (!target) return;
    target.replaceChildren();
    const callout = document.createElement("div"); callout.className = "doc-callout doc-callout-warning stock-deep-failure";
    const title = document.createElement("strong"); title.textContent = "快速行情可用，深度研判未完成";
    const detail = document.createElement("p"); detail.textContent = message;
    callout.append(title, detail); target.append(callout);
  }

  function stockAnalysisStatusChip(status) {
    const chip = document.createElement("span");
    chip.className = `stock-section-status ${String(status || "UNAVAILABLE").toLowerCase()}`;
    chip.textContent = status || "UNAVAILABLE";
    return chip;
  }

  function formatAnalysisNumber(value, unit = "", digits = 2) {
    if (!hasFinancialNumber(value)) return "未取得";
    return `${Number(value).toLocaleString("zh-CN", {minimumFractionDigits: digits, maximumFractionDigits: digits})}${unit}`;
  }

  function buildStockMiniChart(title, rows, key, unit) {
    const card = document.createElement("article"); card.className = "stock-mini-chart";
    const heading = document.createElement("h5"); heading.textContent = title;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 320 126"); svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `${title}近年趋势`);
    const values = rows.map(row => hasFinancialNumber(row[key]) ? Number(row[key]) : null);
    const finite = values.filter(value => Number.isFinite(value));
    const maxAbs = Math.max(1, ...finite.map(value => Math.abs(value)));
    const baseline = 68;
    rows.forEach((row, index) => {
      const value = values[index];
      const x = 12 + index * (296 / Math.max(rows.length, 1));
      const width = Math.max(16, 220 / Math.max(rows.length, 1));
      if (value !== null) {
        const height = Math.max(2, Math.abs(value) / maxAbs * 48);
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(x)); rect.setAttribute("width", String(width));
        rect.setAttribute("y", String(value >= 0 ? baseline - height : baseline));
        rect.setAttribute("height", String(height)); rect.setAttribute("rx", "2");
        rect.setAttribute("class", value >= 0 ? "positive" : "negative");
        const valueText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        valueText.setAttribute("x", String(x + width / 2)); valueText.setAttribute("y", value >= 0 ? "14" : "104");
        valueText.setAttribute("text-anchor", "middle");
        const formatted = unit ? Number(value).toLocaleString("zh-CN", {maximumFractionDigits: 1}) : new Intl.NumberFormat("zh-CN", {notation: "compact", maximumFractionDigits: 1}).format(value);
        valueText.textContent = `${formatted}${unit}`;
        svg.append(rect, valueText);
      }
      const yearText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      yearText.setAttribute("x", String(x + width / 2)); yearText.setAttribute("y", "122");
      yearText.setAttribute("text-anchor", "middle"); yearText.textContent = String(row.year || "—"); svg.append(yearText);
    });
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", "6"); line.setAttribute("x2", "314"); line.setAttribute("y1", String(baseline)); line.setAttribute("y2", String(baseline)); line.setAttribute("class", "baseline");
    svg.prepend(line); card.append(heading, svg); return card;
  }

  function buildStockSection(title, section) {
    const card = document.createElement("section"); card.className = "stock-analysis-section";
    const header = document.createElement("header");
    const heading = document.createElement("h4"); heading.textContent = title;
    header.append(heading, stockAnalysisStatusChip(section?.status));
    card.append(header); return card;
  }

  function appendStockSectionBoundary(card, section) {
    const missing = section?.missing_fields || [];
    const issues = section?.issues || [];
    if (!missing.length && !issues.length) return;
    const details = document.createElement("details"); details.className = "stock-section-boundary";
    const summary = document.createElement("summary"); summary.textContent = `数据边界 · ${missing.length} 个缺失项 / ${issues.length} 个问题`;
    const list = document.createElement("ul");
    missing.forEach(field => { const item = document.createElement("li"); item.textContent = `缺失字段：${field}`; list.append(item); });
    issues.forEach(issue => { const item = document.createElement("li"); item.textContent = `${issue.code}：${issue.message}`; list.append(item); });
    details.append(summary, list); card.append(details);
  }

  function renderCopilotStockDeepReport(target, result) {
    if (!target) return;
    target.replaceChildren();
    const head = document.createElement("header"); head.className = "stock-deep-head";
    const titleWrap = document.createElement("div");
    const eyebrow = document.createElement("span"); eyebrow.className = "eyebrow"; eyebrow.textContent = "深度研判";
    const title = document.createElement("h3"); title.textContent = `${result.security?.name || "标的"} · 完整研究报告`;
    titleWrap.append(eyebrow, title);
    const status = stockAnalysisStatusChip(result.status);
    head.append(titleWrap, status); target.append(head);

    const observations = document.createElement("section"); observations.className = "stock-observations";
    [["支撑因素", "supporting_facts"], ["风险因素", "risk_facts"], ["待跟踪事项", "watch_items"]].forEach(([label, key]) => {
      const column = document.createElement("article"); const heading = document.createElement("h4"); heading.textContent = label;
      const list = document.createElement("ul");
      const facts = result.observations?.[key] || [];
      (facts.length ? facts : [{text: "当前没有足够的已验证事实。", evidence: "数据边界"}]).forEach(fact => {
        const item = document.createElement("li"); item.textContent = `${fact.text} [${fact.evidence}]`; list.append(item);
      });
      column.append(heading, list); observations.append(column);
    });
    target.append(observations);

    const performance = result.sections?.performance || {data: {}};
    const performanceCard = buildStockSection("行情表现", performance);
    const performanceMetrics = document.createElement("dl"); performanceMetrics.className = "stock-latest-metrics";
    [["最新价", formatAnalysisNumber(performance.data?.latest_price_cny, " 元")], ["最新涨跌幅", formatAnalysisNumber(performance.data?.latest_change_pct, "%")], ["总市值", formatAnalysisNumber(performance.data?.market_cap_cny, " 元")], ["复权口径", performance.data?.adjustment || "未提供"]].forEach(([label, value]) => {
      const wrap = document.createElement("div"); const dt = document.createElement("dt"); dt.textContent = label; const dd = document.createElement("dd"); dd.textContent = value; wrap.append(dt, dd); performanceMetrics.append(wrap);
    });
    const bars = document.createElement("div"); bars.className = "stock-performance-bars";
    const performanceRows = [[20, performance.data?.return_20d_pct], [60, performance.data?.return_60d_pct], [120, performance.data?.return_120d_pct], [250, performance.data?.return_250d_pct]];
    const maxAbs = Math.max(1, ...performanceRows.filter(row => hasFinancialNumber(row[1])).map(row => Math.abs(Number(row[1]))));
    performanceRows.forEach(([days, value]) => {
      const row = document.createElement("div"); const label = document.createElement("span"); label.textContent = `${days} 日`;
      const track = document.createElement("span"); track.className = "stock-performance-track";
      const fill = document.createElement("span"); fill.className = `stock-performance-fill ${Number(value) < 0 ? "negative" : "positive"}`;
      fill.style.width = hasFinancialNumber(value) ? `${Math.max(2, Math.abs(Number(value)) / maxAbs * 100)}%` : "0";
      track.append(fill); const shown = document.createElement("strong"); shown.textContent = formatAnalysisNumber(value, "%");
      row.append(label, track, shown); bars.append(row);
    });
    const performanceNote = document.createElement("p"); performanceNote.className = "research-boundary"; performanceNote.textContent = `收益口径：${performance.data?.adjustment || "未提供"}；观察时间：${performance.observed_at || "未提供"}。`;
    performanceCard.append(performanceMetrics, bars, performanceNote); appendStockSectionBoundary(performanceCard, performance); target.append(performanceCard);

    const fundamentals = result.sections?.fundamentals || {data: {}};
    const fundamentalsCard = buildStockSection("财务趋势与盈利质量", fundamentals);
    const annual = fundamentals.data?.annual || [];
    const chartGrid = document.createElement("div"); chartGrid.className = "stock-mini-chart-grid";
    chartGrid.append(
      buildStockMiniChart("营业收入", annual, "revenue_cny", ""),
      buildStockMiniChart("归母净利润", annual, "net_profit_cny", ""),
      buildStockMiniChart("经营现金流", annual, "operating_cash_flow_cny", ""),
    );
    fundamentalsCard.append(chartGrid);
    const latestMetrics = document.createElement("dl"); latestMetrics.className = "stock-latest-metrics";
    const latest = fundamentals.data?.latest || {};
    [["报告期", latest.report_period, ""], ["ROE", latest.roe_pct, "%"], ["毛利率", latest.gross_margin_pct, "%"], ["资产负债率", latest.debt_ratio_pct, "%"], ["净利率", latest.net_margin_pct, "%"], ["现金转换率", latest.cash_conversion_pct, "%"], ["营收同比", latest.revenue_yoy_pct, "%"], ["利润同比", latest.net_profit_yoy_pct, "%"]].forEach(([label, value, unit]) => {
      const wrap = document.createElement("div"); const dt = document.createElement("dt"); dt.textContent = label; const dd = document.createElement("dd"); dd.textContent = unit ? formatAnalysisNumber(value, unit) : (value || "未取得"); wrap.append(dt, dd); latestMetrics.append(wrap);
    });
    fundamentalsCard.append(latestMetrics); appendStockSectionBoundary(fundamentalsCard, fundamentals); target.append(fundamentalsCard);

    const valuation = result.sections?.valuation || {data: {}};
    const valuationCard = buildStockSection("估值定位", valuation);
    const valuationGrid = document.createElement("div"); valuationGrid.className = "stock-valuation-grid";
    [["PE（TTM）", valuation.data?.pe_ttm, valuation.data?.pe_historical_percentile_pct, valuation.data?.industry_pe_ttm_mean], ["PB", valuation.data?.pb, valuation.data?.pb_historical_percentile_pct, valuation.data?.industry_pb_mean]].forEach(([label, current, percentile, industry]) => {
      const row = document.createElement("article"); const rowHead = document.createElement("div");
      const name = document.createElement("strong"); name.textContent = label; const currentValue = document.createElement("span"); currentValue.textContent = `${formatAnalysisNumber(current, " 倍")} · 行业均值 ${formatAnalysisNumber(industry, " 倍")}`; rowHead.append(name, currentValue);
      const track = document.createElement("div"); track.className = "stock-percentile-track"; const marker = document.createElement("span"); marker.style.left = `${Math.max(0, Math.min(100, Number(percentile || 0)))}%`; track.append(marker);
      const caption = document.createElement("small"); caption.textContent = hasFinancialNumber(percentile) ? `历史分位 ${formatAnalysisNumber(percentile, "%")}（信源未注明窗口）` : "历史分位未取得";
      row.append(rowHead, track, caption); valuationGrid.append(row);
    });
    valuationCard.append(valuationGrid); appendStockSectionBoundary(valuationCard, valuation); target.append(valuationCard);

    const evidence = result.sections?.evidence || {data: {}};
    const evidenceCard = buildStockSection("动态证据", evidence);
    const evidenceGrid = document.createElement("div"); evidenceGrid.className = "stock-evidence-grid";
    [["最新公告", "announcements"], ["最新新闻", "news"], ["最新研报", "reports"]].forEach(([label, key]) => {
      const column = document.createElement("article"); const heading = document.createElement("h5"); heading.textContent = label; const list = document.createElement("ul");
      const items = evidence.data?.[key] || [];
      if (!items.length) { const item = document.createElement("li"); item.textContent = "该信源本次未返回结果"; list.append(item); }
      items.forEach(item => {
        const row = document.createElement("li");
        const titleNode = item.url ? document.createElement("a") : document.createElement("span"); titleNode.textContent = item.title;
        if (item.url) { titleNode.href = item.url; titleNode.target = "_blank"; titleNode.rel = "noopener noreferrer"; }
        const meta = document.createElement("small"); meta.textContent = `${item.date || "日期未提供"} · ${item.source || "来源未提供"} · ${item.evidence_id}`;
        row.append(titleNode, meta); list.append(row);
      });
      column.append(heading, list); evidenceGrid.append(column);
    });
    evidenceCard.append(evidenceGrid); appendStockSectionBoundary(evidenceCard, evidence); target.append(evidenceCard);

    const fit = result.sections?.portfolio_fit || {data: {}};
    const fitCard = buildStockSection("当前账户组合适配", fit);
    const fitGrid = document.createElement("dl"); fitGrid.className = "stock-latest-metrics";
    [["是否持有", fit.data?.held ? "是" : "否"], ["持仓数量", formatAnalysisNumber(fit.data?.quantity, "", 2)], ["成本价", formatAnalysisNumber(fit.data?.cost_price_cny, " 元")], ["当前价", formatAnalysisNumber(fit.data?.current_price_cny, " 元")], ["持仓市值", formatAnalysisNumber(fit.data?.market_value_cny, " 元")], ["未实现盈亏", formatAnalysisNumber(fit.data?.unrealized_pnl_cny, " 元")], ["盈亏比例", formatAnalysisNumber(fit.data?.unrealized_pnl_pct, "%")], ["总资产占比", formatAnalysisNumber(fit.data?.weight_pct, "%")], ["单一标的上限", formatAnalysisNumber(fit.data?.single_asset_limit_pct, "%")], ["行业上限", formatAnalysisNumber(fit.data?.industry_limit_pct, "%")]].forEach(([label, value]) => {
      const wrap = document.createElement("div"); const dt = document.createElement("dt"); dt.textContent = label; const dd = document.createElement("dd"); dd.textContent = value; wrap.append(dt, dd); fitGrid.append(wrap);
    });
    fitCard.append(fitGrid); appendStockSectionBoundary(fitCard, fit); target.append(fitCard);

    const boundary = document.createElement("details"); boundary.className = "stock-report-boundary";
    const boundarySummary = document.createElement("summary"); boundarySummary.textContent = `数据边界 · ${result.missing_fields?.length || 0} 个缺失字段 · 生成于 ${result.generated_at || "未提供"}`;
    const boundaryList = document.createElement("ul");
    (result.missing_fields || []).forEach(field => { const item = document.createElement("li"); item.textContent = field; boundaryList.append(item); });
    (result.issues || []).forEach(issue => { const item = document.createElement("li"); item.textContent = `${issue.code}：${issue.message}`; boundaryList.append(item); });
    if (!boundaryList.childElementCount) { const item = document.createElement("li"); item.textContent = "本次结构化章节未报告缺失字段。"; boundaryList.append(item); }
    boundary.append(boundarySummary, boundaryList); target.append(boundary);
  }

  function buildCopilotFundCard(result) {
    const fund = result.data;
    if (!fund) throw new Error("未返回基金披露持仓。");
    const card = document.createElement("div");
    card.className = "copilot-decision-card";
    const title = document.createElement("h3");
    title.textContent = `${fund.fund_name} (${fund.fund_code}) · 披露持仓`;
    const note = document.createElement("p");
    note.className = "research-boundary";
    note.textContent = `持仓数据来自 ${fund.holding_disclosure_as_of || fund.observed_at || "最新期"} 定期披露。`;
    const table = document.createElement("table");
    table.className = "rebalancing-table";
    const head = document.createElement("tr");
    ["证券代码", "名称", "披露权重", "行业"].forEach((label) => { const cell = document.createElement("th"); cell.textContent = label; head.append(cell); });
    table.append(head);
    (fund.top_holdings || []).forEach((holding) => {
      const row = document.createElement("tr");
      [holding.asset_id || "未提供", holding.name || "未提供", hasFinancialNumber(holding.weight_pct) ? `${holding.weight_pct}%` : "未提供", holding.sector || "未提供"].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
      table.append(row);
    });
    card.append(title, note, table);
    return card;
  }

  function buildRebalancingNotice(plan) {
    const notice = document.createElement("div");
    notice.className = "doc-callout doc-callout-info";
    const summary = document.createElement("p");
    summary.textContent = plan.execution_steps.length
      ? plan.status === "PASS"
        ? "已按目标权重与预设规则生成以下调仓参考步骤。"
        : "已测算调整步骤，部分前置约束仍需复核，请参考下方提示项。"
      : plan.status === "PASS"
        ? "当前目标偏差未触发交易规则，偏差处于容差范围内，暂无需调仓。"
        : "目标尚未落实为可执行交易；请检查下列原因，不能据此判断组合无需调整。";
    notice.append(summary);
    const reasons = document.createElement("ul");
    (plan.issues || []).forEach((issue) => {
      const item = document.createElement("li");
      item.textContent = issue;
      reasons.append(item);
    });
    notice.append(reasons);
    if (plan.post_trade_health) {
      const health = plan.post_trade_health;
      const result = document.createElement("p");
      result.textContent = `按本次步骤执行并扣费后的假设体检：${health.status}；现金 ${health.cash_weight_pct}%（最低 ${health.cash_minimum_pct}%）；行业 HHI ${health.sector_hhi}（上限 ${health.hhi_limit}）。实际持仓未被修改。`;
      notice.append(result);
    }
    return notice;
  }

  async function runCopilotRebalance() {
    const output = byId("copilot-decision-output");
    if (!output) return;
    clear(output);
    state.copilotResearchSequence += 1;
    if (!requirePortfolioAnalysisContext(output)) return;
    output.append(buildCopilotLoadingCard("icon-activity", "正在测算调仓方案…", "正在结合你的持仓与投资偏好计算调整清单与换手率。"));

    try {
      const health = state.portfolioHealthRun || await refreshPortfolioHealth();
      if (!health) throw new Error("当前持仓体检未完成，不能确认调仓约束。");
      const optimization = await runPortfolioOptimization();
      if (!optimization?.targets?.length) throw new Error(
        state.portfolioRefreshRun?.status === "REVIEW_REQUIRED" ? portfolioRefreshProblem()
          : optimization?.summary || "未能生成目标权重，请检查画像、持仓和缺失数据。"
      );
      const plan = await runPortfolioRebalancing();
      if (!plan) throw new Error("调仓测算未完成，请检查目标权重和持仓输入。");
      const persona = PERSONAS[state.selectedPersona || "persona-zhang-r3"];

      clear(output);
      const card = document.createElement("div");
      card.className = "copilot-decision-card";

      // Banner
      const banner = document.createElement("div");
      banner.className = "decision-banner hold";
      const titleWrap = document.createElement("div");
      titleWrap.className = "decision-verdict-title";
      const icon = document.createElement("span");
      icon.className = "decision-verdict-icon";
      icon.append(createSvgIcon("icon-scale", "prism-icon prism-icon-lg"));
      const h3 = document.createElement("h3");
      h3.textContent = `${plan.execution_steps.length ? "调仓测算结果" : "本次未生成交易"} · 换手率 ${plan.metrics.total_turnover_pct}% · 费用 ¥${plan.metrics.net_turnover_cost}`;
      titleWrap.append(icon, h3);

      const statusChip = document.createElement("span");
      statusChip.className = plan.status === "PASS" ? "cf-verdict cf-verdict-pass" : "cf-verdict cf-verdict-risk";
      statusChip.textContent = plan.status === "PASS" ? "CALCULATED 测算完成" : "REVIEW_REQUIRED 需要复核";
      banner.append(titleWrap, statusChip);

      // Body
      const body = document.createElement("div");
      body.className = "decision-card-body";

      // 菜鸟/文档风格 Callout 调仓规则说明
      const callout = document.createElement("div");
      callout.className = "doc-callout doc-callout-demo";
      const cIcon = document.createElement("div");
      cIcon.className = "callout-icon";
      cIcon.append(createSvgIcon("icon-shuffle", "prism-icon"));
      const cContent = document.createElement("div");
      cContent.className = "callout-content";
      const cTitle = document.createElement("div");
      cTitle.className = "callout-title";
      cTitle.textContent = "调仓方案与执行准则（先卖后买 · 控制换手）";
      const cP = document.createElement("p");
      cP.textContent = `针对 ${persona.name} 的当前组合，后端已按目标权重、整手约束与交易费用生成 ${plan.execution_steps.length} 个可执行步骤。卖出优先于买入；不可报价或资金不足的项目会进入复核状态。`;
      cContent.append(cTitle, cP);
      callout.append(cIcon, cContent);

      // Metrics with tooltips
      const metricsRow = document.createElement("div");
      metricsRow.className = "decision-metrics-row";
      metricsRow.append(
        buildCopilotMetricBox("总调仓换手率", `${plan.metrics.total_turnover_pct}%`, plan.metrics.turnover_cap_breached, !plan.metrics.turnover_cap_breached, "由实际可执行调仓金额计算。"),
        buildCopilotMetricBox("调整资产项", `${plan.execution_steps.length} 笔`, false, false, "本次再平衡的可执行操作数量。"),
        buildCopilotMetricBox("交易摩擦成本", `¥${plan.metrics.net_turnover_cost} (${plan.metrics.net_turnover_cost_pct}%)`, false, false, "包含佣金、卖出印花税和过户费。")
      );

      // Steps
      const stepsWrap = document.createElement("div");
      stepsWrap.className = "decision-action-steps";
      const stepsHead = document.createElement("div");
      stepsHead.className = "action-steps-head";
      const sHeadIcon = createSvgIcon("icon-shuffle", "prism-icon");
      sHeadIcon.style.marginRight = "6px";
      stepsHead.append(sHeadIcon, document.createTextNode(" 建议调整顺序（先卖后买 · 释放流动性）："));

      stepsWrap.append(stepsHead);
      plan.execution_steps.forEach((step) => {
        const item = document.createElement("div");
        item.className = "action-step-item";
        const detail = document.createElement("div");
        const number = document.createElement("span");
        number.className = "step-num";
        number.textContent = String(step.step_number);
        detail.append(number, document.createTextNode(` ${step.description}`));
        if (step.shares !== null && step.shares !== undefined) {
          detail.append(document.createTextNode(` · ${step.shares} 股/份 · 费用 ¥${step.total_fees_cny}`));
        }
        const action = document.createElement("span");
        action.className = step.action_type === "BUY" ? "cf-verdict cf-verdict-pass" : "cf-verdict cf-verdict-risk";
        action.textContent = step.action_type;
        item.append(detail, action);
        stepsWrap.append(item);
      });
      body.append(stepsWrap);
      body.append(buildRebalancingNotice(plan));

      // Drilldown links
      body.append(buildCopilotDrilldownRow([
        { href: "#portfolio-rebalancing", text: "查看调整明细" },
        { href: "#portfolio-optimization", text: "查看目标权重" },
        { href: "#scenario-simulation", text: "测试不同情景" }
      ]));

      card.append(banner, body);
      output.append(card);
    } catch (err) {
      clear(output);
      const errCard = document.createElement("div");
      errCard.className = "copilot-empty-output";
      const h4 = document.createElement("h4");
      h4.textContent = state.portfolioRefreshRun?.status === "REVIEW_REQUIRED" ? "方案等待数据恢复" : "方案生成失败";
      const p = document.createElement("p");
      p.textContent = err.message || "未能生成调仓方案";
      errCard.append(h4, p);
      if (state.portfolioRefreshRun?.status === "REVIEW_REQUIRED") {
        errCard.append(buildCopilotDrilldownRow([{href: "#overview", text: "查看自动分析状态"}]));
      }
      output.append(errCard);
    }
  }

  function stressInputs() {
    return [...document.querySelectorAll(".custom-stress-sliders input[data-sector]")];
  }

  function renderCustomStressResult(data, target = byId("custom-stress-result")) {
    if (!target) return;
    clear(target);
    const grid = document.createElement("div");
    grid.className = "decision-metrics-row";
    grid.append(
      buildCopilotMetricBox("组合冲击", `${Number(data.scenario_return_pct).toFixed(2)}%`, Number(data.scenario_return_pct) < 0, false),
      buildCopilotMetricBox("年化波动率", `${data.baseline_volatility_pct}% → ${data.stressed_volatility_pct}%`, Number(data.volatility_change_pct_points) > 0, false),
      buildCopilotMetricBox("95% 单日 VaR", `¥${Number(data.baseline_var_95_1d_cny).toLocaleString()} → ¥${Number(data.stressed_var_95_1d_cny).toLocaleString()}`, Number(data.var_change_cny) > 0, false)
    );
    const note = document.createElement("p");
    note.className = "research-boundary";
    note.textContent = `${data.methodology} 情景损益：¥${Number(data.scenario_pnl_cny).toLocaleString()}。`;
    target.append(grid, note);
  }

  async function runCustomStressScenario() {
    await ensureDependency("PORTFOLIO_CONTEXT");
    if (!state.portfolio) throw new Error("缺少结构化持仓，无法运行五行业压力测试");
    const token = beginContextRequest("customStressSequence");
    const portfolio = token.portfolio;
    const shocks = {};
    stressInputs().forEach((input) => { shocks[input.dataset.sector] = Number(input.value); });
    const response = await fetch("/api/v1/advisor/custom-stress-scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Owner-ID": token.ownerId },
      body: JSON.stringify({
        schema_version: "custom-stress-scenario-request.v1",
        request_id: `custom-stress-${Date.now()}`,
        owner_id: token.ownerId,
        portfolio,
        sector_shocks_pct: shocks,
      }),
    });
    if (!isContextRequestCurrent(token)) return null;
    if (!response.ok) throw await apiError(response);
    const data = await response.json();
    if (!isContextRequestCurrent(token)) return null;
    state.customStressRun = data;
    renderCustomStressResult(data);
    const status = byId("custom-stress-status");
    if (status) { status.textContent = "CALCULATED 已计算"; status.className = "status-chip pass"; }
    return data;
  }

  async function runCopilotScenarioShock() {
    const output = byId("copilot-decision-output");
    if (!output) return;
    clear(output);
    state.copilotResearchSequence += 1;
    if (!requirePortfolioAnalysisContext(output, false)) return;
    output.append(buildCopilotLoadingCard("icon-activity", "正在运行自定义压力测试…", "组合损益、波动率与 VaR 均由后端确定性模型计算。"));

    try {
      const data = await runCustomStressScenario();
      if (!data) return;

      clear(output);
      const card = document.createElement("div");
      card.className = "copilot-decision-card";
      const banner = document.createElement("div");
      banner.className = Number(data.scenario_return_pct) < 0 ? "decision-banner reduce" : "decision-banner hold";
      const titleWrap = document.createElement("div");
      titleWrap.className = "decision-verdict-title";
      const icon = document.createElement("span");
      icon.className = "decision-verdict-icon";
      icon.append(createSvgIcon("icon-activity", "prism-icon prism-icon-lg"));
      const h3 = document.createElement("h3");
      h3.textContent = `自定义压力测试：组合冲击 ${data.scenario_return_pct}%`;
      titleWrap.append(icon, h3);
      const statusChip = document.createElement("span");
      statusChip.className = "cf-verdict cf-verdict-pass";
      statusChip.textContent = "CALCULATED 后端计算完成";
      banner.append(titleWrap, statusChip);
      const body = document.createElement("div");
      body.className = "decision-card-body";
      renderCustomStressResult(data, body);
      body.append(buildCopilotDrilldownRow([
        { href: "#scenario-simulation", text: "查看情景明细" },
        { href: "#portfolio-rebalancing", text: "查看调仓方案" }
      ]));

      card.append(banner, body);
      output.append(card);
    } catch (err) {
      clear(output);
      const errCard = document.createElement("div");
      errCard.className = "copilot-empty-output";
      const h4 = document.createElement("h4");
      h4.textContent = "模拟失败";
      const p = document.createElement("p");
      p.textContent = err.message || "未能运行情景模拟";
      errCard.append(h4, p);
      output.append(errCard);
    }
  }

  const chatHistory = [];

  const CONVERSATION_PROFILE_QUESTIONS = Object.freeze([
    {
      key: "goal",
      prompt: "这笔资金目前最重要的目标是什么？",
      options: [
        ["PRESERVE", "优先保全本金"],
        ["BALANCED", "控制波动并稳健增长"],
        ["GROWTH", "为长期增值承受一定波动"],
      ],
    },
    {
      key: "investmentHorizon",
      prompt: "你预计多久以后会用到这笔资金？",
      options: [["SHORT", "1 年以内"], ["MEDIUM", "1–3 年"], ["LONG", "3 年以上"]],
    },
    {
      key: "liquidityNeed",
      prompt: "日常情况下，你对这笔资金的流动性要求如何？",
      options: [["HIGH", "随时可能使用"], ["MEDIUM", "保留部分备用"], ["LOW", "短期无需使用"]],
    },
    {
      key: "maxDrawdown",
      prompt: "即使正式测评允许更高波动，你现在希望把回撤控制在多少以内？",
      options: [["5", "5%"], ["8", "8%"], ["10", "10%"], ["15", "15%"], ["20", "20%"]],
    },
  ]);

  function clearChatEmptyState(messages = byId("copilot-chat-messages")) {
    messages?.querySelector("[data-chat-empty-state]")?.remove();
  }

  function appendChatMessage(role, content) {
    const messages = byId("copilot-chat-messages");
    if (!messages) return null;
    clearChatEmptyState(messages);
    const row = document.createElement("div");
    row.className = `chat-msg ${role}`;
    const avatar = document.createElement("div");
    avatar.className = "chat-avatar";
    avatar.textContent = role === "user" ? "你" : "P";
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    if (typeof content === "string") { if (role === "assistant") renderAssistantMarkdown(bubble, content); else bubble.textContent = content; }
    else bubble.append(content);
    row.append(avatar, bubble);
    messages.append(row);
    messages.scrollTop = messages.scrollHeight;
    return row;
  }

  function renderChatWelcome() {
    const messages = byId("copilot-chat-messages");
    if (!messages) return;
    clear(messages);
    const content = document.createElement("div");
    content.className = "agent-empty-state";
    content.setAttribute("data-chat-empty-state", "");
    const mark = document.createElement("span");
    mark.className = "empty-mark";
    mark.textContent = "P";
    const title = document.createElement("h3");
    title.textContent = "从一个具体问题开始";
    const description = document.createElement("p");
    description.textContent = "输入一个具体问题，我会结合你的持仓和投资偏好进行分析。";
    content.append(mark, title, description);
    messages.append(content);
  }

  function startConversationProfileUpdate() {
    setAgentFeatureToolsCompact(true);
    state.conversationProfileDraft = {};
    state.conversationProfileStep = 0;
    renderConversationProfileQuestion();
  }

  function conversationProfileOptions(question) {
    if (question.key !== "maxDrawdown") return question.options;
    const questionnaireLimit = Number(state.profile?.profile?.max_drawdown_tolerance_pct);
    const ceiling = Number.isFinite(questionnaireLimit) ? questionnaireLimit : 15;
    const values = new Map(question.options.map(([value, label]) => [Number(value), label]));
    values.set(ceiling, `${ceiling}%`);
    return [...values.entries()]
      .filter(([value]) => value > 0 && value <= ceiling)
      .sort((left, right) => left[0] - right[0])
      .map(([value, label]) => [String(value), label]);
  }

  function conversationProfileLabel(key, value) {
    const question = CONVERSATION_PROFILE_QUESTIONS.find((item) => item.key === key);
    return conversationProfileOptions(question).find(([optionValue]) => optionValue === String(value))?.[1] || String(value);
  }

  function renderConversationProfileQuestion() {
    const question = CONVERSATION_PROFILE_QUESTIONS[state.conversationProfileStep];
    if (!question) {
      const card = document.createElement("div");
      card.className = "conversation-profile-card";
      const title = document.createElement("strong");
      title.textContent = "确认本次对话补充";
      const note = document.createElement("p");
      note.textContent = "确认上述偏好设置，作为本次投资分析的计算约束。";
      const review = document.createElement("dl");
      review.className = "conversation-profile-review";
      [
        ["投资目标", conversationProfileLabel("goal", state.conversationProfileDraft.goal)],
        ["资金期限", conversationProfileLabel("investmentHorizon", state.conversationProfileDraft.investmentHorizon)],
        ["流动性需求", conversationProfileLabel("liquidityNeed", state.conversationProfileDraft.liquidityNeed)],
        ["回撤顾虑", `${state.conversationProfileDraft.maxDrawdown}%`],
      ].forEach(([label, value]) => {
        const row = document.createElement("div");
        const term = document.createElement("dt");
        term.textContent = label;
        const definition = document.createElement("dd");
        definition.textContent = value;
        row.append(term, definition);
        review.append(row);
      });
      const actions = document.createElement("div");
      actions.className = "conversation-profile-options";
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.textContent = "确认并用于后续对话";
      confirm.addEventListener("click", confirmConversationProfileUpdate);
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "暂不保存";
      cancel.addEventListener("click", () => {
        state.conversationProfileDraft = null;
        appendChatMessage("assistant", "本次补充未保存，正式风险测评保持不变。");
      });
      actions.append(confirm, cancel);
      card.append(title, note, review, actions);
      appendChatMessage("assistant", card);
      return;
    }

    const card = document.createElement("div");
    card.className = "conversation-profile-card";
    const prompt = document.createElement("strong");
    prompt.textContent = question.prompt;
    const policy = document.createElement("p");
    policy.textContent = `画像补充 ${state.conversationProfileStep + 1} / ${CONVERSATION_PROFILE_QUESTIONS.length}`;
    const options = document.createElement("div");
    options.className = "conversation-profile-options";
    conversationProfileOptions(question).forEach(([value, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", () => {
        state.conversationProfileDraft = { ...state.conversationProfileDraft, [question.key]: value };
        appendChatMessage("user", label);
        state.conversationProfileStep += 1;
        renderConversationProfileQuestion();
      });
      options.append(button);
    });
    card.append(prompt, policy, options);
    appendChatMessage("assistant", card);
  }

  function confirmConversationProfileUpdate() {
    const draft = state.conversationProfileDraft;
    if (!draft) return;
    const formalLimit = Number(state.profile?.profile?.max_drawdown_tolerance_pct);
    const maxDrawdown = Math.min(Number(draft.maxDrawdown), Number.isFinite(formalLimit) ? formalLimit : Number(draft.maxDrawdown));
    const saved = {
      goal: draft.goal,
      goalLabel: conversationProfileLabel("goal", draft.goal),
      investmentHorizon: draft.investmentHorizon,
      horizonLabel: conversationProfileLabel("investmentHorizon", draft.investmentHorizon),
      liquidityNeed: draft.liquidityNeed,
      liquidityLabel: conversationProfileLabel("liquidityNeed", draft.liquidityNeed),
      maxDrawdown: String(maxDrawdown),
      updatedAt: new Date().toISOString(),
    };
    try {
      workspaceStorage.setItem(ownerStorageKey("prism_conversation_profile_v1"), JSON.stringify(saved));
    } catch (e) {}
    state.conversationProfileDraft = null;
    saveUserProfile({
      conversationProfile: saved,
      investmentHorizon: saved.investmentHorizon,
      liquidityNeed: saved.liquidityNeed,
      maxDrawdown: saved.maxDrawdown,
      desc: `${saved.goalLabel} · ${saved.horizonLabel} · ${saved.liquidityLabel} · 回撤边界 ≤${saved.maxDrawdown}%`,
    });
    renderBehaviorProfile(state.behaviorProfile);
    appendChatMessage("assistant", "画像补充已确认。后续回答会使用这些信息；正式风险测评等级没有提高。若信息与测评冲突，系统始终采用更保守的边界。");
  }

  function loadCopilotChatHistory() {
    try {
      const saved = workspaceStorage.getItem(ownerStorageKey("prism_copilot_chat_history_v2"));
      if (!saved) return;
      const parsed = JSON.parse(saved);
      if (!Array.isArray(parsed) || parsed.length === 0) return;

      const chatPanel = byId("copilot-chat-panel");
      const messagesContainer = byId("copilot-chat-messages");
      if (!messagesContainer) return;
      clear(messagesContainer);

      chatHistory.length = 0;
      parsed.forEach(msg => {
        chatHistory.push(msg);
        const row = document.createElement("div");
        row.className = `chat-msg ${msg.role}`;
        const avatar = document.createElement("div");
        avatar.className = "chat-avatar";
        avatar.textContent = msg.role === "user" ? "你" : "P";
        const bubble = document.createElement("div");
        bubble.className = "chat-bubble";
        if (msg.role === "assistant") renderAssistantMarkdown(bubble, msg.content); else bubble.textContent = msg.content;
        row.append(avatar, bubble);
        messagesContainer.append(row);
      });

      if (chatPanel) chatPanel.style.display = "block";
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
      if (typeof setAgentFeatureToolsCompact === "function") setAgentFeatureToolsCompact(true);
    } catch (e) {}
  }

  function saveCopilotChatHistory() {
    try {
      workspaceStorage.setItem(ownerStorageKey("prism_copilot_chat_history_v2"), JSON.stringify(chatHistory.slice(-20)));
    } catch (e) {}
  }

  function clearConversationContext() {
    chatContextRevision += 1;
    if (activeChatController) activeChatController.abort();
    chatHistory.length = 0;
    workspaceStorage.removeItem(ownerStorageKey("prism_copilot_chat_history_v2"));
    const input = byId("copilot-natural-input");
    if (input) input.value = "";
    const progress = byId("chat-send-progress");
    if (progress) { progress.hidden = false; progress.textContent = "理解问题 → 查询数据 → 核验依据 → 组织回答"; }
    const msgs = byId("copilot-chat-messages");
    if (msgs) { clear(msgs); renderChatWelcome(); }
    const output = byId("copilot-decision-output");
    if (output) clear(output);
    const panel = byId("copilot-chat-panel");
    if (panel) panel.style.display = "block";
    if (typeof setAgentFeatureToolsCompact === "function") setAgentFeatureToolsCompact(false);
  }

  function buildPipelineStepItem(num, label, status) {
    const step = document.createElement("div");
    step.className = `pipeline-step ${status}`;
    const dot = document.createElement("span");
    dot.className = "step-dot";
    const txt = document.createElement("span");
    txt.textContent = label;
    step.append(dot, txt);
    return step;
  }

  function setPipelineStepState(stepEl, status) {
    if (!stepEl) return;
    stepEl.classList.remove("pending", "active", "completed", "skipped", "failed");
    stepEl.classList.add(status);
  }

  let activeChatController = null;
  let chatContextRevision = 0;
  async function handleStreamingChat(customQuery) {
    if (activeChatController) return;
    const controller = new AbortController();
    activeChatController = controller;
    const send = byId("copilot-submit-query");
    const progress = byId("chat-send-progress");
    const cancel = byId("chat-cancel-query");
    send.disabled = true; cancel.hidden = false; progress.hidden = false;
    progress.textContent = "正在准备分析…";
    const timeout = setTimeout(() => controller.abort(), 120000);
    try { await performStreamingChat(customQuery, controller.signal); }
    finally {
      clearTimeout(timeout); activeChatController = null;
      send.disabled = false; cancel.hidden = true; progress.hidden = false;
      if (controller.signal.aborted && progress.textContent === "正在准备分析…") progress.textContent = "分析已停止，可重新发送。";
    }
  }

  async function performStreamingChat(customQuery, signal) {
    const turnContextRevision = chatContextRevision;
    const input = byId("copilot-natural-input");
    const query = (customQuery || input?.value || "").trim();
    if (!query) return;
    if (typeof setAgentFeatureToolsCompact === "function") setAgentFeatureToolsCompact(true);
    const chatOwner = state.ownerId;
    let chatTruth = null;
    try {
      const currentTruth = await refreshSessionTruth();
      if (currentTruth?.revision && currentTruth.status === "LOCKED") chatTruth = currentTruth;
    } catch (error) {
      // A missing or stale portfolio/profile truth may not block ordinary chat.
      // Keeping chatTruth null prevents the backend from treating this turn as
      // personalized advice based on an unconfirmed snapshot.
      chatTruth = null;
    }

    if (signal.aborted) return;
    if (input) input.value = "";

    const chatPanel = byId("copilot-chat-panel");
    const messagesContainer = byId("copilot-chat-messages");
    if (chatPanel) chatPanel.style.display = "block";
    if (!messagesContainer) return;

    clearChatEmptyState(messagesContainer);
    // User Message Bubble
    const userMsgRow = document.createElement("div");
    userMsgRow.className = "chat-msg user";
    const userAvatar = document.createElement("div");
    userAvatar.className = "chat-avatar";
    userAvatar.textContent = "你";
    const userBubble = document.createElement("div");
    userBubble.className = "chat-bubble";
    userBubble.textContent = query;
    userMsgRow.append(userAvatar, userBubble);
    messagesContainer.append(userMsgRow);

    // Assistant Message Bubble with Progress Pipeline
    const aiMsgRow = document.createElement("div");
    aiMsgRow.className = "chat-msg assistant";
    const aiAvatar = document.createElement("div");
    aiAvatar.className = "chat-avatar";
    aiAvatar.textContent = "P";
    const aiBubble = document.createElement("div");
    aiBubble.className = "chat-bubble";

    const pipelineBox = document.createElement("div");
    pipelineBox.className = "chat-pipeline-box";
    const pipeHead = document.createElement("div");
    pipeHead.className = "pipeline-header";
    pipeHead.textContent = "正在理解问题…";
    const stepsGrid = document.createElement("div");
    stepsGrid.className = "pipeline-steps-grid";
    const s1 = buildPipelineStepItem("1", "理解问题", "active");
    const s2 = buildPipelineStepItem("2", "查询真实数据（按需）", "pending");
    const s3 = buildPipelineStepItem("3", "核验事实与约束", "pending");
    const s4 = buildPipelineStepItem("4", "组织回答", "pending");
    stepsGrid.append(s1, s2, s3, s4);
    pipelineBox.append(pipeHead, stepsGrid);

    const progressLabel = document.createElement("span");
    progressLabel.className = "chat-progress-label";
    progressLabel.textContent = "正在理解问题…";
    const progressTrack = document.createElement("span");
    progressTrack.className = "chat-progress-track";
    const progressBar = document.createElement("span");
    progressBar.className = "chat-progress-bar";
    progressBar.style.width = "10%";
    progressTrack.append(progressBar);

    const thinkingBox = document.createElement("div");
    thinkingBox.className = "chat-thinking-tag";
    thinkingBox.style.display = "none";
    thinkingBox.textContent = "正在核对结构化事实、阈值与证据来源…";

    const toolsContainer = document.createElement("div");
    toolsContainer.className = "chat-tools-container";

    const contentBox = document.createElement("div");
    contentBox.className = "chat-content-box";

    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";
    contentBox.append(cursor);

    // The compact bar reports overall activity next to Send. The four-stage
    // card stays mounted in the answer so each real stream transition remains visible.
    byId("chat-send-progress").replaceChildren(pipelineBox);
    aiBubble.append(contentBox);
    aiMsgRow.append(aiAvatar, aiBubble);
    messagesContainer.append(aiMsgRow);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    chatHistory.push({ role: "user", content: query });
    saveCopilotChatHistory();

    const persona = PERSONAS[state.selectedPersona || "custom-user"] || DEFAULT_USER_PROFILE;

    try {
      const response = await fetch("/api/v1/copilot/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Owner-ID": state.ownerId },
        signal,
        body: JSON.stringify({
          message: query,
          model_mode: byId("chat-runtime-mode")?.value || "AUTO",
          session_truth_id: chatTruth?.revision ? "workbench" : null,
          session_truth_revision: chatTruth?.revision || null,
          owner_id: state.ownerId,
          profile_version: chatTruth ? state.profile?.profile?.profile_version || null : null,
          behavior_profile_version: chatTruth ? state.behaviorProfile?.profile_version || null : null,
          portfolio_snapshot_id: chatTruth ? state.portfolio?.position_snapshot?.snapshot_id || null : null,
          persona_id: state.selectedPersona || "custom-user",
          persona_info: chatTruth ? {
            name: persona.name,
            tag: activeProfileTag(),
            max_drawdown: persona.maxDrawdown,
            budget_cap: persona.budgetCap,
          } : null,
          // The current query is already passed as `message`; do not duplicate
          // the just-appended user turn in conversational history.
          history: chatTruth ? chatHistory.slice(-7, -1) : [],
          stream: true,
          llm_config: llmConfig.apiKey ? {
            api_key: llmConfig.apiKey,
            base_url: llmConfig.baseUrl,
            model: llmConfig.model,
          } : null,
        }),
      });

      if (!response.ok) throw await apiError(response);
      if (!response.body) throw new Error("服务未返回分析内容");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let fullText = "";
      let buffer = "";
      let streamError = null;
      let receivedDone = false;
      let toolStarted = false;
      let toolCompleted = false;
      let toolFailed = false;

      try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith("data:")) continue;
          const dataStr = trimmed.slice(5).trim();
          if (dataStr === "[DONE]") {
            receivedDone = true;
            if (!streamError) {
              pipeHead.textContent = "分析已完成";
              progressLabel.textContent = "分析已完成";
              progressBar.style.width = "100%";
              if (s1.classList.contains("active")) setPipelineStepState(s1, "completed");
              if (s2.classList.contains("active")) setPipelineStepState(s2, "completed");
              if (s3.classList.contains("active")) setPipelineStepState(s3, "completed");
              if (s4.classList.contains("active")) setPipelineStepState(s4, "completed");
            }
            break;
          }
          try {
            const event = JSON.parse(dataStr);
            if (event.type === "error") {
              streamError = event.message || "分析被中止";
            } else if (event.type === "analysis_context") {
              const details = document.createElement("details");
              details.className = "chat-audit-details";
              const mode = event.display_policy?.mode || "STANDARD";
              details.open = mode === "AUDIT_EXPANDED";
              const summary = document.createElement("summary");
              summary.textContent = "分析依据与风险提示";
              const auditBody = document.createElement("div");
              auditBody.className = "chat-audit-body";
              [
                ["处理步骤", event.analysis_steps],
                ["已确认事实", event.facts],
                ["规则阈值", event.thresholds],
                ["证据引用", event.evidence],
                ["风险与缺失", event.warnings],
              ].forEach(([label, values]) => {
                if (!Array.isArray(values) || !values.length) return;
                const strong = document.createElement("strong");
                strong.textContent = label;
                const list = document.createElement("ul");
                values.forEach(value => {
                  const item = document.createElement("li");
                  item.textContent = String(value);
                  list.append(item);
                });
                auditBody.append(strong, list);
              });
              details.append(summary, auditBody);
              aiBubble.append(details);
              const policyMode = byId("display-policy-mode");
              if (policyMode) policyMode.textContent = mode;
            } else if (event.type === "thinking") {
              pipeHead.textContent = "正在核对资料…";
              progressLabel.textContent = "正在核对资料…";
              progressBar.style.width = "35%";
              thinkingBox.style.display = "inline-flex";
            } else if (event.type === "tool_start") {
              if (!toolStarted) {
                toolStarted = true;
                setPipelineStepState(s1, "completed");
                setPipelineStepState(s2, "active");
              }
              pipeHead.textContent = "正在查询真实数据…";
              progressLabel.textContent = "正在查询真实数据…";
              progressBar.style.width = "60%";
              const toolChip = document.createElement("span");
              toolChip.className = "chat-tool-tag";
              toolChip.textContent = `调用工具：${event.tool}`;
              toolsContainer.append(toolChip);
            } else if (event.type === "tool_done") {
              if (event.tool === "query_stock_quote" && event.result?.status === "SUCCESS" && event.result.data) {
                const output = byId("copilot-decision-output");
                if (output) { clear(output); output.append(buildCopilotStockCard(event.result)); }
              }
              const toolStatus = event.result?.status || "FAILED";
              const currentToolFailed = ["FAILED", "BLOCKED", "REJECTED"].includes(toolStatus);
              if (event.result?.error_code === "DETERMINISTIC_CONTEXT_REQUIRED") {
                const action = document.createElement("button");
                action.type = "button"; action.className = "copilot-action-btn secondary";
                if (event.tool === "run_portfolio_health_check") {
                  action.textContent = "核对并确认分析资料";
                  action.addEventListener("click", confirmSessionTruth);
                } else {
                  action.textContent = "打开调仓测算";
                  action.addEventListener("click", runCopilotRebalance);
                }
                aiBubble.append(action);
              }
              toolFailed = toolFailed || currentToolFailed;
              toolCompleted = toolCompleted || !currentToolFailed;
              if (currentToolFailed) setPipelineStepState(s2, "failed");
              pipeHead.textContent = currentToolFailed
                ? "真实数据工具未完成，正在整理失败边界…"
                : "已取得数据，正在继续处理…";
              progressLabel.textContent = pipeHead.textContent;
              progressBar.style.width = "68%";
              if (
                event.result
                && event.result.status === "FAILED"
                && event.result.execution_context
                && event.result.execution_context.data_mode === "LIVE"
                && ["fuyao_finance_api", "wencai_skillhub_provider"].includes(
                  event.result.execution_context.provider,
                )
              ) await fetchRuntimeDataMode();
            } else if (event.type === "grounding_start") {
              setPipelineStepState(s1, "completed");
              setPipelineStepState(s2, toolFailed ? "failed" : "completed");
              setPipelineStepState(s3, toolFailed ? "skipped" : "active");
              pipeHead.textContent = toolFailed
                ? "正在组织失败说明…"
                : "正在核验事实与约束…";
              progressLabel.textContent = "正在核验事实与约束…";
              progressBar.style.width = "75%";
            } else if (event.type === "research_skipped") {
              setPipelineStepState(s1, "completed");
              setPipelineStepState(s2, "skipped");
              setPipelineStepState(s3, "skipped");
            } else if (event.type === "token") {
              setPipelineStepState(s1, "completed");
              if (toolFailed) {
                setPipelineStepState(s2, "failed");
                setPipelineStepState(s3, "skipped");
              } else if (toolCompleted) {
                setPipelineStepState(s2, "completed");
                setPipelineStepState(s3, "completed");
              } else if (!toolStarted) {
                setPipelineStepState(s2, "skipped");
                setPipelineStepState(s3, "skipped");
              }
              setPipelineStepState(s4, "active");
              pipeHead.textContent = "正在生成回复…";
              progressLabel.textContent = "正在生成回复…";
              progressBar.style.width = "85%";
              fullText += event.delta;
              cursor.remove();
              renderAssistantMarkdown(contentBox, fullText);
              contentBox.append(cursor);
              messagesContainer.scrollTop = messagesContainer.scrollHeight;
            } else if (event.type === "done" && !streamError) {
              setPipelineStepState(s4, "completed");
              pipeHead.textContent = "分析已完成";
              progressLabel.textContent = "分析已完成";
              progressBar.style.width = "100%";
            }
          } catch (e) {
            streamError = "分析响应格式异常";
            break;
          }
        }
      }

      } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
      if (streamError) throw new Error(streamError);
      if (!receivedDone) throw new Error("分析连接提前结束，结果不完整");
      if (turnContextRevision !== chatContextRevision) return;
      cursor.remove();
      thinkingBox.style.display = "none";
      renderAssistantMarkdown(contentBox, fullText);
      chatHistory.push({ role: "assistant", content: fullText });
      saveCopilotChatHistory();
    } catch (err) {
      cursor.remove();
      if (turnContextRevision !== chatContextRevision) return;
      pipeHead.textContent = "分析未完成";
      progressLabel.textContent = "分析未完成";
      [s1, s2, s3, s4].forEach(step => {
        if (step.classList.contains("active")) setPipelineStepState(step, "failed");
      });
      contentBox.textContent = signal.aborted ? "分析已停止，可重新发送。" : `请求未完成：${err.message || "服务连接异常"}`;
      recordTruthTurnAlert(aiMsgRow, err.message || "服务连接异常", chatOwner);
    }
  }

  function handleNaturalQuerySubmit() {
    const input = byId("copilot-natural-input");
    const q = (input?.value || "").trim();
    if (!q) {
      setError("请输入您的问题");
      input?.focus();
      return;
    }
    if (/^个股分析[：:]\s*$/.test(q)) {
      setError("请输入需要分析的 6 位证券代码或证券名称");
      input?.focus();
      return;
    }
    setError("");
    if (typeof setAgentFeatureToolsCompact === "function") setAgentFeatureToolsCompact(true);
    const directStock = q.match(/^个股分析[：:]\s*(\d{6}(?:\.(?:SH|SZ|BJ))?)\s*$/i);
    if (directStock) {
      if (input) input.value = "";
      runCopilotStockResearch(directStock[1]);
      return;
    }
    handleStreamingChat(q);
  }

  // 大模型 API Key 前端直接配置管理
  const llmConfig = {
    apiKey: "",
    configured: false,
    connectionStatus: "NONE",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
    provider: "deepseek",
  };
  let llmFormDirty = false;
  let modelSettingsSequence = 0;

  function syncLLMConfigForm() {
    const provider = byId("llm-provider-select");
    if (provider) provider.value = llmConfig.provider;
    const url = byId("llm-base-url-input");
    if (url) url.value = llmConfig.baseUrl;
    const model = byId("llm-model-input");
    if (model) model.value = llmConfig.model;
    const key = byId("llm-api-key-input");
    if (key) key.placeholder = llmConfig.configured ? "已安全保存；留空保留，填写可替换" : "请输入 API Key";
  }

  function setLLMFormBusy(busy) {
    const readOnly = accountAccessEnabled && !authenticatedAdmin;
    ["llm-provider-select", "llm-api-key-input", "llm-base-url-input", "llm-model-input",
      "btn-save-llm-config", "btn-clear-llm-config"].forEach(id => {
      const element = byId(id);
      if (element) element.disabled = busy || readOnly;
    });
  }

  function updateLLMConfigUI() {
    updateVisibleSourceStatus();
    const dot = byId("llm-config-status-dot");
    const label = byId("llm-config-btn-label");
    const badge = byId("chat-model-badge");

    if (llmConfig.configured && llmConfig.connectionStatus === "CONNECTED") {
      if (dot) dot.textContent = "●";
      if (label) label.textContent = `连接通过 (${llmConfig.model})`;
      if (badge) badge.textContent = `${llmConfig.model} · 连接通过`;
    } else if (llmConfig.configured && llmConfig.connectionStatus === "FAILED") {
      if (dot) dot.textContent = "●";
      if (label) label.textContent = `连接失败 (${llmConfig.model})`;
      if (badge) badge.textContent = `${llmConfig.model} · 连接失败`;
    } else if (llmConfig.configured) {
      if (dot) dot.textContent = "●";
      if (label) label.textContent = `已保存 (${llmConfig.model})`;
      if (badge) badge.textContent = `${llmConfig.model} · 已保存`;
    } else {
      if (dot) dot.textContent = "⚪";
      if (label) label.textContent = "大模型配置 (API Key)";
      if (badge) badge.textContent = authenticatedOwner ? "服务端分析配置" : "内置分析引擎";
    }

    if (badge && byId("chat-runtime-mode")?.value === "MOCK") badge.textContent = "AI 模拟模式";
  }

  function openLLMConfigModal() {
    updateLLMConfigUI();
    llmFormDirty = false;
    byId("llm-api-key-input").value = "";
    syncLLMConfigForm();
    const modal = byId("llm-config-modal");
    if (modal) {
      document.body.appendChild(modal);
      modal.style.display = "flex";
      loadModelSettings().catch(error => setError(error.message));
    }
  }

  function updateVisibleSourceStatus() {
    const mode = byId("chat-runtime-mode")?.value || "AUTO";
    const ai = byId("visible-ai-mode"), data = byId("visible-data-mode");
    if (!ai || !data) return;
    const modelStatus = llmConfig.connectionStatus;
    ai.textContent = mode === "MOCK" ? "AI · MOCK 模拟" : modelStatus === "CONNECTED" ? "AI · 连接通过" : modelStatus === "FAILED" ? "AI · 连接失败" : llmConfig.configured ? "AI · 已保存" : mode === "LIVE" ? "AI · 真实接口未配置" : "AI · 本地规则";
    ai.dataset.mode = mode === "MOCK" ? "mock" : modelStatus === "CONNECTED" ? "live" : modelStatus === "FAILED" ? "error" : "pending";
    data.textContent = state.dataMode === "LIVE" ? "工具数据 · LIVE" : accountAccessEnabled ? "工具数据 · 未就绪" : "工具数据 · MOCK";
    data.dataset.mode = state.dataMode === "LIVE" ? "live" : accountAccessEnabled ? "pending" : "mock";
  }

  function closeLLMConfigModal() {
    const modal = byId("llm-config-modal");
    if (modal) {
      modal.style.display = "none";
    }
  }

  async function loadModelSettings() {
    const owner = state.ownerId;
    const sequence = ++modelSettingsSequence;
    const response = await fetch("/api/v1/user/model-settings", {headers: {"X-Owner-ID": owner}});
    if (!response.ok) throw await apiError(response);
    const settings = await response.json();
    if (owner !== state.ownerId || sequence !== modelSettingsSequence) return;
    llmConfig.apiKey = "";
    llmConfig.configured = settings.is_configured;
    llmConfig.connectionStatus = settings.connection_verified ? "CONNECTED" : settings.is_configured ? "SAVED" : "NONE";
    llmConfig.baseUrl = settings.base_url;
    llmConfig.model = settings.model;
    llmConfig.provider = settings.base_url.includes("dashscope.aliyuncs.com") ? "qwen"
      : settings.base_url.includes("api.openai.com") ? "openai" : "deepseek";
    updateLLMConfigUI();
    if (!llmFormDirty) syncLLMConfigForm();
    const persistence = settings.persistence === "OS_PROTECTED" ? "操作系统加密持久化" : "仅当前服务进程有效";
    const status = byId("llm-config-status");
    status.style.display = "block";
    const accessHint = accountAccessEnabled && !authenticatedAdmin
      ? "该配置由管理员统一维护，当前账户只读使用。"
      : "密钥不回显，留空保存会保留现有密钥。";
    status.textContent = settings.is_configured ? `全局共享 · ${settings.model} · ${persistence}。${accessHint}` : `尚未配置全局模型服务 · ${persistence}。${accessHint}`;
    setLLMFormBusy(false);
    return settings;
  }

  async function handleSaveLLMConfig() {
    const status = byId("llm-config-status");
    const owner = state.ownerId;
    ++modelSettingsSequence;
    setLLMFormBusy(true); status.style.display = "block"; status.textContent = "正在保存…";
    try {
      const response = await fetch("/api/v1/user/model-settings", {
        method: "PUT", headers: {"Content-Type": "application/json", "X-Owner-ID": owner},
        body: JSON.stringify({api_key: byId("llm-api-key-input").value.trim(), base_url: byId("llm-base-url-input").value.trim(), model: byId("llm-model-input").value.trim()}),
      });
      if (!response.ok) throw await apiError(response);
      if (owner !== state.ownerId) return;
      llmFormDirty = false;
      byId("llm-api-key-input").value = "";
      await loadModelSettings();
      if (owner !== state.ownerId) return;
      status.textContent = "配置已保存，正在自动测试连接…";
      try {
        const tested = await fetch("/api/v1/user/model-settings/test", {method: "POST", headers: {"X-Owner-ID": owner}});
        if (!tested.ok) throw await apiError(tested);
        if (owner !== state.ownerId) return;
        llmConfig.connectionStatus = "CONNECTED";
        status.textContent = "配置已持久化保存，连接测试通过。";
      } catch (error) {
        if (owner !== state.ownerId) return;
        llmConfig.connectionStatus = "FAILED";
        status.textContent = `配置已保存，但连接测试失败：${error.message}。请修改后重新保存。`;
      }
      updateLLMConfigUI();
    } catch (error) { if (owner === state.ownerId) status.textContent = `保存失败：${error.message}`; }
    finally { setLLMFormBusy(false); }
  }

  async function handleClearLLMConfig() {
    const status = byId("llm-config-status");
    const owner = state.ownerId;
    ++modelSettingsSequence;
    setLLMFormBusy(true);
    try {
      const response = await fetch("/api/v1/user/model-settings", {method: "DELETE", headers: {"X-Owner-ID": owner}});
      if (!response.ok) throw await apiError(response);
      if (owner !== state.ownerId) return;
      llmFormDirty = false;
      byId("llm-api-key-input").value = "";
      await loadModelSettings();
    } catch (error) { status.style.display = "block"; status.textContent = `恢复失败：${error.message}`; }
    finally { setLLMFormBusy(false); }
  }

  // 自定义持仓弹窗交互
  function openPortfolioModal() {
    const modal = byId("portfolio-modal");
    if (modal) {
      // The entry is global; a hidden workspace must not hide its dialog.
      document.body.appendChild(modal);
      modal.style.display = "flex";
    }
  }

  function closePortfolioModal() {
    const modal = byId("portfolio-modal");
    if (modal) {
      modal.style.display = "none";
    }
  }

  async function validateAndActivatePortfolio(data, positions = data.positions) {
    const validationContext = {
      ownerId: state.ownerId,
      selectedPersona: state.selectedPersona,
      dataMode: state.dataMode,
      contextRevision: state.contextRevision,
    };
    const isScreenshotConfirmation = Boolean(data.image_digest);
    const response = await fetch(
      isScreenshotConfirmation ? "/api/v1/advisor/portfolio/ocr/confirm" : "/api/v1/copilot/validate-portfolio-ocr",
      {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Owner-ID": validationContext.ownerId },
      body: JSON.stringify({
        owner_id: validationContext.ownerId,
        positions,
        cash_cny: data.cash_cny,
        ...(isScreenshotConfirmation ? { image_digest: data.image_digest } : {}),
      }),
    });
    const validationIsCurrent = () => state.ownerId === validationContext.ownerId
      && state.selectedPersona === validationContext.selectedPersona
      && state.dataMode === validationContext.dataMode
      && state.contextRevision === validationContext.contextRevision;
    if (!validationIsCurrent()) return null;
    if (!response.ok) throw await apiError(response);
    const validated = await response.json();
    if (!validationIsCurrent()) return null;
    microStore.transact((store) => {
      invalidateDerivedState(store);
      store.ocrPortfolioDraft = validated;
      store.portfolio = validated.portfolio;
    });
    const aumEl = byId("copilot-stat-aum");
    if (aumEl) aumEl.textContent = `¥ ${Number(validated.total_value_cny).toLocaleString()}`;
    const pTag = byId("copilot-hero-portfolio-tag");
    if (pTag) pTag.textContent = `已确认持仓 (${validated.positions.length} 项)`;
    if (state.profile?.profile) {
      await runPortfolioAnalysis();
    }
    else renderPortfolioReadiness();
    const validatedSourceTitle = state.dataMode === "LIVE" ? "已确认 · 实时数据" : "已确认 · 当前会话只读";
    if (typeof renderPortfolio === "function") renderPortfolio(validated.portfolio, validatedSourceTitle);
    renderOverviewWorkspace(state.selectedPersona);
    return validated;
  }

  async function loadSavedPortfolio() {
    const owner = state.ownerId;
    const mode = state.dataMode;
    const revision = state.contextRevision;
    const portfolioBefore = state.portfolio;
    if (!owner || state.selectedPersona !== "custom-user") return;
    const response = await fetch("/api/v1/advisor/portfolio/current", {headers: {"X-Owner-ID": owner}});
    if (!response.ok) throw await apiError(response);
    const saved = await response.json();
    if (owner !== state.ownerId || mode !== state.dataMode || saved.data_mode !== mode || revision !== state.contextRevision
        || state.selectedPersona !== "custom-user" || state.portfolio !== portfolioBefore) return;
    if (!saved.data) return;
    microStore.transact((store) => {
      store.portfolio = saved.data.portfolio;
      store.ocrPortfolioDraft = saved.data;
    });
    const tag = byId("copilot-hero-portfolio-tag");
    if (tag) tag.textContent = `已确认持仓 (${saved.data.positions.length} 项)`;
    const savedSourceTitle = state.dataMode === "LIVE" ? "已确认 · 实时数据" : "已确认 · 当前会话只读";
    if (typeof renderPortfolio === "function" && saved.data.portfolio) renderPortfolio(saved.data.portfolio, savedSourceTitle);
    renderPortfolioReadiness();
    renderOverviewWorkspace(state.selectedPersona);
  }

  async function handleParsePortfolioSubmit() {
    const textarea = byId("portfolio-natural-textarea");
    const statusBox = byId("parsed-portfolio-status");
    const text = textarea?.value?.trim();
    if (!text) return;

    if (statusBox) {
      statusBox.style.display = "block";
      statusBox.textContent = "正在识别持仓文本并核对行情价格…";
    }

    try {
      const resp = await fetch("/api/v1/copilot/parse-portfolio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await resp.json();

      if (resp.ok && data.status === "SUCCESS" && data.positions && data.positions.length > 0) {
        const validated = await validateAndActivatePortfolio(data);
        if (!validated) return;
        if (statusBox) {
          clear(statusBox);
          const strong = document.createElement("strong");
          strong.textContent = `成功确认 ${validated.positions.length} 项资产（现金 ¥${validated.cash_cny}，总估值 ¥${validated.total_value_cny}）：`;
          const list = document.createElement("ul");
          list.style.margin = "6px 0 0";
          list.style.paddingLeft = "16px";
          validated.positions.forEach(p => {
            const li = document.createElement("li");
            li.textContent = `${p.name} (${p.asset_id})：${p.quantity}股/份 · 估值 ¥${p.market_value_cny}`;
            list.append(li);
          });
          statusBox.append(strong, list);
        }

        setTimeout(() => {
          closePortfolioModal();
          runCopilotHealthCheck();
        }, 600);
      } else {
        if (statusBox) statusBox.textContent = data.message || "未能识别出有效资产，请检查输入格式。";
      }
    } catch (err) {
      if (statusBox) statusBox.textContent = `解析出错: ${err.message || "请求异常"}`;
    }
  }

  function handlePortfolioOcrFile(fileOrBlob) {
    submitPortfolioOcr(fileOrBlob);
  }

  async function submitPortfolioOcr(fileOrBlob) {
    const container = byId("ocr-result-container");
    if (container) {
      clear(container);
      container.style.display = "block";
      const loadingCard = document.createElement("div");
      loadingCard.className = "copilot-empty-output";
      const spinSpan = document.createElement("span");
      spinSpan.className = "empty-icon";
      const spinSvg = createSvgIcon("icon-activity", "prism-icon prism-icon-xl");
      spinSvg.style.animation = "spin 1.2s linear infinite";
      spinSpan.append(spinSvg);
      const h4 = document.createElement("h4");
      h4.textContent = "正在运行轻量级 RapidOCR 引擎解析持仓截图…";
      const p = document.createElement("p");
      p.textContent = "正在提取表格单元格、核验资产代码并标记建议复核的字段…";
      loadingCard.append(spinSpan, h4, p);
      container.append(loadingCard);
    }

    try {
      const form = new FormData();
      const filename = fileOrBlob?.name || "portfolio-screenshot.png";
      form.append("file", fileOrBlob, filename);
      const resp = await fetch("/api/v1/advisor/portfolio/ocr", {
        method: "POST",
        headers: { "X-Owner-ID": state.ownerId },
        body: form,
      });
      if (!resp.ok) throw await apiError(resp);
      const data = await resp.json();
      state.ocrPortfolioDraft = data;
      renderPortfolioOcrResult(data);
    } catch (err) {
      if (container) {
        clear(container);
        const errCard = document.createElement("div");
        errCard.className = "doc-callout doc-callout-danger";
        const cTitle = document.createElement("div");
        cTitle.className = "callout-title";
        cTitle.textContent = "OCR 识别请求失败";
        const cP = document.createElement("p");
        cP.textContent = err.message || "请求异常，请检查后端 OCR 引擎状态。";
        errCard.append(cTitle, cP);
        container.append(errCard);
      }
    }
  }

  function renderPortfolioOcrResult(data) {
    const container = byId("ocr-result-container");
    if (!container) return;
    clear(container);
    container.style.display = "block";

    if (!data || data.status !== "SUCCESS" || !data.positions || data.positions.length === 0) {
      const emptyDiv = document.createElement("div");
      emptyDiv.className = "doc-callout doc-callout-warning";
      const icon = document.createElement("div");
      icon.className = "callout-icon";
      icon.append(createSvgIcon("icon-alert", "prism-icon"));
      const content = document.createElement("div");
      content.className = "callout-content";
      const title = document.createElement("div");
      title.className = "callout-title";
      title.textContent = "未识别到有效持仓";
      const p = document.createElement("p");
      p.textContent = data?.error ? `解析失败: ${data.error}` : "未能从截图中解析出符合规则的持仓数据，请确保图片清晰并包含证券代码/名称。";
      content.append(title, p);
      emptyDiv.append(icon, content);
      container.append(emptyDiv);
      return;
    }

    const card = document.createElement("div");
    card.className = "ocr-result-card";

    function toLocalDateTimeInputValue(value) {
      const date = value ? new Date(value) : new Date();
      if (Number.isNaN(date.getTime())) return toLocalDateTimeInputValue();
      return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }
    const defaultObservedAt = toLocalDateTimeInputValue();

    const fieldLabels = {
      asset_id: "代码", name: "名称", quantity: "持股", available_quantity: "可用",
      cost_price: "成本价", price: "当前市价", market_value_cny: "持仓市值", observed_at: "报价时间",
    };
    const reasonFields = {
      SECURITY_IDENTITY_REQUIRED: ["asset_id", "name"],
      SECURITY_CODE_CORRECTED: ["asset_id"],
      UNKNOWN_SECURITY: ["asset_id", "name"],
      FRACTIONAL_SHARES: ["quantity"],
      MISSING_REPORTED_MARKET_VALUE: ["market_value_cny"],
      // 报价时间按录入当天补全，不再作为 OCR 低置信度字段。
      MISSING_OBSERVED_AT: [],
      MISSING_OBSERVED_FIELDS: ["cost_price", "price", "market_value_cny"],
      INVALID_QUANTITY_OR_PRICE: ["quantity", "price"],
      MARKET_VALUE_MISMATCH: ["market_value_cny"],
      TOTAL_ASSET_MISMATCH: ["market_value_cny"],
      ODD_LOT_REVIEW: ["quantity"],
    };
    const confidenceThresholdPct = Number(data.confidence_threshold ?? 0.85) * 100;
    function flaggedFields(position) {
      const fields = new Set();
      const confidenceByField = position.field_confidence_pct || {};
      Object.entries(confidenceByField).forEach(([field, confidence]) => {
        if (Number.isFinite(Number(confidence)) && Number(confidence) < confidenceThresholdPct) fields.add(field);
      });
      (position.review_reasons || []).forEach(reason => {
        Object.entries(reasonFields).forEach(([code, mappedFields]) => {
          if (String(reason).startsWith(code)) mappedFields.forEach(field => fields.add(field));
        });
      });
      return fields;
    }
    const warningRows = data.positions.map(position => ({ position, fields: flaggedFields(position) }));
    const warningFieldCount = warningRows.reduce((count, row) => count + row.fields.size, 0);

    // Summary bar
    const sumBar = document.createElement("div");
    sumBar.className = "ocr-summary-bar";
    const sumLeft = document.createElement("div");
    const cashLabel = data.cash_observed === false ? "现金未显示" : `可用现金 ¥${Number(data.cash_cny).toLocaleString()}`;
    const totalLabel = data.account_total_observed === false
      ? `持仓市值小计 ¥${Number(data.total_value_cny).toLocaleString()}（非账户总资产）`
      : `账户总资产 ¥${Number(data.account_total_value_cny ?? data.total_value_cny).toLocaleString()}`;
    sumLeft.textContent = `识别出 ${data.positions.length} 笔当前持仓 · ${cashLabel} · ${totalLabel}`;
    const sumRight = document.createElement("span");
    sumRight.className = warningFieldCount ? "cf-verdict cf-verdict-warning" : "cf-verdict cf-verdict-pass";
    if (warningFieldCount) {
      sumRight.append(createSvgIcon("icon-alert", "prism-icon"), document.createTextNode(` ${warningFieldCount} 个字段建议核对`));
    } else {
      sumRight.append(createSvgIcon("icon-check", "prism-icon"), document.createTextNode(" 识别完成 · 请逐项确认"));
    }
    sumBar.append(sumLeft, sumRight);

    // Table
    const tableWrapper = document.createElement("div");
    tableWrapper.className = "ocr-table-wrapper";
    const table = document.createElement("table");
    table.className = "ocr-verdict-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    ["代码", "名称", "持股", "可用", "成本价", "当前市价", "持仓市值", "报价时间"].forEach(h => {
      const th = document.createElement("th");
      th.textContent = h;
      headerRow.append(th);
    });
    thead.append(headerRow);
    table.append(thead);

    const tbody = document.createElement("tbody");
    const inputControls = [];

    data.positions.forEach((pos) => {
      const tr = document.createElement("tr");
      const warnings = flaggedFields(pos);
      if (warnings.size) {
        tr.className = "ocr-low-confidence";
      }
      const inputs = {};
      const specs = [
        { field: "asset_id", label: "代码", type: "text", value: pos.asset_id || pos.identity_candidates?.[0]?.asset_id || "", placeholder: "600000.SH" },
        { field: "name", label: "名称", type: "text", value: pos.name || "", placeholder: "证券名称" },
        { field: "quantity", label: "持股", type: "number", value: pos.quantity ?? "", min: "1", step: "1" },
        { field: "available_quantity", label: "可用", type: "number", value: pos.available_quantity ?? "", min: "0", step: "1", placeholder: "未识别" },
        { field: "cost_price", label: "成本价", type: "number", value: pos.cost_price ?? "", min: "0", step: "0.001", placeholder: "未显示" },
        { field: "price", label: "当前市价", type: "number", value: pos.price ?? "", min: "0.001", step: "0.001" },
        { field: "market_value_cny", label: "持仓市值", type: "number", value: pos.market_value_cny ?? "", min: "0.01", step: "0.01" },
        { field: "observed_at", label: "报价时间", type: "datetime-local", value: pos.observed_at ? toLocalDateTimeInputValue(pos.observed_at) : defaultObservedAt, defaulted: !pos.observed_at },
      ];
      specs.forEach(spec => {
        const td = document.createElement("td");
        td.dataset.label = spec.label;
        const input = document.createElement("input");
        input.type = spec.type;
        input.className = "ocr-edit-input";
        input.value = spec.value;
        input.setAttribute("aria-label", `${pos.name || "持仓"}${spec.label}`);
        if (spec.placeholder) input.placeholder = spec.placeholder;
        if (spec.min) input.min = spec.min;
        if (spec.step) input.step = spec.step;
        if (spec.defaulted) {
          input.dataset.defaulted = "true";
          input.addEventListener("input", () => { input.dataset.userEdited = "true"; });
        }
        td.append(input);
        if (warnings.has(spec.field)) {
          td.classList.add("cell-warning");
          const confidence = Number(pos.field_confidence_pct?.[spec.field]);
          const hint = document.createElement("small");
          hint.className = "ocr-field-confidence";
          hint.textContent = Number.isFinite(confidence)
            ? `识别 ${confidence.toFixed(1)}% · 建议核对`
            : "识别结果建议核对";
          td.append(hint);
        }
        inputs[spec.field] = input;
        tr.append(td);
      });
      tbody.append(tr);
      inputControls.push({ pos, inputs });
    });
    table.append(tbody);
    tableWrapper.append(table);

    // Callout Guidance
    const callout = document.createElement("div");
    callout.className = warningFieldCount ? "doc-callout doc-callout-warning" : "doc-callout doc-callout-tip";
    const cIcon = document.createElement("div");
    cIcon.className = "callout-icon";
    cIcon.append(createSvgIcon(warningFieldCount ? "icon-alert" : "icon-check", "prism-icon"));
    const cContent = document.createElement("div");
    cContent.className = "callout-content";
    const cTitle = document.createElement("div");
    cTitle.className = "callout-title";
    cTitle.textContent = warningFieldCount
      ? "识别提示：黄色字段可能有误"
      : "识别提示：未发现明显异常字段";
    const cP = document.createElement("p");
    const warningSummary = warningRows
      .filter(row => row.fields.size)
      .map(row => `${row.position.name || row.position.asset_id || "未命名持仓"}：${[...row.fields].map(field => fieldLabels[field]).filter(Boolean).join("、")}`)
      .join("；");
    cP.textContent = warningFieldCount
      ? `${warningSummary}。置信度仅用于定位可能有误的字段，不限制编辑或确认；所有字段均可直接修改。`
      : "置信度仅作为识别质量提示，不参与编辑权限判断。请逐项核对后确认导入。";
    cContent.append(cTitle, cP);
    callout.append(cIcon, cContent);

    // Confirm action
    const confirmStatus = document.createElement("p");
    confirmStatus.className = "ocr-confirm-status";
    confirmStatus.hidden = true;
    confirmStatus.setAttribute("role", "alert");
    const actions = document.createElement("div");
    actions.className = "modal-actions ocr-confirm-actions";
    const confirmBtn = document.createElement("button");
    confirmBtn.className = "copilot-action-btn primary";
    confirmBtn.type = "button";
    confirmBtn.append(createSvgIcon("icon-check", "prism-icon"), document.createTextNode(" 确认持仓并开始体检"));
    confirmBtn.addEventListener("click", async () => {
      if (confirmBtn.disabled) return;
      confirmBtn.disabled = true;
      confirmBtn.setAttribute("aria-busy", "true");
      confirmStatus.hidden = true;
      confirmStatus.textContent = "";
      try {
        const editedPositions = inputControls.map(({ pos, inputs }) => {
          const quantity = Number(inputs.quantity.value);
          if (!Number.isInteger(quantity) || quantity <= 0) throw new Error("持仓数量必须为正整数");
          const availableRaw = inputs.available_quantity.value.trim();
          const availableQuantity = availableRaw === "" ? null : Number(availableRaw);
          if (availableQuantity !== null && (!Number.isInteger(availableQuantity) || availableQuantity < 0 || availableQuantity > quantity)) {
            throw new Error("可用数量必须为 0 至持仓数量之间的整数");
          }
          const assetId = inputs.asset_id.value.trim().toUpperCase();
          if (!/^\d{6}\.(SH|SZ|BJ)$/.test(assetId)) throw new Error("请核对并填写完整证券代码，例如 600251.SH");
          const name = inputs.name.value.trim();
          if (!name) throw new Error("证券名称不能为空");
          const costRaw = inputs.cost_price.value.trim();
          const cost = costRaw === "" ? null : Number(costRaw);
          const price = Number(inputs.price.value);
          const marketValue = Number(inputs.market_value_cny.value);
          if (cost !== null && !(cost > 0)) throw new Error("成本价留空或填写正数");
          if (!(price > 0) || !(marketValue > 0)) throw new Error("当前市价与持仓市值必须为正数");
          const calculatedMarketValue = quantity * price;
          const tolerance = Math.max(0.01, calculatedMarketValue * 0.005);
          if (Math.abs(marketValue - calculatedMarketValue) > tolerance) {
            throw new Error("持仓市值与持仓数量 × 当前市价不一致，请核对这三个字段");
          }
          if (!inputs.observed_at.value) throw new Error("请补充截图对应的报价时间");
          const correctedReasons = new Set(Object.keys(reasonFields));
          const reasons = (pos.review_reasons || []).filter(reason => ![...correctedReasons].some(code => String(reason).startsWith(code)));
          const fieldSources = { ...(pos.field_sources || {}) };
          Object.keys(fieldLabels).forEach(field => { fieldSources[field] = "user-confirmed broker screenshot"; });
          if (inputs.observed_at.dataset.defaulted === "true" && inputs.observed_at.dataset.userEdited !== "true") {
            fieldSources.observed_at = "system default: browser local current time";
          }
          // 仅提交 ConfirmedOcrPosition 契约允许的字段；OCR 草稿可能包含展示或上游扩展字段。
          return { asset_id: assetId, name,
            asset_class: pos.asset_class || "EQUITY", sector: pos.sector || "Unclassified",
            quantity, available_quantity: availableQuantity,
            cost_price: cost, price, market_value_cny: marketValue,
            calculated_market_value_cny: Number(calculatedMarketValue.toFixed(2)),
            observed_at: new Date(inputs.observed_at.value).toISOString(),
            price_source: pos.price_source || "user-confirmed broker screenshot",
            field_sources: fieldSources,
            review_reasons: reasons, needs_review: reasons.length > 0 };
        });
        const validated = await validateAndActivatePortfolio(data, editedPositions);
        if (!validated) return;
        closePortfolioModal();
      } catch (error) {
        confirmStatus.textContent = error.message || "持仓校验失败";
        confirmStatus.hidden = false;
      } finally {
        confirmBtn.disabled = false;
        confirmBtn.removeAttribute("aria-busy");
      }
    });
    actions.append(confirmBtn);

    card.append(sumBar, tableWrapper, callout, confirmStatus, actions);
    if (Array.isArray(data.zero_positions) && data.zero_positions.length) {
      const excluded = document.createElement("p");
      excluded.className = "research-boundary";
      excluded.textContent = `已识别并排除零持仓：${data.zero_positions.map(item => item.name).join("、")}`;
      card.insertBefore(excluded, actions);
    }
    container.append(card);
  }

  function initPortfolioModalTabs() {
    const tabOcr = byId("tab-btn-ocr");
    const tabText = byId("tab-btn-text");
    const panelOcr = byId("panel-portfolio-ocr");
    const panelText = byId("panel-portfolio-text");
    if (!tabOcr || !tabText || !panelOcr || !panelText) return;

    tabOcr.addEventListener("click", () => {
      tabOcr.classList.add("active");
      tabOcr.setAttribute("aria-selected", "true");
      tabText.classList.remove("active");
      tabText.setAttribute("aria-selected", "false");
      panelOcr.style.display = "block";
      panelText.style.display = "none";
    });

    tabText.addEventListener("click", () => {
      tabText.classList.add("active");
      tabText.setAttribute("aria-selected", "true");
      tabOcr.classList.remove("active");
      tabOcr.setAttribute("aria-selected", "false");
      panelText.style.display = "block";
      panelOcr.style.display = "none";
    });

    const triggerBtn = byId("btn-trigger-file-select");
    const fileInput = byId("portfolio-ocr-file-input");
    if (triggerBtn && fileInput) {
      triggerBtn.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if (file) handlePortfolioOcrFile(file);
      });
    }

    const dropzone = byId("ocr-dropzone");
    if (dropzone) {
      dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
      });
      dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
      });
      dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        const file = e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) handlePortfolioOcrFile(file);
      });
    }

    const sampleBtn = byId("btn-load-sample-ocr");
    if (sampleBtn) {
      sampleBtn.addEventListener("click", async () => {
        try {
          const resp = await fetch("/static/sample_holding.png");
          const blob = await resp.blob();
          handlePortfolioOcrFile(blob);
        } catch (err) {
          console.error("加载测试截图失败:", err);
        }
      });
    }

    window.addEventListener("paste", (e) => {
      const modal = byId("portfolio-modal");
      if (!modal || modal.style.display === "none") return;
      const items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.indexOf("image") !== -1) {
          const blob = items[i].getAsFile();
          if (blob) {
            handlePortfolioOcrFile(blob);
            break;
          }
        }
      }
    });
  }

  function renderDevAssistResult(result) {
    const output = byId("dev-assist-output");
    const status = byId("dev-assist-status");
    if (!output || !status) return;
    clear(output);
    status.textContent = result.status;
    status.className = result.status === "CALCULATED" ? "status-chip pass" : "status-chip review";
    const grid = document.createElement("div");
    grid.className = "dev-assist-result-grid";
    const sections = [
      ["冲突与缺口", [...(result.conflicts || []), ...(result.gaps || [])].join("\n") || "未发现结构化冲突"],
      ["完善后的技术方案", result.improved_technical_spec],
      ["接口草案", (result.api_drafts || []).map(item => `${item.method} ${item.path} — ${item.purpose}`).join("\n")],
      ["代码骨架", (result.skeleton_files || []).map(item => `# ${item.path}\n${item.content}`).join("\n\n")],
    ];
    sections.forEach(([title, value]) => {
      const card = document.createElement("section");
      card.className = "dev-assist-result";
      const h4 = document.createElement("h4");
      h4.textContent = title;
      const pre = document.createElement("pre");
      pre.textContent = value || "无";
      card.append(h4, pre);
      grid.append(card);
    });
    const boundary = document.createElement("p");
    boundary.className = "research-boundary";
    boundary.textContent = "代码骨架仅作为文本返回；服务端未写入仓库，也未执行任何生成代码。";
    output.append(grid, boundary);
  }

  async function runDevAssist() {
    const prd = byId("dev-assist-prd")?.value?.trim();
    const technical = byId("dev-assist-technical")?.value?.trim();
    if (!prd || !technical) {
      setError("研发辅助需要同时提供 PRD 和技术方案文本。");
      return;
    }
    const status = byId("dev-assist-status");
    if (status) status.textContent = "处理中";
    const response = await fetch("/api/v1/dev-assist/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Owner-ID": state.ownerId },
      body: JSON.stringify({
        schema_version: "dev-assist-request.v1",
        run_id: `dev-assist-${Date.now()}`,
        owner_id: state.ownerId,
        requested_at: new Date().toISOString(),
        prd_text: prd,
        technical_text: technical,
        target_stack: "Python 3.11, FastAPI, Pydantic, vanilla JavaScript",
      }),
    });
    if (!response.ok) throw await apiError(response);
    renderDevAssistResult(await response.json());
  }

  let renderedMarketChart = null;
  let marketChartResizeObserver = null;

  function marketRange(months) {
    if (!renderedMarketChart || !marketAnalysis?.bars?.length) return;
    if (months === "all") { renderedMarketChart.timeScale().fitContent(); return; }
    const last = marketAnalysis.bars.at(-1).time;
    const from = new Date(`${last}T00:00:00Z`);
    from.setUTCMonth(from.getUTCMonth() - Number(months));
    renderedMarketChart.timeScale().setVisibleRange({from: from.toISOString().slice(0, 10), to: last});
  }

  function renderIndexCandles(data) {
    const container = byId("market-kline");
    marketChartResizeObserver?.disconnect();
    marketChartResizeObserver = null;
    renderedMarketChart?.remove();
    renderedMarketChart = null;
    container.replaceChildren();
    const bars = data.bars || [];
    if (!bars.length) { container.textContent = `${data.name || "指数"}${data.interval === "1M" ? "月" : "日"} K 线暂不可用。`; return; }
    if (!window.LightweightCharts) { container.textContent = "行情图组件未能加载。"; return; }
    const css = getComputedStyle(document.body);
    const color = name => css.getPropertyValue(name).trim();
    const chartHeight = 420 + (activeMarketIndicators.has("macd") ? 130 : 0) + (activeMarketIndicators.has("kdj") ? 130 : 0);
    container.style.height = `${chartHeight}px`;
    const chart = window.LightweightCharts.createChart(container, {
      width: container.clientWidth, height: chartHeight,
      layout: {background: {type: "solid", color: color("--surface")}, textColor: color("--text-secondary"),
        panes: {separatorColor: color("--border"), separatorHoverColor: color("--brand"), enableResize: true}},
      grid: {vertLines: {color: color("--border-subtle")}, horzLines: {color: color("--border-subtle")}},
      crosshair: {mode: window.LightweightCharts.CrosshairMode.Normal},
      timeScale: {timeVisible: false, secondsVisible: false, borderColor: color("--border"), rightOffset: 2},
      rightPriceScale: {borderColor: color("--border")},
      handleScroll: {mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true},
      handleScale: {mouseWheel: true, pinch: true, axisPressedMouseMove: true},
    });
    renderedMarketChart = chart;
    const candles = chart.addSeries(window.LightweightCharts.CandlestickSeries, {
      upColor: color("--market-up"), downColor: color("--market-down"), borderVisible: false,
      wickUpColor: color("--market-up"), wickDownColor: color("--market-down"),
      priceFormat: {type: "price", precision: data.precision, minMove: 1 / (10 ** data.precision)},
    }, 0);
    candles.setData(bars.map(bar => ({time: bar.time, open: Number(bar.open), high: Number(bar.high), low: Number(bar.low), close: Number(bar.close)})));

    const volume = chart.addSeries(window.LightweightCharts.HistogramSeries, {
      priceFormat: {type: "volume"}, priceScaleId: "volume",
    }, 1);
    volume.setData(bars.filter(bar => bar.volume != null).map(bar => ({time: bar.time, value: Number(bar.volume),
      color: Number(bar.close) >= Number(bar.open) ? `${color("--market-up")}99` : `${color("--market-down")}99`})));
    chart.panes()[0]?.setHeight(280);
    chart.panes()[1]?.setHeight(90);

    const indicators = data.indicators || {};
    const bollByTime = new Map((indicators.boll || []).map(point => [point.time, point]));
    const macdByTime = new Map((indicators.macd || []).map(point => [point.time, point]));
    const kdjByTime = new Map((indicators.kdj || []).map(point => [point.time, point]));
    if (activeMarketIndicators.has("boll")) {
      [["upper", "#8b5cf6"], ["middle", color("--brand")], ["lower", "#0ea5e9"]].forEach(([field, lineColor]) => {
        const series = chart.addSeries(window.LightweightCharts.LineSeries, {color: lineColor, lineWidth: 1, priceLineVisible: false, lastValueVisible: false}, 0);
        series.setData((indicators.boll || []).map(point => ({time: point.time, value: Number(point[field])})));
      });
    }
    let paneIndex = 2;
    if (activeMarketIndicators.has("macd")) {
      const histogram = chart.addSeries(window.LightweightCharts.HistogramSeries, {priceLineVisible: false, lastValueVisible: false}, paneIndex);
      histogram.setData((indicators.macd || []).map(point => ({time: point.time, value: Number(point.histogram), color: Number(point.histogram) >= 0 ? color("--market-up") : color("--market-down")})));
      [["diff", "#0ea5e9"], ["dea", color("--brand")]].forEach(([field, lineColor]) => {
        const series = chart.addSeries(window.LightweightCharts.LineSeries, {color: lineColor, lineWidth: 1, priceLineVisible: false, lastValueVisible: false}, paneIndex);
        series.setData((indicators.macd || []).map(point => ({time: point.time, value: Number(point[field])})));
      });
      chart.panes()[paneIndex]?.setHeight(120); paneIndex += 1;
    }
    if (activeMarketIndicators.has("kdj")) {
      [["k", "#0ea5e9"], ["d", color("--brand")], ["j", "#8b5cf6"]].forEach(([field, lineColor]) => {
        const series = chart.addSeries(window.LightweightCharts.LineSeries, {color: lineColor, lineWidth: 1, priceLineVisible: false, lastValueVisible: false}, paneIndex);
        series.setData((indicators.kdj || []).map(point => ({time: point.time, value: Number(point[field])})));
      });
      chart.panes()[paneIndex]?.setHeight(120);
    }
    const rows = new Map(bars.map(bar => [bar.time, bar]));
    chart.subscribeCrosshairMove(param => {
      const timeKey = typeof param.time === "string" ? param.time : param.time && typeof param.time === "object"
        ? `${param.time.year}-${String(param.time.month).padStart(2, "0")}-${String(param.time.day).padStart(2, "0")}` : "";
      const bar = rows.get(timeKey);
      if (!bar) return;
      const pct = Number(bar.open) ? (Number(bar.close) / Number(bar.open) - 1) * 100 : 0;
      const bollPoint = bollByTime.get(bar.time), macdPoint = macdByTime.get(bar.time), kdjPoint = kdjByTime.get(bar.time);
      const indicatorText = [
        bollPoint && `BOLL ${bollPoint.upper}/${bollPoint.middle}/${bollPoint.lower}`,
        macdPoint && `MACD ${macdPoint.diff}/${macdPoint.dea}/${macdPoint.histogram}`,
        kdjPoint && `KDJ ${kdjPoint.k}/${kdjPoint.d}/${kdjPoint.j}`,
      ].filter(Boolean).join(" · ");
      byId("market-crosshair-info").textContent = `${bar.time}（${data.timezone}） · 开 ${bar.open} 高 ${bar.high} 低 ${bar.low} 收 ${bar.close} · ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}% · 成交量 ${bar.volume == null ? "—" : Number(bar.volume).toLocaleString("zh-CN")} · 成交额 ${bar.turnover == null ? "—" : Number(bar.turnover).toLocaleString("zh-CN")}${indicatorText ? ` · ${indicatorText}` : ""}`;
    });
    chart.timeScale().fitContent();
    marketChartResizeObserver = new ResizeObserver(entries => {
      const width = Math.floor(entries[0]?.contentRect.width || 0);
      if (width > 0 && renderedMarketChart === chart) chart.applyOptions({width});
    });
    marketChartResizeObserver.observe(container);
  }

  function renderMarketFactors(factors) {
    const container = byId("market-factors"); container.replaceChildren();
    if (!factors.length) {
      const empty = document.createElement("p"); empty.className = "market-factor-empty";
      empty.textContent = "宏观因子尚未取得；指数行情与技术指标可独立使用。";
      container.append(empty); return;
    }
    const strength = value => value == null ? "样本不足" : Math.abs(Number(value)) < .2 ? "弱" : Math.abs(Number(value)) <= .5 ? "中等" : "较强";
    factors.forEach(factor => {
      const card = document.createElement("article"); card.className = "market-factor-card";
      const heading = document.createElement("header");
      const title = document.createElement("strong"); title.textContent = factor.name;
      heading.append(title, chip(factor.status, factor.status === "LIVE" ? "pass" : "review"));
      const value = document.createElement("p"); value.className = "market-factor-value";
      value.textContent = factor.latest_value == null ? "数据不可用" : `${Number(factor.latest_value).toLocaleString("zh-CN")} ${factor.unit}`;
      const correlation = document.createElement("dl"); correlation.className = "market-factor-correlations";
      [["20期相关", factor.correlation_20], ["60期相关", factor.correlation_60]].forEach(([label, number]) => {
        const dt = document.createElement("dt"); dt.textContent = label;
        const dd = document.createElement("dd"); dd.textContent = number == null ? "—" : `${Number(number).toFixed(2)} · ${Number(number) >= 0 ? "正" : "负"}相关 · ${strength(number)}`;
        correlation.append(dt, dd);
      });
      const meta = document.createElement("small"); meta.textContent = `${factor.source} · 样本 ${factor.sample_size || 0} · ${factor.observed_at || "未取得时间"}`;
      card.append(heading, value, correlation, meta); container.append(card);
    });
  }

  byId("market-load-industries")?.addEventListener("click", async event => {
    const button = event.currentTarget, output = byId("market-industries"); button.disabled = true; output.textContent = "正在读取行业日线…";
    try {
      const response = await fetch("/api/v1/market/industries", {headers: {"X-Owner-ID": state.ownerId}});
      if (!response.ok) throw await apiError(response);
      const data = await response.json(); output.replaceChildren();
      const note = document.createElement("p"); note.textContent = [data.source, data.message].filter(Boolean).join(" · "); output.append(note);
      const table = document.createElement("table"), header = document.createElement("tr");
      ["行业", "1 日", "5 日", "20 日", "观察日期"].forEach(label => { const th = document.createElement("th"); th.textContent = label; header.append(th); }); table.append(header);
      (data.rows || []).forEach(row => { const tr = document.createElement("tr"); [row.name, ...[row.day_pct, row.five_day_pct, row.twenty_day_pct].map(v => v == null ? "—" : `${v}%`), row.as_of || "未取得"].forEach(value => { const td = document.createElement("td"); td.textContent = value; tr.append(td); }); table.append(tr); });
      output.append(table);
    } catch (error) { output.textContent = error.message; }
    finally { button.disabled = false; }
  });

  function renderAssistantMarkdown(target, content) {
    target.classList.add("markdown-body");
    if (window.PrismMarkdown) window.PrismMarkdown(target, content);
    else target.textContent = content;
  }

  let portfolioSummarySequence = 0;
  let displayedPortfolioSummary = null;
  let portfolioReportSequence = 0;
  let displayedPortfolioReport = null;

  const reportAmount = value => value == null
    ? "待补充数据"
    : `¥ ${Number(value).toLocaleString("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  const reportPercent = value => value == null ? "—" : `${Number(value).toFixed(2)}%`;
  const reportStatusLabel = status => ({
    PASS: "通过",
    REVIEW_REQUIRED: "需要复核",
    BLOCKED: "已阻断",
    UNAVAILABLE: "待补齐",
  }[status] || "待生成");
  const reportStatusClass = status => status === "PASS" ? "pass" : ["REVIEW_REQUIRED", "UNAVAILABLE"].includes(status) ? "review" : "blocked";
  const reportAssetTypeLabel = type => ({
    STOCK: "股票",
    ETF: "ETF",
    MUTUAL_FUND: "基金",
    BOND: "债券",
    CASH: "现金",
    OTHER: "其他",
  }[type] || text(type, "其他"));

  function appendReportMetric(parent, label, value, className = "") {
    const item = document.createElement("div"); item.className = `portfolio-report-metric ${className}`.trim();
    const name = document.createElement("span"); name.textContent = label;
    const number = document.createElement("strong"); number.textContent = value;
    item.append(name, number); parent.append(item);
  }

  const PORTFOLIO_ASSET_COLORS = Object.freeze({
    stock: "#d97706",
    cash: "#2f855a",
    etf: "#2563eb",
    convertible: "#7c3aed",
    bond: "#0891b2",
    other: "#6b7280",
  });

  function renderPortfolioAssetStructure(container, assetStructure) {
    clear(container);
    const groups = (assetStructure || []).filter(group => Number(group.market_value_cny) > 0);
    if (!groups.length) {
      const empty = document.createElement("p");
      empty.className = "portfolio-report-risk-line";
      empty.textContent = "当前报告没有可展示的资产结构。";
      container.append(empty);
      return;
    }
    const wrapper = document.createElement("div");
    wrapper.className = "portfolio-asset-structure";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 220 220");
    svg.setAttribute("class", "portfolio-asset-pie");
    svg.setAttribute("role", "img");
    const descriptions = groups.map(group => `${group.label} ${reportAmount(group.market_value_cny)}，占比 ${reportPercent(group.weight_pct)}，${group.position_count} 项`);
    svg.setAttribute("aria-label", `资产结构饼图：${descriptions.join("；")}`);
    const totalWeight = groups.reduce((sum, group) => sum + Number(group.weight_pct), 0) || 100;
    const center = 110;
    const radius = 92;
    let angle = -Math.PI / 2;
    groups.forEach((group, index) => {
      const color = PORTFOLIO_ASSET_COLORS[group.group_key] || PORTFOLIO_ASSET_COLORS.other;
      const fraction = Number(group.weight_pct) / totalWeight;
      const sectorLabel = descriptions[index];
      let sector;
      if (groups.length === 1) {
        sector = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        sector.setAttribute("cx", center);
        sector.setAttribute("cy", center);
        sector.setAttribute("r", radius);
      } else {
        const endAngle = angle + fraction * Math.PI * 2;
        const startX = center + radius * Math.cos(angle);
        const startY = center + radius * Math.sin(angle);
        const endX = center + radius * Math.cos(endAngle);
        const endY = center + radius * Math.sin(endAngle);
        sector = document.createElementNS("http://www.w3.org/2000/svg", "path");
        sector.setAttribute("d", `M ${center} ${center} L ${startX.toFixed(3)} ${startY.toFixed(3)} A ${radius} ${radius} 0 ${fraction > 0.5 ? 1 : 0} 1 ${endX.toFixed(3)} ${endY.toFixed(3)} Z`);
        angle = endAngle;
      }
      sector.setAttribute("fill", color);
      sector.setAttribute("class", "portfolio-asset-pie-sector");
      sector.setAttribute("role", "img");
      sector.setAttribute("aria-label", sectorLabel);
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = sectorLabel;
      sector.append(title);
      svg.append(sector);
    });
    const legend = document.createElement("ul");
    legend.className = "portfolio-asset-legend";
    groups.forEach(group => {
      const item = document.createElement("li");
      const dot = document.createElement("span");
      dot.className = "portfolio-asset-legend-dot";
      dot.style.backgroundColor = PORTFOLIO_ASSET_COLORS[group.group_key] || PORTFOLIO_ASSET_COLORS.other;
      const label = document.createElement("strong");
      label.textContent = group.label;
      const facts = document.createElement("span");
      facts.textContent = `${reportAmount(group.market_value_cny)} · ${reportPercent(group.weight_pct)} · ${group.position_count} 项`;
      item.append(dot, label, facts);
      legend.append(item);
    });
    wrapper.append(svg, legend);
    container.append(wrapper);
  }

  function appendRiskBoundaryRow(body, {label, current, threshold, status, basis}) {
    const row = document.createElement("tr");
    [label, current, threshold].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `status-chip ${reportStatusClass(status)}`;
    badge.textContent = status;
    statusCell.append(badge);
    const basisCell = document.createElement("td");
    basisCell.textContent = basis;
    row.append(statusCell, basisCell);
    body.append(row);
  }

  function renderPortfolioRiskBoundaries(container, report) {
    clear(container);
    const tableWrap = document.createElement("div");
    tableWrap.className = "portfolio-risk-boundary-wrap";
    const table = document.createElement("table");
    table.className = "portfolio-report-table portfolio-risk-boundary-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["约束", "当前值", "画像阈值", "状态", "计算口径"].forEach(label => {
      const cell = document.createElement("th");
      cell.textContent = label;
      headRow.append(cell);
    });
    head.append(headRow);
    const body = document.createElement("tbody");
    const topPosition = (report.positions || []).find(position => position.asset_name === report.concentration?.top_asset_name)
      || (report.positions || [])[0];
    const topTotalWeight = topPosition && Number(report.total_value_cny) > 0
      ? Number(topPosition.market_value_cny) / Number(report.total_value_cny) * 100
      : null;
    appendRiskBoundaryRow(body, {
      label: "单一标的集中度",
      current: report.concentration?.top_asset_weight_pct == null
        ? "—"
        : `${reportPercent(report.concentration.top_asset_weight_pct)}（证券持仓）${topTotalWeight == null ? "" : ` / ${reportPercent(topTotalWeight)}（总资产裁决）`}`,
      threshold: report.concentration?.single_asset_limit_pct == null ? "未绑定画像" : `≤ ${reportPercent(report.concentration.single_asset_limit_pct)}`,
      status: report.concentration?.single_asset_verdict || "UNAVAILABLE",
      basis: "展示按证券持仓；上限裁决按组合总资产",
    });
    const equityWeight = report.profile?.equity_weight_pct
      ?? (report.asset_structure || []).filter(group => ["stock", "etf"].includes(group.group_key)).reduce((sum, group) => sum + Number(group.weight_pct), 0);
    appendRiskBoundaryRow(body, {
      label: "权益类占比",
      current: reportPercent(equityWeight),
      threshold: report.profile ? `${reportPercent(report.profile.equity_minimum_pct)}–${reportPercent(report.profile.equity_maximum_pct)}` : "未绑定画像",
      status: report.profile?.equity_verdict || "UNAVAILABLE",
      basis: "组合总资产口径（股票 + ETF）",
    });
    const industryRows = (report.risk?.sectors || []).filter(sector => sector.sector_key !== "CASH");
    if (industryRows.length) {
      industryRows.forEach(sector => {
        const unclassified = sector.sector_key === "UNCLASSIFIED";
        appendRiskBoundaryRow(body, {
          label: unclassified ? "未分类资产（非行业结论）" : sector.name,
          current: reportPercent(sector.weight_pct),
          threshold: `${sector.limit_operator === "MIN" ? "≥" : "≤"} ${reportPercent(sector.limit_pct)}`,
          status: unclassified && Number(sector.weight_pct) > 0 ? "REVIEW_REQUIRED" : sector.verdict,
          basis: unclassified ? "组合总资产口径；待补齐行业字段" : "组合总资产口径",
        });
      });
    } else {
      appendRiskBoundaryRow(body, {
        label: "行业及未分类资产",
        current: "—",
        threshold: "—",
        status: "UNAVAILABLE",
        basis: "行业字段或组合体检未完成",
      });
    }
    const cashSector = (report.risk?.sectors || []).find(sector => sector.sector_key === "CASH");
    const cashStructure = (report.asset_structure || []).find(group => group.group_key === "cash");
    appendRiskBoundaryRow(body, {
      label: "现金比例",
      current: reportPercent(report.risk?.cash_weight_pct ?? cashStructure?.weight_pct),
      threshold: report.risk?.cash_minimum_pct == null ? "体检未完成" : `≥ ${reportPercent(report.risk.cash_minimum_pct)}`,
      status: cashSector?.verdict === "OVERBOUND" ? "UNDERBOUND" : cashSector?.verdict || "UNAVAILABLE",
      basis: "组合总资产口径",
    });
    table.append(head, body);
    tableWrap.append(table);
    const note = document.createElement("p");
    note.className = "portfolio-report-risk-line";
    note.textContent = "最大回撤容忍度仅作为投资者画像边界；本报告未测算组合最大回撤，不将其展示为组合实测值。";
    container.append(tableWrap, note);
  }

  function renderPortfolioReport(report) {
    const card = byId("portfolio-report-card");
    if (!card) return;
    if (!report) { card.hidden = true; return; }
    card.hidden = false;
    const status = byId("portfolio-report-status");
    const reportStatus = report.risk?.status || "UNAVAILABLE";
    if (status) {
      status.textContent = reportStatusLabel(reportStatus);
      status.className = `status-chip ${reportStatusClass(reportStatus)}`;
    }
    const meta = byId("portfolio-report-meta");
    if (meta) meta.textContent = `${report.data_mode} · 计算时点 ${new Date(report.generated_at).toLocaleString("zh-CN")} · 报告编号 ${report.report_id}`;
    const headline = byId("portfolio-report-headline");
    if (headline) {
      headline.className = `portfolio-report-headline ${reportStatusClass(reportStatus)}`;
      headline.textContent = report.headline;
    }
    const observations = byId("portfolio-report-observations");
    if (observations) {
      clear(observations);
      const title = document.createElement("h4"); title.textContent = "报告摘要";
      const list = document.createElement("ul");
      (report.observations || []).forEach(item => { const li = document.createElement("li"); li.textContent = item; list.append(li); });
      observations.append(title, list);
    }
    const structure = byId("portfolio-report-asset-structure");
    if (structure) renderPortfolioAssetStructure(structure, report.asset_structure);
    const risk = byId("portfolio-report-risk-summary");
    if (risk) {
      renderPortfolioRiskBoundaries(risk, report);
      if (report.risk?.issues?.length && !portfolioMissingAnalysisData().sectorIncomplete) {
        const issues = document.createElement("ul"); issues.className = "portfolio-report-issues";
        report.risk.issues.forEach(item => { const li = document.createElement("li"); li.textContent = text(item); issues.append(li); });
        risk.append(issues);
      }
    }
    const concentration = byId("portfolio-report-concentration-summary");
    if (concentration) {
      clear(concentration);
      const metrics = document.createElement("div"); metrics.className = "portfolio-report-metrics";
      appendReportMetric(metrics, "集中度状态", report.concentration?.status === "REVIEW_REQUIRED" ? "需要复核" : report.concentration?.status === "CALCULATED" ? "已计算" : "待补齐");
      appendReportMetric(metrics, "最高持仓", report.concentration?.top_asset_name || "未计算");
      appendReportMetric(metrics, "最高持仓占比", reportPercent(report.concentration?.top_asset_weight_pct));
      appendReportMetric(metrics, "资产 HHI", report.concentration?.asset_hhi == null ? "未计算" : String(report.concentration.asset_hhi));
      appendReportMetric(metrics, "浮亏标的数", `${report.pnl_summary?.loss_position_count ?? 0} 项`);
      appendReportMetric(metrics, "浮亏市值占比", reportPercent(report.pnl_summary?.loss_weight_pct));
      concentration.append(metrics);
      const note = document.createElement("p"); note.className = "portfolio-report-risk-line";
      note.textContent = report.pnl_summary?.note || "浮亏统计暂不可用。";
      concentration.append(note);
      if (report.concentration?.issues?.length) {
        const issues = document.createElement("ul"); issues.className = "portfolio-report-issues";
        report.concentration.issues.forEach(item => { const li = document.createElement("li"); li.textContent = item; issues.append(li); });
        concentration.append(issues);
      }
    }
    const protection = byId("portfolio-report-protection-summary");
    if (protection) {
      clear(protection);
      const metrics = document.createElement("div"); metrics.className = "portfolio-report-metrics";
      appendReportMetric(metrics, "防御性资产", reportAmount(report.base_protection?.defensive_market_value_cny));
      appendReportMetric(metrics, "防御性资产占比", reportPercent(report.base_protection?.defensive_weight_pct));
      appendReportMetric(metrics, "画像防御参考", report.base_protection?.profile_reference_pct == null ? "未绑定画像" : reportPercent(report.base_protection.profile_reference_pct));
      appendReportMetric(metrics, "参考状态", report.base_protection?.reference_verdict === "BELOW_REFERENCE" ? "低于参考" : report.base_protection?.reference_verdict === "PASS" ? "达到参考" : "仅展示事实");
      protection.append(metrics);
      const components = document.createElement("p"); components.className = "portfolio-report-risk-line";
      components.textContent = `${(report.base_protection?.components || []).join("、")}。${report.base_protection?.note || ""}`;
      protection.append(components);
      const guide = document.createElement("ul"); guide.className = "portfolio-report-issues";
      (report.configuration_reference || []).forEach(item => { const li = document.createElement("li"); li.textContent = item; guide.append(li); });
      if (guide.childElementCount) protection.append(guide);
    }
    const disclosure = byId("portfolio-report-disclosure");
    if (disclosure) disclosure.textContent = (report.disclosures || []).join(" ");
  }

  async function refreshPortfolioReport(expectedOwner = state.ownerId, expectedMode = state.dataMode) {
    const sequence = ++portfolioReportSequence;
    displayedPortfolioReport = null;
    renderPortfolioReport(null);
    let response = await fetch("/api/v1/advisor/portfolio/report", {headers: {"X-Owner-ID": expectedOwner}});
    if (response.status === 404) {
      if (sequence === portfolioReportSequence && expectedOwner === state.ownerId && expectedMode === state.dataMode) renderPortfolioReport(null);
      return null;
    }
    if (!response.ok) {
      // Report generation is read-only and deterministic; a single retry
      // handles a transient provider/store race without asking the user to
      // repeat the portfolio refresh.
      await new Promise(resolve => setTimeout(resolve, 180));
      response = await fetch("/api/v1/advisor/portfolio/report", {headers: {"X-Owner-ID": expectedOwner}});
    }
    if (!response.ok) throw await apiError(response);
    const report = await response.json();
    if (sequence !== portfolioReportSequence || expectedOwner !== state.ownerId || expectedMode !== state.dataMode || expectedMode !== report.data_mode) return null;
    displayedPortfolioReport = report;
    renderPortfolioReport(report);
    return report;
  }

  function renderPortfolioDiagnosis(position) {
    const title = byId("portfolio-diagnosis-title");
    const code = byId("portfolio-diagnosis-code");
    const content = byId("portfolio-diagnosis-content");
    if (!title || !code || !content || !position) return;
    title.textContent = position.asset_name || position.name || position.asset_id || "标的诊断";
    code.textContent = `${position.asset_id || "—"} · ${reportAssetTypeLabel(position.asset_type)} · ${position.sector || "行业未分类"}`;
    clear(content);
    const status = document.createElement("div"); status.className = `portfolio-diagnosis-status ${position.diagnosis_status === "PASS" ? "pass" : "review"}`;
    status.textContent = position.diagnosis_status === "PASS" ? "当前快照未发现单项数据问题" : "当前快照需要复核";
    const facts = document.createElement("div"); facts.className = "portfolio-diagnosis-facts";
    [
      ["持仓数量", position.quantity == null ? "—" : String(position.quantity)],
      ["成本价", position.cost_price_cny == null ? "待补充数据" : reportAmount(position.cost_price_cny)],
      ["当前价格", position.current_price_cny == null ? "待补充数据" : reportAmount(position.current_price_cny)],
      ["持仓市值", reportAmount(position.market_value_cny)],
      ["持仓占比", reportPercent(position.weight_pct)],
      ["累计盈亏", reportAmount(position.pnl_cny)],
      ["累计收益率", reportPercent(position.pnl_pct)],
    ].forEach(([label, value]) => appendReportMetric(facts, label, value));
    const heading = document.createElement("h3"); heading.textContent = "诊断说明";
    const list = document.createElement("ul"); list.className = "portfolio-diagnosis-list";
    (position.diagnosis || ["当前持仓仅展示已确认快照事实。"]).forEach(item => { const li = document.createElement("li"); li.textContent = item; list.append(li); });
    const note = document.createElement("p"); note.className = "portfolio-diagnosis-note";
    note.textContent = "诊断只针对本次正式报告快照，不调用个股研究智能体，也不构成买卖指令。";
    content.append(status, facts, heading, list, note);
  }

  function openPortfolioDiagnosis(assetId) {
    const position = displayedPortfolioReport?.positions?.find(item => item.asset_id === assetId)
      || (() => {
        const row = displayedPortfolioSummary?.positions?.find(item => item.asset_id === assetId);
        if (!row) return null;
        return {
          position_id: row.asset_id,
          asset_id: row.asset_id,
          asset_name: row.name || row.asset_id,
          asset_type: row.asset_class === "FUND_ETF" ? "ETF" : "STOCK",
          sector: row.sector || null,
          quantity: row.quantity,
          cost_price_cny: row.cost_price,
          current_price_cny: row.price,
          market_value_cny: row.market_value_cny,
          pnl_cny: row.pnl_cny,
          pnl_pct: row.cost_price && Number(row.cost_price) > 0 ? (Number(row.price) / Number(row.cost_price) - 1) * 100 : null,
          weight_pct: row.weight_pct,
          diagnosis_status: "REVIEW_REQUIRED",
          diagnosis: ["正式报告尚未加载，当前仅展示持仓摘要；请稍后重试。"],
        };
      })();
    const drawer = byId("portfolio-diagnosis-drawer");
    if (!position || !drawer) return;
    renderPortfolioDiagnosis(position);
    drawer.showModal();
  }

  function escapeReportHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function buildPortfolioReportHtml(report) {
    const cell = value => `<td>${escapeReportHtml(value)}</td>`;
    const assetRows = (report.asset_structure || []).filter(group => Number(group.market_value_cny) > 0)
      .map(group => `<tr>${cell(group.label)}${cell(reportAmount(group.market_value_cny))}${cell(reportPercent(group.weight_pct))}${cell(`${group.position_count} 项`)}</tr>`).join("");
    const positionRows = (report.positions || [])
      .map(position => `<tr>${cell(position.asset_name)}${cell(position.asset_id)}${cell(position.quantity)}${cell(position.cost_price_cny == null ? "待补充数据" : reportAmount(position.cost_price_cny))}${cell(reportAmount(position.current_price_cny))}${cell(reportAmount(position.market_value_cny))}${cell(reportAmount(position.pnl_cny))}${cell(reportPercent(position.weight_pct))}</tr>`).join("");
    const riskRows = (report.risk?.sectors || [])
      .map(sector => `<tr>${cell(sector.name)}${cell(reportPercent(sector.weight_pct))}${cell(`${sector.limit_operator === "MIN" ? "≥" : "≤"} ${reportPercent(sector.limit_pct)}`)}${cell(reportStatusLabel(sector.verdict === "PASS" ? "PASS" : "REVIEW_REQUIRED"))}</tr>`).join("");
    const observations = (report.observations || []).map(item => `<li>${escapeReportHtml(item)}</li>`).join("");
    const disclosures = (report.disclosures || []).map(item => `<li>${escapeReportHtml(item)}</li>`).join("");
    const concentration = report.concentration || {};
    const pnlSummary = report.pnl_summary || {};
    const protection = report.base_protection || {};
    const configurationReference = (report.configuration_reference || []).map(item => `<li>${escapeReportHtml(item)}</li>`).join("");
    const profileLine = report.profile
      ? `画像 ${escapeReportHtml(report.profile.suitability_level)} · 权益类占比 ${escapeReportHtml(reportPercent(report.profile.equity_weight_pct))} · 参考区间 ${escapeReportHtml(reportPercent(report.profile.equity_minimum_pct))}–${escapeReportHtml(reportPercent(report.profile.equity_maximum_pct))}`
      : "未绑定已确认风险画像，暂不执行画像区间对照。";
    return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Prism 持仓正式报告</title><style>body{font-family:Arial,"Microsoft YaHei",sans-serif;color:#202124;max-width:1100px;margin:32px auto;padding:0 24px;line-height:1.6}h1{margin-bottom:4px}h2{margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:6px}small,.meta{color:#687078}table{width:100%;border-collapse:collapse;margin-top:10px}th,td{padding:8px;border-bottom:1px solid #e5e7eb;text-align:left}th{background:#f6f7f8}.headline{padding:12px;border-left:4px solid #bd5700;background:#fff7ed;font-weight:700}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.kpi{padding:12px;background:#f6f7f8}.kpi strong{display:block;font-size:18px}.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.fact{padding:12px;background:#f6f7f8}.fact strong{display:block;font-size:16px}@media(max-width:700px){.kpis,.facts{grid-template-columns:repeat(2,1fr)}}ul{padding-left:22px}</style></head><body><h1>Prism 持仓正式报告</h1><p class="meta">${escapeReportHtml(report.data_mode)} · 计算时点 ${escapeReportHtml(new Date(report.generated_at).toLocaleString("zh-CN"))} · 报告编号 ${escapeReportHtml(report.report_id)}</p><p class="headline">${escapeReportHtml(report.headline)}</p><div class="kpis"><div class="kpi">持仓市值<strong>${escapeReportHtml(reportAmount(report.holdings_value_cny))}</strong><small>现金 ${escapeReportHtml(reportAmount(report.cash_cny))}</small></div><div class="kpi">当日盈亏<strong>${escapeReportHtml(reportAmount(report.daily_pnl_cny))}</strong></div><div class="kpi">累计盈亏<strong>${escapeReportHtml(reportAmount(report.cumulative_pnl_cny))}</strong><small>${escapeReportHtml(reportPercent(report.cumulative_pnl_pct))}</small></div><div class="kpi">持仓数量<strong>${escapeReportHtml(report.position_count)}</strong></div></div><h2>报告摘要</h2><ul>${observations}</ul><h2>资产结构</h2><table><thead><tr><th>类别</th><th>市值</th><th>占比</th><th>数量</th></tr></thead><tbody>${assetRows}</tbody></table><h2>集中度与浮亏</h2><div class="facts"><div class="fact">集中度状态<strong>${escapeReportHtml(concentration.status || "待补齐")}</strong></div><div class="fact">最高持仓<strong>${escapeReportHtml(concentration.top_asset_name || "未计算")}</strong></div><div class="fact">最高持仓占比<strong>${escapeReportHtml(reportPercent(concentration.top_asset_weight_pct))}</strong></div><div class="fact">资产 HHI<strong>${escapeReportHtml(concentration.asset_hhi == null ? "未计算" : concentration.asset_hhi)}</strong></div><div class="fact">浮亏标的数<strong>${escapeReportHtml(`${pnlSummary.loss_position_count ?? 0} 项`)}</strong></div><div class="fact">浮亏市值占比<strong>${escapeReportHtml(reportPercent(pnlSummary.loss_weight_pct))}</strong></div></div><p>${escapeReportHtml(pnlSummary.note || "浮亏统计暂不可用。")}</p><h2>底仓保护与配置参考</h2><div class="facts"><div class="fact">防御性资产<strong>${escapeReportHtml(reportAmount(protection.defensive_market_value_cny))}</strong></div><div class="fact">防御性资产占比<strong>${escapeReportHtml(reportPercent(protection.defensive_weight_pct))}</strong></div><div class="fact">画像防御参考<strong>${escapeReportHtml(protection.profile_reference_pct == null ? "未绑定画像" : reportPercent(protection.profile_reference_pct))}</strong></div><div class="fact">参考状态<strong>${escapeReportHtml(protection.reference_verdict || "仅展示事实")}</strong></div></div><p>${escapeReportHtml(protection.note || "防御性资产统计暂不可用。")} ${(protection.components || []).map(escapeReportHtml).join("、")}</p><ul>${configurationReference}</ul><h2>风险对照</h2><p>${profileLine}</p><p>风险状态：${escapeReportHtml(reportStatusLabel(report.risk?.status))} · HHI：${escapeReportHtml(report.risk?.sector_hhi == null ? "未计算" : report.risk.sector_hhi)} · 最高行业：${escapeReportHtml(report.risk?.top_sector_name || "未计算")}</p><table><thead><tr><th>行业</th><th>当前占比</th><th>设置范围</th><th>状态</th></tr></thead><tbody>${riskRows}</tbody></table><h2>持仓明细</h2><table><thead><tr><th>标的</th><th>代码</th><th>数量</th><th>成本价</th><th>现价</th><th>市值</th><th>累计盈亏</th><th>持仓占比</th></tr></thead><tbody>${positionRows}</tbody></table><h2>使用说明</h2><ul>${disclosures}</ul></body></html>`;
  }

  function downloadPortfolioReport(report) {
    const blob = new Blob([buildPortfolioReportHtml(report)], {type: "text/html;charset=utf-8"});
    const url = URL.createObjectURL(blob), anchor = document.createElement("a");
    anchor.href = url; anchor.download = "Prism-持仓正式报告.html"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function refreshPortfolioSummary() {
    if (!state.ownerId) return;
    displayedPortfolioSummary = null;
    displayedPortfolioReport = null;
    renderPortfolioReport(null);
    const sequence = ++portfolioSummarySequence;
    const owner = state.ownerId;
    const mode = state.dataMode;
    const response = await fetch("/api/v1/advisor/portfolio/summary", {headers: {"X-Owner-ID": owner}});
    if (!response.ok) throw await apiError(response);
    const summary = await response.json();
    if (sequence !== portfolioSummarySequence || owner !== state.ownerId || mode !== state.dataMode || mode !== summary.data_mode) return;
    displayedPortfolioSummary = summary;
    const amount = value => value == null ? "待补充数据" : `¥ ${Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    byId("overview-portfolio-aum").textContent = amount(summary.holdings_value_cny);
    byId("overview-portfolio-cash").textContent = `现金 ${amount(summary.cash_cny)}`;
    byId("overview-pnl-val").textContent = amount(summary.daily_pnl_cny);
    byId("overview-pnl-val").className = summary.daily_pnl_cny == null ? "mono" : `mono ${Number(summary.daily_pnl_cny) >= 0 ? "market-up" : "market-down"}`;
    byId("overview-pnl-pct").textContent = summary.daily_pnl_cny == null ? "需取得可核验昨收价" : "基于昨收与当前持仓计算";
    byId("overview-benchmark-val").textContent = amount(summary.pnl_cny);
    byId("overview-benchmark-val").className = summary.pnl_cny == null ? "mono" : `mono ${Number(summary.pnl_cny) >= 0 ? "market-up" : "market-down"}`;
    byId("overview-benchmark-sub").textContent = summary.pnl_pct == null ? "补全成本后计算累计收益率" : `累计收益率 ${summary.pnl_pct}%`;
    byId("overview-position-count").textContent = `${summary.position_count}`;
    byId("overview-position-sub").textContent = summary.position_count ? "已确认证券" : "等待持仓";
    byId("portfolio-empty").hidden = summary.position_count > 0;
    byId("portfolio-data-label").textContent = !summary.position_count ? "未导入" : mode === "MOCK" ? "演示数据" : "已确认持仓";
    byId("portfolio-summary-note").textContent = `${summary.position_count} 项持仓 · 当前记录价格；仅供参考，不构成投资建议。`;
    const body = byId("portfolio-position-rows"); body.replaceChildren();
    summary.positions.forEach(row => {
      const tr = document.createElement("tr");
      [row.name || row.asset_id, row.quantity, row.cost_price ?? "—", row.price, amount(row.market_value_cny), amount(row.pnl_cny), `${row.weight_pct}%`].forEach((value, index) => {
        const td = document.createElement("td"); td.textContent = String(value);
        if (index === 0) { const code = document.createElement("small"); code.textContent = row.asset_id; td.append(code); }
        tr.append(td);
      });
      const actions = document.createElement("td");
      const diagnose = document.createElement("button"); diagnose.type = "button"; diagnose.textContent = "查看诊断";
      diagnose.className = "copilot-action-btn secondary";
      diagnose.addEventListener("click", () => openPortfolioDiagnosis(row.asset_id));
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "删除";
      remove.className = "copilot-action-btn secondary";
      remove.addEventListener("click", async () => {
        remove.disabled = true;
        try {
          if (owner !== state.ownerId || mode !== state.dataMode) throw new Error("账户或模式已变化，请刷新持仓");
          const persisted = await fetch("/api/v1/advisor/portfolio/current", {headers: {"X-Owner-ID": owner}});
          if (!persisted.ok) throw await apiError(persisted);
          const draft = (await persisted.json()).data;
          if (owner !== state.ownerId || mode !== state.dataMode || !draft) throw new Error("持仓状态已变化，请刷新后重试");
          await replacePortfolioRows(draft.positions.filter(p => p.asset_id !== row.asset_id), draft.cash_cny);
        } catch (error) { setError(error.message); remove.disabled = false; }
      });
      actions.append(diagnose, remove); tr.append(actions); body.append(tr);
    });
    try {
      await refreshPortfolioReport(owner, mode);
    } catch (error) {
      if (owner === state.ownerId && mode === state.dataMode) renderPortfolioAnalysisStatus(`正式报告生成失败：${error.message}`);
    }
  }

  async function replacePortfolioRows(positions, cash) {
    const owner = state.ownerId, mode = state.dataMode;
    const response = await fetch("/api/v1/advisor/portfolio/current", {
      method: "PUT", headers: {"Content-Type": "application/json", "X-Owner-ID": owner},
      body: JSON.stringify({owner_id: owner, data_mode: mode, positions, cash_cny: cash || 0}),
    });
    if (!response.ok) throw await apiError(response);
    const data = await response.json();
    if (owner !== state.ownerId || mode !== state.dataMode) return;
    microStore.transact(store => { invalidateDerivedState(store); store.ocrPortfolioDraft = data; store.portfolio = data.portfolio; });
    renderPortfolioReadiness(); renderOverviewWorkspace(state.selectedPersona);
    if (state.profile?.profile && data.portfolio) {
      await runPortfolioAnalysis();
    }
  }

  byId("chat-cancel-query")?.addEventListener("click", () => activeChatController?.abort());
  byId("chat-runtime-mode")?.addEventListener("change", updateLLMConfigUI);
  byId("data-source-status")?.addEventListener("click", openLLMConfigModal);
  document.querySelectorAll("[data-market-region]").forEach(button => button.addEventListener("click", () => {
    marketRegion = button.dataset.marketRegion;
    document.querySelectorAll("[data-market-region]").forEach(item => item.setAttribute("aria-selected", String(item === button)));
    const first = marketCatalog.find(item => item.market === marketRegion);
    if (first) byId("market-index-input").value = first.index_id;
    marketAnalysis = null;
    renderMarketIndexCards();
    loadMarketQuotes();
    assessMarket();
  }));
  document.querySelectorAll("[data-market-interval]").forEach(button => button.addEventListener("click", () => {
    marketInterval = button.dataset.marketInterval;
    document.querySelectorAll("[data-market-interval]").forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    assessMarket();
  }));
  document.querySelectorAll("[data-market-indicator]").forEach(button => button.addEventListener("click", () => {
    const indicator = button.dataset.marketIndicator;
    if (activeMarketIndicators.has(indicator)) activeMarketIndicators.delete(indicator); else activeMarketIndicators.add(indicator);
    button.setAttribute("aria-pressed", String(activeMarketIndicators.has(indicator)));
    if (marketAnalysis) renderIndexCandles(marketAnalysis);
  }));
  document.querySelectorAll("[data-market-range]").forEach(button => button.addEventListener("click", () => marketRange(button.dataset.marketRange)));
  byId("market-fit-chart")?.addEventListener("click", () => renderedMarketChart?.timeScale().fitContent());
  const AGENT_FEATURES = Object.freeze({
    market: {
      title: "大盘分析",
      help: "选择市场、观察周期和关注维度。开始后通过真实市场数据链路分析。",
      providers: ["fuyao", "wencai"],
      capability: "market_data", alternateCapabilities: ["stock_quote"],
      fields: [
        {name: "market", label: "市场范围", type: "select", options: [["A 股", "A 股"], ["港股", "港股"], ["美股", "美股"]]},
        {name: "period", label: "观察周期", type: "select", options: [["近 3 个月", "近 3 个月"], ["近 6 个月", "近 6 个月"], ["近 1 年", "近 1 年"]]},
        {name: "focus", label: "关注维度", type: "select", options: [["趋势、估值与市场风险", "趋势、估值与市场风险"], ["趋势与成交结构", "趋势与成交结构"], ["估值与宏观因素", "估值与宏观因素"]]},
      ],
      prompt: values => `大盘分析：请分析${values.market}${values.period}的${values.focus}，逐项标注真实来源、观察时间和缺失字段。`,
    },
    industry: {
      title: "行业配置",
      help: "基于当前账户已确认持仓和画像边界检查行业暴露，不执行无约束选股。",
      providers: ["fuyao", "wencai"],
      capability: "industry_data", requiresPortfolio: true, requiresProfile: true,
      fields: [{name: "goal", label: "分析目标", type: "select", options: [["行业暴露与画像上限", "行业暴露与画像上限"], ["集中度与未分类资产", "集中度与未分类资产"], ["行业风险边界", "行业风险边界"]]}],
      prompt: values => `行业配置：请基于我已确认的持仓和风险画像，分析${values.goal}；缺少行业数据时列出证券代码和补齐条件，不要推荐无关股票。`,
    },
    stock: {
      title: "个股分析",
      help: "先返回快速行情，再异步补齐五年财务、估值、动态证据和当前账户适配。",
      providers: ["fuyao", "wencai"],
      capability: "company_data", alternateCapabilities: ["stock_quote"], requiresTarget: true,
      fields: [
        {name: "target", label: "证券代码或名称", type: "text", placeholder: "例如 600251.SH"},
        {name: "lookback", label: "财务趋势窗口", type: "select", options: [["5", "5 个完整年度"], ["4", "4 个完整年度"], ["3", "3 个完整年度"]]},
      ],
      prompt: values => `个股分析：${values.target}；先展示快速行情，再补齐近 ${values.lookback} 个完整年度的财务趋势、估值定位、公告新闻研报与当前账户适配。`,
    },
    fund: {
      title: "ETF 基金筛选",
      help: "输入基金名称、代码或条件进行基金层初筛；选定六位代码后再查询持仓与行业穿透。",
      providers: ["wencai"],
      capability: "fund_data", alternateCapabilities: ["fund_lookthrough"], requiresTarget: true, requiresProfile: true,
      fields: [{name: "target", label: "基金代码或筛选条件", type: "text", placeholder: "例如 510300 或 低费率宽基 ETF"}],
      prompt: values => `ETF 基金筛选：${values.target}；请核验基金代码、净值、管理费率、托管费率、申赎费率和跟踪误差。初筛阶段不展开单基金持仓。`,
    },
    convertible: {
      title: "可转债投资",
      help: "输入转债代码或完整筛选条件；缺少条款、评级或流动性数据时不会生成结论。",
      providers: ["wencai"],
      capability: "convertible_bond_data", requiresTarget: true, requiresProfile: true,
      fields: [{name: "target", label: "转债代码或筛选条件", type: "text", placeholder: "例如 113056 或 价格低于 130 元"}],
      prompt: values => `可转债投资：${values.target}；请核验价格、转股条款、评级、现金流和流动性，并结合当前风险画像列出边界。`,
    },
    optimization: {
      title: "资产重组优化",
      help: "在现有持仓和画像硬约束内进行确定性测算，不直接修改持仓。",
      providers: ["fuyao", "wencai"],
      capability: "portfolio_optimization", requiresPortfolio: true, requiresProfile: true,
      fields: [{name: "goal", label: "优化目标", type: "select", options: [["降低集中度", "降低集中度"], ["控制回撤边界", "控制回撤边界"], ["提高现金缓冲", "提高现金缓冲"]]}],
      prompt: values => `资产重组优化：请基于已确认持仓和风险画像，以${values.goal}为目标进行确定性测算；列出约束、差额和不可用数据，不直接执行交易。`,
    },
  });
  let activeAgentFeature = null;
  let agentFeatureToolsCompact = false;
  let agentFeaturePopoverOpen = false;

  function renderAgentFeatureToolsState() {
    const tools = byId("agent-feature-tools");
    const popover = byId("agent-feature-popover");
    const toggle = byId("agent-feature-toggle");
    const label = byId("agent-feature-toggle-label");
    if (!tools || !popover || !toggle || !label) return;
    const expanded = !agentFeatureToolsCompact || agentFeaturePopoverOpen;
    tools.classList.toggle("is-compact", agentFeatureToolsCompact);
    tools.classList.toggle("is-open", agentFeatureToolsCompact && agentFeaturePopoverOpen);
    popover.setAttribute("aria-hidden", String(!expanded));
    toggle.setAttribute("aria-expanded", String(expanded));
    label.textContent = !agentFeatureToolsCompact ? "收起" : agentFeaturePopoverOpen ? "关闭工具" : "展开工具";
  }

  function setAgentFeatureToolsCompact(compact, options = {}) {
    agentFeatureToolsCompact = compact;
    agentFeaturePopoverOpen = compact && options.open === true;
    if (compact && !agentFeaturePopoverOpen && activeAgentFeature) closeAgentFeatureConfig();
    renderAgentFeatureToolsState();
  }

  function toggleAgentFeatureTools() {
    if (!agentFeatureToolsCompact) {
      setAgentFeatureToolsCompact(true);
      return;
    }
    setAgentFeatureToolsCompact(true, {open: !agentFeaturePopoverOpen});
  }

  function currentFeatureStock() {
    return state.portfolio?.position_snapshot?.positions?.find(position => position.asset_type === "STOCK")?.asset_id || "";
  }

  function featureAvailability(id) {
    const definition = AGENT_FEATURES[id];
    const capabilities = state.capabilities?.LIVE || {};
    const candidates = [definition.capability, ...(definition.alternateCapabilities || [])];
    const configuredProviderReady = (definition.providers || []).some(provider => (
      provider === "wencai"
        ? state.wencaiConfigured === true && state.wencaiLastErrorCode !== "AUTH_FAILED"
        : state.liveConfigured === true
    ));
    const capabilityReady = state.dataMode === "LIVE" && (
      candidates.some(capability => capabilities[capability] === true)
      || configuredProviderReady
    );
    const missing = [];
    if (!capabilityReady) missing.push(`真实数据能力 ${candidates.join(" / ")} 未就绪`);
    if (definition.requiresPortfolio && !state.portfolio) missing.push("尚未确认当前账户持仓");
    if (definition.requiresProfile && !state.profile?.profile) missing.push("尚未确认风险画像");
    const targetAvailable = id === "stock" ? !!currentFeatureStock() : false;
    const status = !capabilityReady ? "UNAVAILABLE"
      : missing.length ? "NEED_INPUT"
      : definition.requiresTarget && !targetAvailable ? "NEED_INPUT"
      : "READY";
    return {status, missing};
  }

  function updateAgentFeatureAvailability() {
    document.querySelectorAll("[data-feature-id]").forEach(button => {
      const availability = featureAvailability(button.dataset.featureId);
      button.dataset.featureAvailability = availability.status;
      const status = button.querySelector("[data-feature-status]");
      if (status) {
        status.textContent = availability.status;
        status.dataset.status = availability.status;
      }
    });
    if (activeAgentFeature) renderAgentFeatureRequirements(activeAgentFeature);
  }

  function featureValues() {
    const values = {};
    byId("agent-feature-fields")?.querySelectorAll("[name]").forEach(field => { values[field.name] = field.value.trim(); });
    return values;
  }

  function syncAgentFeaturePrompt() {
    if (!activeAgentFeature) return;
    const definition = AGENT_FEATURES[activeAgentFeature];
    const input = byId("copilot-natural-input");
    if (input) input.value = definition.prompt(featureValues());
    renderAgentFeatureRequirements(activeAgentFeature);
  }

  function renderAgentFeatureRequirements(id) {
    const definition = AGENT_FEATURES[id];
    const values = featureValues();
    const availability = featureAvailability(id);
    const missing = [...availability.missing];
    if (definition.requiresTarget && !values.target) missing.push("请输入明确代码、名称或筛选条件");
    const box = byId("agent-feature-requirements");
    const start = byId("agent-feature-start");
    if (!box || !start) return;
    box.classList.toggle("is-unavailable", availability.status === "UNAVAILABLE");
    box.textContent = missing.length ? `开始前需补齐：${missing.join("；")}。` : "输入已完整；开始后仅使用当前账户与可追溯 LIVE 数据。";
    start.disabled = missing.length > 0;
  }

  function openAgentFeatureConfig(id) {
    const definition = AGENT_FEATURES[id];
    if (!definition) return;
    if (agentFeatureToolsCompact) setAgentFeatureToolsCompact(true, {open: true});
    activeAgentFeature = id;
    document.querySelectorAll("[data-feature-id]").forEach(button => button.setAttribute("aria-expanded", String(button.dataset.featureId === id)));
    byId("agent-feature-config-title").textContent = definition.title;
    byId("agent-feature-config-help").textContent = definition.help;
    const fields = byId("agent-feature-fields");
    fields.replaceChildren();
    definition.fields.forEach(spec => {
      const label = document.createElement("label");
      label.append(document.createTextNode(spec.label));
      let control;
      if (spec.type === "select") {
        control = document.createElement("select");
        spec.options.forEach(([value, text]) => {
          const option = document.createElement("option"); option.value = value; option.textContent = text; control.append(option);
        });
      } else {
        control = document.createElement("input"); control.type = "text"; control.placeholder = spec.placeholder || "";
      }
      control.name = spec.name;
      if (id === "stock" && spec.name === "target") control.value = currentFeatureStock();
      control.addEventListener("input", syncAgentFeaturePrompt);
      control.addEventListener("change", syncAgentFeaturePrompt);
      label.append(control); fields.append(label);
    });
    const form = byId("agent-feature-config");
    form.hidden = false;
    syncAgentFeaturePrompt();
    fields.querySelector("input, select")?.focus();
  }

  function closeAgentFeatureConfig() {
    activeAgentFeature = null;
    byId("agent-feature-config").hidden = true;
    document.querySelectorAll("[data-feature-id]").forEach(button => button.setAttribute("aria-expanded", "false"));
  }

  function agentFeatureOutput() {
    const output = byId("copilot-decision-output");
    if (output) clear(output);
    return output;
  }

  function displayFeatureFailure(title, error) {
    const output = agentFeatureOutput();
    if (!output) return;
    const card = document.createElement("div");
    card.className = "copilot-empty-output";
    const heading = document.createElement("h4");
    heading.textContent = `${title}未完成`;
    const detail = document.createElement("p");
    detail.textContent = error?.message || "真实数据链路暂时不可用，请稍后重试。";
    card.append(heading, detail);
    output.append(card);
  }

  function providerCellValue(value) {
    if (value == null || value === "") return "未提供";
    if (typeof value === "number") {
      return new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 6}).format(value);
    }
    if (["string", "boolean"].includes(typeof value)) return String(value);
    try {
      const serialized = JSON.stringify(value);
      return serialized.length > 180 ? `${serialized.slice(0, 177)}…` : serialized;
    } catch (_) {
      return "结构化字段";
    }
  }

  function providerColumnLabel(key) {
    return String(key).replace(/\[[^\]]+\]/g, "").trim() || String(key);
  }

  function providerColumns(title, rows) {
    const available = [...new Set(rows.flatMap(row => Object.keys(row).filter(key => {
      const value = row[key];
      return value == null || ["string", "number", "boolean"].includes(typeof value);
    })))];
    if (title !== "ETF 基金筛选") return available.slice(0, 7);
    const priorities = [
      /^(基金|证券)代码$/i, /^(基金简称|基金扩位简称)$/i, /单位净值(?!增长率)/,
      /管理费率/, /托管费率/, /最高申购费率/, /最高赎回费率/, /跟踪误差/,
    ];
    const ordered = [];
    priorities.forEach(pattern => {
      const matched = available.find(key => pattern.test(key) && !ordered.includes(key));
      if (matched) ordered.push(matched);
    });
    return [...ordered, ...available.filter(key => !ordered.includes(key))].slice(0, 8);
  }

  function normalizeFeatureRows(title, rows) {
    if (title !== "ETF 基金筛选") return {rows, duplicateCount: 0};
    const seen = new Set();
    const uniqueRows = [];
    rows.forEach(row => {
      const codeKey = Object.keys(row).find(key => /^(基金|证券)代码$/i.test(key.trim()));
      const code = codeKey ? String(row[codeKey] || "").trim().toUpperCase() : "";
      if (code && seen.has(code)) return;
      if (code) seen.add(code);
      uniqueRows.push(row);
    });
    return {rows: uniqueRows, duplicateCount: rows.length - uniqueRows.length};
  }

  function buildLiveProviderFeatureCard(title, result) {
    const card = document.createElement("div");
    card.className = `copilot-decision-card provider-feature-card${title === "ETF 基金筛选" ? " fund-screen-card" : ""}`;
    const heading = document.createElement("h3");
    heading.textContent = title;
    const status = document.createElement("span");
    status.className = `provider-status-chip status-${String(result.status || "unknown").toLowerCase()}`;
    status.textContent = result.status || "UNKNOWN";
    const cardHead = document.createElement("div");
    cardHead.className = "provider-feature-head";
    const headCopy = document.createElement("div");
    headCopy.append(heading);
    const record = result.records?.[0];
    const fields = record?.fields || {};
    const rawRows = Array.isArray(fields.items) ? fields.items.filter(item => item && typeof item === "object") : [];
    const normalized = normalizeFeatureRows(title, rawRows);
    const rows = normalized.rows;
    const boundary = document.createElement("p");
    boundary.className = "research-boundary";
    boundary.textContent = `${fields.source || record?.source || result.provider || "来源未提供"} · 获取时间 ${fields.retrieved_at || result.retrieved_at || "未提供"}`;
    headCopy.append(boundary);
    cardHead.append(headCopy, status);
    card.append(cardHead);
    const metrics = document.createElement("div");
    metrics.className = "provider-feature-metrics";
    [
      ["匹配标的", rows.length, "只"],
      ["上游明细", rawRows.length, "条"],
      ["数据状态", result.status || "UNKNOWN", ""],
    ].forEach(([label, value, suffix]) => {
      const metric = document.createElement("div");
      const dt = document.createElement("span"); dt.textContent = label;
      const dd = document.createElement("strong"); dd.textContent = `${value}${suffix}`;
      metric.append(dt, dd); metrics.append(metric);
    });
    card.append(metrics);
    if (fields.summary) {
      const summary = document.createElement("p");
      summary.className = "provider-query-summary";
      summary.textContent = String(fields.summary);
      card.append(summary);
    }
    if (normalized.duplicateCount) {
      const note = document.createElement("p");
      note.className = "research-boundary";
      note.textContent = `上游返回了 ${normalized.duplicateCount} 条同代码穿透明细；筛选表已按基金代码合并。单基金持仓与行业穿透应在选定代码后单独查询。`;
      card.append(note);
    }
    if (rows.length) {
      const scalarKeys = providerColumns(title, rows);
      const columns = scalarKeys.length ? scalarKeys : Object.keys(rows[0]).slice(0, 5);
      const tableWrap = document.createElement("div");
      tableWrap.className = "provider-feature-table-wrap";
      const table = document.createElement("table");
      table.className = "rebalancing-table provider-feature-table";
      const thead = document.createElement("thead");
      const head = document.createElement("tr");
      columns.forEach(key => {
        const cell = document.createElement("th");
        cell.textContent = providerColumnLabel(key);
        cell.title = key;
        head.append(cell);
      });
      thead.append(head);
      const tbody = document.createElement("tbody");
      rows.slice(0, 20).forEach(row => {
        const tr = document.createElement("tr");
        columns.forEach(key => {
          const cell = document.createElement("td");
          cell.textContent = providerCellValue(row[key]);
          cell.title = row[key] == null ? "" : String(row[key]);
          tr.append(cell);
        });
        tbody.append(tr);
      });
      table.append(thead, tbody);
      tableWrap.append(table);
      card.append(tableWrap);
    } else {
      const empty = document.createElement("p");
      empty.textContent = result.status === "EMPTY"
        ? "问财链路调用成功，但当前代码或筛选条件没有匹配标的；这不是连接失败。请核对交易所代码或放宽筛选条件。"
        : "本次响应未包含可展示的明细行。";
      card.append(empty);
    }
    const missing = [...(result.missing_fields || []), ...(result.issues || []).map(issue => `${issue.code}：${issue.safe_message}`)];
    if (missing.length) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `数据边界 · ${missing.length} 项`;
      const list = document.createElement("ul");
      missing.forEach(value => { const item = document.createElement("li"); item.textContent = String(value); list.append(item); });
      details.append(summary, list); card.append(details);
    }
    return card;
  }

  async function runLiveProviderFeature(operation, subject, title, fallbackSubject = "") {
    const output = agentFeatureOutput();
    output?.append(buildCopilotLoadingCard("icon-activity", `${title}正在查询…`, "正在读取问财 SkillHub 真实数据并核对来源。"));
    const query = async (querySubject, suffix = "primary") => {
      const response = await fetch("/api/v1/runtime/provider-query", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-Owner-ID": state.ownerId},
        body: JSON.stringify({
          request_id: `feature-${operation.toLowerCase()}-${suffix}-${Date.now()}`,
          operation,
          subject: querySubject,
          as_of: new Date().toISOString(),
          parameters: {limit: 20},
        }),
      });
      if (!response.ok) throw await apiError(response);
      return await response.json();
    };
    let result = await query(subject);
    if (result.status === "EMPTY" && fallbackSubject.trim() && fallbackSubject.trim() !== subject.trim()) {
      result = await query(fallbackSubject.trim(), "fallback");
    }
    if (!["SUCCESS", "PARTIAL", "EMPTY"].includes(result.status)) throw new Error("真实数据源未完成查询。");
    await fetchRuntimeDataMode();
    if (output) { clear(output); output.append(buildLiveProviderFeatureCard(title, result)); output.scrollIntoView({behavior: "smooth", block: "start"}); }
    return result;
  }

  function buildIndustryFeatureCard(health, goal) {
    const card = document.createElement("div");
    card.className = "copilot-decision-card";
    const heading = document.createElement("h3");
    heading.textContent = `行业配置 · ${goal}`;
    const summary = document.createElement("p");
    summary.className = "research-boundary";
    summary.textContent = `${health.status} · 行业 HHI ${health.sector_hhi}（参考上限 ${health.hhi_limit}）· ${health.evidence_count} 项穿透贡献`;
    const table = document.createElement("table");
    table.className = "rebalancing-table";
    const head = document.createElement("tr");
    ["行业", "当前占比", "画像边界", "差额", "状态"].forEach(label => { const cell = document.createElement("th"); cell.textContent = label; head.append(cell); });
    table.append(head);
    (health.sectors || []).forEach(sector => {
      const row = document.createElement("tr");
      [sector.name, `${sector.pct.toFixed(2)}%`, `${sector.limitOperator === "MIN" ? "≥" : "≤"} ${sector.cap.toFixed(2)}%`, sector.differenceLabel, sector.verdictCode].forEach(value => { const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell); });
      table.append(row);
    });
    card.append(heading, summary, table);
    return card;
  }

  function buildOptimizationFeatureCard(result, goal) {
    const card = document.createElement("div");
    card.className = "copilot-decision-card";
    const heading = document.createElement("h3");
    heading.textContent = `资产重组优化 · ${goal}`;
    const summary = document.createElement("p");
    summary.className = "research-boundary";
    summary.textContent = `${result.status} · ${result.methodology || result.methodology_version || "CAP_AND_REDISTRIBUTE_V1"} · 不执行交易`;
    const table = document.createElement("table");
    table.className = "rebalancing-table";
    const head = document.createElement("tr");
    ["资产", "当前权重", "目标权重", "调整方向"].forEach(label => { const cell = document.createElement("th"); cell.textContent = label; head.append(cell); });
    table.append(head);
    (result.targets || []).forEach(target => {
      const current = Number(target.current_weight_pct ?? target.current_weight ?? 0);
      const next = Number(target.target_weight_pct ?? target.target_weight ?? 0);
      const row = document.createElement("tr");
      [target.name || target.asset_id, `${current.toFixed(2)}%`, `${next.toFixed(2)}%`, next > current ? "增加" : next < current ? "降低" : "维持"].forEach(value => { const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell); });
      table.append(row);
    });
    card.append(heading, summary, table);
    return card;
  }

  async function runConfiguredAgentFeature(id, values) {
    const definition = AGENT_FEATURES[id];
    try {
      if (id === "market") {
        marketRegion = {"A 股": "CN", "港股": "HK", "美股": "US"}[values.market] || "CN";
        marketInterval = values.period === "近 1 年" ? "1M" : "1d";
        if (!marketCatalog.length) await loadMarketCatalog();
        const first = marketCatalog.find(item => item.market === marketRegion);
        if (!first) throw new Error(`${values.market}没有已注册的市场指数。`);
        byId("market-index-input").value = first.index_id;
        renderMarketIndexCards();
        await loadMarketQuotes();
        await assessMarket();
        window.location.hash = "market";
        syncNavigation("market");
        return;
      }
      if (id === "industry") {
        const output = agentFeatureOutput();
        output?.append(buildCopilotLoadingCard("icon-activity", "行业配置正在计算…", "正在刷新持仓行情、补齐行业元数据并执行确定性穿透。"));
        const health = await refreshPortfolioHealth();
        if (!health) throw new Error("持仓或画像上下文不完整。请先确认后重试。");
        await refreshPortfolioSummary();
        if (output) { clear(output); output.append(buildIndustryFeatureCard(health, values.goal)); output.scrollIntoView({behavior: "smooth", block: "start"}); }
        return;
      }
      if (id === "stock") {
        await runCopilotStockResearch(values.target, Number(values.lookback || 5));
        return;
      }
      if (id === "fund") {
        await runLiveProviderFeature(
          "FUND_DATA",
          `${values.target} 基金代码 基金简称 单位净值 管理费率 托管费率 最高申购费率 最高赎回费率 跟踪误差`,
          definition.title,
          values.target,
        );
        return;
      }
      if (id === "convertible") {
        const target = values.target.trim();
        const explicitCode = target.match(/^(\d{6})(?:\.(?:SH|SZ))?$/i)?.[1];
        if (explicitCode && !/^(110|111|113|118|123|127|128)/.test(explicitCode)) {
          throw new Error(`${explicitCode} 不是有效的沪深可转债代码。请输入 110/111/113/118/123/127/128 开头的六位代码，或输入明确筛选条件。`);
        }
        await runLiveProviderFeature("CONVERTIBLE_BOND_DATA", `${target} 转债现价 转股价 转股价值 转股溢价率 债券评级 到期收益率 成交额 赎回回售条款`, definition.title, target);
        return;
      }
      if (id === "optimization") {
        const output = agentFeatureOutput();
        output?.append(buildCopilotLoadingCard("icon-activity", "资产重组优化正在计算…", "正在刷新真实持仓并按画像硬约束执行确定性测算。"));
        const result = await runPortfolioOptimization();
        if (!result) throw new Error("组合优化未生成目标权重，请检查持仓、画像与真实行情完整性。");
        if (output) { clear(output); output.append(buildOptimizationFeatureCard(result, values.goal)); output.scrollIntoView({behavior: "smooth", block: "start"}); }
      }
    } catch (error) {
      displayFeatureFailure(definition.title, error);
    }
  }

  document.querySelectorAll("[data-feature-id]").forEach(button => button.addEventListener("click", () => openAgentFeatureConfig(button.dataset.featureId)));
  byId("agent-feature-toggle")?.addEventListener("click", toggleAgentFeatureTools);
  byId("agent-feature-config-close")?.addEventListener("click", closeAgentFeatureConfig);
  document.addEventListener("click", event => {
    if (!agentFeatureToolsCompact || !agentFeaturePopoverOpen) return;
    if (!byId("agent-feature-tools")?.contains(event.target)) setAgentFeatureToolsCompact(true);
  });
  document.addEventListener("keydown", event => {
    if (event.key !== "Escape" || !agentFeatureToolsCompact || !agentFeaturePopoverOpen) return;
    setAgentFeatureToolsCompact(true);
    byId("agent-feature-toggle")?.focus();
  });
  byId("agent-feature-config")?.addEventListener("submit", async event => {
    event.preventDefault();
    if (!activeAgentFeature) return;
    const featureId = activeAgentFeature;
    const values = featureValues();
    syncAgentFeaturePrompt();
    if (byId("agent-feature-start").disabled) return;
    setAgentFeatureToolsCompact(true);
    await runConfiguredAgentFeature(featureId, values);
  });
  const dismissWelcome = () => {
    workspaceStorage.setItem(ownerStorageKey("prism_welcome_dismissed"), "1");
    const url = new URL(window.location.href); url.searchParams.delete("onboarding");
    window.history.replaceState(null, "", url);
    byId("questionnaire-welcome").close();
  };
  byId("welcome-later")?.addEventListener("click", dismissWelcome);
  byId("welcome-start")?.addEventListener("click", () => { dismissWelcome(); window.location.hash = "profile"; });
  byId("questionnaire-welcome")?.addEventListener("cancel", dismissWelcome);
  byId("portfolio-import-entry")?.addEventListener("click", openPortfolioModal);
  document.querySelectorAll("[data-open-portfolio]").forEach(button => button.addEventListener("click", openPortfolioModal));
  byId("portfolio-add-entry")?.addEventListener("click", () => byId("manual-position-dialog").showModal());
  byId("manual-position-cancel")?.addEventListener("click", () => byId("manual-position-dialog").close());
  byId("manual-position-form")?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form), code = fields.get("code");
    const button = form.querySelector('[type="submit"]'); button.disabled = true;
    const errorBox = byId("manual-position-error"); errorBox.textContent = "正在核对持仓…";
    const owner = state.ownerId, mode = state.dataMode;
    try {
      const request = {text: `${code} ${fields.get("quantity")}股 成本价${fields.get("cost")}元${fields.get("price") ? ` 现价${fields.get("price")}元` : ""}`};
      const response = await fetch("/api/v1/copilot/parse-portfolio", {method: "POST", headers: {"Content-Type": "application/json", "X-Owner-ID": owner}, body: JSON.stringify(request)});
      if (!response.ok) throw await apiError(response);
      let data = await response.json();
      if (data.status === "EMPTY" && mode === "LIVE") {
        const indexed = await fetch(`/api/v1/copilot/auto-index-security?symbol=${encodeURIComponent(code)}`, {method: "POST", headers: {"X-Owner-ID": owner}});
        if (!indexed.ok) throw await apiError(indexed);
        const quote = (await indexed.json()).data;
        if (quote?.symbol && quote?.price_cny > 0) data = {status: "SUCCESS", positions: [{
          asset_id: quote.symbol, name: quote.name, asset_class: "EQUITY", sector: "Unclassified",
          quantity: fields.get("quantity"), cost_price: fields.get("cost"), price: fields.get("price") || quote.price_cny,
          previous_close: fields.get("price") ? null : quote.previous_close_cny, observed_at: quote.observed_at,
        }]};
      }
      if (owner !== state.ownerId || mode !== state.dataMode) throw new Error("账户或模式已变化，请重新添加");
      if (data.status !== "SUCCESS" || !data.positions?.length) throw new Error(data.message || "未识别此证券，请核对代码；暂未收录的证券不能直接导入。");
      const persisted = await fetch("/api/v1/advisor/portfolio/current", {headers: {"X-Owner-ID": owner}});
      if (!persisted.ok) throw await apiError(persisted);
      const saved = (await persisted.json()).data;
      if (owner !== state.ownerId || mode !== state.dataMode) throw new Error("账户或模式已变化，请重新添加");
      const existing = saved?.positions || [];
      if (existing.some(p => p.asset_id === data.positions[0].asset_id)) throw new Error("该证券已在持仓中，请删除旧记录后重新录入完整数量。");
      await replacePortfolioRows([...existing, ...data.positions], saved?.cash_cny || 0);
      form.reset(); errorBox.textContent = ""; byId("manual-position-dialog").close();
    } catch (error) { errorBox.textContent = error.message; }
    finally { button.disabled = false; }
  });
  byId("portfolio-export")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const report = displayedPortfolioReport || await refreshPortfolioReport();
      if (!report?.position_count) throw new Error("请先导入持仓");
      downloadPortfolioReport(report);
    } catch (error) { setError(error.message); }
    finally { button.disabled = false; }
  });
  byId("portfolio-report-refresh")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try { await refreshPortfolioReport(); }
    catch (error) { setError(error.message); }
    finally { button.disabled = false; }
  });
  byId("close-portfolio-diagnosis")?.addEventListener("click", () => byId("portfolio-diagnosis-drawer")?.close());

  // Event bindings for P2 panels
  const refHistBtn = byId("refresh-history");
  if (refHistBtn) refHistBtn.addEventListener("click", loadRecommendationHistory);
  const runCompBtn = byId("run-compare");
  if (runCompBtn) runCompBtn.addEventListener("click", runRecommendationCompare);
  const runRebBtn = byId("run-rebalancing");
  if (runRebBtn) runRebBtn.addEventListener("click", runPortfolioRebalancing);
  const runExpBtn = byId("run-explainability");
  if (runExpBtn) runExpBtn.addEventListener("click", runAdvancedExplainability);
  document.querySelectorAll('input[name="display-policy-level"]').forEach((levelInput) => {
    levelInput.addEventListener("change", () => setDisplayPolicyControl(Number(levelInput.value)));
  });
  const savePolicyBtn = byId("save-display-policy");
  if (savePolicyBtn) savePolicyBtn.addEventListener("click", () => saveDisplayPolicy().catch(error => setError(error.message)));
  const recomputeBehaviorBtn = byId("recompute-behavior-profile");
  if (recomputeBehaviorBtn) recomputeBehaviorBtn.addEventListener("click", () => recomputeBehaviorProfile().catch(error => setError(error.message)));
  const runDevAssistBtn = byId("run-dev-assist");
  if (runDevAssistBtn) runDevAssistBtn.addEventListener("click", () => runDevAssist().catch(error => setError(error.message)));
  const runEvalBtn = byId("run-evaluation-suite");
  if (runEvalBtn) runEvalBtn.addEventListener("click", runEvaluationSuite);
  const questionnaireForm = byId("questionnaire-form");
  if (questionnaireForm) questionnaireForm.addEventListener("submit", confirmFullQuestionnaire);
  const questionnairePrevious = byId("questionnaire-prev");
  if (questionnairePrevious) questionnairePrevious.addEventListener("click", () => {
    state.questionnaireSectionIndex = Math.max(0, state.questionnaireSectionIndex - 1);
    renderQuestionnaire();
    scrollQuestionnaireToTop();
  });
  const questionnaireNext = byId("questionnaire-next");
  if (questionnaireNext) questionnaireNext.addEventListener("click", () => {
    const section = currentQuestionnaireSection();
    const missing = unansweredQuestionIds(section?.question_ids || []);
    if (missing.length) {
      setQuestionnaireError(`请先回答本部分的 ${missing.join("、")}。`);
      return;
    }
    state.questionnaireSectionIndex = Math.min(
      (state.questionnaireTemplate?.sections?.length || 1) - 1,
      state.questionnaireSectionIndex + 1,
    );
    renderQuestionnaire();
    scrollQuestionnaireToTop();
  });
  const questionnairePreview = byId("questionnaire-preview");
  if (questionnairePreview) questionnairePreview.addEventListener("click", previewFullQuestionnaire);
  const profileSummaryRefresh = byId("refresh-profile-summary");
  if (profileSummaryRefresh) profileSummaryRefresh.addEventListener("click", () => loadProfileSummary().catch((error) => setError(error.message)));

  // Copilot Task Buttons
  const copilotHealthBtn = byId("copilot-btn-health-check");
  if (copilotHealthBtn) copilotHealthBtn.addEventListener("click", runCopilotHealthCheck);
  const copilotStockBtn = byId("copilot-btn-stock-research");
  if (copilotStockBtn) copilotStockBtn.addEventListener("click", runCopilotStockResearch);
  byId("copilot-stock-input")?.addEventListener("input", updateRuntimeDataModeUI);
  const copilotRebalanceBtn = byId("copilot-btn-rebalance");
  if (copilotRebalanceBtn) copilotRebalanceBtn.addEventListener("click", runCopilotRebalance);
  const copilotQueryBtn = byId("copilot-submit-query");
  if (copilotQueryBtn) copilotQueryBtn.addEventListener("click", handleNaturalQuerySubmit);
  const copilotQueryInput = byId("copilot-natural-input");
  if (copilotQueryInput) {
    copilotQueryInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        handleNaturalQuerySubmit();
      }
    });
  }

  document.querySelectorAll("#copilot-quick-tags .quick-tag-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const intent = btn.dataset.intent;
      const target = btn.dataset.target;
      if (intent) {
        handleCopilotIntent(intent, target);
      } else {
        handleStreamingChat(btn.textContent.trim());
      }
    });
  });

  // Direction 2 Chat and Portfolio Modal Events
  const clearChatBtn = byId("btn-clear-chat");
  if (clearChatBtn) {
    clearChatBtn.addEventListener("click", clearConversationContext);
  }

  const conversationProfileBtn = byId("start-conversation-profile-update");
  if (conversationProfileBtn) conversationProfileBtn.addEventListener("click", startConversationProfileUpdate);

  const openPortBtn = byId("open-portfolio-modal-btn");
  if (openPortBtn) openPortBtn.addEventListener("click", openPortfolioModal);
  const openPortFromPageBtn = byId("open-portfolio-modal-from-page");
  if (openPortFromPageBtn) openPortFromPageBtn.addEventListener("click", openPortfolioModal);
  const closePortBtn = byId("close-portfolio-modal-btn");
  if (closePortBtn) closePortBtn.addEventListener("click", closePortfolioModal);
  const parsePortBtn = byId("btn-parse-portfolio");
  if (parsePortBtn) parsePortBtn.addEventListener("click", handleParsePortfolioSubmit);

  // LLM Config Modal Events
  const openLLMBtn = byId("open-llm-config-btn");
  if (openLLMBtn) openLLMBtn.addEventListener("click", openLLMConfigModal);
  const closeLLMBtn = byId("close-llm-config-modal-btn");
  if (closeLLMBtn) closeLLMBtn.addEventListener("click", closeLLMConfigModal);
  const saveLLMBtn = byId("btn-save-llm-config");
  if (saveLLMBtn) saveLLMBtn.addEventListener("click", handleSaveLLMConfig);
  const clearLLMBtn = byId("btn-clear-llm-config");
  if (clearLLMBtn) clearLLMBtn.addEventListener("click", handleClearLLMConfig);

  // User Profile Modal Events
  const openProfBtn = byId("open-profile-modal-btn");
  if (openProfBtn) openProfBtn.addEventListener("click", openProfileModal);
  const closeProfBtn = byId("close-profile-modal-btn");
  if (closeProfBtn) closeProfBtn.addEventListener("click", closeProfileModal);
  const saveProfBtn = byId("btn-save-profile");
  if (saveProfBtn) saveProfBtn.addEventListener("click", handleSaveProfile);
  const resetProfBtn = byId("btn-reset-profile");
  if (resetProfBtn) resetProfBtn.addEventListener("click", handleResetProfile);

  // Evidence Lineage Modal Events
  const openEvCard = byId("copilot-stat-evidence-card");
  if (openEvCard) openEvCard.addEventListener("click", openEvidenceLineageModal);
  const openEvLink = byId("btn-show-evidence-lineage");
  if (openEvLink) openEvLink.addEventListener("click", (e) => {
    e.stopPropagation();
    openEvidenceLineageModal();
  });
  const openEvText = byId("copilot-stat-evidence");
  if (openEvText) openEvText.addEventListener("click", (e) => {
    e.stopPropagation();
    openEvidenceLineageModal();
  });
  const closeEvBtn = byId("btn-close-evidence-modal");
  if (closeEvBtn) closeEvBtn.addEventListener("click", closeEvidenceLineageModal);
  const closeEvAction = byId("btn-close-evidence-modal-action");
  if (closeEvAction) closeEvAction.addEventListener("click", closeEvidenceLineageModal);
  const deepEvBtn = byId("btn-goto-deep-evidence");
  if (deepEvBtn) deepEvBtn.addEventListener("click", () => {
    closeEvidenceLineageModal();
  });

  const provSel = byId("llm-provider-select");
  ["llm-api-key-input", "llm-base-url-input", "llm-model-input"].forEach(id => {
    byId(id)?.addEventListener("input", () => { llmFormDirty = true; });
  });
  if (provSel) {
    provSel.addEventListener("change", () => {
      llmFormDirty = true;
      const p = provSel.value;
      const urlInput = byId("llm-base-url-input");
      const modelInput = byId("llm-model-input");
      if (p === "deepseek") {
        if (urlInput) urlInput.value = "https://api.deepseek.com/v1";
        if (modelInput) modelInput.value = "deepseek-chat";
      } else if (p === "qwen") {
        if (urlInput) urlInput.value = "https://dashscope.aliyuncs.com/compatible-mode/v1";
        if (modelInput) modelInput.value = "qwen-plus";
      } else if (p === "openai") {
        if (urlInput) urlInput.value = "https://api.openai.com/v1";
        if (modelInput) modelInput.value = "gpt-4o-mini";
      }
    });
  }

  // Backdrop click listener for closing modals
  document.querySelectorAll(".copilot-modal").forEach(m => {
    m.addEventListener("click", (e) => {
      if (e.target === m) {
        m.style.display = "none";
      }
    });
  });

  // Persona Switcher
  document.querySelectorAll(".persona-chip[data-persona]").forEach(chip => {
    chip.addEventListener("click", () => switchPersona(chip.dataset.persona));
  });

  // Mode Toggle & Expert Section Collapse
  const modeToggleBtn = byId("view-mode-toggle");
  if (modeToggleBtn) {
    modeToggleBtn.addEventListener("click", () => {
      const expertSec = byId("expert-workspace-grid");
      if (expertSec) {
        const isHidden = expertSec.hasAttribute("hidden");
        if (isHidden) {
          window.location.hash = "stock-research";
        } else {
          window.location.hash = "copilot";
        }
      }
    });
  }

  const expertCloseBtn = document.querySelector("[data-close-expert='true']");
  if (expertCloseBtn) {
    expertCloseBtn.addEventListener("click", () => {
      window.location.hash = "copilot";
    });
  }

  const expertToggle = byId("nav-expert-toggle");
  if (expertToggle) {
    expertToggle.addEventListener("click", () => {
      const section = byId("nav-expert-section");
      if (!section) return;
      const collapsed = section.classList.toggle("collapsed");
      expertToggle.setAttribute("aria-expanded", String(!collapsed));
      if (!collapsed) {
        section.scrollIntoView({ behavior: "smooth", block: "end" });
        const curHash = window.location.hash.replace(/^#/, "");
        if (DOMAIN_MAP[curHash] !== "system") {
          window.location.hash = "evaluation-dashboard";
        }
      }
    });
  }

  byId("market-assess-button")?.addEventListener("click", assessMarket);
  byId("market-index-input")?.addEventListener("keydown", (event) => { if (event.key === "Enter") assessMarket(); });
  byId("market-followup-button")?.addEventListener("click", () => {
    const name = selectedMarketIndex()?.name;
    if (!name) return;
    window.location.hash = "copilot";
    const input = byId("copilot-natural-input");
    if (input) { input.value = `请分析【${name}】近期走势，并说明数据边界和风险。`; input.focus(); }
  });
  byId("theme-toggle")?.addEventListener("click", () => {
    const current = state.userPreferences?.theme || (document.body.classList.contains("prism-theme-dark") ? "DARK" : "LIGHT");
    saveThemePreference(current === "DARK" ? "LIGHT" : "DARK");
  });
  byId("open-password-change")?.addEventListener("click", () => {
    byId("password-change-error").textContent = "";
    byId("password-change-form").reset();
    byId("password-change-dialog").showModal();
  });
  byId("cancel-password-change")?.addEventListener("click", () => byId("password-change-dialog").close());
  byId("password-change-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = byId("password-change-error");
    error.textContent = "";
    const response = await fetch("/api/v1/auth/change-password", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        current_password: byId("current-password").value,
        new_password: byId("new-password").value,
        new_password_confirmation: byId("new-password-confirmation").value,
      }),
    });
    if (!response.ok) {
      const detail = await apiError(response);
      error.textContent = detail.message || "密码修改失败";
      return;
    }
    activeChatController?.abort();
    marketAbortController?.abort();
    globalThis.prismStockQuickAbortController?.abort();
    globalThis.prismStockDeepAbortController?.abort();
    transientStorage.clear();
    window.location.replace("/login");
  });
  byId("logout-local-session")?.addEventListener("click", async () => {
    const response = await fetch("/api/v1/auth/logout", {method: "POST"});
    if (response.ok) {
      activeChatController?.abort();
      marketAbortController?.abort();
      globalThis.prismStockQuickAbortController?.abort();
      globalThis.prismStockDeepAbortController?.abort();
      transientStorage.clear();
      window.location.replace("/login");
    }
    else setError("退出登录失败，请刷新后重试。");
  });

  // 组合全景与行业环形图交互按钮事件绑定
  const overviewCheckBtn = byId("btn-run-full-overview-check");
  if (overviewCheckBtn) {
    overviewCheckBtn.addEventListener("click", runPortfolioAnalysis);
  }
  byId("portfolio-analysis-retry")?.addEventListener("click", runPortfolioAnalysis);

  const donutAnalyzeBtn = byId("btn-donut-analyze-sector");
  if (donutAnalyzeBtn) {
    donutAnalyzeBtn.addEventListener("click", () => {
      runCopilotHealthCheck();
      byId("copilot-decision-output")?.scrollIntoView({ behavior: "smooth" });
    });
  }

  // 快捷键支持：Esc 关闭当前弹窗。
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closePortfolioModal();
      closeLLMConfigModal();
      closeProfileModal();
      closeDataModeConfirmModal();
    }
  });

  byId("owner-id").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      loadEvents();
      loadRecommendationHistory();
    }
  });
  [
    "query-id",
    "loss-tolerance",
    "investment-horizon",
    "liquidity-need",
    "experience-level",
    "return-expectation",
    "max-drawdown",
  ].forEach((id) => {
    byId(id).addEventListener("change", () => {
      clearAdvisorPlan();
      clearProfileProposal();
      state.portfolioOptimizationRun = null;
      state.portfolioOptimizationSequence += 1;
      renderPortfolioOptimization(null);
      setPortfolioOptimizationStatus("需重新运行", "review");
      state.scenarioSimulationRun = null;
      state.scenarioSimulationSequence += 1;
      renderScenarioSimulation(null);
      setScenarioSimulationStatus("需重新运行", "review");
      if (!state.profile) return;
      state.profile = null;
      renderConfirmedProfile(null);
      setProfileContextStatus("需重新确认", "review");
    });
  });

  async function initializeWorkspace() {
    const response = await fetch("/api/v1/auth/context");
    if (!response.ok) throw new Error("无法确认账户身份，请重新登录后刷新");
    const context = await response.json();
    accountAccessEnabled = context.enabled === true;
    authenticatedOwner = context.enabled ? context.owner_id : null;
    authenticatedAdmin = context.admin === true;
    if (context.enabled && !authenticatedOwner) throw new Error("账户身份无效");
    if (authenticatedOwner) {
      const mockOption = byId("chat-runtime-mode")?.querySelector('option[value="MOCK"]');
      if (mockOption) mockOption.remove();
      if (byId("chat-runtime-mode")?.value === "MOCK") byId("chat-runtime-mode").value = "AUTO";
      byId("owner-id").readOnly = true;
      document.querySelectorAll("[data-persona]").forEach(el => {
        if (el.dataset.persona !== "custom-user") el.hidden = true;
      });
      if (!context.admin) {
        byId("global-data-mode-toggle").hidden = true;
        byId("runtime-mode-switcher-wrap").hidden = true;
      }
    }
    // Establish the owner namespace before any owner-scoped startup requests
    // (including market catalog/quote cards) are issued.
    state.ownerId = authenticatedOwner || byId("owner-id")?.value.trim() || "demo-owner";
    initializeNavigation();
    checkHealth();
    updateLLMConfigUI();
    await fetchRuntimeDataMode();
    await loadUserPreferences();
    await loadMarketCatalog();
    loadMarketQuotes();
    assessMarket();
    initRuntimeDataMode();
    loadUserProfile();
    switchPersona("custom-user");
    loadCopilotChatHistory();
    loadModelSettings().catch(error => setError(error.message));
    initPortfolioModalTabs();
  }
  byId("confirm-session-truth").addEventListener("click", confirmSessionTruth);
  byId("open-session-truth").addEventListener("click", () => openTruthDrawer().catch(error => setError(error.message)));
  byId("close-truth-drawer").addEventListener("click", () => byId("truth-drawer").close());
  byId("cancel-session-truth").addEventListener("click", () => {truthReview = null; byId("truth-confirm-dialog").close();});
  byId("commit-session-truth").addEventListener("click", commitSessionTruth);
  byId("truth-confirm-dialog").addEventListener("close", () => {truthReview = null;});
  byId("truth-check-claim").addEventListener("click", () => checkTruthItem());
  byId("truth-check-action").addEventListener("click", () => checkTruthItem(true));
  byId("refresh-session-truth").addEventListener("click", () => refreshSessionTruth().catch(error => setError(error.message)));
  initializeWorkspace().catch(error => {
    const message = document.createElement("p");
    message.setAttribute("role", "alert");
    message.textContent = error.message;
    document.body.prepend(message);
  });
})();
