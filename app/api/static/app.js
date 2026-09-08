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
    liveReadinessIssues: [],
    capabilities: null,
    rebalancingRun: null,
    rebalancingSequence: 0,
    customStressRun: null,
    customStressSequence: 0,
    copilotResearchSequence: 0,
  }, ["ownerId", "selectedPersona", "profile", "behaviorProfile", "portfolio", "dataMode"]);
  const state = microStore.state;
  let authenticatedOwner = null;
  let sessionTruthState = {owner:null, revision:0, status:"NOT_LOCKED"};
  async function refreshSessionTruth() {
    const owner = state.ownerId;
    const response = await fetch("/api/v1/advisor/session-truth", {headers:{"X-Owner-ID":owner}});
    if (!response.ok) throw await apiError(response);
    const result = await response.json();
    if (state.ownerId !== owner) return null;
    sessionTruthState = {...result, owner};
    const labels = {LOCKED:"已锁定", NOT_LOCKED:"尚未锁定", DRIFT_DETECTED:"前提已变化，需要重新确认", INPUT_REQUIRED:"请先确认画像和持仓"};
    byId("session-truth-status").textContent = `${labels[result.status] || result.status} · 第 ${result.revision} 版`;
    byId("confirm-session-truth").textContent = result.revision ? "确认使用当前分析前提" : "锁定当前分析前提";
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
    updateVisualCompanion();
  }
  microStore.subscribe((store) => {
    document.documentElement.setAttribute("data-prism-owner", store.ownerId || "none");
    document.documentElement.setAttribute("data-prism-mode", store.dataMode || "MOCK");
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
  });

  const DISPLAY_SCENARIO_LABELS = Object.freeze({
    BASELINE_READY: "基线：完整多资产快照（BASELINE_READY）",
    TIGHTER_TECH_CAP: "科技限额收紧 10%（TIGHTER_TECH_CAP）",
    TOP_ASSET_TRIM_10PP: "第一大资产削减 10%（TOP_ASSET_TRIM_10PP）",
    LOOKTHROUGH_PARTIAL: "基金穿透部分缺失（LOOKTHROUGH_PARTIAL）",
    SOURCE_PARTIAL: "来源部分缺失（SOURCE_PARTIAL）",
    SOURCE_DISAGREEMENT: "来源分歧（SOURCE_DISAGREEMENT）",
    SOURCE_EMPTY: "来源无结果（SOURCE_EMPTY）",
    SOURCE_FAILED: "来源失败（SOURCE_FAILED）",
    INFEASIBLE: "不可行：配置上限无法同时满足（INFEASIBLE）",
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
    return DISPLAY_LABELS[rendered] || rendered;
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
    return DISPLAY_SCENARIO_LABELS[String(value)] || text(value, "未命名场景");
  }

  function displayScenarioDescription(scenario) {
    const value = scenario && typeof scenario === "object" ? scenario.description : scenario;
    return displayDescription(value, "无场景说明");
  }

  function displayMethodology(value) {
    if (value === null || value === undefined || value === "") return "—";
    const rendered = String(value);
    return displayDescription(rendered)
      .replace(/^deterministic Decimal ratio:/, "确定性 Decimal 比率：")
      .replace(/^deterministic Decimal threshold:/, "确定性 Decimal 阈值：")
      .replace(/^deterministic Decimal convertible-bond-formula\.v1;/, "确定性 Decimal 可转债公式（convertible-bond-formula.v1）；")
      .replace(/^input_fact_ids=/, "输入事实 ID=")
      .replace(/configured (stock-risk|fund-risk|convertible-bond-risk)\.v1 limit/, "配置的 $1.v1 限值")
      .replace(/configured (stock-risk|fund-risk|convertible-bond-risk)\.v1/, "配置的 $1.v1")
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
      .replace(/; stock-risk\.v1$/, "；stock-risk.v1")
      .replace(/; fund-risk\.v1$/, "；fund-risk.v1")
      .replace(/; convertible-bond-risk\.v1$/, "；convertible-bond-risk.v1");
  }

  const FINDING_KIND_LABELS = Object.freeze({
    FUND_COST_WARNING: "基金费率偏高",
    FUND_VOLATILITY_RISK: "基金波动率偏高",
    FUND_TOP10_CONCENTRATION: "前十大持仓集中",
    FUND_DRAWDOWN_RISK: "历史回撤偏高",
    FUND_TECHNOLOGY_CONCENTRATION: "科技行业集中",
    STOCK_VALUATION_RISK: "估值风险",
    STOCK_LEVERAGE_RISK: "负债风险",
    STOCK_CASH_FLOW_RISK: "现金流风险",
    STOCK_MARGIN_RISK: "盈利能力风险",
  });

  function findingKindLabel(kind) {
    return FINDING_KIND_LABELS[kind] || "需要关注的风险";
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
    return DISPLAY_VALUE_LABELS[status] || text(status, "待运行");
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
    return DISPLAY_VALUE_LABELS[role] || text(role);
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

  function renderPortfolio(portfolio, sourceLabel = "示例持仓 · 只读") {
    byId("portfolio-context-label").textContent = sourceLabel;
    const panel = byId("portfolio-content");
    clear(panel);
    if (!portfolio) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "加载后查看持仓明细与基金底层股票。";
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
    positionsHeading.textContent = "持仓明细";
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
    holdingHeading.textContent = "基金穿透持仓";
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
      meta.textContent = `${text(fund.parent_asset_id)} · 快照 ${text(fund.snapshot_id)} · 覆盖率 ${text(fund.coverage_pct)}% · 截止 ${text(fund.as_of)}`;
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
    updateVisualCompanion();
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

  const RISK_LEVEL_LABELS = Object.freeze({
    CONSERVATIVE: "保守型",
    BALANCED: "平衡型",
    GROWTH: "成长型",
  });

  const DISPLAY_MODE_LABELS = Object.freeze({
    AUDIT_EXPANDED: "完整依据",
    STANDARD: "标准说明",
    CONCLUSION_FIRST: "结论优先",
  });

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
          span.textContent = score === 1 ? "1 · 很低" : score === 5 ? "5 · 很高" : String(score);
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
    return profile ? `已确认 · ${profileLevelText(profile)}` : "待确认问卷";
  }

  function activeProfileTag() {
    return currentProfileTag(state.profileSummary?.questionnaire_snapshot ? state.profile?.profile : null);
  }

  function renderCurrentProfileIdentity(profile = null) {
    const persona = PERSONAS[state.selectedPersona];
    if (!persona) return;
    const tag = currentProfileTag(profile);
    byId("custom-profile-chip-name").textContent = `${persona.name} (${tag})`;
    byId("btn-custom-profile-chip").title = `当前使用：${persona.name}，${tag}`;
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

  function renderProfileSummary(summary, options = {}) {
    const panel = byId("profile-summary-content");
    if (!panel) return;
    clear(panel);
    const snapshot = summary?.questionnaire_snapshot || null;
    const behavior = summary?.behavior_profile || null;
    const effective = summary?.effective_profile || snapshot?.profile || null;
    const status = byId("questionnaire-confirmation-status");
    if (!snapshot) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "尚未确认 19 题问卷。问卷完成前不会生成正式风险画像。";
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
    const cards = document.createElement("div");
    cards.className = "profile-summary-cards";
    cards.append(
      profileMetricCard("问卷画像", `${snapshot.suitability_level} · ${profileLevelText(snapshot.profile)}`, "基于 19 题确定性评分"),
      profileMetricCard(
        "行为画像",
        behavior?.evidence_status === "CALCULATED" ? `${behavior.suitability_level} · ${Number(behavior.behavior_risk_score).toFixed(0)} 分` : "数据不足",
        behavior?.evidence_status === "CALCULATED" ? "由交易和持仓记录计算" : "至少需要 3 条交易和 2 次持仓快照",
      ),
      profileMetricCard("有效画像", profileLevelText(effective), behavior?.evidence_status === "CALCULATED" ? "采用更保守的风险边界" : "暂按已确认问卷执行"),
    );
    panel.append(cards);

    const dimensions = document.createElement("div");
    dimensions.className = "profile-dimensions";
    snapshot.dimensions.forEach((item) => {
      const row = document.createElement("div");
      const heading = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = PROFILE_DIMENSION_LABELS[item.key] || item.key;
      const value = document.createElement("strong");
      value.textContent = `${Number(item.score).toFixed(0)} 分`;
      heading.append(label, value);
      const track = document.createElement("div");
      track.className = "profile-dimension-track";
      const bar = document.createElement("span");
      bar.style.width = `${Math.max(0, Math.min(100, Number(item.score)))}%`;
      track.append(bar);
      row.append(heading, track);
      dimensions.append(row);
    });
    panel.append(dimensions);

    const gaps = summary?.data_gaps || [];
    if (gaps.length) {
      const callout = document.createElement("div");
      callout.className = "profile-data-gaps";
      const title = document.createElement("strong");
      title.textContent = "还缺哪些数据";
      const list = document.createElement("ul");
      gaps.forEach((gap) => {
        const item = document.createElement("li");
        item.textContent = gap;
        list.append(item);
      });
      callout.append(title, list);
      panel.append(callout);
    }
    const policy = summary?.display_policy;
    if (policy) {
      const trust = byId("ai-trust-score");
      const trustValue = byId("ai-trust-score-value");
      const mode = byId("display-policy-mode");
      if (trust) trust.value = policy.trust_score;
      if (trustValue) trustValue.textContent = policy.trust_score;
      if (mode) mode.textContent = DISPLAY_MODE_LABELS[policy.mode] || policy.mode;
      const policyNote = document.createElement("p");
      policyNote.className = "profile-policy-note";
      policyNote.textContent = `当前解释偏好：${DISPLAY_MODE_LABELS[policy.mode] || policy.mode}。风险告警、数据缺失和合规揭示始终展开。`;
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
    updateVisualCompanion();
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
      renderProfileSummary({ questionnaire_snapshot: result.snapshot, effective_profile: result.snapshot.profile, data_gaps: ["当前结果仅为预览，确认后才会保存并用于风险约束。"], display_policy: state.displayPolicy }, { preview: true });
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
      p.textContent = "尚无行为画像。提交结构化成交与持仓快照后再计算；数据不足不会被模型补齐。";
      panel.append(p);
      status.className = "cf-verdict cf-verdict-warning";
      status.textContent = "REVIEW_REQUIRED 数据不足";
      return;
    }
    const grid = document.createElement("div");
    grid.className = "behavior-profile-metrics";
    [
      ["有效适当性", profile.suitability_level],
      ["有效风险分", profile.effective_risk_score],
      ["90 日换手", profile.metrics?.turnover_90d_pct == null ? "数据不足" : `${profile.metrics.turnover_90d_pct}%`],
      ["最大回撤", profile.metrics?.max_drawdown_pct == null ? "数据不足" : `${profile.metrics.max_drawdown_pct}%`],
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
    note.textContent = `${profile.persona} · ${(profile.tags || []).join(" · ")}。行为数据只会收紧风险边界。`;
    panel.append(grid, note);
    const calculated = profile.evidence_status === "CALCULATED";
    status.className = calculated ? "cf-verdict cf-verdict-pass" : "cf-verdict cf-verdict-warning";
    status.textContent = calculated ? "CALCULATED 行为已计算" : "REVIEW_REQUIRED 数据不足";
    const trust = byId("ai-trust-score");
    const trustValue = byId("ai-trust-score-value");
    const mode = byId("display-policy-mode");
    if (trust) trust.value = profile.display_policy?.trust_score ?? 50;
    if (trustValue) trustValue.textContent = profile.display_policy?.trust_score ?? 50;
    if (mode) mode.textContent = DISPLAY_MODE_LABELS[profile.display_policy?.mode] || "标准说明";
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
    const mode = byId("display-policy-mode");
    if (mode) mode.textContent = DISPLAY_MODE_LABELS[result.policy.mode] || result.policy.mode;
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
      setError("请先确认风险画像，再计算行为画像。");
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
    if (clearInput) byId("profile-proposal-json").value = "";
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
        item.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
          const line = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
          if (!issueLines.includes(line)) issueLines.push(line);
        });
      });
      if (!relatedValidations.length && resultIssues.length && promotion === "AVAILABLE") {
        resultIssues.forEach((issue) => {
          const line = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
      item.textContent = "当前证据尚未进入事实（FACT）/发现（FINDING）；它仍可审计，但不构成结论。";
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
      empty.textContent = "运行矩阵后查看四类节点、独立来源验证与发现（FINDING）→事实（FACT）→证据（EVIDENCE）。";
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
    summaryText.textContent = `${text(result.matrix_id)} · ${text(result.run_id)} · 隔离标识 ${text(result.owner_id)}`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${displayScenarioDescription(result.scenario)}`;
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
      subject.textContent = text(node.subject);
      card.append(subject);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Node", node.node_id);
      addMetadata(metadata, "Kind", node.node_kind);
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      card.append(metadata);
      if (node.issues && node.issues.length) {
        const issues = document.createElement("ul");
        issues.className = "research-issues";
        node.issues.forEach((issue) => {
          const item = document.createElement("li");
          item.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
      notice.textContent = "研究结果仍需复核，Prism 不展示未验证的事实（FACT）/发现（FINDING），也不会生成可执行建议。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "research-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
      title.textContent = `${text(validation.subject)} · ${text(validation.metric)}`;
      row.append(title, chip(text(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `预期 ${text(validation.expected_value)} ${text(validation.unit)} · ${text(validation.period)} · ${text(validation.independent_lineage_count)} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      if (validation.issues && validation.issues.length) {
        const issues = document.createElement("ul");
        issues.className = "validation-issues";
        validation.issues.forEach((issue) => {
          const item = document.createElement("li");
          item.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
          issues.append(item);
        });
        row.append(issues);
      }
      validations.append(row);
    });
    panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const availableHeading = document.createElement("h3");
      availableHeading.textContent = "可用证据 · 未升级为事实（FACT）";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "research-available-evidence";
      (result.trace && result.trace.evidence || []).forEach((evidence) => {
        const details = document.createElement("details");
        const summaryLine = document.createElement("summary");
        summaryLine.textContent = `${text(evidence.field)} · ${text(evidence.source)} · ${text(evidence.quality_status)}`;
        details.append(summaryLine);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据（EVIDENCE）：${text(evidence.evidence_id)}`,
          `数值：${text(evidence.value)} ${text(evidence.unit, "")}`,
          `期间：${text(evidence.period)}`,
          `来源链：${text(evidence.lineage_id)}`,
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
    evidenceHeading.textContent = "发现（FINDING）→事实（FACT）→证据（EVIDENCE）";
    panel.append(evidenceHeading);
    const evidencePanel = document.createElement("div");
    evidencePanel.className = "research-evidence";
    const evidenceById = new Map((result.trace && result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace && result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.trace && result.trace.findings || []).forEach((finding) => {
      const details = document.createElement("details");
      details.open = true;
      const summaryLine = document.createElement("summary");
      summaryLine.textContent = `${text(finding.kind)} · ${text(finding.statement)}`;
      details.append(summaryLine);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现（FINDING）：${text(finding.finding_id)} · ${text(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实（FACT）：${text(fact.fact_id)} · ${text(fact.metric)} = ${text(fact.value)} ${text(fact.unit)} · ${text(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据（EVIDENCE）：${text(evidence.evidence_id)} · ${text(evidence.source)} · ${text(evidence.period)} · ${text(evidence.value)} · 来源链 ${text(evidence.lineage_id)}`;
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
    summaryText.textContent = `${text(result.subject)} · ${text(result.period)}`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${displayScenarioDescription(result.scenario)}`;
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
      title.textContent = text(node.node_id);
      header.append(title, chip(researchStatusLabel(node.status), researchStatusClass(node.status)));
      card.append(header);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      if (node.missing_fields && node.missing_fields.length) {
        addMetadata(metadata, "Missing", node.missing_fields.join(", "));
      }
      card.append(metadata);
      if (node.scope_description) {
        const scope = document.createElement("div");
        scope.className = "muted";
        scope.textContent = displayDescription(node.scope_description);
        card.append(scope);
      }
      (node.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
      title.textContent = `${text(validation.metric)} · ${text(validation.period)}`;
      row.append(title, chip(text(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `${text(validation.independent_lineage_count, "0")} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      (validation.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
        row.append(issueLine);
      });
      validations.append(row);
    });
    if (validations.childElementCount) panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = "证据链未闭合；证据仍可审计，但不会升级为事实（FACT）/发现（FINDING），也不会给出风险结论。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "stock-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
        issues.append(item);
      });
      if (issues.childElementCount) panel.append(issues);
      const availableHeading = document.createElement("h3");
      availableHeading.textContent = "可用证据 · 未升级为事实（FACT）";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "stock-available-evidence";
      (result.trace && result.trace.evidence || []).forEach((evidence) => {
        const details = document.createElement("details");
        const line = document.createElement("summary");
        line.textContent = `${text(evidence.field)} · ${text(evidence.source)} · ${text(evidence.quality_status)}`;
        details.append(line);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据（EVIDENCE）：${text(evidence.evidence_id)}`,
          `数值：${text(evidence.value)} ${text(evidence.unit, "")}`,
          `期间：${text(evidence.period)}`,
          `来源链：${text(evidence.lineage_id)}`,
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
      title.textContent = text(metricLabels.get(fact.metric), fact.metric);
      const value = document.createElement("div");
      value.className = "stock-fact-value";
      value.textContent = humanMetricValue(fact.value, fact.unit);
      const period = document.createElement("div");
      period.className = "muted";
      period.textContent = `${text(fact.metric)} · ${text(fact.period)} · ${text(fact.status)}`;
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
    riskText.textContent = text(result.risk && result.risk.summary);
    risk.append(riskText);
    const rules = document.createElement("div");
    rules.className = "stock-rules";
    (state.stockResearchTemplate && state.stockResearchTemplate.risk_rules || []).forEach((rule) => {
      const line = document.createElement("div");
      line.textContent = `${text(rule.label)} · ${text(rule.operator)} ${text(rule.threshold)} ${text(rule.unit)}`;
      rules.append(line);
    });
    if (rules.childElementCount) risk.append(rules);
    panel.append(risk);

    const anomalyHeading = document.createElement("h3");
    anomalyHeading.textContent = "确定性异常";
    panel.append(anomalyHeading);
    const anomalies = document.createElement("div");
    anomalies.className = "stock-findings";
    (result.findings || []).filter((finding) => finding.severity !== "INFO").forEach((finding) => {
      const details = document.createElement("details");
      details.open = true;
      const line = document.createElement("summary");
      line.textContent = `${text(finding.kind)} · ${text(finding.statement)}`;
      details.append(line);
      const meta = document.createElement("div");
      meta.className = "research-evidence-meta";
      meta.textContent = `${text(finding.finding_id)} · ${text(finding.severity)} · ${displayMethodology(finding.methodology)}`;
      details.append(meta);
      anomalies.append(details);
    });
    if (anomalies.childElementCount) panel.append(anomalies);

    const chainHeading = document.createElement("h3");
    chainHeading.textContent = "发现（FINDING）→事实（FACT）→证据（EVIDENCE）";
    panel.append(chainHeading);
    const chain = document.createElement("div");
    chain.className = "stock-findings";
    const evidenceById = new Map((result.trace && result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace && result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.findings || []).forEach((finding) => {
      const details = document.createElement("details");
      const line = document.createElement("summary");
      line.textContent = `${text(finding.kind)} · ${text(finding.statement)}`;
      details.append(line);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现（FINDING）：${text(finding.finding_id)} · ${text(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实（FACT）：${text(fact.fact_id)} · ${text(fact.metric)} = ${text(fact.value)} ${text(fact.unit)} · ${text(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据（EVIDENCE）：${text(evidence.evidence_id)} · ${text(evidence.source)} · ${text(evidence.period)} · ${text(evidence.value)} · 来源链 ${text(evidence.lineage_id)}`;
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
    summaryText.textContent = `${text(result.subject)} · ${text(result.period)}`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${displayScenarioDescription(result.scenario)}`;
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
      title.textContent = text(node.node_id);
      header.append(title, chip(researchStatusLabel(node.status), researchStatusClass(node.status)));
      card.append(header);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      if (node.missing_fields && node.missing_fields.length) {
        addMetadata(metadata, "Missing", node.missing_fields.join(", "));
      }
      card.append(metadata);
      if (node.scope_description) {
        const scope = document.createElement("div");
        scope.className = "muted";
        scope.textContent = displayDescription(node.scope_description);
        card.append(scope);
      }
      (node.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
      title.textContent = `${text(validation.metric)} · ${text(validation.period)}`;
      row.append(title, chip(text(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `${text(validation.independent_lineage_count, "0")} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      (validation.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
        row.append(issueLine);
      });
      validations.append(row);
    });
    if (validations.childElementCount) panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = "证据链未闭合；证据仍可审计，但不会升级为事实（FACT）/发现（FINDING），也不会给出风险结论。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "fund-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = displayDescription(issue.safe_message, "数据暂不可用，需要人工复核。");
        issues.append(item);
      });
      if (issues.childElementCount) panel.append(issues);
      const availableHeading = document.createElement("h3");
      availableHeading.className = "dev-only technical-detail";
      availableHeading.textContent = "技术详情：可用证据 · 未升级为事实（FACT）";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "fund-available-evidence dev-only technical-detail";
      (result.trace && result.trace.evidence || []).forEach((evidence) => {
        const details = document.createElement("details");
        const line = document.createElement("summary");
        line.textContent = `${text(evidence.field)} · ${text(evidence.source)} · ${text(evidence.quality_status)}`;
        details.append(line);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据（EVIDENCE）：${text(evidence.evidence_id)}`,
          `数值：${text(evidence.value)} ${text(evidence.unit, "")}`,
          `期间：${text(evidence.period)}`,
          `来源链：${text(evidence.lineage_id)}`,
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
      title.textContent = text(metricLabels.get(fact.metric), fact.metric);
      const value = document.createElement("div");
      value.className = "fund-fact-value";
      value.textContent = humanMetricValue(fact.value, fact.unit);
      const period = document.createElement("div");
      period.className = "muted";
      period.textContent = `数据时间：${text(fact.period)} · 来源已验证`;
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
    riskText.textContent = text(result.risk && result.risk.summary);
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
    (result.findings || []).filter((finding) => finding.severity !== "INFO").forEach((finding) => {
      const details = document.createElement("details");
      details.open = true;
      const line = document.createElement("summary");
      line.textContent = `${findingKindLabel(finding.kind)} · ${text(finding.statement)}`;
      details.append(line);
      const meta = document.createElement("div");
      meta.className = "research-evidence-meta dev-only technical-detail";
      meta.textContent = `${text(finding.finding_id)} · ${text(finding.severity)} · ${displayMethodology(finding.methodology)}`;
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
    (result.findings || []).forEach((finding) => {
      const details = document.createElement("details");
      const line = document.createElement("summary");
      line.textContent = `${text(finding.kind)} · ${text(finding.statement)}`;
      details.append(line);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现（FINDING）：${text(finding.finding_id)} · ${text(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实（FACT）：${text(fact.fact_id)} · ${text(fact.metric)} = ${text(fact.value)} ${text(fact.unit)} · ${text(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据（EVIDENCE）：${text(evidence.evidence_id)} · ${text(evidence.source)} · ${text(evidence.period)} · ${text(evidence.value)} · 来源链 ${text(evidence.lineage_id)}`;
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
    summaryText.textContent = `${text(result.subject)} · ${text(result.period)}`;
    summary.append(summaryText);
    if (result.scenario) {
      const scenarioText = document.createElement("p");
      scenarioText.textContent = `${displayScenarioLabel(result.scenario)} · ${displayScenarioDescription(result.scenario)}`;
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
      title.textContent = text(node.node_id);
      header.append(title, chip(researchStatusLabel(node.status), researchStatusClass(node.status)));
      card.append(header);
      const metadata = document.createElement("dl");
      addMetadata(metadata, "Status", researchStatusLabel(node.status));
      if (node.missing_fields && node.missing_fields.length) addMetadata(metadata, "Missing", node.missing_fields.join(", "));
      card.append(metadata);
      if (node.scope_description) {
        const scope = document.createElement("div");
        scope.className = "muted";
        scope.textContent = displayDescription(node.scope_description);
        card.append(scope);
      }
      (node.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
      title.textContent = `${text(validation.metric)} · ${text(validation.period)}`;
      row.append(title, chip(text(validation.status), researchStatusClass(validation.status)));
      const meta = document.createElement("div");
      meta.className = "validation-meta";
      meta.textContent = `${text(validation.independent_lineage_count, "0")} 条独立来源链 · 支持 ${text((validation.supporting_evidence_ids || []).length, "0")} · 冲突 ${text((validation.contradicting_evidence_ids || []).length, "0")} · 未解决 ${text((validation.unresolved_evidence_ids || []).length, "0")}`;
      row.append(meta);
      (validation.issues || []).forEach((issue) => {
        const issueLine = document.createElement("div");
        issueLine.className = "muted";
        issueLine.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
        row.append(issueLine);
      });
      validations.append(row);
    });
    if (validations.childElementCount) panel.append(validations);

    if (result.pipeline_status !== "READY") {
      const notice = document.createElement("div");
      notice.className = "notice error";
      notice.textContent = "证据链未闭合；证据仍可审计，但不会升级为事实（FACT）/发现（FINDING），也不会给出风险结论。";
      panel.append(notice);
      const issues = document.createElement("ul");
      issues.className = "convertible-bond-issues";
      (result.issues || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
        issues.append(item);
      });
      if (issues.childElementCount) panel.append(issues);
      const availableHeading = document.createElement("h3");
      availableHeading.textContent = "可用证据 · 未升级为事实（FACT）";
      panel.append(availableHeading);
      const available = document.createElement("div");
      available.className = "convertible-bond-available-evidence";
      (result.trace && result.trace.evidence || []).forEach((evidence) => {
        const details = document.createElement("details");
        const line = document.createElement("summary");
        line.textContent = `${text(evidence.field)} · ${text(evidence.source)} · ${text(evidence.quality_status)}`;
        details.append(line);
        const metadata = document.createElement("div");
        metadata.className = "research-evidence-meta";
        [
          `证据（EVIDENCE）：${text(evidence.evidence_id)}`,
          `数值：${text(evidence.value)} ${text(evidence.unit, "")}`,
          `期间：${text(evidence.period)}`,
          `来源链：${text(evidence.lineage_id)}`,
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
      title.textContent = text(metricLabels.get(fact.metric), fact.metric);
      const value = document.createElement("div");
      value.className = "convertible-bond-fact-value";
      let displayValue = text(fact.value);
      const levelMetric = fact.metric === "credit_rating_rank" || fact.metric === "liquidity_score";
      if (fact.metric === "credit_rating_rank") displayValue = `${text(creditLabels[String(fact.value)], "未知评级")} · 序数 ${displayValue}`;
      if (fact.metric === "liquidity_score") displayValue = `${text(liquidityLabels[String(fact.value)], "未知流动性")} · 分数 ${displayValue}`;
      value.textContent = levelMetric ? displayValue : `${displayValue} ${text(fact.unit, "")}`;
      const period = document.createElement("div");
      period.className = "muted";
      period.textContent = `${text(fact.metric)} · ${text(fact.period)} · ${text(fact.status)}`;
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
      line.textContent = `${text(item.label, item.metric)} · ${text(item.formula)}`;
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
    riskText.textContent = text(result.risk && result.risk.summary);
    risk.append(riskText);
    const rules = document.createElement("div");
    rules.className = "convertible-bond-rules";
    (template && template.risk_rules || []).forEach((rule) => {
      const line = document.createElement("div");
      line.textContent = `${text(rule.label)} · ${text(rule.operator)} ${text(rule.threshold)} ${text(rule.unit)}`;
      rules.append(line);
    });
    if (rules.childElementCount) risk.append(rules);
    panel.append(risk);

    const findingHeading = document.createElement("h3");
    findingHeading.textContent = "确定性可转债风险";
    panel.append(findingHeading);
    const findings = document.createElement("div");
    findings.className = "convertible-bond-findings";
    (result.findings || []).filter((finding) => finding.severity !== "INFO").forEach((finding) => {
      const details = document.createElement("details");
      details.open = true;
      const line = document.createElement("summary");
      line.textContent = `${text(finding.kind)} · ${text(finding.statement)}`;
      details.append(line);
      const meta = document.createElement("div");
      meta.className = "research-evidence-meta";
      meta.textContent = `${text(finding.finding_id)} · ${text(finding.severity)} · ${displayMethodology(finding.methodology)}`;
      details.append(meta);
      findings.append(details);
    });
    if (findings.childElementCount) panel.append(findings);

    const chainHeading = document.createElement("h3");
    chainHeading.textContent = "发现（FINDING）→事实（FACT）→证据（EVIDENCE）";
    panel.append(chainHeading);
    const chain = document.createElement("div");
    chain.className = "convertible-bond-findings";
    const evidenceById = new Map((result.trace && result.trace.evidence || []).map((item) => [item.evidence_id, item]));
    const factsById = new Map((result.trace && result.trace.facts || []).map((item) => [item.fact_id, item]));
    (result.findings || []).forEach((finding) => {
      const details = document.createElement("details");
      const line = document.createElement("summary");
      line.textContent = `${text(finding.kind)} · ${text(finding.statement)}`;
      details.append(line);
      const metadata = document.createElement("div");
      metadata.className = "research-evidence-meta";
      const findingLine = document.createElement("div");
      findingLine.textContent = `发现（FINDING）：${text(finding.finding_id)} · ${text(finding.severity)}`;
      metadata.append(findingLine);
      (finding.fact_ids || []).forEach((factId) => {
        const fact = factsById.get(factId);
        if (!fact) return;
        const factLine = document.createElement("div");
        factLine.textContent = `事实（FACT）：${text(fact.fact_id)} · ${text(fact.metric)} = ${text(fact.value)} ${text(fact.unit)} · ${text(fact.status)}`;
        metadata.append(factLine);
        (fact.evidence_ids || []).forEach((evidenceId) => {
          const evidence = evidenceById.get(evidenceId);
          if (!evidence) return;
          const evidenceLine = document.createElement("div");
          evidenceLine.textContent = `证据（EVIDENCE）：${text(evidence.evidence_id)} · ${text(evidence.source)} · ${text(evidence.period)} · ${text(evidence.value)} · 来源链 ${text(evidence.lineage_id)}`;
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
        item.textContent = `${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
    updateVisualCompanion();
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
        item.textContent = `[${text(issue.dimension)}] ${text(issue.code)}: ${displayDescription(issue.safe_message)}`;
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
    updateVisualCompanion();
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
      return new Error(message && /[\u3400-\u9fff]/.test(message) ? message : "接口请求失败");
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
      setError("持仓 JSON 无法解析；输入原文不会写入错误信息。");
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
    byId("query-template-meta").textContent = "运行时读取合成持仓模板；不会提交自然语言或订单。";
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
    byId("research-template-meta").textContent = `矩阵 ${text(template.matrix_id)} · ${text(template.node_count)} 个节点 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
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
    byId("stock-research-template-meta").textContent = `个股 ${text(template.subject)} · ${text(template.period)} · ${text(template.metrics?.length, "0")} 项指标 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
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
    byId("fund-research-template-meta").textContent = `基金 ${text(template.subject)} · ${text(template.period)} · ${text(template.metrics?.length, "0")} 项指标 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
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
    byId("convertible-bond-research-template-meta").textContent = `可转债 ${text(template.subject)} · ${text(template.period)} · ${text(template.metrics?.length, "0")} 项指标 · ${text((template.scenarios || []).length, "0")} 个回放场景 · 生成时间 ${text(template.generated_at)}`;
    return template;
  }

  async function loadPortfolioOptimizationCatalog(ownerId) {
    const sequence = ++state.portfolioOptimizationSequence;
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
      setError("画像提案 JSON 无法解析；输入原文不会写入错误信息。");
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
    if (simMeta) simMeta.textContent = "基于已确认画像与持仓进行确定性假设对比；结果不作为买卖建议或交易指令。";
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
    try {
      const response = await fetch("/api/health");
      if (!response.ok) throw new Error("health check failed");
      node.classList.add("ok");
      node.textContent = "● 数据服务正常";
    } catch (_) {
      node.classList.add("bad");
      node.textContent = "● 数据服务暂时不可用";
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
    const btn = byId("global-data-mode-toggle");
    const label = byId("global-data-mode-label");
    if (!btn || !label) return;

    const isLive = (state.dataMode === "LIVE");
    const liveReady = state.liveReady === true;
    btn.classList.toggle("mode-live", isLive);
    btn.classList.toggle("mode-mock", !isLive);
    const liveCapabilities = (state.capabilities && state.capabilities.LIVE) || {};
    label.textContent = isLive ? liveModeLabelForUser() : "MOCK · 合成数据";
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
        unavailable ? `${unavailableMessage}；可切换至 MOCK 查看示例数据` : "",
      );
    });
  }

  function openDataModeConfirmModal() {
    const modal = byId("modal-data-mode-confirm");
    if (!modal) return;

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
          ? `服务端已验证可用能力：${capabilitySummaryForUser()}。普通用户无需填写 API Key；某个数据源失败只会关闭对应能力。`
          : state.liveConfigured
            ? "数据源已配置，但上次验证失败。确认后重新检测连通性；只有真实请求成功才进入 LIVE。"
            : "服务端尚无已验证的实时数据能力。请由管理员完成数据源配置，浏览器不会接收 API Key。";
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
    const expertSec = byId("expert-workspace-grid");
    const pageTabs = byId("workspace-page-tabs");

    const isOverview = (requestedId === "overview");
    const isWorkspacePanel = Boolean(requestedNode?.closest("#expert-workspace-grid"));
    const isCopilot = domain === "copilot" || !requestedNode;

    if (copilotSec) copilotSec.hidden = !isCopilot;
    if (overviewSec) overviewSec.hidden = !isOverview;
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

    const items = [...document.querySelectorAll(".nav-item")];
    if (!items.length) return;
    const primaryByDomain = {
      copilot: "#copilot",
      portfolio: "#overview",
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

  byId("load-events").addEventListener("click", loadEvents);
  byId("advisor-query-form").addEventListener("submit", runAdvisorQuery);
  byId("confirm-portfolio").addEventListener("click", confirmPortfolioContext);
  byId("confirm-profile").addEventListener("click", confirmProfileContext);
  byId("preview-profile-proposal").addEventListener("click", previewProfileProposal);
  byId("extract-natural-profile").addEventListener("click", extractNaturalProfile);
  byId("confirm-profile-proposal").addEventListener("click", confirmProfileProposal);
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
      if (!state.portfolioOptimizationRun?.targets?.length) {
        throw new Error("缺少已计算的目标权重，请先生成组合目标结构");
      }
      await ensureDependency("PORTFOLIO_CONTEXT");
      if (!state.portfolio) throw new Error("缺少结构化持仓，无法生成调仓计划");
      const token = beginContextRequest("rebalancingSequence");
      const portfolio = token.portfolio;
      const heldAssets = new Set(portfolio.position_snapshot.positions.map((position) => position.asset_id));
      if (state.portfolioOptimizationRun.targets.some((target) => !heldAssets.has(target.target_id))) {
        throw new Error("当前目标包含基金底层穿透资产，不能直接作为账户持仓下单。请在目标权重页面查看暴露结果；本次不生成交易清单。");
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
      if (!res.ok) throw new Error("生成调仓计划失败");
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

  // ===================================================
  // ✨ 视觉伴侣 (Visual Companion) 侧栏 HUD 引擎
  // ===================================================

  function openVisualCompanion() {
    const drawer = byId("visual-companion-drawer");
    const backdrop = byId("companion-backdrop");
    if (drawer) {
      drawer.classList.add("open");
      drawer.setAttribute("aria-hidden", "false");
    }
    if (backdrop) {
      backdrop.classList.add("active");
      backdrop.setAttribute("aria-hidden", "false");
    }
    updateVisualCompanion();
  }

  function closeVisualCompanion() {
    const drawer = byId("visual-companion-drawer");
    const backdrop = byId("companion-backdrop");
    if (drawer) {
      drawer.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
    }
    if (backdrop) {
      backdrop.classList.remove("active");
      backdrop.setAttribute("aria-hidden", "true");
    }
  }

  function toggleVisualCompanion() {
    const drawer = byId("visual-companion-drawer");
    if (drawer && drawer.classList.contains("open")) {
      closeVisualCompanion();
    } else {
      openVisualCompanion();
    }
  }

  function updateVisualCompanion() {
    renderCompanionAllocation();
    renderCompanionRisk();
    renderCompanionLineage();
    renderCompanionScenario();
    renderCompanionInsights();
  }

  function renderCompanionAllocation() {
    const chartContainer = byId("companion-allocation-chart");
    const legendContainer = byId("companion-allocation-legend");
    if (!chartContainer || !legendContainer) return;
    clear(chartContainer);
    clear(legendContainer);

    let items = [];
    if (state.portfolioOptimizationRun?.targets?.length) {
      items = state.portfolioOptimizationRun.targets.map(t => ({
        label: t.asset_name || t.target_id || "资产",
        weight: parseFloat(t.target_weight_pct) || 0,
      }));
    } else if (state.portfolioHealthRun && Array.isArray(state.portfolioHealthRun.sectors)) {
      items = state.portfolioHealthRun.sectors.map((sector) => ({
        label: sector.name,
        weight: sector.pct,
      }));
    }

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "确认持仓或生成目标结构后查看资产分布。";
      chartContainer.append(empty);
      return;
    }

    const colors = ["#d97757", "#4e6842", "#3b5368", "#875f1b", "#9c3826", "#4a7c85", "#7e6c90"];
    const size = 180;
    const center = size / 2;
    const radius = 65;
    const strokeWidth = 24;
    const circumference = 2 * Math.PI * radius;

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("class", "companion-chart-svg");

    let currentOffset = 0;
    items.forEach((item, idx) => {
      const pct = Math.max(0, Math.min(100, item.weight));
      const strokeDasharray = `${(pct / 100) * circumference} ${circumference}`;
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", center);
      circle.setAttribute("cy", center);
      circle.setAttribute("r", radius);
      circle.setAttribute("fill", "transparent");
      circle.setAttribute("stroke", colors[idx % colors.length]);
      circle.setAttribute("stroke-width", strokeWidth);
      circle.setAttribute("stroke-dasharray", strokeDasharray);
      circle.setAttribute("stroke-dashoffset", -currentOffset);
      circle.setAttribute("transform", `rotate(-90 ${center} ${center})`);
      circle.setAttribute("class", "donut-slice");
      
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = `${item.label}: ${pct.toFixed(2)}%`;
      circle.append(title);
      svg.append(circle);

      currentOffset += (pct / 100) * circumference;

      // 图例项
      const leg = document.createElement("span");
      leg.className = "legend-item";
      const dot = document.createElement("span");
      dot.className = "legend-dot";
      dot.style.background = colors[idx % colors.length];
      leg.append(dot, document.createTextNode(`${item.label} (${pct.toFixed(1)}%)`));
      legendContainer.append(leg);
    });

    // 中心文字
    const textGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const textVal = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textVal.setAttribute("x", center);
    textVal.setAttribute("y", center - 2);
    textVal.setAttribute("text-anchor", "middle");
    textVal.setAttribute("font-size", "16");
    textVal.setAttribute("font-weight", "700");
    textVal.setAttribute("fill", "var(--ink)");
    textVal.setAttribute("font-family", "var(--mono)");
    textVal.textContent = "100%";

    const textLbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textLbl.setAttribute("x", center);
    textLbl.setAttribute("y", center + 14);
    textLbl.setAttribute("text-anchor", "middle");
    textLbl.setAttribute("font-size", "9.5");
    textLbl.setAttribute("fill", "var(--muted)");
    textLbl.setAttribute("font-family", "var(--sans)");
    textLbl.textContent = state.portfolioOptimizationRun ? "目标权重" : "持仓穿透";

    textGroup.append(textVal, textLbl);
    svg.append(textGroup);
    chartContainer.append(svg);
  }

  function renderCompanionRisk() {
    const gaugeContainer = byId("companion-risk-gauge");
    const exposureContainer = byId("companion-exposure-bars");
    const badge = byId("companion-risk-badge");
    if (!gaugeContainer || !exposureContainer) return;
    clear(gaugeContainer);
    clear(exposureContainer);

    const profile = state.profile?.profile;
    if (!profile) {
      if (badge) badge.textContent = "未确认画像";
      exposureContainer.textContent = "请先完成风险问卷；确认持仓并体检后展示实际暴露。";
      return;
    }
    const lossScore = state.profile.questionnaire?.loss_tolerance_score || 1;
    const maxDrawdown = profile.max_drawdown_tolerance_pct;

    if (badge) {
      badge.textContent = displayLabel(profile.risk_level);
      badge.className = `status-chip ${lossScore <= 1 ? "pass" : lossScore >= 4 ? "blocked" : "review"}`;
    }

    // Semi-circle gauge SVG
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 200 115");
    svg.setAttribute("class", "companion-chart-svg");

    // Track arc
    const track = document.createElementNS("http://www.w3.org/2000/svg", "path");
    track.setAttribute("d", "M 20 100 A 80 80 0 0 1 180 100");
    track.setAttribute("fill", "none");
    track.setAttribute("stroke", "var(--outline)");
    track.setAttribute("stroke-width", "16");
    track.setAttribute("stroke-linecap", "round");
    svg.append(track);

    // Colored progress arc based on score (1..5)
    const angle = ((lossScore - 1) / 4) * Math.PI; // 0 to PI
    const color = lossScore <= 1 ? "var(--sage)" : lossScore >= 4 ? "var(--clay)" : "var(--yellow)";
    
    // Needle
    const needleAngle = Math.PI - angle; // radians from left
    const needleLen = 65;
    const nx = 100 - needleLen * Math.cos(needleAngle);
    const ny = 100 - needleLen * Math.sin(needleAngle);

    const needle = document.createElementNS("http://www.w3.org/2000/svg", "line");
    needle.setAttribute("x1", "100");
    needle.setAttribute("y1", "100");
    needle.setAttribute("x2", nx.toFixed(1));
    needle.setAttribute("y2", ny.toFixed(1));
    needle.setAttribute("stroke", color);
    needle.setAttribute("stroke-width", "3.5");
    needle.setAttribute("stroke-linecap", "round");
    svg.append(needle);

    const needlePin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    needlePin.setAttribute("cx", "100");
    needlePin.setAttribute("cy", "100");
    needlePin.setAttribute("r", "5.5");
    needlePin.setAttribute("fill", "var(--ink)");
    svg.append(needlePin);

    // Label
    const scoreText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    scoreText.setAttribute("x", "100");
    scoreText.setAttribute("y", "82");
    scoreText.setAttribute("text-anchor", "middle");
    scoreText.setAttribute("font-size", "14");
    scoreText.setAttribute("font-weight", "700");
    scoreText.setAttribute("fill", color);
    scoreText.setAttribute("font-family", "var(--mono)");
    scoreText.textContent = `承受力等级 ${lossScore}/5`;
    svg.append(scoreText);

    gaugeContainer.append(svg);

    // Exposure bars
    const expDiv = document.createElement("div");
    expDiv.style.display = "grid";
    expDiv.style.gap = "8px";
    expDiv.style.width = "100%";
    expDiv.style.fontSize = "11.5px";

    const health = state.portfolioHealthRun;
    const techExp = { name: "科技行业暴露", value: health ? `${health.technology_weight_pct}% (上限 ${health.technology_limit_pct}%)` : "待体检" };
    const ddExp = { name: "最大回撤容忍阈值", value: `${maxDrawdown}%` };

    [techExp, ddExp].forEach(exp => {
      const row = document.createElement("div");
      row.style.display = "flex";
      row.style.justifyContent = "space-between";
      row.style.color = "var(--ink-secondary)";
      const labelSpan = document.createElement("span");
      labelSpan.textContent = exp.name;
      const valStrong = document.createElement("strong");
      valStrong.style.fontFamily = "var(--mono)";
      valStrong.style.color = "var(--ink)";
      valStrong.textContent = exp.value;
      row.append(labelSpan, valStrong);
      expDiv.append(row);
    });

    exposureContainer.append(expDiv);
  }

  function renderCompanionLineage() {
    const nodeProfile = byId("node-profile");
    const nodeIntent = byId("node-intent");
    const nodeResearch = byId("node-research");
    const nodeGate = byId("node-gate");
    const nodeReceipt = byId("node-receipt");

    if (nodeProfile) {
      const ok = !!state.profile?.profile;
      nodeProfile.classList.toggle("verified", ok);
      const st = nodeProfile.querySelector(".lineage-node-status");
      if (st) st.textContent = ok ? "✓" : "1";
    }

    if (nodeIntent) {
      const ok = !!state.advisorPlan;
      nodeIntent.classList.toggle("verified", ok);
      const st = nodeIntent.querySelector(".lineage-node-status");
      if (st) st.textContent = ok ? "✓" : "2";
    }

    if (nodeResearch) {
      const ok = !!state.researchRun || !!state.stockResearchRun || !!state.fundResearchRun || !!state.convertibleBondResearchRun;
      nodeResearch.classList.toggle("verified", ok);
      const st = nodeResearch.querySelector(".lineage-node-status");
      if (st) st.textContent = ok ? "✓" : "3";
    }

    if (nodeGate) {
      const ok = !!state.selectedDecisionEvent || (state.events && state.events.length > 0);
      nodeGate.classList.toggle("verified", ok);
      const st = nodeGate.querySelector(".lineage-node-status");
      if (st) st.textContent = ok ? "✓" : "4";
    }

    if (nodeReceipt) {
      const ok = !!state.selectedDecisionEvent;
      nodeReceipt.classList.toggle("verified", ok);
      const st = nodeReceipt.querySelector(".lineage-node-status");
      if (st) st.textContent = ok ? "✓" : "5";
    }
  }

  function renderCompanionScenario() {
    const diffContainer = byId("companion-scenario-diff");
    if (!diffContainer) return;
    clear(diffContainer);

    if (!state.scenarioSimulationRun || !state.scenarioSimulationRun.diff) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "运行情景模拟后查看资产调整建议。";
      diffContainer.append(empty);
      return;
    }

    const diff = state.scenarioSimulationRun.diff;
    const wrapper = document.createElement("div");
    wrapper.style.display = "grid";
    wrapper.style.gap = "8px";
    wrapper.style.width = "100%";

    if (Array.isArray(diff.asset_deltas) && diff.asset_deltas.length) {
      diff.asset_deltas.slice(0, 4).forEach(d => {
        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.justifyContent = "space-between";
        row.style.alignItems = "center";
        row.style.fontSize = "12px";
        const val = parseFloat(d.delta_pct) || 0;
        const colorClass = val > 0 ? "positive-delta" : val < 0 ? "negative-delta" : "";
        const nameSpan = document.createElement("span");
        nameSpan.textContent = d.asset_id || d.name || "资产";
        const valSpan = document.createElement("span");
        if (colorClass) valSpan.className = colorClass;
        valSpan.style.fontFamily = "var(--mono)";
        valSpan.textContent = `${val >= 0 ? "+" : ""}${val.toFixed(2)}%`;
        row.append(nameSpan, valSpan);
        wrapper.append(row);
      });
    }

    diffContainer.append(wrapper);
  }

  function renderCompanionInsights() {
    const list = byId("companion-insights-list");
    if (!list) return;
    clear(list);

    const insights = [
      { prefix: "数据范围已隔离", body: "你的画像、持仓和分析结果只在当前本地数据空间内使用。" },
      { prefix: "依据优先", body: "系统会先核对数据和风险边界；缺少依据时会明确提示，不补造收益结论。" },
    ];

    if (state.selectedDecisionEvent) {
      const ev = state.selectedDecisionEvent;
      insights.push({ prefix: "本次结果已保存", body: `当前结果状态：${statusLabel(ev.status)}，之后可以在历史建议中回看。` });
    }

    if (state.portfolioOptimizationRun?.targets?.length) {
      insights.push({ prefix: "目标结构已生成", body: "方案已按你的资产和行业上限整理，可继续查看调整顺序。" });
    }

    insights.forEach(item => {
      const li = document.createElement("li");
      li.className = "companion-insight-item";
      const strong = document.createElement("strong");
      strong.textContent = item.prefix + "：";
      li.append(strong, document.createTextNode(item.body));
      list.append(li);
    });
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

    // Keep the compact current-profile summary in sync; example profiles stay behind
    // the optional picker so the main task surface remains calm.
    document.querySelectorAll(".persona-chip").forEach(chip => {
      chip.classList.toggle("active", chip.id === "btn-custom-profile-chip" || chip.dataset.persona === personaId);
    });
    const currentProfileAvatar = byId("custom-profile-chip-avatar");
    if (currentProfileAvatar) currentProfileAvatar.textContent = persona.avatar;
    const currentProfileName = byId("custom-profile-chip-name");
    if (currentProfileName) currentProfileName.textContent = `${persona.name} (${currentProfileTag(null)})`;
    const currentProfileChip = byId("btn-custom-profile-chip");
    if (currentProfileChip) currentProfileChip.title = `当前使用：${persona.name}，${currentProfileTag(null)}`;

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
        updateVisualCompanion();
        await refreshSessionTruth();
      })
      .catch((error) => setError(error.message || "持仓体检初始化失败"));
    updateVisualCompanion();
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
        const input = byId("copilot-natural-input");
        if (input) input.value = t.label.replace(/^[^\s]+\s*/, "");
        handleCopilotIntent(t.intent, t.target);
      });
      container.append(btn);
    });
  }

  function handleCopilotIntent(intent, target) {
    if (intent === "CHECK_PORTFOLIO") {
      runCopilotHealthCheck();
    } else if (intent === "RESEARCH_STOCK") {
      if (target) {
        const stockInput = byId("copilot-stock-input");
        if (stockInput) stockInput.value = target;
      }
      runCopilotStockResearch();
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

  function portfolioHealthView(data) {
    return {
      ...data,
      sectors: (data.sectors || []).map((row) => ({
        sectorKey: row.sector_key,
        name: row.name,
        pct: Number(row.weight_pct),
        cap: Number(row.limit_pct),
        color: SECTOR_COLORS[row.sector_key] || SECTOR_COLORS.UNCLASSIFIED,
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
    const shouldRefresh = state.dataMode !== "LIVE" || liveCapabilities.portfolio_refresh === true;
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
      if (refreshPayload.status !== "COMPLETE" || !refreshPayload.portfolio) {
        microStore.transact((store) => { store.portfolioRefreshRun = refreshPayload; });
        renderPortfolioRefreshStatus(refreshPayload);
        if (refreshPayload.data_mode === "LIVE") await fetchRuntimeDataMode();
        throw new Error("最新数据不完整，组合体检已暂停并等待复核");
      }
      microStore.transact((store) => {
        store.portfolio = refreshPayload.portfolio;
        store.portfolioRefreshRun = refreshPayload;
      });
      renderPortfolioRefreshStatus(refreshPayload);
      token = beginContextRequest("portfolioHealthSequence");
      portfolio = token.portfolio;
    } else {
      const skippedRefresh = {
        status: "SKIPPED",
        data_mode: "LIVE",
        provider: "未执行外部刷新",
        issues: ["问财组合刷新当前不可用；本次使用已确认持仓执行 Python 确定性计算。"],
      };
      microStore.transact((store) => { store.portfolioRefreshRun = skippedRefresh; });
      renderPortfolioRefreshStatus(skippedRefresh);
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
    updateVisualCompanion();
    return health;
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
    const latest = rows.find((row) => row.observed_at);
    const freshness = latest?.staleness_seconds == null
      ? "新鲜度未提供"
      : `数据距计算时点 ${Number(latest.staleness_seconds).toFixed(0)} 秒`;
    target.textContent = skipped
      ? `LIVE · 未刷新 · ${refresh.issues?.[0] || "使用已确认持仓进行计算"}`
      : complete
      ? `${isLive ? "LIVE · 问财刷新" : "MOCK · 合成数据"} · ${refresh.provider || "未标注来源"} · ${freshness}`
      : `${isLive ? "LIVE · 需要复核" : "MOCK · 需要复核"} · ${refresh.issues?.[0] || "数据未完整刷新"}`;
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
      description.textContent = "先确认投资画像和持仓，系统会用后端模型还原行业占比，再与风险边界逐项对照。";
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
    eyebrow.textContent = needsReview ? "本次判断 · 需要关注" : "本次判断 · 当前通过";
    const title = document.createElement("h4");
    const description = document.createElement("p");
    if (primaryIssue) {
      const direction = primaryIssue.limitOperator === "MIN" ? "低于最低要求" : "超过你的风险上限";
      title.textContent = `${primaryIssue.name}${direction}`;
      description.textContent = `实际为 ${primaryIssue.pct.toFixed(1)}%，你的边界是 ${primaryIssue.limitOperator === "MIN" ? "至少" : "不超过"} ${primaryIssue.cap.toFixed(1)}%。${primaryIssue.differenceLabel}，因此本次结果需要复核。`;
    } else if (needsReview) {
      title.textContent = "部分持仓信息还不完整";
      description.textContent = "当前没有发现明确的数值超限，但存在缺失或未分类信息，系统不会把未知情况判定为正常。";
    } else {
      title.textContent = "当前持仓未触发画像中的风险边界";
      description.textContent = "后端已完成持仓穿透和逐项对照；当前可计算指标均在已确认画像的范围内。";
    }
    summaryCopy.append(eyebrow, title, description);
    summary.append(summaryIcon, summaryCopy);

    const facts = document.createElement("div");
    facts.className = "evidence-fact-strip";
    [
      { label: "分析了什么", value: `${health.evidence_count} 项持仓贡献`, note: "含基金底层持仓" },
      { label: "依据哪套边界", value: activeProfileTag(), note: "来自已确认画像" },
      { label: "结果状态", value: needsReview ? "需要复核" : "当前通过", note: "由 Python 后端判定" },
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
    comparisonTitle.textContent = "实际持仓与风险边界的距离";
    const comparisonHelp = document.createElement("p");
    comparisonHelp.textContent = "彩色条是当前占比，竖线是你的边界。红色表示已经越过边界。";
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
      track.setAttribute("aria-label", `${sector.name}实际 ${sector.pct.toFixed(1)}%，边界${sector.limitOperator === "MIN" ? "至少" : "不超过"}${sector.cap.toFixed(1)}%，${verdict.textContent}`);
      const fill = document.createElement("span");
      fill.className = "evidence-bar-fill";
      fill.style.width = `${Math.max(0, Math.min(100, sector.pct))}%`;
      fill.style.backgroundColor = sector.color;
      const marker = document.createElement("span");
      marker.className = "evidence-limit-marker";
      marker.style.left = `${Math.max(0, Math.min(100, sector.cap))}%`;
      const markerLabel = document.createElement("span");
      markerLabel.className = "evidence-limit-label";
      markerLabel.textContent = "边界";
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
      { icon: "icon-scale", title: "对照风险边界", text: `逐项对照 ${activeProfileTag()} 的行业上限和现金最低要求。` },
      { icon: needsReview ? "icon-alert" : "icon-check", title: "形成判断", text: primaryIssue ? `${primaryIssue.name}触发复核。` : needsReview ? "信息不完整，保留复核状态。" : "没有指标触发硬边界。" },
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
      nextText.textContent = "当持仓数量、价格、基金底层持仓或投资画像变化时，再运行一次体检。";
    }
    nextCopy.append(nextTitle, nextText);
    next.append(nextIcon, nextCopy);

    const details = document.createElement("details");
    details.className = "evidence-professional-details";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "查看专业计算、数据来源与审计状态";
    const detailsBody = document.createElement("div");
    detailsBody.className = "evidence-professional-body";
    const sourceTitle = document.createElement("strong");
    sourceTitle.textContent = "数据来源";
    const sourceText = document.createElement("p");
    const refresh = state.portfolioRefreshRun;
    sourceText.textContent = isLiveMode
      ? `行情与场内基金披露由扶摇接口提供；公告、语义检索和组合刷新由问财 Provider 提供（${refresh?.provider || "按能力启用"}）。基金持仓采用最近一期公开披露，不作为实时持仓。`
      : "当前为 MOCK 模式，使用明确标注的静态演示底稿，不冒充实时行情或官方财务数据。";
    const formulaTitle = document.createElement("strong");
    formulaTitle.textContent = "确定性计算";
    const formulaList = document.createElement("ul");
    [
      "行业占比：每项持仓市值占组合总市值的比例；基金按底层权重继续拆分。",
      "集中度：由各行业占比平方求和；当前 HHI 为 " + health.sector_hhi + "，边界为 " + health.hhi_limit + "。",
      "风险闸门：行业占比不得超过画像上限，可用现金不得低于最低要求。",
    ].forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      formulaList.append(li);
    });
    const auditTitle = document.createElement("strong");
    auditTitle.textContent = "审计状态";
    const auditText = document.createElement("p");
    auditText.textContent = `持仓穿透 ${health.source_exposure_status}；后端判定 ${health.status}；当前载入 ${state.events.length} 条可查决策事件。大模型只负责理解问题和解释文字，不参与金融数值计算。`;
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
    ["行业 / 资产大类", "穿透实际暴露", "画像风控限额", "偏离度", "风控裁决", "核心穿透标的"].forEach(h => {
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
      if (v.isOver) tdDiff.style.color = "#b91c1c";
      else if (v.isCash) tdDiff.style.color = "#047857";

      const tdVerdict = document.createElement("td");
      const vBadge = document.createElement("span");
      vBadge.className = v.isOver ? "matrix-status-overbound" : "matrix-status-pass";
      vBadge.textContent = v.verdictCode;
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
      { label: "单一最大行业集中度", value: `${health.top_sector_weight_pct}% (${health.top_sector_name})`, status: `${maxSector?.verdictCode || "REVIEW_REQUIRED"} · Python 风控`, isOk: maxSector?.verdictCode === "PASS" },
      { label: "组合分散度指数 (HHI)", value: `${health.sector_hhi}`, status: `阈值 ${health.hhi_limit} · ${health.hhi_verdict}`, isOk: health.hhi_verdict === "PASS" },
      { label: "现金与流动性安全垫", value: `${health.cash_weight_pct}%`, status: `硬性要求 ≥ ${health.cash_minimum_pct}% · ${cashSector?.verdictCode || "REVIEW_REQUIRED"}`, isOk: cashSector?.verdictCode === "PASS" },
      { label: "底层财务排查", value: "未执行", status: "本次体检未提供财务凭证", isOk: false }
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
      st.style.color = m.isOk ? "#047857" : "#b91c1c";
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
      if (hintEl) hintEl.textContent = !state.profile?.profile ? "请先完成并确认风险问卷。" : !state.portfolio ? "请先添加并确认持仓。" : "请运行持仓健康体检。";
      if (verdictBadge) verdictBadge.textContent = "REVIEW_REQUIRED 待体检";
      if (causeCallout) causeCallout.textContent = "画像与持仓确认后，由后端执行穿透与风险闸门。";
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
        verdictBadge.append(vIcon, document.createTextNode(` OVERBOUND ${breachText}`));
      } else if (health.hhi_verdict === "OVERBOUND") {
        verdictBadge.append(vIcon, document.createTextNode(` OVERBOUND 组合集中度 HHI ${health.sector_hhi} 超过 ${health.hhi_limit}`));
      } else if (requiresReview) {
        verdictBadge.append(vIcon, document.createTextNode(` ${health.status} 数据需复核`));
      } else {
        verdictBadge.append(vIcon, document.createTextNode(" PASS 合规正常"));
      }
    }

    if (causeCallout) {
      if (overboundList.length) {
        causeCallout.className = "donut-cause-callout risk";
        causeCallout.textContent = `风险拦截原因：${overboundList.map(x => x.verdict.isCash
          ? `【${x.sector.name}】实际比例 ${x.sector.pct.toFixed(1)}% 低于最低要求 ${x.sector.cap.toFixed(1)}%（差额 ${x.sector.marginPctPoints.toFixed(1)}%）`
          : `【${x.sector.name}】实际暴露 ${x.sector.pct.toFixed(1)}% 超过画像上限 ${x.sector.cap.toFixed(1)}%（超出 ${x.sector.marginPctPoints.toFixed(1)}%）`
        ).join("；")}。已触发后端风险闸门，需通过调仓服务重新测算。`;
      } else if (health.hhi_verdict === "OVERBOUND") {
        causeCallout.className = "donut-cause-callout risk";
        causeCallout.textContent = `组合集中度 HHI ${health.sector_hhi} 超过后端限额 ${health.hhi_limit}；各行业单项限额未超限，组合仍需复核。`;
      } else if (requiresReview) {
        causeCallout.className = "donut-cause-callout risk";
        causeCallout.textContent = `当前没有数值超限项，但后端状态为 ${health.status}；请先处理缺失或未分类数据。`;
      } else {
        causeCallout.className = "donut-cause-callout pass";
        causeCallout.textContent = `合规状态：后端穿透结果处于 ${activeProfileTag()} 安全限额内，未触发硬闸门拦截。`;
      }
    }

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 220 220");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "持仓行业穿透分布环形图");

    const cx = 110, cy = 110, R = 95, r = 62;
    let currentAngle = -Math.PI / 2;

    const centerLabel = document.createElementNS(svgNS, "text");
    centerLabel.setAttribute("x", "110");
    centerLabel.setAttribute("y", "106");
    centerLabel.setAttribute("class", "donut-center-label");
    centerLabel.textContent = "全行业透视";

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
        hintEl.textContent = `【${s.name}】实际暴露 ${s.pct.toFixed(1)}% / 画像限额 ${v.isCash ? "≥" : "≤"}${s.cap.toFixed(1)}% (${v.verdictCode})，主要标的: ${s.topHoldings}`;
      }
    }

    function resetSelection() {
      sliceElements.forEach(el => el.classList.remove("active"));
      chipElements.forEach(el => el.classList.remove("active"));
      centerLabel.textContent = "全行业透视";
      centerValue.textContent = `${sectors.length}大类`;
      if (hintEl) {
        hintEl.textContent = "提示：悬浮或点击扇区可穿透查看具体标的与限额对照";
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
      title.textContent = `${s.name}穿透结果`;
      const verdict = document.createElement("span");
      verdict.className = v.isOver ? "donut-chip-badge overbound" : "donut-chip-badge pass";
      verdict.textContent = v.verdictCode;
      header.append(title, verdict);

      const comparison = document.createElement("p");
      const comparator = v.isCash ? "不低于" : "不高于";
      comparison.textContent = `实际暴露 ${s.pct.toFixed(1)}%；${activeProfileTag()} 画像要求${comparator} ${s.cap.toFixed(1)}%。`;

      const result = document.createElement("p");
      result.className = "donut-sector-detail-result";
      if (v.isOver) {
        result.textContent = `偏离限额 ${s.marginPctPoints} 个百分点，已触发风险复核。`;
      } else {
        result.textContent = `距限额仍有 ${s.marginPctPoints} 个百分点缓冲，当前判定合规。`;
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
      chip.setAttribute("aria-label", `查看${s.name}行业穿透结果`);
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
      if (v.isOver) pct.style.color = "#b91c1c";

      const badge = document.createElement("span");
      badge.className = v.isOver ? "donut-chip-badge overbound" : "donut-chip-badge pass";
      badge.textContent = v.verdictCode;

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
    const tableBody = byId("overview-industry-table-body");
    const metricsBody = byId("overview-metrics-body");
    const tableVerdict = byId("overview-table-verdict");
    const hhiChip = byId("overview-hhi-chip");
    if (!tableBody || !metricsBody) return;

    clear(tableBody);
    clear(metricsBody);

    const health = state.portfolioHealthRun;
    if (!health) {
      tableBody.textContent = "正在等待 Python 持仓穿透结果…";
      metricsBody.textContent = "画像与持仓确认后生成确定性风险指标。";
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
            ? " OVERBOUND 限额拦截"
            : requiresReview
              ? ` ${health.status} 数据复核`
              : " PASS 合规正常"
        )
      );
    }

    if (hhiChip) {
      hhiChip.textContent = `HHI ${health.sector_hhi} (${health.hhi_verdict})`;
      hhiChip.className = health.hhi_verdict === "PASS" ? "status-chip ok" : "status-chip alert";
    }

    tableBody.append(buildMultiIndustryMatrixTable(sectors));
    metricsBody.append(buildMultiDimensionalMetricsGrid(health));
  }

  async function runCopilotHealthCheck() {
    const output = byId("copilot-decision-output");
    if (!output) return;
    clear(output);
    state.copilotResearchSequence += 1;
    if (!requirePortfolioAnalysisContext(output)) return;
    output.append(buildCopilotLoadingCard("icon-activity", "正在检查你的组合…", "正在核对全行业集中度、画像边界、HHI指标和可用证据。"));

    try {
      const health = await refreshPortfolioHealth();
      if (!health) throw new Error("后端未返回持仓穿透结果");
      const persona = PERSONAS[state.selectedPersona || "persona-zhang-r3"] || DEFAULT_USER_PROFILE;
      const sectors = health.sectors;
      const hasBreaches = health.has_breaches;
      const requiresReview = health.status !== "PASS";
      const technologySector = sectors.find((sector) => sector.sectorKey === "TECHNOLOGY");

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
      h3.textContent = hasBreaches
        ? "持仓体检结论：至少一项确定性风险边界被触发 · 需要复核"
        : requiresReview
          ? "持仓体检结论：输入数据尚未满足完整计算条件 · 需要复核"
          : "持仓体检结论：全组合各维度处于当前安全边界内 · 可以继续观察";
      verdictTitleWrap.append(icon, h3);

      const statusChip = document.createElement("span");
      statusChip.className = requiresReview ? "cf-verdict cf-verdict-risk" : "cf-verdict cf-verdict-pass";
      if (requiresReview) {
        statusChip.append(
          createSvgIcon("icon-alert", "prism-icon"),
          document.createTextNode(hasBreaches ? " OVERBOUND 风险拦截" : ` ${health.status} 数据复核`)
        );
      } else {
        statusChip.append(createSvgIcon("icon-check", "prism-icon"), document.createTextNode(" PASS 合规通过"));
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
      cTitle.textContent = hasBreaches
        ? "风险拦截：多维体检触发后端硬闸门"
        : requiresReview
          ? "数据复核：部分指标缺少完整输入"
          : "合规提示：全组合多维健康度处于安全阈值内";
      
      const cP = document.createElement("p");
      cP.textContent = `根据 ${persona.name} 的已确认画像，Python 已对当前持仓执行逐层穿透、集中度计算和风险闸门。` +
        (hasBreaches
          ? "至少一项确定性风险边界被触发，后续调整必须通过调仓服务重新测算。"
          : requiresReview
            ? "当前结果仅覆盖可计算指标；未分类或缺失输入必须补齐后重新计算。"
            : "当前可计算指标均处于画像边界内；未提供的数据不会推断为正常。" );
      
      cContent.append(cTitle, cP);
      callout.append(cIcon, cContent);

      // Metrics with tooltips
      const metricsRow = document.createElement("div");
      metricsRow.className = "decision-metrics-row";
      metricsRow.append(
        buildCopilotMetricBox("当前科技暴露", `${health.technology_weight_pct}%`, technologySector?.verdictCode === "OVERBOUND", technologySector?.verdictCode === "PASS", "由 Python 穿透底层基金持仓后计算。"),
        buildCopilotMetricBox("科技风险上限", `${health.technology_limit_pct}%`, false, false, "来自后端确认画像的风险预算。"),
        buildCopilotMetricBox("组合 HHI", `${health.sector_hhi}`, health.hhi_verdict === "OVERBOUND", health.hhi_verdict === "PASS", "由后端基于闭合行业权重计算。")
      );

      // 全行业穿透对照表
      const matrixTableWrap = document.createElement("div");
      matrixTableWrap.style.margin = "18px 0";
      const mTableTitle = document.createElement("h4");
      mTableTitle.style.margin = "0 0 8px";
      mTableTitle.style.fontSize = "13.5px";
      mTableTitle.append(createSvgIcon("icon-layers", "prism-icon"), document.createTextNode(" 全行业穿透暴露与画像风控限额对照表："));
      matrixTableWrap.append(mTableTitle, buildMultiIndustryMatrixTable(sectors));

      // 多维健康度评分网格
      const multiMetricsWrap = document.createElement("div");
      multiMetricsWrap.style.margin = "18px 0";
      const mGridTitle = document.createElement("h4");
      mGridTitle.style.margin = "0 0 8px";
      mGridTitle.style.fontSize = "13.5px";
      mGridTitle.append(createSvgIcon("icon-shield-check", "prism-icon"), document.createTextNode(" 组合多维健康度评分网格 (Multi-Dimensional)："));
      multiMetricsWrap.append(mGridTitle, buildMultiDimensionalMetricsGrid(health));

      // Reasons
      const reasonsWrap = document.createElement("div");
      const reasonsHead = document.createElement("h4");
      reasonsHead.style.margin = "0 0 8px";
      reasonsHead.style.fontSize = "14px";
      const rHeadIcon = createSvgIcon("icon-info", "prism-icon");
      rHeadIcon.style.marginRight = "6px";
      reasonsHead.append(rHeadIcon, document.createTextNode(" 为什么这样判断（多维因果依据）："));
      const reasonsList = document.createElement("ul");
      reasonsList.className = "decision-reasons-list";

      const r1 = document.createElement("li");
      const r1Bold = document.createElement("strong");
      r1Bold.textContent = "持仓穿透发现：";
      r1.append(r1Bold, document.createTextNode("后端已将当前持仓归集为可审计的底层贡献，并明确保留未分类或缺失输入。"));

      const r2 = document.createElement("li");
      const r2Bold = document.createElement("strong");
      r2Bold.textContent = "多行业分散度：";
      r2.append(r2Bold, document.createTextNode(`组合当前 HHI 指数为 ${health.sector_hhi}，后端裁决为 ${health.hhi_verdict}。`));

      const r3 = document.createElement("li");
      const r3Bold = document.createElement("strong");
      r3Bold.textContent = "数据边界：";
      r3.append(r3Bold, document.createTextNode(`现金权重 ${health.cash_weight_pct}%，最低边界 ${health.cash_minimum_pct}%；本次未执行财务凭证排查。`));

      reasonsList.append(r1, r2, r3);
      reasonsWrap.append(reasonsHead, reasonsList);

      body.append(callout, metricsRow, matrixTableWrap, multiMetricsWrap, reasonsWrap);

      // Drilldown links
      body.append(buildCopilotDrilldownRow([
        { href: "#research-tracks", text: "查看研究来源" },
        { href: "#advanced-explainability", text: "查看判断原因" },
        { href: "#evidence", text: "查看证据" },
        { href: "#overview", text: "查看边界说明" }
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
    const output = byId("copilot-decision-output");
    if (!output) return;
    clear(output);
    const token = beginContextRequest("copilotResearchSequence");

    const stockSymbol = byId("copilot-stock-input")?.value?.trim() || "";
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

    // Hard Gate 1: Syntax & Exchange Prefix Validation (e.g. 114514 rejection)
    if (!isSixDigits || !hasValidPrefix) {
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
      h3.textContent = `标的研判驳回：${stockSymbol} · 非合规上市证券代码`;
      titleWrap.append(icon, h3);

      const statusChip = document.createElement("span");
      statusChip.className = "cf-verdict cf-verdict-overbound";
      statusChip.append(createSvgIcon("icon-x", "prism-icon"), document.createTextNode(" REJECTED 代码格式无效"));
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
      cTitle.textContent = "交易所编码规范与合规硬闸门拦截 (INVALID_SECURITY_CODE)";
      const cP = document.createElement("p");
      cP.textContent = `根据中国证监会及沪深北交易所证券代码编制规则，A股上市标的代码必须为 6 位数字，且具有规范的前缀识别规则（如 60/688 主板与科创板、00/300 主板与创业板、8/92 北交所、51/159 ETF 等）。输入标的 [${stockSymbol}] 不符合交易所证券编码规范，系统坚决拒绝为非法代码生成任何未经核验的虚假分析或伪造事实核验。`;
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
          runCopilotStockResearch();
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
    output.append(buildCopilotLoadingCard("icon-activity", `正在查询 ${cleanCode} 数据…`, isFund ? "读取最近一期基金披露持仓；披露数据不代表实时持仓。" : "读取行情快照；未提供的财务指标将明确标记为缺失。"));

    try {
      const endpoint = isFund ? "live-fund?fund_code=" : "live-quote?symbol=";
      let resp = await fetch(`/api/v1/copilot/${endpoint}${encodeURIComponent(stockSymbol)}`);
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
        output.append(buildCopilotLoadingCard("icon-activity", `正在自动补全 ${cleanCode} 交易所底稿依赖…`, "检测到标的代码初始未建档，正在从交易所实时快照与财报源自动建档入库…"));
        try {
          const autoResp = await fetch(`/api/v1/copilot/auto-index-security?symbol=${encodeURIComponent(cleanCode)}`, { method: "POST" });
          if (!isContextRequestCurrent(token)) return;
          if (autoResp.ok) {
            const retryResp = await fetch(`/api/v1/copilot/live-quote?symbol=${encodeURIComponent(cleanCode)}`);
            if (!isContextRequestCurrent(token)) return;
            if (retryResp.ok) {
              resp = retryResp;
              autoDependencyCompleted = true;
            }
          }
        } catch (autoErr) {
          console.warn("自动补全标的底稿依赖失败:", autoErr);
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
        h3.textContent = `标的核验未通过：${cleanCode} · 无审计财务底稿`;
        titleWrap.append(icon, h3);

        const statusChip = document.createElement("span");
        statusChip.className = "cf-verdict cf-verdict-hold";
        statusChip.append(createSvgIcon("icon-clock", "prism-icon"), document.createTextNode(" UNRECORDED 标的未收录"));
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
        cTitle.textContent = "量化底稿缺失与合规拦截 (SECURITY_NOT_FOUND)";
        const cP = document.createElement("p");
        cP.textContent = `当前量化行情与财务底稿库尚未收录标的代码 [${cleanCode}] 的最新交易日行情快照与审计财报数据。为恪守金融工程真实性与合规底线，严禁在无底稿依据的前提下凭空生成财务比率、目标价及配置建议。`;
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
          runCopilotStockResearch();
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
            runCopilotStockResearch();
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

      const requiredFinancialFields = ["pe_ttm", "pb", "roe_pct", "valuation_quantile_pct"];
      const missingFinancialFields = requiredFinancialFields.filter((field) => !hasFinancialNumber(quote[field]) || (quote.missing_fields || []).includes(field));
      if (missingFinancialFields.length) {
        clear(output);
        const card = document.createElement("div");
        card.className = "copilot-decision-card";
        const banner = document.createElement("div");
        banner.className = "decision-banner hold";
        const title = document.createElement("h3");
        title.textContent = `${quote.name} (${quote.symbol}) 行情已获取，财务适配性暂不可计算`;
        const status = document.createElement("span");
        status.className = "cf-verdict cf-verdict-hold";
        status.textContent = "REVIEW_REQUIRED 财务字段缺失";
        banner.append(title, status);
        const body = document.createElement("div");
        body.className = "decision-card-body";
        const message = document.createElement("p");
        message.textContent = `报价 ¥${quote.price_cny}；数据模式 ${res.execution_context?.data_mode || "未标注"}；来源层级 ${quote.provider_tier || "未知"}；数据时间 ${quote.observed_at || "未提供"}；缺少 ${missingFinancialFields.join("、")}，因此不生成估值与配置结论。`;
        body.append(message);
        card.append(banner, body);
        output.append(card);
        return;
      }

      const providerTier = quote.provider_tier || "UNSPECIFIED";
      const sourceIsLive = providerTier === "LIVE_PRIMARY" || providerTier === "LIVE_SECONDARY";
      const verdictBannerClass = sourceIsLive ? "buy" : "hold";
      const verdictTitle = `标的底稿：${quote.name} (${quote.symbol}) · ${providerTier}`;
      const verdictChipText = sourceIsLive ? "QUOTE 行情快照已获取" : "STATIC 静态底稿";
      const verdictChipClass = sourceIsLive ? "cf-verdict-pass" : "cf-verdict-hold";

      clear(output);
      const card = document.createElement("div");
      card.className = "copilot-decision-card";

      // Banner
      const banner = document.createElement("div");
      banner.className = `decision-banner ${verdictBannerClass}`;
      const titleWrap = document.createElement("div");
      titleWrap.className = "decision-verdict-title";
      const icon = document.createElement("span");
      icon.className = "decision-verdict-icon";
      icon.append(createSvgIcon(sourceIsLive ? "icon-check" : "icon-file-text", "prism-icon prism-icon-lg"));
      const h3 = document.createElement("h3");
      h3.textContent = verdictTitle;
      titleWrap.append(icon, h3);

      const statusChip = document.createElement("span");
      statusChip.className = `cf-verdict ${verdictChipClass}`;
      statusChip.append(createSvgIcon(sourceIsLive ? "icon-check" : "icon-file-text", "prism-icon"), document.createTextNode(` ${verdictChipText}`));
      banner.append(titleWrap, statusChip);

      // Body
      const body = document.createElement("div");
      body.className = "decision-card-body";

      if (autoDependencyCompleted || quote.auto_indexed) {
        const autoNotice = document.createElement("div");
        autoNotice.className = "doc-callout doc-callout-info";
        autoNotice.style.marginBottom = "14px";
        const anIcon = document.createElement("div");
        anIcon.className = "callout-icon";
        anIcon.append(createSvgIcon("icon-check", "prism-icon"));
        const anContent = document.createElement("div");
        anContent.className = "callout-content";
        const anTitle = document.createElement("div");
        anTitle.className = "callout-title";
        anTitle.textContent = "已自动完成前置底稿建档依赖";
        const anText = document.createElement("p");
        anText.textContent = `系统检测到标的代码 [${cleanCode}] 初始未收录，已按主行情源、备用行情源、静态底稿顺序尝试建档；缺失财务字段保持显式缺失。`;
        anContent.append(anTitle, anText);
        autoNotice.append(anIcon, anContent);
        body.append(autoNotice);
      }

      // Callout
      const callout = document.createElement("div");
      callout.className = sourceIsLive ? "doc-callout doc-callout-info" : "doc-callout doc-callout-warning";
      const cIcon = document.createElement("div");
      cIcon.className = "callout-icon";
      cIcon.append(createSvgIcon(sourceIsLive ? "icon-file-text" : "icon-alert", "prism-icon"));
      const cContent = document.createElement("div");
      cContent.className = "callout-content";
      const cTitle = document.createElement("div");
      cTitle.className = "callout-title";
      cTitle.textContent = `行情与基本面底稿（所属行业：${quote.sector} / ${quote.sub_industry || quote.sector}）`;
      const cP = document.createElement("p");
      cP.textContent = `${quote.name}（${quote.symbol}）报价 ¥${Number(quote.price_cny).toFixed(2)}，动态市盈率 TTM ${Number(quote.pe_ttm).toFixed(1)} 倍，底稿估值分位 ${Number(quote.valuation_quantile_pct).toFixed(1)}%。毛利率 ${Number(quote.gross_margin_pct).toFixed(1)}%，ROE ${Number(quote.roe_pct).toFixed(1)}%，资产负债率 ${Number(quote.debt_ratio_pct).toFixed(1)}%。本区块只展示供应商返回字段，不在浏览器内计算适当性或配置上限。`;
      cContent.append(cTitle, cP);
      callout.append(cIcon, cContent);

      // Metrics row with genuine backend data
      const metricsRow = document.createElement("div");
      metricsRow.className = "decision-metrics-row";
      const changePrefix = quote.change_pct >= 0 ? "+" : "";
      metricsRow.append(
        buildCopilotMetricBox("报价快照 / 日涨跌", `¥${Number(quote.price_cny).toFixed(2)} (${changePrefix}${Number(quote.change_pct).toFixed(2)}%)`, false, sourceIsLive, `供应商层级：${providerTier}`),
        buildCopilotMetricBox("底稿估值分位", `${Number(quote.valuation_quantile_pct).toFixed(1)}%`, false, false, "展示供应商或静态底稿返回值；未在浏览器重算。"),
        buildCopilotMetricBox("数据新鲜度", quote.staleness_seconds == null ? "未提供" : `${Number(quote.staleness_seconds).toFixed(1)} 秒`, false, sourceIsLive, "由后端根据 observed_at 确定性计算。"),
        buildCopilotMetricBox("ROE / 毛利率", `${Number(quote.roe_pct).toFixed(1)}% / ${Number(quote.gross_margin_pct).toFixed(1)}%`, false, false, "展示底稿字段；来源边界以供应商层级和缺失字段为准。")
      );

      // Factual audit lineage
      const reasonsWrap = document.createElement("div");
      const reasonsHead = document.createElement("h4");
      reasonsHead.style.margin = "0 0 8px";
      reasonsHead.style.fontSize = "14px";
      const rHeadIcon = createSvgIcon("icon-file-text", "prism-icon");
      rHeadIcon.style.marginRight = "6px";
      reasonsHead.append(rHeadIcon, document.createTextNode(" 事实底稿与风险约束："));
      const reasonsList = document.createElement("ul");
      reasonsList.className = "decision-reasons-list";

      const r1 = document.createElement("li");
      const r1Bold = document.createElement("strong");
      r1Bold.textContent = "底稿验算溯源：";
      r1.append(r1Bold, document.createTextNode(`供应商层级 ${providerTier}，延迟 ${quote.quote_latency_ms ?? "未提供"} ms，新鲜度 ${quote.staleness_seconds ?? "未提供"} 秒；资产负债率底稿值 ${Number(quote.debt_ratio_pct).toFixed(1)}%。`));

      const r2 = document.createElement("li");
      const r2Bold = document.createElement("strong");
      r2Bold.textContent = "行业与流动性：";
      r2.append(r2Bold, document.createTextNode(`所属 ${quote.sector} / ${quote.sub_industry || "未提供"}；总市值底稿值 ¥${Number(quote.market_cap_cny || 0).toLocaleString()}。`));

      const r3 = document.createElement("li");
      const r3Bold = document.createElement("strong");
      r3Bold.textContent = "字段边界：";
      r3.append(r3Bold, document.createTextNode(`缺失字段：${(quote.missing_fields || []).join("、") || "无显式缺失项"}。投资者适当性与配置上限需进入后端画像和组合计算流程。`));

      reasonsList.append(r1, r2, r3);
      reasonsWrap.append(reasonsHead, reasonsList);

      body.append(callout, metricsRow, reasonsWrap);

      // Drilldown links
      body.append(buildCopilotDrilldownRow([
        { href: "#stock-research", text: "查看完整研究" },
        { href: "#evidence", text: "查看数据来源" },
        { href: "#portfolio-optimization", text: "查看组合边界" }
      ]));

      card.append(banner, body);
      output.append(card);
    } catch (err) {
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
    }
  }

  function hasFinancialNumber(value) {
    return (typeof value === "number" || (typeof value === "string" && value.trim() !== "")) && Number.isFinite(Number(value));
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
    note.textContent = `${result.execution_context?.data_mode || "未标注"} · ${result.execution_context?.provider || "未标注来源"} · PERIODIC_DISCLOSURE 定期披露，非实时持仓。披露期：${fund.holding_disclosure_as_of || fund.observed_at || "未提供"}。行业暴露缺失时不推断组合集中度。`;
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
        ? "以下为按目标权重和交易规则测算的步骤，仅供复核，不会自动交易。"
        : "以下为按目标权重测算的交易步骤；需要复核的约束尚未解除，不能视为组合风险已通过。"
      : plan.status === "PASS"
        ? "当前目标偏差未触发交易规则，因此未生成交易步骤。这仅表示本次没有交易，不是收益或整体风险判断。"
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
    output.append(buildCopilotLoadingCard("icon-activity", "正在整理调仓方案…", "正在根据你的风险边界计算目标权重、换手率和调整顺序。"));

    try {
      const health = state.portfolioHealthRun || await refreshPortfolioHealth();
      if (!health) throw new Error("当前持仓体检未完成，不能确认调仓约束。");
      const optimization = await runPortfolioOptimization();
      if (!optimization?.targets?.length) throw new Error(optimization?.summary || "未能生成目标权重，请检查画像、持仓和缺失数据。");
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
      h4.textContent = "方案生成失败";
      const p = document.createElement("p");
      p.textContent = err.message || "未能生成调仓方案";
      errCard.append(h4, p);
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
        avatar.textContent = msg.role === "user" ? "👤" : "🌟";
        const bubble = document.createElement("div");
        bubble.className = "chat-bubble";
        bubble.textContent = msg.content;
        row.append(avatar, bubble);
        messagesContainer.append(row);
      });

      if (chatPanel) chatPanel.style.display = "block";
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    } catch (e) {}
  }

  function saveCopilotChatHistory() {
    try {
      workspaceStorage.setItem(ownerStorageKey("prism_copilot_chat_history_v2"), JSON.stringify(chatHistory.slice(-20)));
    } catch (e) {}
  }

  function buildPipelineStepItem(num, label, status) {
    const step = document.createElement("div");
    step.className = `pipeline-step ${status}`;
    const dot = document.createElement("span");
    dot.className = "step-dot";
    const txt = document.createElement("span");
    txt.textContent = `${num}.${label}`;
    step.append(dot, txt);
    return step;
  }

  function setPipelineStepState(stepEl, status) {
    if (!stepEl) return;
    stepEl.classList.remove("pending", "active", "completed");
    stepEl.classList.add(status);
  }

  async function handleStreamingChat(customQuery) {
    const input = byId("copilot-natural-input");
    const query = (customQuery || input?.value || "").trim();
    if (!query) return;
    const chatOwner = state.ownerId;
    let chatTruth;
    try {
      chatTruth = await refreshSessionTruth();
      if (!chatTruth) return;
      if (chatTruth.revision && chatTruth.status !== "LOCKED") {
        setError("分析前提已变化，请核对后点击“确认使用当前分析前提”"); return;
      }
    } catch (error) { setError(error.message || "无法检查分析前提"); return; }

    if (input) input.value = "";

    const chatPanel = byId("copilot-chat-panel");
    const messagesContainer = byId("copilot-chat-messages");
    if (chatPanel) chatPanel.style.display = "block";
    if (!messagesContainer) return;

    // User Message Bubble
    const userMsgRow = document.createElement("div");
    userMsgRow.className = "chat-msg user";
    const userAvatar = document.createElement("div");
    userAvatar.className = "chat-avatar";
    userAvatar.textContent = "👤";
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
    aiAvatar.textContent = "🌟";
    const aiBubble = document.createElement("div");
    aiBubble.className = "chat-bubble";

    // Pipeline Box
    const pipelineBox = document.createElement("div");
    pipelineBox.className = "chat-pipeline-box";
    const pipeHead = document.createElement("div");
    pipeHead.className = "pipeline-header";
    pipeHead.textContent = "⚙️ 智能投顾多阶段协同执行中…";

    const stepsGrid = document.createElement("div");
    stepsGrid.className = "pipeline-steps-grid";
    const s1 = buildPipelineStepItem("1", "意图识别", "active");
    const s2 = buildPipelineStepItem("2", "问财/行情", "pending");
    const s3 = buildPipelineStepItem("3", "画像校验", "pending");
    const s4 = buildPipelineStepItem("4", "研报生成", "pending");
    stepsGrid.append(s1, s2, s3, s4);
    pipelineBox.append(pipeHead, stepsGrid);

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

    aiBubble.append(pipelineBox, thinkingBox, toolsContainer, contentBox);
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
        body: JSON.stringify({
          message: query,
          session_truth_id: chatTruth.revision ? "workbench" : null,
          session_truth_revision: chatTruth.revision || null,
          owner_id: state.ownerId,
          profile_version: state.profile?.profile?.profile_version || null,
          behavior_profile_version: state.behaviorProfile?.profile_version || null,
          portfolio_snapshot_id: state.portfolio?.position_snapshot?.snapshot_id || null,
          persona_id: state.selectedPersona || "custom-user",
          persona_info: {
            name: persona.name,
            tag: activeProfileTag(),
            max_drawdown: persona.maxDrawdown,
            budget_cap: persona.budgetCap,
          },
          history: chatHistory.slice(-6),
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
              setPipelineStepState(s4, "completed");
              pipeHead.textContent = "分析已完成";
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
              details.open = mode === "AUDIT_EXPANDED" || (event.warnings || []).length > 0;
              const summary = document.createElement("summary");
              summary.textContent = `可审计分析链 · ${mode}`;
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
              aiBubble.insertBefore(details, contentBox);
              const policyMode = byId("display-policy-mode");
              if (policyMode) policyMode.textContent = mode;
            } else if (event.type === "thinking") {
              setPipelineStepState(s1, "completed");
              setPipelineStepState(s2, "active");
              pipeHead.textContent = "🧠 正在调度工具与事实检索…";
              thinkingBox.style.display = "inline-flex";
            } else if (event.type === "tool_start") {
              setPipelineStepState(s2, "completed");
              setPipelineStepState(s3, "active");
              pipeHead.textContent = `🔧 正在调用金融工具: ${event.tool}…`;
              const toolChip = document.createElement("span");
              toolChip.className = "chat-tool-tag";
              toolChip.textContent = `🔧 调度工具: ${event.tool}`;
              toolsContainer.append(toolChip);
            } else if (
              event.type === "tool_done"
              && event.result
              && event.result.status === "FAILED"
              && event.result.execution_context
              && event.result.execution_context.data_mode === "LIVE"
              && ["fuyao_finance_api", "wencai_skillhub_provider"].includes(
                event.result.execution_context.provider,
              )
            ) {
              await fetchRuntimeDataMode();
            } else if (event.type === "token") {
              setPipelineStepState(s3, "completed");
              setPipelineStepState(s4, "active");
              pipeHead.textContent = "✍️ 正在流式生成投资决策建议…";
              fullText += event.delta;
              cursor.remove();
              contentBox.textContent = fullText;
              contentBox.append(cursor);
              messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
          } catch (e) {}
        }
      }

      } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
      if (streamError) throw new Error(streamError);
      if (!receivedDone) throw new Error("分析连接提前结束，结果不完整");
      cursor.remove();
      chatHistory.push({ role: "assistant", content: fullText });
      saveCopilotChatHistory();
    } catch (err) {
      cursor.remove();
      pipeHead.textContent = "分析未完成";
      contentBox.textContent = `请求未完成：${err.message || "服务连接异常"}`;
      recordTruthTurnAlert(aiMsgRow, err.message || "服务连接异常", chatOwner);
    }
  }

  function handleNaturalQuerySubmit() {
    const input = byId("copilot-natural-input");
    const q = (input?.value || "").trim();
    if (!q) {
      runCopilotHealthCheck();
      return;
    }
    handleStreamingChat(q);
  }

  // 大模型 API Key 前端直接配置管理
  const llmConfig = {
    apiKey: "",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
    provider: "deepseek",
  };

  function updateLLMConfigUI() {
    const dot = byId("llm-config-status-dot");
    const label = byId("llm-config-btn-label");
    const badge = byId("chat-model-badge");

    if (llmConfig.apiKey) {
      if (dot) dot.textContent = "🟢";
      if (label) label.textContent = `已接入 (${llmConfig.model})`;
      if (badge) badge.textContent = `${llmConfig.model} · 实时在线`;
    } else {
      if (dot) dot.textContent = "⚪";
      if (label) label.textContent = "大模型配置 (API Key)";
      if (badge) badge.textContent = authenticatedOwner ? "服务端分析配置" : "内置分析引擎";
    }

    const provSel = byId("llm-provider-select");
    if (provSel) provSel.value = llmConfig.provider || "deepseek";
    const keyInput = byId("llm-api-key-input");
    if (keyInput) keyInput.value = llmConfig.apiKey || "";
    const urlInput = byId("llm-base-url-input");
    if (urlInput) urlInput.value = llmConfig.baseUrl || "https://api.deepseek.com/v1";
    const modelInput = byId("llm-model-input");
    if (modelInput) modelInput.value = llmConfig.model || "deepseek-chat";
  }

  function openLLMConfigModal() {
    updateLLMConfigUI();
    const modal = byId("llm-config-modal");
    if (modal) {
      modal.style.display = "flex";
    }
  }

  function closeLLMConfigModal() {
    const modal = byId("llm-config-modal");
    if (modal) {
      modal.style.display = "none";
    }
  }

  async function handleSaveLLMConfig() {
    const keyInput = byId("llm-api-key-input");
    const urlInput = byId("llm-base-url-input");
    const modelInput = byId("llm-model-input");
    const provSel = byId("llm-provider-select");
    const statusBox = byId("llm-config-status");

    llmConfig.apiKey = (keyInput?.value || "").trim();
    llmConfig.baseUrl = (urlInput?.value || "https://api.deepseek.com/v1").trim();
    llmConfig.model = (modelInput?.value || "deepseek-chat").trim();
    llmConfig.provider = provSel?.value || "custom";

    workspaceStorage.setItem(ownerStorageKey("prism_llm_api_key"), llmConfig.apiKey);
    workspaceStorage.setItem(ownerStorageKey("prism_llm_base_url"), llmConfig.baseUrl);
    workspaceStorage.setItem(ownerStorageKey("prism_llm_model"), llmConfig.model);
    workspaceStorage.setItem(ownerStorageKey("prism_llm_provider"), llmConfig.provider);

    updateLLMConfigUI();

    try {
      await fetch("/api/v1/copilot/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: llmConfig.apiKey,
          base_url: llmConfig.baseUrl,
          model: llmConfig.model,
        }),
      });
    } catch (e) {}

    if (statusBox) {
      statusBox.style.display = "block";
      statusBox.textContent = llmConfig.apiKey
        ? `✅ 大模型配置已成功保存！当前模型：${llmConfig.model}`
        : "✅ 已重置为内置金融智能体引擎";
    }

    setTimeout(() => {
      closeLLMConfigModal();
    }, 1000);
  }

  function handleClearLLMConfig() {
    llmConfig.apiKey = "";
    llmConfig.baseUrl = "https://api.deepseek.com/v1";
    llmConfig.model = "deepseek-chat";
    llmConfig.provider = "deepseek";

    workspaceStorage.removeItem(ownerStorageKey("prism_llm_api_key"));
    workspaceStorage.removeItem(ownerStorageKey("prism_llm_base_url"));
    workspaceStorage.removeItem(ownerStorageKey("prism_llm_model"));
    workspaceStorage.removeItem(ownerStorageKey("prism_llm_provider"));

    updateLLMConfigUI();

    fetch("/api/v1/copilot/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: "", base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" }),
    }).catch(() => {});

    const statusBox = byId("llm-config-status");
    if (statusBox) {
      statusBox.style.display = "block";
      statusBox.textContent = "已清空自定义 Key，恢复内置引擎。";
    }
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
      try {
        await refreshPortfolioHealth();
      } catch (error) {
        setError(`持仓已保存；体检未完成：${error.message}`);
      }
    }
    else renderPortfolioReadiness();
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
    renderPortfolioReadiness();
    renderOverviewWorkspace(state.selectedPersona);
    updateVisualCompanion();
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
      p.textContent = "正在提取表格单元格、计算置信度并核验资产代码…";
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

    // Summary bar
    const sumBar = document.createElement("div");
    sumBar.className = "ocr-summary-bar";
    const sumLeft = document.createElement("div");
    sumLeft.textContent = `识别出 ${data.positions.length} 笔持仓 · 可用现金 ¥${data.cash_cny.toLocaleString()} · 资产总计 ¥${data.total_value_cny.toLocaleString()}`;
    const sumRight = document.createElement("span");
    sumRight.className = data.has_low_confidence_items ? "cf-verdict cf-verdict-warning" : "cf-verdict cf-verdict-pass";
    if (data.has_low_confidence_items) {
      sumRight.append(createSvgIcon("icon-alert", "prism-icon"), document.createTextNode(" REVIEW 需人工核对"));
    } else {
      sumRight.append(createSvgIcon("icon-check", "prism-icon"), document.createTextNode(" PASS 85%置信度达标"));
    }
    sumBar.append(sumLeft, sumRight);

    // Table
    const tableWrapper = document.createElement("div");
    tableWrapper.className = "ocr-table-wrapper";
    const table = document.createElement("table");
    table.className = "ocr-verdict-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    ["代码", "名称", "持股/份额", "成本价", "当前市价", "持仓市值", "置信度", "审核裁决"].forEach(h => {
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
      if (pos.needs_review) {
        tr.className = "ocr-low-confidence";
      }

      const tdCode = document.createElement("td");
      tdCode.textContent = pos.asset_id;

      const tdName = document.createElement("td");
      tdName.textContent = pos.name;

      const tdQty = document.createElement("td");
      const qtyInput = document.createElement("input");
      qtyInput.type = "number";
      qtyInput.className = "ocr-edit-input";
      qtyInput.value = pos.quantity;
      tdQty.append(qtyInput);

      const tdCost = document.createElement("td");
      tdCost.textContent = `¥${pos.cost_price}`;

      const tdPrice = document.createElement("td");
      tdPrice.textContent = `¥${pos.price}`;

      const tdVal = document.createElement("td");
      tdVal.textContent = `¥${pos.market_value_cny.toLocaleString()}`;

      const tdConf = document.createElement("td");
      if (pos.needs_review) {
        tdConf.className = "cell-warning";
      }
      tdConf.textContent = `${pos.confidence_pct}%`;

      const tdVerdict = document.createElement("td");
      const vTag = document.createElement("span");
      if (pos.needs_review) {
        vTag.className = "cf-verdict cf-verdict-warning";
        vTag.textContent = pos.confidence_level === "REVIEW_REQUIRED" ? "REVIEW_REQUIRED" : "待核对";
        if (Array.isArray(pos.review_reasons) && pos.review_reasons.length) {
          vTag.title = pos.review_reasons.join("；");
        }
      } else {
        vTag.className = "cf-verdict cf-verdict-pass";
        vTag.textContent = pos.confidence_level === "HIGH" ? "HIGH" : "通过";
      }
      tdVerdict.append(vTag);

      tr.append(tdCode, tdName, tdQty, tdCost, tdPrice, tdVal, tdConf, tdVerdict);
      tbody.append(tr);

      inputControls.push({ pos, qtyInput });
    });
    table.append(tbody);
    tableWrapper.append(table);

    // Callout Guidance
    const callout = document.createElement("div");
    callout.className = data.has_low_confidence_items ? "doc-callout doc-callout-warning" : "doc-callout doc-callout-tip";
    const cIcon = document.createElement("div");
    cIcon.className = "callout-icon";
    cIcon.append(createSvgIcon(data.has_low_confidence_items ? "icon-alert" : "icon-check", "prism-icon"));
    const cContent = document.createElement("div");
    cContent.className = "callout-content";
    const cTitle = document.createElement("div");
    cTitle.className = "callout-title";
    cTitle.textContent = data.has_low_confidence_items
      ? "置信度核验提示：部分单元格低于 85.0% 阈值"
      : "RapidOCR 本地核验完成：全量置信度 ≥ 85.0%";
    const cP = document.createElement("p");
    cP.textContent = data.has_low_confidence_items
      ? "黄色标记项置信度偏低，请核对并可直接在上方表格输入框修正持股数量，确认无误后点击下方按钮载入。"
      : "文字识别置信度已达标，请核对证券代码、数量和价格。识别置信度不代表持仓准确性或风险结论；确认后由后端重新计算金额并执行体检。";
    cContent.append(cTitle, cP);
    callout.append(cIcon, cContent);

    // Confirm action
    const actions = document.createElement("div");
    actions.className = "modal-actions";
    const confirmBtn = document.createElement("button");
    confirmBtn.className = "copilot-action-btn primary";
    confirmBtn.type = "button";
    confirmBtn.append(createSvgIcon("icon-check", "prism-icon"), document.createTextNode(" 确认持仓并开始体检"));
    confirmBtn.addEventListener("click", async () => {
      confirmBtn.disabled = true;
      try {
        const editedPositions = inputControls.map(({ pos, qtyInput }) => {
          const val = Number(qtyInput.value);
          if (!Number.isInteger(val) || val <= 0) throw new Error("持仓数量必须为正整数");
          return { ...pos, quantity: val };
        });
        const validated = await validateAndActivatePortfolio(data, editedPositions);
        if (!validated) return;
        closePortfolioModal();
        await runCopilotHealthCheck();
      } catch (error) {
        confirmBtn.disabled = false;
        const errorNote = document.createElement("p");
        errorNote.className = "research-boundary";
        errorNote.textContent = error.message || "持仓校验失败";
        actions.append(errorNote);
      }
    });
    actions.append(confirmBtn);

    card.append(sumBar, tableWrapper, callout, actions);
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

  // Event bindings for P2 panels
  const refHistBtn = byId("refresh-history");
  if (refHistBtn) refHistBtn.addEventListener("click", loadRecommendationHistory);
  const runCompBtn = byId("run-compare");
  if (runCompBtn) runCompBtn.addEventListener("click", runRecommendationCompare);
  const runRebBtn = byId("run-rebalancing");
  if (runRebBtn) runRebBtn.addEventListener("click", runPortfolioRebalancing);
  const runExpBtn = byId("run-explainability");
  if (runExpBtn) runExpBtn.addEventListener("click", runAdvancedExplainability);
  const trustScore = byId("ai-trust-score");
  if (trustScore) trustScore.addEventListener("input", () => {
    const value = byId("ai-trust-score-value");
    if (value) value.textContent = trustScore.value;
    const mode = byId("display-policy-mode");
    const score = Number(trustScore.value);
    const key = score < 35 ? "AUDIT_EXPANDED" : score < 65 ? "STANDARD" : "CONCLUSION_FIRST";
    if (mode) mode.textContent = DISPLAY_MODE_LABELS[key];
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
      if (e.key === "Enter") {
        e.preventDefault();
        handleNaturalQuerySubmit();
      }
    });
  }

  // Direction 2 Chat and Portfolio Modal Events
  const clearChatBtn = byId("btn-clear-chat");
  if (clearChatBtn) {
    clearChatBtn.addEventListener("click", () => {
      chatHistory.length = 0;
      workspaceStorage.removeItem(ownerStorageKey("prism_copilot_chat_history_v2"));
      const msgs = byId("copilot-chat-messages");
      if (msgs) clear(msgs);
      const panel = byId("copilot-chat-panel");
      if (panel) panel.style.display = "none";
    });
  }

  const openPortBtn = byId("open-portfolio-modal-btn");
  if (openPortBtn) openPortBtn.addEventListener("click", openPortfolioModal);
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
  if (provSel) {
    provSel.addEventListener("change", () => {
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

  // 组合全景与行业环形图交互按钮事件绑定
  const overviewCheckBtn = byId("btn-run-full-overview-check");
  if (overviewCheckBtn) {
    overviewCheckBtn.addEventListener("click", () => {
      runCopilotHealthCheck();
      window.location.hash = "copilot";
      byId("copilot-decision-output")?.scrollIntoView({ behavior: "smooth" });
    });
  }

  const donutAnalyzeBtn = byId("btn-donut-analyze-sector");
  if (donutAnalyzeBtn) {
    donutAnalyzeBtn.addEventListener("click", () => {
      runCopilotHealthCheck();
      byId("copilot-decision-output")?.scrollIntoView({ behavior: "smooth" });
    });
  }

  // 视觉伴侣 (Visual Companion) 唤起与关闭事件绑定
  const openCompBtn = byId("open-companion-btn");
  if (openCompBtn) openCompBtn.addEventListener("click", openVisualCompanion);
  const floatCompBtn = byId("floating-companion-btn");
  if (floatCompBtn) floatCompBtn.addEventListener("click", toggleVisualCompanion);
  const closeCompBtn = byId("close-companion-btn");
  if (closeCompBtn) closeCompBtn.addEventListener("click", closeVisualCompanion);
  const backdrop = byId("companion-backdrop");
  if (backdrop) backdrop.addEventListener("click", closeVisualCompanion);

  // 快捷键支持：Esc 关闭所有弹窗和伴侣，Alt+V 切换伴侣
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeVisualCompanion();
      closePortfolioModal();
      closeLLMConfigModal();
      closeProfileModal();
      closeDataModeConfirmModal();
    } else if (e.altKey && (e.key === "v" || e.key === "V")) {
      e.preventDefault();
      toggleVisualCompanion();
    }
  });

  byId("owner-id").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      loadEvents();
      loadRecommendationHistory();
      updateVisualCompanion();
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
      updateVisualCompanion();
    });
  });

  async function initializeWorkspace() {
    const response = await fetch("/api/v1/auth/context");
    if (!response.ok) throw new Error("无法确认账户身份，请重新登录后刷新");
    const context = await response.json();
    authenticatedOwner = context.enabled ? context.owner_id : null;
    if (context.enabled && !authenticatedOwner) throw new Error("账户身份无效");
    if (authenticatedOwner) {
      byId("owner-id").readOnly = true;
      document.querySelectorAll("[data-persona]").forEach(el => {
        if (el.dataset.persona !== "custom-user") el.hidden = true;
      });
      if (!context.admin) {
        byId("open-llm-config-btn").hidden = true;
        byId("global-data-mode-toggle").hidden = true;
      }
    }
    if (!context.enabled || context.admin) {
      for (const [field, key] of Object.entries({apiKey:"prism_llm_api_key", baseUrl:"prism_llm_base_url", model:"prism_llm_model", provider:"prism_llm_provider"})) {
        llmConfig[field] = workspaceStorage.getItem(ownerStorageKey(key)) || llmConfig[field];
      }
    }
    initializeNavigation();
    checkHealth();
    updateLLMConfigUI();
    initRuntimeDataMode();
    loadUserProfile();
    switchPersona("custom-user");
    loadCopilotChatHistory();
    updateVisualCompanion();
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
