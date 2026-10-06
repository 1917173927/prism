/* Personal systems are declarative. Financial values and policy effects come from the server. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const owner = () => byId("owner-id")?.value.trim() || "";
  const readOnly = () => window.PRISM_PAGES_SNAPSHOT === true;
  const clone = value => JSON.parse(JSON.stringify(value));
  const FIELD_NAMES = Object.freeze({price: "最新价", revenue: "营业收入", net_profit: "净利润", pe: "市盈率", nav: "单位净值"});
  const OPERATOR_NAMES = Object.freeze({ratio_pct: "比率（百分比）", difference: "两项之差", weighted_mean: "加权平均"});
  const ACTION_NAMES = Object.freeze({BUY: "买入", SELL: "卖出", REDUCE: "减仓", HOLD: "保持"});
  const STATUS_NAMES = Object.freeze({QUEUED: "排队中", RUNNING: "进行中", COMPLETED: "已完成", PARTIAL: "部分资料待补充", FAILED: "未完成", TIMED_OUT: "已超时", CANCELLED: "已取消", CALCULATED: "已计算", UNAVAILABLE: "暂无法计算", SUCCESS: "资料已返回", EMPTY: "暂无资料", PASS: "通过", REVIEW_REQUIRED: "需要复核", BLOCKED: "已拦截", ACTIVE: "已确认并生效", STALE: "依据已变化，需重新确认", UNCONFIRMED: "尚未确认"});
  const statusName = value => STATUS_NAMES[value] || "状态待确认";
  function actionSummary(action) {
    if (!action) return "—";
    const quantity = action.shares && action.action_type !== "HOLD" ? ` · ${format(action.shares, action.asset_type === "STOCK" ? "股" : "份")}` : "";
    return `${ACTION_NAMES[action.action_type] || "待核对"} · ${format(action.cash_delta_cny, "元")}${quantity}`;
  }
  const terminalRun = run => ["COMPLETED", "PARTIAL", "FAILED", "TIMED_OUT", "CANCELLED"].includes(run?.status);
  const state = {owner: owner(), epoch: 0, catalog: null, systems: [], system: null, draft: null, run: null, memory: null, context: null, rebalancingInput: null, preview: null};
  const requests = new Map();
  let runPoll = null;
  let idSequence = 0;

  function element(tag, text, className = "") {
    const result = document.createElement(tag);
    if (text != null) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  }
  function section(title, description) {
    const result = element("section", null, "surface personal-section");
    result.append(element("h3", title));
    if (description) result.append(element("p", description, "personal-context-note"));
    return result;
  }
  function button(label, callback, {write = false, primary = false, id = ""} = {}) {
    const result = element("button", label, `copilot-action-btn ${primary ? "primary" : "secondary"}`);
    result.type = "button";
    if (id) result.id = id;
    result.disabled = write && readOnly();
    result.addEventListener("click", callback);
    return result;
  }
  function field(label, {id = "", value = "", type = "text", options = null, change = null, multiline = false, min = null, max = null} = {}) {
    const wrapper = element("label", null, "personal-field");
    wrapper.append(element("span", label));
    const control = element(options ? "select" : multiline ? "textarea" : "input");
    if (id) control.id = id;
    if (!options && !multiline) control.type = type;
    if (options) for (const [key, name] of options) { const option = element("option", name); option.value = key; control.append(option); }
    control.value = value == null ? "" : String(value);
    if (min != null) control.min = String(min);
    if (max != null) control.max = String(max);
    if (type === "number") control.step = "any";
    if (change) control.addEventListener(options ? "change" : "input", () => change(control.value));
    wrapper.append(control);
    return wrapper;
  }
  function notice(id) {
    const result = element("p", null, "personal-notice"); result.id = id;
    result.hidden = true; result.setAttribute("role", "status"); result.setAttribute("aria-live", "polite"); return result;
  }
  function message(id, text, failure = false) {
    const result = byId(id); if (!result) return;
    result.textContent = text; result.hidden = !text;
    result.classList.toggle("error", failure);
  }
  function record(label, value) {
    const result = element("details", null, "personal-record");
    result.append(element("summary", label), element("pre", JSON.stringify(value, null, 2))); return result;
  }
  function table(headers, rows) {
    const wrapper = element("div", null, "table-wrap research-table-wrap");
    const result = element("table"); const header = element("tr");
    if (headers.length >= 4) result.className = "personal-wide-table";
    headers.forEach(name => header.append(element("th", name)));
    const head = element("thead"); head.append(header); result.append(head);
    const body = element("tbody");
    for (const values of rows) { const row = element("tr"); values.forEach(value => row.append(element("td", value == null ? "—" : value))); body.append(row); }
    result.append(body); wrapper.append(result); return wrapper;
  }
  function format(value, unit = "") {
    if (value == null || value === "") return "—";
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toLocaleString("zh-CN", {maximumFractionDigits: 4})}${unit}` : "—";
  }
  function displayUnit(unit) { return ({CNY: "元", "CNY/share": "元/股", PCT: "%", percent: "%", ratio: "倍", shares: "股", "%": "%"})[unit] || (/\p{Script=Han}/u.test(unit || "") ? unit : ""); }
  function nextId(prefix) {
    const existing = new Set([...(state.draft?.data_agents || []).map(item => item.agent_id), ...(state.draft?.indicators || []).map(item => item.indicator_id), ...(state.draft?.observers || []).map(item => item.agent_id)]);
    let id; do { id = `${prefix}-${++idSequence}`; } while (existing.has(id)); return id;
  }
  function systemId() { return `research-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${++idSequence}`}`; }
  async function request(channel, path, {method = "GET", body} = {}) {
    if (readOnly() && method !== "GET") throw new Error("只读页面不能保存或执行研究，请进入已登录的工作台。");
    requests.get(channel)?.abort();
    const controller = new AbortController(); requests.set(channel, controller);
    const requestOwner = owner(), epoch = state.epoch;
    try {
      const response = await fetch(path, {method, signal: controller.signal, headers: {"X-Owner-ID": requestOwner, ...(body ? {"Content-Type": "application/json"} : {})}, ...(body ? {body: JSON.stringify(body)} : {})});
      const data = await response.json().catch(() => ({}));
      if (controller.signal.aborted || requestOwner !== owner() || epoch !== state.epoch) throw new DOMException("请求上下文已失效", "AbortError");
      if (!response.ok) {
        const descriptions = {401: "请先登录账户。", 403: "当前账户没有访问权限。", 404: "记录不可访问，可能已删除或不属于当前账户。", 409: "资料或版本已变化，请刷新并重新确认。", 422: "配置未通过检查，请核对输入字段、指标依赖与研究期间。", 429: "当前研究容量已满，请稍后重试。", 503: "数据工具或服务暂不可用。"};
        const hasBusinessExplanation = /^(?:PERSONAL_|INVESTMENT_)/.test(data?.error_code || "");
        const explanation = channel === "preview" && response.status === 422 ? "目标权重合计须为 100%，每项应在 0 至 100% 之间。请核对本次测算目标。" : descriptions[response.status];
        throw new Error(hasBusinessExplanation && data.message ? data.message : explanation || "请求未完成，请稍后重试。");
      }
      return data;
    } finally { if (requests.get(channel) === controller) requests.delete(channel); }
  }
  async function busy(control, statusId, operation) {
    if (control.disabled) return;
    const epoch = state.epoch; control.disabled = true;
    message(statusId, "正在处理…");
    try { await operation(); }
    catch (error) { if (error.name !== "AbortError" && epoch === state.epoch) message(statusId, error.message, true); }
    finally { if (control.isConnected) control.disabled = readOnly(); }
  }
  function sourceChoices(indicatorId) {
    const choices = [["", "请选择输入数据"]];
    for (const agent of state.draft?.data_agents || []) for (const name of agent.fields || []) choices.push([`${agent.agent_id}.${name}`, `${agent.name || "资料助手"} · ${FIELD_NAMES[name] || "数据项"}`]);
    for (const indicator of state.draft?.indicators || []) if (indicator.indicator_id !== indicatorId) choices.push([indicator.indicator_id, `自定义指标 · ${indicator.name || "未命名指标"}`]);
    return choices;
  }
  function selectedSkill(agent) { return state.catalog?.skills?.find(item => item.skill_id === agent.skill_id && item.version === agent.version); }
  function createDataAgent() {
    const skill = state.catalog?.skills?.find(item => item.callable);
    return {agent_id: nextId("data"), name: "资料助手", skill_id: skill?.skill_id || "", version: skill?.version || "", fields: (skill?.fields || []).slice(0, 2)};
  }
  function markEdited() { message("personal-system-message", "配置已修改，请保存新版本后运行。"); updateRunControls(); }
  function renderDataAgents() {
    const root = byId("personal-data-agents"); root.replaceChildren();
    for (const [index, agent] of state.draft.data_agents.entries()) {
      const block = element("article", null, "personal-block");
      const heading = element("div", null, "personal-heading");
      heading.append(element("h4", `资料助手 ${index + 1}`), button("移除", () => { state.draft.data_agents.splice(index, 1); renderEditor(); markEdited(); }));
      const grid = element("div", null, "personal-form-grid");
      grid.append(field("助手名称", {value: agent.name, change: value => { agent.name = value; markEdited(); }}));
      const skills = [["", "请选择已启用的数据工具"], ...(state.catalog?.skills || []).map((item, skillIndex) => [String(skillIndex), `${item.name} · ${item.version}${item.callable ? "" : "（当前不可用）"}`])];
      const skillIndex = state.catalog?.skills?.findIndex(item => item.skill_id === agent.skill_id && item.version === agent.version) ?? -1;
      grid.append(field("数据工具", {value: skillIndex < 0 ? "" : skillIndex, options: skills, change: value => {
        const skill = state.catalog?.skills?.[Number(value)];
        agent.skill_id = value !== "" ? skill?.skill_id || "" : ""; agent.version = value !== "" ? skill?.version || "" : ""; agent.fields = value !== "" ? (skill?.fields || []).slice(0, 2) : [];
        renderEditor(); markEdited();
      }}));
      block.append(heading, grid, element("p", "选择需要读取的数据项：", "personal-context-note"));
      const checks = element("div", null, "personal-checks");
      for (const name of selectedSkill(agent)?.fields || []) {
        const label = element("label"); const input = element("input"); input.type = "checkbox"; input.checked = agent.fields.includes(name);
        input.addEventListener("change", () => { agent.fields = input.checked ? [...agent.fields, name] : agent.fields.filter(item => item !== name); renderIndicators(); markEdited(); });
        label.append(input, element("span", FIELD_NAMES[name] || "数据项")); checks.append(label);
      }
      if (!checks.childElementCount) checks.append(element("span", "请先选择可用的数据工具。", "personal-context-note"));
      block.append(checks); root.append(block);
    }
    if (!state.draft.data_agents.length) root.append(element("p", "添加资料助手，选择可以调用的数据工具。", "empty-state"));
  }
  function renderIndicators() {
    const root = byId("personal-indicators"); root.replaceChildren();
    for (const [index, indicator] of state.draft.indicators.entries()) {
      const block = element("article", null, "personal-block"); const heading = element("div", null, "personal-heading");
      heading.append(element("h4", `指标 ${index + 1}`), button("移除", () => { state.draft.indicators.splice(index, 1); renderIndicators(); renderObservers(); markEdited(); }));
      const grid = element("div", null, "personal-form-grid");
      grid.append(field("指标名称", {value: indicator.name, change: value => { indicator.name = value; markEdited(); }}), field("计算方法", {value: indicator.operator, options: Object.entries(OPERATOR_NAMES), change: value => {
        indicator.operator = value; if (value !== "weighted_mean") { indicator.inputs = indicator.inputs.slice(0, 2); delete indicator.weights; }
        else indicator.weights = indicator.inputs.map(() => "1");
        renderIndicators(); markEdited();
      }}));
      block.append(heading, grid, element("p", indicator.operator === "ratio_pct" ? "输入顺序为分子、分母；由服务端计算百分比。" : "输入必须具有相同单位、标的和报告期。服务端检查条件后计算。", "personal-context-note"));
      for (const [inputIndex, value] of indicator.inputs.entries()) {
        const row = element("div", null, "personal-input-row");
        const label = indicator.operator === "ratio_pct" ? (inputIndex === 0 ? "分子" : "分母") : `输入 ${inputIndex + 1}`;
        row.append(field(label, {value, options: sourceChoices(indicator.indicator_id), change: selected => { indicator.inputs[inputIndex] = selected; markEdited(); }}));
        if (indicator.operator === "weighted_mean") {
          row.append(field("权重", {type: "number", min: 0, value: indicator.weights?.[inputIndex] ?? "1", change: selected => { indicator.weights[inputIndex] = selected; markEdited(); }}));
          if (indicator.inputs.length > 2) row.append(button("移除输入", () => { indicator.inputs.splice(inputIndex, 1); indicator.weights.splice(inputIndex, 1); renderIndicators(); markEdited(); }));
        }
        block.append(row);
      }
      if (indicator.operator === "weighted_mean" && indicator.inputs.length < 8) block.append(button("添加输入项", () => { indicator.inputs.push(""); indicator.weights.push("1"); renderIndicators(); markEdited(); }));
      root.append(block);
    }
    if (!state.draft.indicators.length) root.append(element("p", "添加指标，将数据字段组合成可重复计算的研究工具。", "empty-state"));
  }
  function renderObservers() {
    const root = byId("personal-observers"); root.replaceChildren();
    for (const [index, observer] of state.draft.observers.entries()) {
      const block = element("article", null, "personal-block"); const heading = element("div", null, "personal-heading");
      heading.append(element("h4", `观察助手 ${index + 1}`), button("移除", () => { state.draft.observers.splice(index, 1); renderObservers(); markEdited(); }));
      const grid = element("div", null, "personal-form-grid");
      grid.append(field("助手名称", {value: observer.name, change: value => { observer.name = value; markEdited(); }}), field("观察指标", {value: observer.indicator_id, options: [["", "请选择指标"], ...state.draft.indicators.map(item => [item.indicator_id, item.name || "未命名指标"])], change: value => { observer.indicator_id = value; markEdited(); }}), field("观察条件", {value: observer.comparison, options: [["gte", "大于或等于"], ["lte", "小于或等于"]], change: value => { observer.comparison = value; markEdited(); }}), field("阈值（采用指标单位）", {type: "number", value: observer.threshold, change: value => { observer.threshold = value; markEdited(); }}), field("满足条件时的说明", {value: observer.matched_message, change: value => { observer.matched_message = value; markEdited(); }}), field("未满足条件时的说明", {value: observer.unmatched_message, change: value => { observer.unmatched_message = value; markEdited(); }}));
      block.append(heading, grid); root.append(block);
    }
    if (!state.draft.observers.length) root.append(element("p", "可添加观察助手，按指标结果产生明确的研究提示。", "empty-state"));
  }
  function renderEditor() {
    if (!state.draft || !byId("personal-system-name")) return;
    byId("personal-system-name").value = state.draft.name || ""; byId("personal-system-description").value = state.draft.description || "";
    byId("personal-system-version").textContent = state.system ? `已保存第 ${state.system.revision} 版` : "新系统 · 尚未保存";
    renderDataAgents(); renderIndicators(); renderObservers(); updateRunControls();
  }
  function setDraft(definition, saved = null) {
    stopPolling(); requests.get("run-status")?.abort(); state.run = null; state.system = saved; state.draft = clone(definition);
    byId("personal-system-result")?.replaceChildren(element("p", "保存后输入标的，运行自己的研究系统。", "empty-state"));
    renderEditor(); renderSystemList();
  }
  function emptyDraft() { return {name: "我的研究系统", description: "", data_agents: [createDataAgent()], indicators: [], observers: []}; }
  function draftSaved() { return !!state.system && JSON.stringify(state.draft) === JSON.stringify(state.system.definition); }
  function updateRunControls() {
    const run = byId("personal-system-run"); const cancel = byId("personal-system-cancel");
    const active = state.run && !terminalRun(state.run);
    if (run) run.disabled = readOnly() || !draftSaved() || !!active;
    if (cancel) cancel.disabled = readOnly() || !active;
  }
  function renderSystemList() {
    const root = byId("personal-system-list"); if (!root) return; root.replaceChildren();
    for (const item of state.systems) {
      const card = element("article", null, "personal-system-card"); card.setAttribute("aria-current", String(item.system_id === state.system?.system_id));
      card.append(element("strong", item.name || item.definition?.name || "未命名研究系统"), element("p", `第 ${item.revision} 版 · ${item.definition?.data_agents?.length || 0} 个资料助手 · ${item.definition?.indicators?.length || 0} 项指标`), button("载入配置", () => { setDraft(item.definition, item); message("personal-system-message", "已载入已保存版本，可修改或直接运行。"); }));
      root.append(card);
    }
    if (!state.systems.length) root.append(element("p", "尚无个人系统。可从示例结构开始，再保存自己的版本。", "empty-state"));
  }
  async function loadSystems() {
    const [catalog, systems] = await Promise.all([request("catalog", "/api/v1/personal-research/catalog"), request("systems", "/api/v1/personal-research/systems")]);
    state.catalog = catalog; state.systems = systems.items || [];
    const templates = byId("personal-system-templates"); templates.replaceChildren();
    for (const template of catalog.templates || []) templates.append(button(`采用${template.name}`, () => { setDraft(template.definition); message("personal-system-message", "已载入配置结构，数据将在运行时读取。"); }));
    if (!state.draft) setDraft(emptyDraft()); else renderEditor();
    renderSystemList();
    message("personal-system-message", readOnly() ? "此页面只读，无法保存或运行。" : "");
  }
  function validateDraft() {
    const draft = state.draft;
    if (!draft) throw new Error("请先读取工具目录，再建立研究系统。");
    if (!draft.name.trim()) throw new Error("请填写系统名称。");
    if (!draft.data_agents.length || draft.data_agents.some(item => !item.name.trim() || !item.skill_id || !item.fields.length)) throw new Error("每个资料助手需要名称、数据工具及至少一个数据项。");
    if (draft.data_agents.some(item => !selectedSkill(item)?.callable)) throw new Error("系统包含当前不可调用的工具，请启用工具或更换版本。");
    if (!draft.indicators.length || draft.indicators.some(item => !item.name.trim() || item.inputs.some(value => !value))) throw new Error("请至少设置一项指标，并选齐输入数据。");
    if (draft.indicators.some(item => item.operator === "weighted_mean" && item.weights.some(value => value === "" || !Number.isFinite(Number(value)) || Number(value) < 0))) throw new Error("指标权重需要填写非负数。");
    if (draft.observers.some(item => !item.name.trim() || !item.indicator_id || item.threshold === "" || !Number.isFinite(Number(item.threshold)) || !item.matched_message.trim() || !item.unmatched_message.trim())) throw new Error("请填写观察助手的指标、阈值和两种结果说明。");
  }
  async function saveSystem() {
    validateDraft(); const submitted = clone(state.draft); const previousSystem = state.system;
    const saved = await request("save-system", `/api/v1/personal-research/systems/${encodeURIComponent(previousSystem?.system_id || systemId())}`, {method: "PUT", body: {definition: submitted, expected_revision: previousSystem?.revision || 0}});
    const sameEditor = previousSystem === state.system;
    const editedWhileSaving = JSON.stringify(state.draft) !== JSON.stringify(submitted);
    if (sameEditor) { state.system = saved; if (!editedWhileSaving) state.draft = clone(saved.definition); }
    const index = state.systems.findIndex(item => item.system_id === saved.system_id);
    if (index < 0) state.systems.unshift(saved); else state.systems[index] = saved;
    renderEditor(); renderSystemList(); message("personal-system-message", sameEditor && !editedWhileSaving ? `系统已保存为第 ${saved.revision} 版，可在其他标的上重复运行。` : `系统第 ${saved.revision} 版已保存；当前编辑内容保留，请保存后再运行。`);
  }
  function renderRun(run) {
    state.run = run; const root = byId("personal-system-result"); root.replaceChildren();
    root.append(element("h4", `研究结果 · ${statusName(run.status)}`), element("p", `${run.subject || "研究标的"} · 系统第 ${run.system_revision} 版${run.elapsed_ms == null ? "" : ` · 用时 ${format(run.elapsed_ms)} 毫秒`} · ${run.data_mode === "STORED_FACTS" ? "使用已存资料重算" : "本次新采集"}`, "personal-context-note"));
    const cutoff = new Date(run.effective_as_of || run.as_of || "");
    if (run.is_synthetic) root.append(element("p", "本次使用受控演示数据，用于展示配置和执行过程。", "personal-notice"));
    const failures = {RESEARCH_INTERRUPTED: "上次运行因服务重启中断，可以重新运行。", RESEARCH_CAPACITY: "研究容量已满，请稍后重试。", RESEARCH_EXECUTION_FAILED: "研究工具或输入条件未满足，请检查本次配置和数据连接。"};
    if (run.error_code) root.append(element("p", failures[run.error_code] || "本次研究未完成，请检查数据工具和输入条件。", "personal-notice"));
    if (Number.isFinite(cutoff.getTime())) root.append(element("p", `资料截止时点：${cutoff.toLocaleString("zh-CN", {hour12: false})}`, "personal-context-note"));
    for (const indicator of run.indicators || []) {
      const card = element("article", null, "personal-block");
      card.append(element("h4", indicator.name), element("strong", indicator.status === "CALCULATED" ? format(indicator.value, displayUnit(indicator.unit)) : "暂无法计算"), element("p", indicator.reason_message || (indicator.status === "CALCULATED" ? "由已保存指标配置与本次实际输入计算。" : "缺少输入或计算条件，请补充资料。"), "personal-context-note"));
      root.append(card);
    }
    for (const observer of run.observers || []) root.append(element("p", `${observer.name || "观察助手"}：${observer.message || "指标尚未满足计算条件。"}`, "personal-notice"));
    if (run.data_agents?.length) root.append(table(["资料助手", "返回状态", "资料情况"], run.data_agents.map(item => [item.name, statusName(item.status), item.observations?.length ? `返回 ${item.observations.length} 项观察值` : "暂无可计算资料"])));
    const replayable = terminalRun(run) && run.data_agents?.length && run.data_agents.every(agent => agent.fact_refs?.length);
    if (replayable) {
      const replay = button("用本次已保存资料重算", event => busy(event.currentTarget, "personal-system-message", async () => {
        if (!draftSaved() || state.system.system_id !== run.system_id || state.system.revision !== run.system_revision) throw new Error("请先载入与本次研究相同的已保存系统版本。");
        const body = {expected_revision: run.system_revision, subject: run.subject, fact_ids: Object.fromEntries(run.data_agents.map(agent => [agent.agent_id, agent.fact_refs]))};
        if (run.period) body.period = run.period;
        if (run.as_of || run.effective_as_of) body.as_of = run.as_of || run.effective_as_of;
        const replayed = await request("replay-run", `/api/v1/personal-research/systems/${encodeURIComponent(run.system_id)}/fact-runs`, {method: "POST", body});
        if (state.system?.system_id !== run.system_id || state.system?.revision !== run.system_revision) return;
        renderRun(replayed); message("personal-system-message", "已用同一资料、同一系统版本重算，没有新增上游请求。");
      }), {write: true});
      root.append(replay);
    }
    root.append(element("p", "观察提示用于研究筛选；不直接产生交易指令。真实资料不足时，系统保留未计算状态。", "personal-context-note"), record("配置版本、输入与原始结果", run)); updateRunControls();
  }
  function stopPolling() { if (runPoll) clearTimeout(runPoll); runPoll = null; }
  function schedulePolling() {
    stopPolling();
    if (!state.run || terminalRun(state.run) || location.hash !== "#skill-store" || document.hidden) return;
    const runId = state.run.run_id;
    runPoll = setTimeout(async () => {
      try { const run = await request("run-status", `/api/v1/personal-research/runs/${encodeURIComponent(runId)}`); if (state.run?.run_id !== runId) return; renderRun(run); schedulePolling(); }
      catch (error) { if (error.name !== "AbortError") message("personal-system-message", error.message, true); }
    }, 1500);
  }
  function initializeSystems() {
    const root = byId("personal-system-workspace"); if (!root) return; root.className = "personal-workbench";
    const builder = section("我的研究系统", "将数据工具、自定义指标和研究助手组合为可保存、可复用的个人研究方法。");
    builder.append(notice("personal-system-message"));
    const collection = element("div", null, "personal-collection"); collection.id = "personal-system-list";
    builder.append(collection);
    const actions = element("div", null, "personal-actions");
    actions.append(button("新建系统", () => { setDraft(emptyDraft()); message("personal-system-message", "请设置数据工具、指标和观察条件。"); }), button("刷新已保存系统", event => busy(event.currentTarget, "personal-system-message", loadSystems)));
    const templates = element("div", null, "personal-actions"); templates.id = "personal-system-templates"; builder.append(actions, templates);
    const grid = element("div", null, "personal-form-grid");
    grid.append(field("系统名称", {id: "personal-system-name", change: value => { if (state.draft) { state.draft.name = value; markEdited(); } }}), field("研究用途", {id: "personal-system-description", multiline: true, change: value => { if (state.draft) { state.draft.description = value; markEdited(); } }}));
    builder.append(grid, Object.assign(element("p", "尚未载入", "personal-context-note"), {id: "personal-system-version"}));
    builder.append(element("h4", "第一步：选择数据工具"), Object.assign(element("div"), {id: "personal-data-agents"}));
    builder.append(button("添加资料助手", () => { if (!state.draft || state.draft.data_agents.length >= 8) return; state.draft.data_agents.push(createDataAgent()); renderEditor(); markEdited(); }));
    builder.append(element("h4", "第二步：组合自定义指标"), Object.assign(element("div"), {id: "personal-indicators"}));
    builder.append(button("添加指标", () => { if (!state.draft || state.draft.indicators.length >= 16) return; state.draft.indicators.push({indicator_id: nextId("indicator"), name: "自定义指标", operator: "ratio_pct", inputs: ["", ""]}); renderIndicators(); renderObservers(); markEdited(); }));
    builder.append(element("h4", "第三步：设置研究助手的观察条件"), Object.assign(element("div"), {id: "personal-observers"}));
    builder.append(button("添加观察助手", () => { if (!state.draft || state.draft.observers.length >= 8) return; state.draft.observers.push({agent_id: nextId("observer"), name: "观察助手", indicator_id: state.draft.indicators[0]?.indicator_id || "", comparison: "gte", threshold: "15", matched_message: "达到观察条件，可进一步研究", unmatched_message: "尚未达到观察条件"}); renderObservers(); markEdited(); }));
    const saveActions = element("div", null, "personal-actions");
    saveActions.append(button("保存我的研究系统", event => busy(event.currentTarget, "personal-system-message", saveSystem), {write: true, primary: true})); builder.append(saveActions);
    const runSection = section("运行与复用", "资料助手读取已启用工具，指标助手执行确定性计算，观察助手按你的条件生成提示。");
    const runFields = element("div", null, "personal-form-grid");
    runFields.append(field("A 股代码", {id: "personal-system-subject", value: "600519", max: 12}), field("报告期（可选）", {id: "personal-system-period", value: "", type: "text"}), field("研究截止时间（可选）", {id: "personal-system-as-of", type: "datetime-local"})); runSection.append(runFields, element("p", "多期财务资料需要指定报告期，例如 2025-Q4；截止时间之后的资料不能参与历史研究。", "personal-context-note"));
    const runActions = element("div", null, "personal-actions");
    runActions.append(button("运行已保存系统", event => busy(event.currentTarget, "personal-system-message", async () => {
      if (!draftSaved()) throw new Error("请先保存当前配置。");
      const subject = byId("personal-system-subject").value.trim(); if (!subject) throw new Error("请输入研究标的。");
      const body = {expected_revision: state.system.revision, subject, budget_seconds: 60};
      if (byId("personal-system-period").value.trim()) body.period = byId("personal-system-period").value.trim();
      if (byId("personal-system-as-of").value) { const date = new Date(byId("personal-system-as-of").value); if (!Number.isFinite(date.getTime())) throw new Error("研究截止时间无效。"); body.as_of = date.toISOString(); }
      const system = state.system;
      const run = await request("start-run", `/api/v1/personal-research/systems/${encodeURIComponent(system.system_id)}/runs`, {method: "POST", body});
      if (state.system?.system_id !== system.system_id || state.system?.revision !== system.revision) return;
      renderRun(run); schedulePolling(); message("personal-system-message", "研究已提交，可查看进度和返回资料。");
    }).finally(updateRunControls), {id: "personal-system-run", write: true, primary: true}), button("取消本次研究", event => busy(event.currentTarget, "personal-system-message", async () => {
      if (!state.run) return; stopPolling(); const run = await request("cancel-run", `/api/v1/personal-research/runs/${encodeURIComponent(state.run.run_id)}`, {method: "DELETE"}); renderRun(run); message("personal-system-message", "已返回取消结果。");
    }).finally(updateRunControls), {id: "personal-system-cancel", write: true})); runSection.append(runActions);
    const output = element("div"); output.id = "personal-system-result"; runSection.append(output); root.append(builder, runSection); updateRunControls();
  }

  const PARAMETER_NAMES = Object.freeze({max_turnover_pct: "单次调仓换手上限", minimum_cash_pct: "现金保留比例下限", deadband_pct: "微小权重偏差忽略幅度"});
  function policyGrid(parameters) {
    const grid = element("div", null, "personal-summary-grid");
    for (const [key, label] of Object.entries(PARAMETER_NAMES)) { const card = element("article"); card.append(element("small", label), element("strong", format(parameters?.[key], "%"))); grid.append(card); }
    return grid;
  }
  function renderMemory() {
    const data = state.memory; const output = byId("investment-memory-result"); if (!output) return;
    if (state.preview && (data?.policy_status !== "ACTIVE" || state.preview.policy?.revision !== data?.policy?.revision)) {
      requests.get("preview")?.abort(); state.preview = null; renderPreview();
    }
    output.replaceChildren();
    if (!data) { output.append(element("p", "读取已保存偏好与历史交易，查看可确认的长期投资风格。", "empty-state")); updatePreviewControls(); return; }
    for (const key of Object.keys(PARAMETER_NAMES)) byId(`investment-memory-${key}`).value = data.memory?.preferences?.[key] ?? "";
    output.append(element("h4", data.policy_status === "ACTIVE" ? "已确认的调仓偏好" : "待确认的调仓偏好"), element("p", `偏好记录第 ${data.memory?.revision || 0} 版 · ${statusName(data.policy_status)}`, "personal-context-note"), policyGrid(data.candidate?.parameters));
    const basis = element("ul", null, "personal-basis"); for (const text of data.candidate?.basis || []) basis.append(element("li", text)); output.append(basis);
    if (data.candidate?.primary_style) output.append(element("p", `历史风格参考：${data.candidate.primary_style}`, "personal-context-note"));
    if (data.policy) output.append(element("p", `已确认政策第 ${data.policy.revision} 版。${data.policy_status === "STALE" ? "偏好或交易资料已变化，旧政策暂不能用于新调仓。" : "调仓时可以使用本版本约束。"}`, "personal-context-note"));
    const confirm = button("确认并用于调仓", event => busy(event.currentTarget, "investment-memory-message", async () => {
      const candidate = state.memory?.candidate; if (!candidate) throw new Error("请先读取或保存偏好。");
      state.memory = await request("confirm-memory", "/api/v1/advisor/investment-memory/policy/confirm", {method: "POST", body: {candidate_id: candidate.candidate_id, expected_memory_revision: candidate.memory_revision, expected_style_profile_version: candidate.style_profile_version || 0}});
      renderMemory(); message("investment-memory-message", "长期偏好已确认。可以在调仓方案中对比实际影响。");
    }), {write: true, primary: true});
    confirm.disabled = readOnly() || !data.candidate || data.policy_status === "ACTIVE";
    output.append(confirm, element("p", "历史习惯只生成候选偏好，确认后才参与计算。个人偏好始终接受风险画像和适当性约束。", "personal-context-note"), record("偏好来源、样本与确认记录", data)); updatePreviewControls();
  }
  async function loadMemory() { state.memory = await request("memory", "/api/v1/advisor/investment-memory"); renderMemory(); message("investment-memory-message", ""); }
  function initializeMemory() {
    const root = byId("investment-memory-workspace"); if (!root) return; root.className = "personal-workbench";
    const panel = section("长期投资偏好", "保存你的调仓习惯，结合已导入的历史交易形成可确认、可撤销的个性化约束。");
    panel.append(notice("investment-memory-message")); const grid = element("div", null, "personal-form-grid");
    for (const [key, label] of Object.entries(PARAMETER_NAMES)) grid.append(field(`${label}（%，可留空）`, {id: `investment-memory-${key}`, type: "number", min: 0, max: 100}));
    panel.append(grid, element("p", "留空时按可用交易样本产生候选值；样本不足会注明默认值。换手率定义为买入、卖出金额合计除以组合市值再除以二。", "personal-context-note"));
    const controls = element("div", null, "personal-actions");
    controls.append(button("保存偏好并生成候选", event => busy(event.currentTarget, "investment-memory-message", async () => {
      const preferences = {};
      for (const key of Object.keys(PARAMETER_NAMES)) { const value = byId(`investment-memory-${key}`).value.trim(); if (value && (!Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 100)) throw new Error("偏好比例需要填写 0 至 100 之间的数值。"); preferences[key] = value || null; }
      state.memory = await request("save-memory", "/api/v1/advisor/investment-memory", {method: "PUT", body: {expected_revision: state.memory?.memory?.revision || 0, preferences}});
      renderMemory(); message("investment-memory-message", "偏好已保存，请核对候选约束后确认。");
    }), {write: true, primary: true}), button("读取最新偏好与交易依据", event => busy(event.currentTarget, "investment-memory-message", loadMemory)), button("撤销个人偏好", event => busy(event.currentTarget, "investment-memory-message", async () => {
      state.memory = await request("save-memory", "/api/v1/advisor/investment-memory", {method: "PUT", body: {expected_revision: state.memory?.memory?.revision || 0, preferences: {max_turnover_pct: null, minimum_cash_pct: null, deadband_pct: null}}});
      state.preview = null; renderMemory(); renderPreview(); message("investment-memory-message", "已清除手工偏好，旧政策失效；需要重新确认候选后才会应用。");
    }), {write: true})); panel.append(controls, Object.assign(element("div"), {id: "investment-memory-result"})); root.append(panel); renderMemory();
  }
  function updatePreviewControls() {
    const profileReady = state.rebalancingInput?.profile_ready !== false;
    const control = byId("personal-rebalancing-preview"); if (control) control.disabled = readOnly() || !state.context || !profileReady || state.memory?.policy_status !== "ACTIVE";
    const info = byId("personal-rebalancing-context");
    if (info) info.textContent = !state.context ? "读取当前持仓并设置目标，或生成现有调仓计划，再比较个人偏好影响。" : !profileReady ? "当前风险画像尚未确认，请到个人中心完成确认后重新读取持仓。" : state.memory?.policy_status !== "ACTIVE" ? "请到交易复盘确认最新长期偏好，再生成个性化对比。" : `当前调仓输入已准备，可使用已确认第 ${state.memory.policy.revision} 版偏好进行对比。`;
  }
  function renderTargetEditor() {
    const root = byId("personal-rebalancing-targets"); if (!root) return;
    root.replaceChildren();
    if (!state.rebalancingInput || !state.context) { root.hidden = true; return; }
    root.hidden = false;
    const input = state.rebalancingInput;
    root.append(element("h4", "设置本次测算的目标权重"), element("p", input.is_synthetic ? "受控演示持仓：用于功能展示，不代表真实账户。" : "当前账户持仓：初始目标按服务端当前权重填写，可按研究假设调整。", "personal-context-note"));
    const grid = element("div", null, "personal-target-grid");
    for (const position of input.positions || []) {
      const card = element("article", null, "personal-target-card");
      card.append(element("strong", position.asset_name || position.asset_id), element("small", `当前权重 ${format(position.current_weight_pct, "%")}`));
      const control = field("目标权重（%）", {value: state.context.request.target_weights[position.asset_id] ?? "", type: "number", min: 0, max: 100, change: value => {
        if (!state.context) return;
        requests.get("preview")?.abort();
        const context = state.context;
        state.context = {...context, request: {...context.request, target_weights: {...context.request.target_weights, [position.asset_id]: value}}};
        state.preview = null; renderPreview(); message("personal-rebalancing-message", "目标已修改，请重新计算两套方案。");
      }});
      control.querySelector("input").setAttribute("aria-label", `${position.asset_name || position.asset_id}的目标权重（%）`);
      card.append(control); grid.append(card);
    }
    root.append(grid, element("p", "目标权重合计须为 100%。持仓市值、价格、资产类型和交易单位使用已确认资料；前端不重新估价。测算不提交交易。", "personal-context-note"));
  }
  async function loadRebalancingInput() {
    clearContext();
    const input = await request("rebalancing-input", "/api/v1/advisor/investment-memory/rebalancing-input");
    if (!input.bundle || !input.target_weights || !Array.isArray(input.positions) || !input.positions.length) throw new Error("尚无可用于测算的当前持仓，请先导入并确认持仓。");
    state.rebalancingInput = input;
    state.context = {request: {bundle: input.bundle, target_weights: clone(input.target_weights), deadband_pct: "0.50", max_turnover_pct: "50", minimum_cash_pct: "0"}};
    state.preview = null; renderTargetEditor(); renderPreview();
    message("personal-rebalancing-message", input.profile_ready === false ? "已读取持仓，请先确认风险画像再计算。" : "已读取当前持仓。设置目标权重后即可比较基础方案和个人方案。");
  }
  function renderPreview() {
    const output = byId("personal-rebalancing-result"); if (!output) return; output.replaceChildren();
    if (!state.preview) { output.append(element("p", "同一持仓与目标权重，比较基础方案和个人方案的实际计算结果。", "empty-state")); updatePreviewControls(); return; }
    const data = state.preview;
    output.append(element("h4", "个性化约束的实际影响"), policyGrid(data.effective_parameters));
    const rows = [
      ["换手率", format(data.baseline?.metrics?.total_turnover_pct, "%"), format(data.personalized?.metrics?.total_turnover_pct, "%")],
      ["买入金额", format(data.baseline?.metrics?.total_buy_cny, "元"), format(data.personalized?.metrics?.total_buy_cny, "元")],
      ["卖出金额", format(data.baseline?.metrics?.total_sell_cny, "元"), format(data.personalized?.metrics?.total_sell_cny, "元")],
      ["预计费用", format(data.baseline?.metrics?.net_turnover_cost, "元"), format(data.personalized?.metrics?.net_turnover_cost, "元")],
      ["调整后现金", format(data.baseline?.metrics?.cash_after_cny, "元"), format(data.personalized?.metrics?.cash_after_cny, "元")],
      ["审查状态", statusName(data.baseline?.status), statusName(data.personalized?.status)],
    ]; output.append(table(["计算项目", "基础方案", "个人方案"], rows));
    const actions = new Map((data.baseline?.actions || []).map(item => [item.asset_id, item]));
    output.append(element("p", "个人方案按本次换手预算分步接近原目标；调整幅度受限时，本次目标可能尚未到达。后续调整仍需重新测算。", "personal-context-note"));
    const actionRows = (data.personalized?.actions || []).map(item => {
      const baseline = actions.get(item.asset_id);
      const targets = `${format(data.source_target_weights?.[item.asset_id] || "0", "%")} → ${format(data.effective_target_weights?.[item.asset_id] || "0", "%")}`;
      return [item.asset_name || item.asset_id, targets, actionSummary(baseline), actionSummary(item), String(item.rationale || "").replaceAll("死区阈值", "微调忽略范围").replaceAll("CNY", "元")];
    });
    if (actionRows.length) output.append(table(["资产", "原目标 → 本次个人目标", "基础调整", "个人调整", "个人方案说明"], actionRows));
    const differences = element("ul", null, "personal-basis"); for (const text of data.differences || []) differences.append(element("li", text)); output.append(differences);
    for (const issue of data.personalized?.issues || []) output.append(element("p", issue, "personal-notice"));
    output.append(element("p", "以上为服务端按当前输入计算的建议方案。风险约束优先，系统不自动提交交易。", "personal-context-note"), record("政策版本与两套计算记录", data)); updatePreviewControls();
  }
  function initializePreview() {
    const root = byId("personal-rebalancing-workspace"); if (!root) return; root.className = "personal-workbench";
    const panel = section("调仓偏好对比", "长期偏好参与实际调仓测算，查看换手、现金和调整清单如何变化。");
    panel.append(notice("personal-rebalancing-message"), Object.assign(element("p", null, "personal-context-note"), {id: "personal-rebalancing-context"}));
    const controls = element("div", null, "personal-actions");
    controls.append(button("读取当前持仓并设置目标", event => busy(event.currentTarget, "personal-rebalancing-message", loadRebalancingInput), {id: "personal-rebalancing-input"}));
    controls.append(button("对比基础与个人方案", event => busy(event.currentTarget, "personal-rebalancing-message", async () => {
      if (!state.context || state.memory?.policy_status !== "ACTIVE") throw new Error("请准备当前调仓输入，并确认长期偏好。");
      if (state.rebalancingInput?.profile_ready === false) throw new Error("请先确认风险画像，再重新读取持仓。");
      const context = state.context; const policyRevision = state.memory.policy.revision;
      const original = context.request; const body = {expected_policy_revision: policyRevision};
      if (Object.values(original.target_weights).some(value => value === "" || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 100)) throw new Error("每项目标权重需要填写 0 至 100 之间的百分比，合计由服务端核验。");
      for (const key of ["target_weights", "deadband_pct", "max_turnover_pct", "minimum_cash_pct", "bundle"]) if (original[key] != null) body[key] = original[key];
      const preview = await request("preview", "/api/v1/advisor/investment-memory/rebalancing-preview", {method: "POST", body});
      if (state.context !== context || state.memory?.policy?.revision !== policyRevision || state.memory?.policy_status !== "ACTIVE") return;
      state.preview = preview; renderPreview(); message("personal-rebalancing-message", "两套方案已按相同持仓与目标计算。");
    }).finally(updatePreviewControls), {id: "personal-rebalancing-preview", write: true, primary: true}));
    const link = element("a", "管理长期投资偏好", "copilot-action-btn secondary"); link.href = "#trading-style"; controls.append(link);
    panel.append(controls, Object.assign(element("div", null, "personal-block"), {id: "personal-rebalancing-targets", hidden: true}), Object.assign(element("div"), {id: "personal-rebalancing-result"})); root.append(panel); renderPreview();
  }
  function clearContext() { requests.get("preview")?.abort(); requests.get("rebalancing-input")?.abort(); state.context = null; state.rebalancingInput = null; state.preview = null; renderTargetEditor(); renderPreview(); message("personal-rebalancing-message", ""); }
  function resetAccount() {
    state.epoch++; state.owner = owner(); stopPolling(); requests.forEach(controller => controller.abort()); requests.clear();
    state.catalog = null; state.systems = []; state.system = null; state.draft = null; state.run = null; state.memory = null; state.context = null; state.rebalancingInput = null; state.preview = null;
    for (const id of ["personal-system-list", "personal-system-templates", "personal-data-agents", "personal-indicators", "personal-observers", "personal-system-result"]) byId(id)?.replaceChildren();
    if (byId("personal-system-name")) byId("personal-system-name").value = "";
    if (byId("personal-system-description")) byId("personal-system-description").value = "";
    if (byId("personal-system-version")) byId("personal-system-version").textContent = "尚未载入";
    for (const key of Object.keys(PARAMETER_NAMES)) if (byId(`investment-memory-${key}`)) byId(`investment-memory-${key}`).value = "";
    for (const id of ["personal-system-message", "investment-memory-message", "personal-rebalancing-message"]) message(id, "");
    renderMemory(); renderTargetEditor(); renderPreview(); updateRunControls();
  }
  async function activate() {
    if (state.owner !== owner()) resetAccount();
    try {
      if (location.hash === "#skill-store" && byId("personal-system-workspace")) { if (!state.catalog) await loadSystems(); schedulePolling(); }
      else stopPolling();
      if (["#trading-style", "#portfolio-style", "#portfolio-rebalancing"].includes(location.hash) && byId("investment-memory-workspace")) await loadMemory();
    } catch (error) { if (error.name !== "AbortError") message(location.hash === "#skill-store" ? "personal-system-message" : "investment-memory-message", error.message, true); }
  }
  initializeSystems(); initializeMemory(); initializePreview();
  document.addEventListener("prism:rebalancing-context", event => {
    const requestData = event.detail?.request;
    if (!requestData?.target_weights || !requestData.bundle || (requestData.owner_id && requestData.owner_id !== owner())) return;
    requests.get("preview")?.abort(); requests.get("rebalancing-input")?.abort();
    state.context = clone(event.detail); state.rebalancingInput = null; state.preview = null; renderTargetEditor(); renderPreview();
    if (!state.memory) loadMemory().catch(error => { if (error.name !== "AbortError") message("personal-rebalancing-message", error.message, true); });
  });
  document.addEventListener("prism:context-invalidated", clearContext);
  document.addEventListener("prism:personal-system-saved", () => { state.catalog = null; loadSystems().catch(error => { if (error.name !== "AbortError") message("personal-system-message", error.message, true); }); });
  document.addEventListener("prism:owner-change", () => { resetAccount(); activate(); });
  byId("owner-id")?.addEventListener("input", resetAccount);
  byId("owner-id")?.addEventListener("change", () => { resetAccount(); activate(); });
  byId("load-events")?.addEventListener("click", () => { if (state.owner !== owner()) resetAccount(); clearContext(); activate(); });
  window.addEventListener("hashchange", activate);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopPolling(); else activate(); });
  window.addEventListener("pagehide", () => { stopPolling(); requests.forEach(controller => controller.abort()); requests.clear(); });
  activate();
})();
