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
    metadata.textContent = metric ? `${METRIC_LABELS[selectedMetric]} · ${metric.unit || "单位未提供"} · ${metric.input_start || "起点缺失"} 至 ${metric.input_end || "终点缺失"} · ${metric.source || "来源未提供"}` : "";
    if (!metricAvailable(metric) || !points.length) {
      container.append(node("p", "资料或计算条件不足，尚无可展示的时间序列。具体原因可在数据与方法中查看。", "empty-state"));
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
      status.textContent = detail.status === "LOADING" ? "正在读取" : "暂无法分析";
      cards.append(node("p", detail.status === "LOADING" ? "正在读取新的指标输入；上一结果已失效。" : detail.message || "尚未取得研究指标。", "empty-state"));
      renderMetricChart();
      return;
    }
    const metrics = metricData.research_metrics || {};
    status.textContent = Object.values(metrics).some(metricAvailable) ? "已计算" : "暂无法分析";
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
      card.append(button, node("small", available ? `已计算 · 样本 ${metric.sample_count} · 日频` : "暂无法分析 · 资料或计算条件不足"));
      const details = node("details");
      details.append(node("summary", "数据与方法"));
      const definition = node("dl");
      const fields = {
        "计算窗口": metric ? `${metric.input_start || "未提供"} 至 ${metric.input_end || "未提供"}` : "未提供",
        "来源": metric?.source || "未提供", "方法版本": metric?.method_version || "未提供",
        "参数": metric?.parameters ? JSON.stringify(metric.parameters) : "未提供",
        "输入快照": metric?.snapshot_id || metricData.input_snapshot_id || "未提供", "缺少条件": metric?.missing_reason || "未报告",
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
  const OPERATION_DESCRIPTIONS = Object.freeze({
    MARKET_DATA: "查询市场行情，查看价格、成交与走势数据。",
    COMPANY_DATA: "查询公司财务数据，了解经营表现与财务状况。",
    INDUSTRY_DATA: "查询行业数据，了解行业变化与公司所属领域。",
    MACRO_DATA: "查询宏观经济数据，为市场研究补充背景信息。",
    FUND_DATA: "查询基金与理财产品数据，了解产品及持仓信息。",
    CONVERTIBLE_BOND_DATA: "按条件查询可转债，查看相关行情与公司信息。",
    SEARCH_NEWS: "搜索公告与新闻，查看相关内容及来源。",
    SEARCH_REPORTS: "搜索研究报告，查找相关观点与研究依据。",
  });
  const OPERATION_ICONS = Object.freeze({MARKET_DATA: "activity", COMPANY_DATA: "file-text", INDUSTRY_DATA: "layers", MACRO_DATA: "compass", FUND_DATA: "layers", CONVERTIBLE_BOND_DATA: "file-text", SEARCH_NEWS: "search", SEARCH_REPORTS: "file-text"});
  let skillItems = [];
  let skillAdmin = false;
  let skillDirectory = "PUBLIC";
  let skillCategory = "ALL";
  let skillOwner = null;
  let skillLoadSequence = 0;
  let skillMutation = false;
  let skillDetailItem = null;
  let skillDetailReturnKey = null;
  let skillDetailReturnFocus = true;
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
    for (const id of ["skill-store-message", "skill-detail-message"]) {
      const output = byId(id);
      if (!output) continue;
      output.textContent = message;
      output.classList.toggle("error", failure);
      output.hidden = !message;
    }
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
    const owner = currentOwner();
    skillMutation = true;
    setSkillMessage("正在提交操作…");
    renderSkillDirectory();
    if (skillDetailItem) showSkillDetail(skillDetailItem);
    try {
      const result = await operation();
      if (owner !== currentOwner()) return;
      await loadSkills(false);
      if (owner !== currentOwner()) return;
      setSkillMessage(typeof message === "function" ? message(result) : message);
      if (skillDetailItem) showSkillDetail(skillItems.find(item => item.skill_id === skillDetailItem.skill_id && item.version === skillDetailItem.version));
    } catch (error) {
      if (owner !== currentOwner()) return;
      if (error.status === 409) await loadSkills(false).catch(() => {});
      setSkillMessage(error.message, true);
    } finally {
      skillMutation = false;
      renderSkillDirectory();
      if (skillDetailItem) showSkillDetail(skillItems.find(item => item.skill_id === skillDetailItem.skill_id && item.version === skillDetailItem.version));
    }
  }
  function skillIcon(name) {
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("class", "prism-icon");
    icon.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#icon-${name}`);
    icon.append(use);
    return icon;
  }
  function skillGlyph(item) {
    const glyph = node("span", null, "research-skill-glyph");
    glyph.dataset.operation = item.operation;
    glyph.append(skillIcon(OPERATION_ICONS[item.operation] || "grid"));
    return glyph;
  }
  function skillDescription(item) {
    if (item.channel === "announcement") return "搜索公司公告，查看公告内容、发布时间与来源。";
    if (item.channel === "news") return "搜索市场与公司新闻，为研究补充相关信息。";
    return OPERATION_DESCRIPTIONS[item.operation] || "查看该技能的研究用途与数据接口。";
  }
  function showSkillDetail(item) {
    const output = byId("skill-store-detail");
    skillDetailItem = item || null;
    if (!item) { output.close(); return; }
    const wasOpen = output.open;
    const openedSections = new Set([...output.querySelectorAll("details[open]")].map(section => section.id));
    const focusedId = output.contains(document.activeElement) ? document.activeElement.id : null;
    if (!wasOpen) {
      skillDetailReturnKey = {skill_id: item.skill_id, version: item.version};
      skillDetailReturnFocus = true;
    }
    output.replaceChildren();
    const header = node("header", null, "research-skill-dialog-header");
    const title = node("h2", "技能详情"); title.id = "skill-detail-title";
    const close = actionButton("×", () => output.close()); close.id = "skill-detail-close"; close.className = "research-skill-close"; close.setAttribute("aria-label", "关闭技能详情");
    header.append(title, close);
    const body = node("div", null, "research-skill-dialog-body");
    const identity = node("div", null, "research-skill-identity");
    const name = node("div"); name.append(node("strong", item.name), node("small", `${OPERATION_LABELS[item.operation] || item.operation} · ${item.version}`));
    identity.append(skillGlyph(item), name);
    const description = node("p", skillDescription(item), "research-skill-description"); description.id = "skill-detail-description";
    body.append(identity, description);
    const technical = node("details", null, "research-skill-disclosure"); technical.id = "skill-technical-details"; technical.open = wasOpen && openedSections.has(technical.id);
    technical.append(node("summary", "数据与接口"));
    const data = node("dl", null, "research-detail-list");
    for (const [label, value] of Object.entries({"能力标识": item.skill_id, "版本": item.version, "用途": OPERATION_LABELS[item.operation] || item.operation, "注册状态": SKILL_STATUS[item.status] || item.status, "全局状态": item.enabled ? "已启用" : "已停用", "调用状态": item.callable ? "可调用" : "不可调用", "修订号": item.revision, "执行方式": "受控 API 适配器", "审核接口": item.endpoint, "渠道": item.channel || "不适用", "更新时间": item.updated_at, "包哈希": item.package_sha256 || "未提供", "完整性状态": item.package_integrity === "REGISTERED_HASH_ONLY" ? "仅登记哈希；未执行下载包" : "未提供哈希"})) data.append(node("dt", label), node("dd", value));
    technical.append(data); body.append(technical);
    if (skillAdmin && !isReadOnly()) {
      const management = node("details", null, "research-skill-disclosure"); management.id = "skill-management-details"; management.open = wasOpen && openedSections.has(management.id);
      management.append(node("summary", "管理技能"));
      const controls = node("div", null, "research-action-row");
      if (item.status === "PENDING") controls.append(actionButton("验证能力", () => mutateSkill(() => api(`${skillPath(item)}/verify`, {method: "POST", body: JSON.stringify({expected_revision: item.revision})}), result => result.status === "PASS" ? "验证通过，版本已启用。" : `验证未通过，保持待验证。${result.error_code ? `原因：${result.error_code}` : ""}`), skillMutation));
      if (item.status === "INSTALLED") controls.append(actionButton(item.enabled ? "全局停用" : "全局启用", () => mutateSkill(() => api(skillPath(item), {method: "PATCH", body: JSON.stringify({action: item.enabled ? "disable" : "enable", expected_revision: item.revision})}), "能力状态已更新。"), skillMutation));
      if (item.status !== "UNINSTALLED") controls.append(actionButton("卸载此版本", () => mutateSkill(() => api(skillPath(item), {method: "PATCH", body: JSON.stringify({action: "uninstall", expected_revision: item.revision})}), "版本已卸载；可以重新登记。"), skillMutation));
      controls.append(actionButton(item.status === "UNINSTALLED" ? "重新安装" : "登记新版本", () => {
        const metadata = Object.fromEntries(["skill_id", "version", "name", "operation", "endpoint", "channel", "package_sha256"].filter(key => item[key] != null).map(key => [key, item[key]]));
        byId("skill-metadata-input").value = JSON.stringify(metadata, null, 2);
        byId("skill-import-panel").open = true;
        skillDetailReturnFocus = false;
        output.close();
        byId("skill-metadata-input").focus();
      }, skillMutation));
      management.append(controls); body.append(management);
    }
    const message = node("p", null, "notice"); message.id = "skill-detail-message"; message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite");
    message.textContent = byId("skill-store-message").textContent; message.hidden = !message.textContent; message.classList.toggle("error", byId("skill-store-message").classList.contains("error")); body.append(message);
    const footer = node("footer", null, "research-skill-dialog-footer");
    footer.append(node("small", item.personal_enabled ? "已加入个人技能" : "尚未加入个人技能"));
    const selection = actionButton(item.personal_enabled ? "取消选择" : "选择技能", () => mutateSkill(() => api(`/api/v1/skills/${encodeURIComponent(item.skill_id)}/selection`, {method: "PUT", body: JSON.stringify({enabled: !item.personal_enabled, expected_revision: item.selection_revision})}), "个人能力选择已保存。"), skillMutation || isReadOnly() || item.status === "UNINSTALLED");
    selection.id = "skill-personal-toggle"; selection.className = "research-skill-primary"; selection.setAttribute("aria-pressed", String(item.personal_enabled)); footer.append(selection);
    output.append(header, body, footer);
    if (!wasOpen) { output.showModal(); document.body.classList.add("skill-dialog-open"); }
    else if (focusedId) byId(focusedId)?.focus({preventScroll: true});
  }
  function renderSkillDirectory() {
    const output = byId("skill-store-catalog");
    if (!output) return;
    output.replaceChildren();
    const search = (byId("skill-store-search")?.value || "").trim().toLowerCase();
    const installedOnly = byId("skill-store-installed")?.checked;
    const showVersions = byId("skill-store-versions")?.checked;
    const items = skillItems.filter(item => (skillDirectory !== "PERSONAL" || item.personal_enabled) && (skillCategory === "ALL" || item.operation === skillCategory) && (!installedOnly || item.status === "INSTALLED") && [item.name, item.skill_id, item.version, OPERATION_LABELS[item.operation]].some(value => String(value || "").toLowerCase().includes(search)));
    byId("skill-store-count").textContent = `${items.length} 项技能`;
    byId("skill-store-catalog-title").textContent = skillDirectory === "PUBLIC" ? "全部技能" : "我已选择";
    byId("skill-import-panel").hidden = !skillAdmin || isReadOnly();
    byId("skill-register-button").disabled = skillMutation;
    for (const [id, directory] of [["skill-store-public", "PUBLIC"], ["skill-store-personal", "PERSONAL"]]) {
      const tab = byId(id); const selected = skillDirectory === directory;
      tab.setAttribute("aria-selected", String(selected)); tab.setAttribute("aria-pressed", String(selected)); tab.tabIndex = selected ? 0 : -1;
    }
    byId("skill-store-catalog-panel").setAttribute("aria-labelledby", skillDirectory === "PUBLIC" ? "skill-store-public" : "skill-store-personal");
    byId("skill-metadata-input").disabled = skillMutation;
    if (!items.length) { output.append(node("p", "当前筛选条件下没有能力版本。", "empty-state")); return; }
    for (const item of items) {
      const card = node("article", null, "research-skill-card");
      card.dataset.skillId = item.skill_id;
      card.dataset.skillVersion = item.version;
      const header = node("div", null, "research-skill-heading");
      const name = node("div", null, "research-skill-name");
      const heading = node("h3"); const open = actionButton(item.name, () => showSkillDetail(item)); open.className = "research-skill-open"; open.setAttribute("aria-label", `${item.name} ${item.version}，查看详情`); heading.append(open);
      name.append(heading, node("small", `${OPERATION_LABELS[item.operation] || item.operation}${showVersions ? ` · ${item.version}` : ""}`));
      header.append(skillGlyph(item), name);
      card.append(header, node("p", skillDescription(item)));
      const footer = node("div", null, "research-skill-footer"); const selected = node("span", item.personal_enabled ? "已选择" : "未选择"); selected.classList.toggle("selected", item.personal_enabled);
      if (item.status !== "INSTALLED" || !item.enabled) selected.append(node("span", ` · ${item.status !== "INSTALLED" ? SKILL_STATUS[item.status] || item.status : "全局已停用"}`));
      const detail = actionButton("查看详情", () => showSkillDetail(item)); detail.className = "research-skill-open"; detail.append(skillIcon("chevron-right"));
      detail.setAttribute("aria-label", `${item.name} ${item.version}，查看详情`); footer.append(selected, detail); card.append(footer);
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
    container.className = "research-store-shell";
    container.removeAttribute("role");
    container.removeAttribute("aria-live");
    container.replaceChildren();
    const searchBox = node("label", null, "research-store-search");
    const search = node("input"); search.id = "skill-store-search"; search.type = "search"; search.placeholder = "搜索技能"; search.autocomplete = "off"; search.setAttribute("aria-label", "搜索技能");
    search.addEventListener("input", renderSkillDirectory);
    searchBox.append(skillIcon("search"), search); container.append(searchBox);
    const toolbar = node("div", null, "research-store-toolbar");
    const tabs = node("div", null, "research-store-tabs"); tabs.setAttribute("role", "tablist"); tabs.setAttribute("aria-label", "技能目录");
    const publicButton = actionButton("全部技能", () => { skillDirectory = "PUBLIC"; renderSkillDirectory(); }); publicButton.id = "skill-store-public";
    const personalButton = actionButton("我已选择", () => { skillDirectory = "PERSONAL"; renderSkillDirectory(); }); personalButton.id = "skill-store-personal";
    for (const button of [publicButton, personalButton]) {
      button.setAttribute("role", "tab"); button.setAttribute("aria-controls", "skill-store-catalog-panel");
      button.addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === "Home" ? publicButton : event.key === "End" ? personalButton : button === publicButton ? personalButton : publicButton;
        next.click(); next.focus();
      });
    }
    tabs.append(publicButton, personalButton);
    const filters = node("details", null, "research-store-filters"); filters.id = "skill-store-filters";
    const filterSummary = node("summary", "筛选"); filterSummary.prepend(skillIcon("sliders")); filters.append(filterSummary);
    const filterPanel = node("div", null, "research-store-filter-panel");
    const installed = node("label"); const checkbox = node("input"); checkbox.id = "skill-store-installed"; checkbox.type = "checkbox"; checkbox.addEventListener("change", renderSkillDirectory); installed.append(checkbox, node("span", "仅已安装"));
    const versions = node("label"); const versionCheckbox = node("input"); versionCheckbox.id = "skill-store-versions"; versionCheckbox.type = "checkbox"; versionCheckbox.addEventListener("change", renderSkillDirectory); versions.append(versionCheckbox, node("span", "显示版本"));
    filterPanel.append(installed, versions, actionButton("刷新目录", () => { filters.open = false; loadSkills(); }), actionButton("重置筛选", () => {
      search.value = ""; checkbox.checked = false; versionCheckbox.checked = false; skillCategory = "ALL";
      byId("skill-store-categories").querySelectorAll("button").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.skillCategory === "ALL")));
      filters.open = false; renderSkillDirectory(); search.focus();
    }));
    filters.append(filterPanel); toolbar.append(tabs, filters);
    container.append(toolbar);
    const message = node("p", null, "notice"); message.id = "skill-store-message"; message.hidden = true; message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite"); container.append(message);
    const categories = node("nav", null, "research-store-categories"); categories.id = "skill-store-categories"; categories.setAttribute("aria-label", "技能分类");
    for (const [key, label] of Object.entries({ALL: "全部", ...OPERATION_LABELS})) {
      const button = actionButton(label, () => { skillCategory = key; categories.querySelectorAll("button").forEach(item => item.setAttribute("aria-pressed", String(item === button))); renderSkillDirectory(); });
      button.dataset.skillCategory = key;
      button.setAttribute("aria-pressed", String(key === skillCategory)); categories.append(button);
    }
    container.append(categories);
    const catalogPanel = node("section"); catalogPanel.id = "skill-store-catalog-panel"; catalogPanel.setAttribute("role", "tabpanel");
    const catalogHeading = node("div", null, "research-store-catalog-heading");
    const catalogTitle = node("h3", "全部技能"); catalogTitle.id = "skill-store-catalog-title";
    const count = node("span", "0 项技能"); count.id = "skill-store-count"; count.setAttribute("aria-live", "polite"); catalogHeading.append(catalogTitle, count);
    const catalog = node("div", null, "research-skill-grid"); catalog.id = "skill-store-catalog"; catalogPanel.append(catalogHeading, catalog); container.append(catalogPanel);
    const detail = node("dialog", null, "research-skill-detail"); detail.id = "skill-store-detail"; detail.setAttribute("aria-labelledby", "skill-detail-title"); detail.setAttribute("aria-describedby", "skill-detail-description"); container.append(detail);
    detail.addEventListener("close", () => {
      skillDetailItem = null; document.body.classList.remove("skill-dialog-open");
      if (!skillDetailReturnFocus || !document.body.classList.contains("skill-store-active")) return;
      const card = [...catalog.children].find(item => item.dataset.skillId === skillDetailReturnKey?.skill_id && item.dataset.skillVersion === skillDetailReturnKey?.version);
      (card?.querySelector("button") || byId("skill-store-title")).focus({preventScroll: true});
    });
    let backdropPressed = false;
    const outsideDetail = event => { const bounds = detail.getBoundingClientRect(); return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom; };
    detail.addEventListener("pointerdown", event => { backdropPressed = event.target === detail && outsideDetail(event); });
    detail.addEventListener("click", event => { if (backdropPressed && event.target === detail && outsideDetail(event)) detail.close(); backdropPressed = false; });
    document.addEventListener("click", event => { if (!filters.contains(event.target)) filters.open = false; });
    filters.addEventListener("keydown", event => { if (event.key === "Escape") { filters.open = false; filterSummary.focus(); event.stopPropagation(); } });
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
    const activate = () => {
      if (window.location.hash !== "#skill-store") { showSkillDetail(null); filters.open = false; return; }
      if (skillOwner !== currentOwner()) { skillItems = []; skillAdmin = false; showSkillDetail(null); renderSkillDirectory(); }
      if (document.documentElement.dataset.prismOwner !== currentOwner()) { setSkillMessage("正在读取账户与能力目录…"); return; }
      loadSkills();
    };
    window.addEventListener("hashchange", activate);
    document.addEventListener("prism:owner-ready", () => {
      skillOwner = null; skillLoadSequence++; skillItems = []; skillAdmin = false; showSkillDetail(null); renderSkillDirectory();
      activate();
    });
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
