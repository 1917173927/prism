/* Research results render server-calculated values; this module performs no financial calculations. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const METRIC_LABELS = Object.freeze({daily_return: "日收益率", momentum_20: "20 日动量", realized_volatility_20: "20 日实现波动", current_drawdown: "当前回撤", maximum_drawdown: "窗口最大回撤"});
  let metricData = null;
  let selectedMetric = "realized_volatility_20";
  let metricChart = null;
  let metricResize = null;
  let darkTheme = document.body.classList.contains("prism-theme-dark");

  function node(tag, text, className = "") {
    const result = document.createElement(tag);
    if (text != null) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  }
  function destroyMetricChart() {
    metricResize?.disconnect();
    metricResize = null;
    metricChart?.remove();
    metricChart = null;
  }
  function metricAvailable(metric) {
    return metric?.status === "CALCULATED" && metric.value != null && Number.isFinite(Number(metric.value));
  }
  function renderMetricChart() {
    const container = byId("research-metric-chart");
    const metadata = byId("research-metric-chart-meta");
    if (!container || !metadata) return;
    destroyMetricChart();
    container.replaceChildren();
    container.style.height = "auto";
    const metric = metricData?.research_metrics?.[selectedMetric];
    const points = metric?.series || [];
    metadata.textContent = metric ? `${METRIC_LABELS[selectedMetric]} · ${metric.unit || "单位未提供"} · ${metric.input_start || "起点缺失"} 至 ${metric.input_end || "终点缺失"} · ${metric.source || "来源未提供"} · ${metric.method_version || "方法版本未提供"}` : "";
    if (!metricAvailable(metric) || !points.length) {
      container.append(node("p", metric?.missing_reason || "尚无可展示的时间序列。", "empty-state"));
      return;
    }
    if (!window.LightweightCharts) { container.append(node("p", "行情图组件未能加载。")); return; }
    // Invalid series must remain unavailable instead of being repaired into invented observations.
    if (points.some((point, index) => point.value == null || !Number.isFinite(Number(point.value)) || !/^\d{4}-\d{2}-\d{2}$/.test(point.time) || (index > 0 && points[index - 1].time >= point.time))) {
      container.append(node("p", "时间序列未通过日期及数值校验。", "empty-state"));
      return;
    }
    const css = getComputedStyle(document.body);
    const color = name => css.getPropertyValue(name).trim();
    container.style.height = "280px";
    metricChart = window.LightweightCharts.createChart(container, {
      width: container.clientWidth, height: 280,
      layout: {background: {type: "solid", color: color("--surface")}, textColor: color("--text-secondary")},
      grid: {vertLines: {color: color("--border-subtle")}, horzLines: {color: color("--border-subtle")}},
      timeScale: {timeVisible: false, borderColor: color("--border")},
      rightPriceScale: {borderColor: color("--border")},
    });
    const chart = metricChart;
    const series = chart.addSeries(window.LightweightCharts.LineSeries, {color: color("--brand"), lineWidth: 2, priceFormat: {type: "price", precision: 4, minMove: .0001}});
    series.setData(points.map(point => ({time: point.time, value: Number(point.value)})));
    chart.timeScale().fitContent();
    metricResize = new ResizeObserver(entries => {
      const width = Math.floor(entries[0]?.contentRect.width || 0);
      if (width > 0 && metricChart === chart) { chart.applyOptions({width}); chart.timeScale().fitContent(); }
    });
    metricResize.observe(container);
  }
  function renderMetrics(detail = {}) {
    const cards = byId("research-metric-cards");
    const status = byId("research-metrics-status");
    if (!cards || !status) return;
    metricData = detail.data || null;
    cards.replaceChildren();
    if (!metricData) {
      status.textContent = detail.status === "LOADING" ? "正在读取" : "UNAVAILABLE";
      cards.append(node("p", detail.status === "LOADING" ? "正在读取新的指标输入；上一结果已失效。" : detail.message || "尚未取得研究指标。", "empty-state"));
      renderMetricChart();
      return;
    }
    const metrics = metricData.research_metrics || {};
    status.textContent = Object.values(metrics).some(metricAvailable) ? "CALCULATED" : "UNAVAILABLE";
    for (const [key, label] of Object.entries(METRIC_LABELS)) {
      const metric = metrics[key];
      const available = metricAvailable(metric);
      const card = node("article", null, "research-metric-card");
      const button = node("button");
      button.type = "button";
      button.dataset.researchMetric = key;
      button.setAttribute("aria-pressed", String(selectedMetric === key));
      button.append(node("span", label), node("strong", available ? `${Number(metric.value).toFixed(4)}${metric.unit || ""}` : "—"));
      button.addEventListener("click", () => {
        selectedMetric = key;
        cards.querySelectorAll("[data-research-metric]").forEach(item => item.setAttribute("aria-pressed", String(item.dataset.researchMetric === key)));
        renderMetricChart();
      });
      card.append(button, node("small", available ? `CALCULATED · 样本 ${metric.sample_count} · 日频` : `UNAVAILABLE · ${metric?.missing_reason || "后端未提供该指标"}`));
      const details = node("details");
      details.append(node("summary", "数据与方法"));
      const definition = node("dl");
      const fields = {
        "计算窗口": metric ? `${metric.input_start || "未提供"} 至 ${metric.input_end || "未提供"}` : "未提供",
        "来源": metric?.source || "未提供", "方法版本": metric?.method_version || "未提供",
        "参数": metric?.parameters ? JSON.stringify(metric.parameters) : "未提供",
        "输入快照": metric?.snapshot_id || metricData.input_snapshot_id || "未提供",
      };
      for (const [name, value] of Object.entries(fields)) definition.append(node("dt", name), node("dd", value));
      details.append(definition);
      card.append(details);
      cards.append(card);
    }
    renderMetricChart();
  }
  document.addEventListener("prism:market-analysis", event => renderMetrics(event.detail));

  const OPERATION_LABELS = Object.freeze({MARKET_DATA: "行情", COMPANY_DATA: "财务", INDUSTRY_DATA: "行业", MACRO_DATA: "宏观", FUND_DATA: "基金", CONVERTIBLE_BOND_DATA: "可转债", SEARCH_NEWS: "公告与新闻", SEARCH_REPORTS: "研报"});
  const SKILL_STATUS = Object.freeze({INSTALLED: "已安装", PENDING: "待验证", UNINSTALLED: "已卸载"});
  let skillItems = [];
  let skillAdmin = false;
  let skillDirectory = "PUBLIC";
  let skillCategory = "ALL";
  let skillOwner = null;
  let skillLoadSequence = 0;
  let skillMutation = false;
  let skillDetailItem = null;
  const isReadOnly = () => window.PRISM_PAGES_SNAPSHOT === true;
  const currentOwner = () => byId("owner-id")?.value.trim() || "demo-owner";
  const skillPath = item => `/api/v1/skills/${encodeURIComponent(item.skill_id)}/${encodeURIComponent(item.version)}`;

  async function api(path, options = {}) {
    const owner = currentOwner();
    const response = await fetch(path, {...options, headers: {"X-Owner-ID": owner, ...(options.body ? {"Content-Type": "application/json"} : {}), ...options.headers}});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(response.status === 409 ? "记录版本已变化或能力暂不可用，请刷新后重试。" : response.status === 403 ? "当前账户没有执行该操作的权限。" : response.status === 422 ? "输入未通过校验，请检查字段、版本与已审核接口。" : "操作未完成，请检查服务状态后重试。");
      error.status = response.status;
      throw error;
    }
    if (owner !== currentOwner()) throw new Error("账户已切换，本次结果已失效。");
    return body;
  }
  function setSkillMessage(message, failure = false) {
    const output = byId("skill-store-message");
    if (!output) return;
    output.textContent = message;
    output.classList.toggle("error", failure);
    output.hidden = !message;
  }
  function actionButton(label, action, disabled = false) {
    const button = node("button", label, "copilot-action-btn secondary");
    button.type = "button";
    button.disabled = disabled;
    button.addEventListener("click", action);
    return button;
  }
  async function mutateSkill(operation, message) {
    if (skillMutation || isReadOnly()) return;
    skillMutation = true;
    setSkillMessage("正在提交操作…");
    renderSkillDirectory();
    try {
      const result = await operation();
      await loadSkills(false);
      setSkillMessage(typeof message === "function" ? message(result) : message);
      if (skillDetailItem) showSkillDetail(skillItems.find(item => item.skill_id === skillDetailItem.skill_id && item.version === skillDetailItem.version));
    } catch (error) {
      if (error.status === 409) await loadSkills(false).catch(() => {});
      setSkillMessage(error.message, true);
    } finally {
      skillMutation = false;
      renderSkillDirectory();
      if (skillDetailItem) showSkillDetail(skillItems.find(item => item.skill_id === skillDetailItem.skill_id && item.version === skillDetailItem.version));
    }
  }
  function showSkillDetail(item) {
    const output = byId("skill-store-detail");
    output.replaceChildren();
    skillDetailItem = item || null;
    output.hidden = !item;
    if (!item) return;
    output.append(node("h3", `${item.name} · ${item.version}`), node("p", `${SKILL_STATUS[item.status] || item.status} · 注册状态 ${item.callable ? "可调用" : "不可调用"} · 修订 ${item.revision}`));
    const data = node("dl", null, "research-detail-list");
    for (const [label, value] of Object.entries({"能力标识": item.skill_id, "用途": OPERATION_LABELS[item.operation] || item.operation, "执行方式": "受控 API 适配器", "审核接口": item.endpoint, "渠道": item.channel || "不适用", "更新时间": item.updated_at, "包哈希": item.package_sha256 || "未提供", "完整性状态": item.package_integrity === "REGISTERED_HASH_ONLY" ? "仅登记哈希；未执行下载包" : "未提供哈希"})) data.append(node("dt", label), node("dd", value));
    output.append(data);
    if (skillAdmin && !isReadOnly()) {
      const controls = node("div", null, "research-action-row");
      if (item.status === "PENDING") controls.append(actionButton("验证能力", () => mutateSkill(() => api(`${skillPath(item)}/verify`, {method: "POST", body: JSON.stringify({expected_revision: item.revision})}), result => result.status === "PASS" ? "验证通过，版本已启用。" : `验证未通过，保持待验证。${result.error_code ? `原因：${result.error_code}` : ""}`), skillMutation));
      if (item.status === "INSTALLED") controls.append(actionButton(item.enabled ? "全局停用" : "全局启用", () => mutateSkill(() => api(skillPath(item), {method: "PATCH", body: JSON.stringify({action: item.enabled ? "disable" : "enable", expected_revision: item.revision})}), "能力状态已更新。"), skillMutation));
      if (item.status !== "UNINSTALLED") controls.append(actionButton("卸载此版本", () => mutateSkill(() => api(skillPath(item), {method: "PATCH", body: JSON.stringify({action: "uninstall", expected_revision: item.revision})}), "版本已卸载；可以重新登记。"), skillMutation));
      controls.append(actionButton(item.status === "UNINSTALLED" ? "重新安装" : "登记新版本", () => {
        const metadata = Object.fromEntries(["skill_id", "version", "name", "operation", "endpoint", "channel", "package_sha256"].filter(key => item[key] != null).map(key => [key, item[key]]));
        byId("skill-metadata-input").value = JSON.stringify(metadata, null, 2);
        byId("skill-import-panel").open = true;
        byId("skill-metadata-input").focus();
      }, skillMutation));
      output.append(controls);
    }
  }
  function renderSkillDirectory() {
    const output = byId("skill-store-catalog");
    if (!output) return;
    output.replaceChildren();
    const search = (byId("skill-store-search")?.value || "").trim().toLowerCase();
    const installedOnly = byId("skill-store-installed")?.checked;
    const items = skillItems.filter(item => (skillDirectory !== "PERSONAL" || item.personal_enabled) && (skillCategory === "ALL" || item.operation === skillCategory) && (!installedOnly || item.status === "INSTALLED") && [item.name, item.skill_id, item.version, OPERATION_LABELS[item.operation]].some(value => String(value || "").toLowerCase().includes(search)));
    byId("skill-store-count").textContent = `${items.length} 项版本`;
    byId("skill-import-panel").hidden = !skillAdmin || isReadOnly();
    byId("skill-register-button").disabled = skillMutation;
    byId("skill-store-public").setAttribute("aria-pressed", String(skillDirectory === "PUBLIC"));
    byId("skill-store-personal").setAttribute("aria-pressed", String(skillDirectory === "PERSONAL"));
    if (!items.length) { output.append(node("p", "当前筛选条件下没有能力版本。", "empty-state")); return; }
    for (const item of items) {
      const card = node("article", null, "research-skill-card");
      card.dataset.skillId = item.skill_id;
      card.dataset.skillVersion = item.version;
      const header = node("div", null, "research-skill-heading");
      header.append(node("h3", item.name), node("span", SKILL_STATUS[item.status] || item.status, "status-chip"));
      card.append(header, node("p", `${OPERATION_LABELS[item.operation] || item.operation} · ${item.version}`), node("small", `注册状态：${item.callable ? "可调用" : "不可调用"} · ${item.enabled ? "全局启用" : "全局停用"}`));
      const selection = node("label", null, "research-skill-selection");
      const input = node("input"); input.type = "checkbox"; input.checked = item.personal_enabled;
      input.disabled = skillMutation || isReadOnly() || item.status === "UNINSTALLED";
      input.setAttribute("aria-label", `${item.name} ${item.version} 个人启用`);
      input.addEventListener("change", () => {
        const enabled = input.checked;
        mutateSkill(() => api(`/api/v1/skills/${encodeURIComponent(item.skill_id)}/selection`, {method: "PUT", body: JSON.stringify({enabled, expected_revision: item.selection_revision})}), "个人能力选择已保存。");
      });
      selection.append(input, node("span", "个人启用"));
      card.append(selection, actionButton("查看版本详情", () => showSkillDetail(item)));
      output.append(card);
    }
  }
  async function loadSkills(showLoading = true) {
    const sequence = ++skillLoadSequence;
    const owner = currentOwner();
    if (showLoading) setSkillMessage("正在读取能力目录…");
    try {
      const context = await api("/api/v1/auth/context");
      const data = await api("/api/v1/skills");
      if (sequence !== skillLoadSequence || owner !== currentOwner()) return;
      skillOwner = owner;
      skillItems = data.items || [];
      skillAdmin = context.enabled === false || context.admin === true;
      if (isReadOnly()) skillAdmin = false;
      renderSkillDirectory();
      if (showLoading) setSkillMessage(isReadOnly() ? "页面快照仅供查看，管理操作不可用。" : "");
    } catch (error) {
      if (sequence !== skillLoadSequence) return;
      skillItems = []; skillAdmin = false;
      renderSkillDirectory();
      setSkillMessage(isReadOnly() ? "该只读快照没有技能目录记录；管理操作不可用。" : error.message, true);
    }
  }
  function initializeSkillStore() {
    const container = byId("skill-store-content");
    if (!container) return;
    container.className = "surface research-store-shell";
    container.removeAttribute("role");
    container.removeAttribute("aria-live");
    container.replaceChildren();
    const toolbar = node("div", null, "research-store-toolbar");
    const search = node("input"); search.id = "skill-store-search"; search.type = "search"; search.placeholder = "搜索名称、能力或版本"; search.setAttribute("aria-label", "搜索技能");
    search.addEventListener("input", renderSkillDirectory);
    const publicButton = actionButton("公开能力", () => { skillDirectory = "PUBLIC"; renderSkillDirectory(); }); publicButton.id = "skill-store-public";
    const personalButton = actionButton("个人能力", () => { skillDirectory = "PERSONAL"; renderSkillDirectory(); }); personalButton.id = "skill-store-personal";
    const installed = node("label"); const checkbox = node("input"); checkbox.id = "skill-store-installed"; checkbox.type = "checkbox"; checkbox.addEventListener("change", renderSkillDirectory); installed.append(checkbox, node("span", "仅已安装"));
    toolbar.append(search, publicButton, personalButton, installed, actionButton("刷新目录", () => loadSkills()), Object.assign(node("span", "0 项版本", "status-chip"), {id: "skill-store-count"}));
    container.append(toolbar);
    const message = node("p", null, "notice"); message.id = "skill-store-message"; message.hidden = true; message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite"); container.append(message);
    container.append(node("p", "注册状态与上游权限分别核验。安装、验证与全局启停由管理员管理；个人选择按账户保存。新版本通过验证后才允许启用。", "research-data-meta"));
    const layout = node("div", null, "research-store-layout");
    const categories = node("nav", null, "research-store-categories"); categories.setAttribute("aria-label", "技能分类");
    for (const [key, label] of Object.entries({ALL: "全部能力", ...OPERATION_LABELS})) {
      const button = actionButton(label, () => { skillCategory = key; categories.querySelectorAll("button").forEach(item => item.setAttribute("aria-pressed", String(item === button))); renderSkillDirectory(); });
      button.setAttribute("aria-pressed", String(key === skillCategory)); categories.append(button);
    }
    const catalog = node("div", null, "research-skill-grid"); catalog.id = "skill-store-catalog"; layout.append(categories, catalog); container.append(layout);
    const detail = node("section", null, "research-skill-detail"); detail.id = "skill-store-detail"; detail.hidden = true; container.append(detail);
    const importer = node("details", null, "research-skill-import"); importer.id = "skill-import-panel"; importer.hidden = true;
    importer.append(node("summary", "管理员：登记已审核能力版本"), node("p", "填写受控接口元数据；新版本需通过接口探测。相同版本已卸载时可重新安装。"));
    const metadata = node("textarea"); metadata.id = "skill-metadata-input"; metadata.rows = 9; metadata.placeholder = "填写能力元数据 JSON"; metadata.setAttribute("aria-label", "能力元数据 JSON");
    const register = actionButton("登记版本", () => mutateSkill(async () => {
      let value;
      try { value = JSON.parse(metadata.value); } catch { throw new Error("元数据 JSON 格式无效。"); }
      const existing = skillItems.find(item => item.skill_id === value.skill_id && item.version === value.version);
      return api("/api/v1/skills", {method: "POST", body: JSON.stringify({metadata: value, expected_revision: existing?.revision || 0})});
    }, "版本已登记，等待验证。")); register.id = "skill-register-button";
    importer.append(metadata, register); container.append(importer);
    renderSkillDirectory();
    const activate = () => { if (window.location.hash === "#skill-store") { if (skillOwner !== currentOwner()) { skillItems = []; showSkillDetail(null); } loadSkills(); } };
    window.addEventListener("hashchange", activate);
    byId("load-events")?.addEventListener("click", () => { skillOwner = null; skillLoadSequence++; skillItems = []; skillAdmin = false; showSkillDetail(null); renderSkillDirectory(); });
    if (window.location.hash === "#skill-store") activate();
  }
  initializeSkillStore();
  const themeObserver = new MutationObserver(() => {
    const nextDark = document.body.classList.contains("prism-theme-dark");
    if (nextDark !== darkTheme) { darkTheme = nextDark; renderMetricChart(); }
  });
  themeObserver.observe(document.body, {attributes: true, attributeFilter: ["class"]});
  window.addEventListener("pagehide", () => { destroyMetricChart(); themeObserver.disconnect(); });
})();
