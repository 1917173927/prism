/* Owner-scoped library, research jobs and deterministic paper-algorithm views. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const owner = () => byId("owner-id")?.value.trim() || "demo-owner";
  const readOnly = () => window.PRISM_PAGES_SNAPSHOT === true;
  let accountEpoch = 0;
  let viewOwner = owner();
  let administrator = false;
  const el = (tag, text, className = "") => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  };
  function button(text, callback, write = false) {
    const result = el("button", text, "copilot-action-btn secondary");
    result.type = "button";
    result.disabled = write && readOnly();
    if (write) result.dataset.write = "true";
    result.addEventListener("click", callback);
    return result;
  }
  function field(id, label, {tag = "input", type = "text", value = "", options = null} = {}) {
    const wrapper = el("label", null, "research-form-field");
    wrapper.append(el("span", label));
    const input = el(tag); input.id = id;
    if (tag === "input") input.type = type;
    if (options) for (const [key, text] of Object.entries(options)) { const option = el("option", text); option.value = key; input.append(option); }
    if (tag === "textarea") input.rows = 6;
    if (value) input.value = value;
    wrapper.append(input);
    return wrapper;
  }
  function message(id, text, failure = false) {
    const output = byId(id);
    if (!output) return;
    output.textContent = text;
    output.className = failure ? "notice error" : "notice";
    output.hidden = !text;
  }
  function notice(id) { const result = el("p", null, "notice"); result.id = id; result.hidden = true; result.setAttribute("role", "status"); result.setAttribute("aria-live", "polite"); return result; }
  function section(title) { const result = el("section", null, "surface research-tool-section"); result.append(el("h3", title)); return result; }
  function table(headers, rows) {
    const wrapper = el("div", null, "table-wrap research-table-wrap");
    const result = el("table"); const head = el("thead"); const heading = el("tr");
    headers.forEach(text => heading.append(el("th", text))); head.append(heading); result.append(head);
    const body = el("tbody");
    rows.forEach(values => { const row = el("tr"); values.forEach(value => { const cell = el("td"); if (value instanceof Node) cell.append(value); else cell.textContent = value == null ? "—" : String(value); row.append(cell); }); body.append(row); });
    result.append(body); wrapper.append(result); return wrapper;
  }
  async function request(path, {method = "GET", body = null, signal} = {}) {
    if (readOnly() && method !== "GET") throw new Error("只读页面快照不支持写入、提交或计算。");
    const requestOwner = owner(), epoch = accountEpoch;
    const form = body instanceof FormData;
    const response = await fetch(path, {method, signal, headers: {"X-Owner-ID": requestOwner, ...(body && !form ? {"Content-Type": "application/json"} : {})}, ...(body ? {body: form ? body : JSON.stringify(body)} : {})});
    const data = await response.json().catch(() => ({}));
    if (requestOwner !== owner() || epoch !== accountEpoch) throw new Error("账户已切换，本次结果已失效。");
    if (!response.ok) {
      const descriptions = {401: "账户身份失效，请重新登录。", 403: "当前账户没有该操作权限。", 404: "记录不可用，可能已删除或不属于当前账户。", 409: "版本已变化，请刷新记录后重试。", 422: "输入未通过校验，请检查字段、时点及数据格式。", 429: "研究容量已满，请稍后重试。", 503: "服务或资料完整性暂不可用。"};
      const error = new Error(data.detail === "RESEARCH_AS_OF_FUTURE" ? "历史截止时点不能晚于服务器当前时间。" : descriptions[response.status] || "请求未完成，请稍后重试。"); error.status = response.status; throw error;
    }
    return data;
  }
  async function busy(control, statusId, callback) {
    if (control.disabled) return;
    control.disabled = true;
    message(statusId, "正在处理…");
    try { await callback(); }
    catch (error) { message(statusId, error.message, true); }
    finally { control.disabled = control.dataset.write === "true" && readOnly(); }
  }
  function parseJSON(id) {
    try { const value = JSON.parse(byId(id).value); if (!value || Array.isArray(value) || typeof value !== "object") throw new Error(); return value; }
    catch { throw new Error("请输入有效的 JSON 对象。"); }
  }
  function safeLink(url, text) {
    try { const parsed = new URL(url); if (!["https:", "http:"].includes(parsed.protocol) || parsed.username || parsed.password) return el("span", "来源地址未通过校验"); }
    catch { return el("span", "未提供来源链接"); }
    const link = el("a", text); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; return link;
  }

  const knowledgePrefix = "/api/v1/research/knowledge";
  let knowledgeSequence = 0;
  let knowledgeDocuments = [];
  let knowledgeMatches = [];
  let knowledgeAsOf = null;
  async function showOriginal(documentId, match = null) {
    const result = await request(`${knowledgePrefix}/documents/${encodeURIComponent(documentId)}`);
    const original = result.original;
    const output = byId("knowledge-original"); output.replaceChildren();
    output.append(el("h3", original.title), el("p", `${original.source} · 公告 ${original.published_at} · 修订 ${result.revision} · ${result.content_hash}`, "research-data-meta"));
    if (original.source_url) output.append(safeLink(original.source_url, "打开原始来源"));
    if (match) output.append(el("p", `引用位置：${match.page == null ? "页码未提供" : `第 ${match.page} 页`} · 第 ${match.paragraph} 段 · ${match.chunk_id}`, "research-data-meta"));
    const text = el("pre", original.text, "research-original-text"); output.append(text);
    output.hidden = false;
  }
  async function loadKnowledge() {
    const sequence = ++knowledgeSequence;
    const context = await request("/api/v1/auth/context");
    const data = await request(`${knowledgePrefix}/documents`);
    if (sequence !== knowledgeSequence) return;
    administrator = context.enabled === false || context.admin === true;
    byId("knowledge-visibility").querySelector('option[value="PUBLIC"]').disabled = !administrator || readOnly();
    byId("knowledge-rebuild").hidden = !administrator || readOnly();
    knowledgeDocuments = data.items || [];
    const output = byId("knowledge-documents"); output.replaceChildren();
    if (!knowledgeDocuments.length) output.append(el("p", "当前账户没有可查看的资料。", "empty-state"));
    else output.append(table(["资料", "标的／期间", "公告时间", "可见范围", "版本与索引"], knowledgeDocuments.map(item => {
      const title = button(item.title, event => busy(event.currentTarget, "knowledge-message", () => showOriginal(item.document_id)));
      return [title, [item.subject, item.period].filter(Boolean).join(" / ") || "未限定", item.published_at, item.visibility === "PUBLIC" ? "公开" : "个人", `${item.revision} · 向量 ${item.embedding_status} · ${item.chunk_count} 片段`];
    })));
    message("knowledge-message", readOnly() ? "页面快照只读，上传与检索操作不可用。" : "");
  }
  function renderKnowledgeMatches(data) {
    const output = byId("knowledge-matches"); output.replaceChildren();
    knowledgeMatches = data.matches || [];
    knowledgeAsOf = data.as_of;
    output.append(el("p", `${data.mode} · ${data.fulltext_backend} · 候选 ${data.candidate_count} · ${data.elapsed_ms} ms · ${data.quality_gate} · ${data.degraded_reason || "未报告降级"}`, "research-data-meta"));
    if (!knowledgeMatches.length) output.append(el("p", "没有匹配资料；缺少依据时不生成金融结论。", "empty-state"));
    for (const match of knowledgeMatches) {
      const card = el("article", null, "research-result-card");
      card.append(el("h4", match.title), el("span", "RETRIEVED_UNVERIFIED · 检索相关，事实未核验", "status-chip"), el("p", `${match.source} · 公告 ${match.published_at} · 修订 ${match.revision} · ${match.subject || "标的未限定"} · ${match.period || "期间未限定"}`, "research-data-meta"), el("blockquote", match.text));
      const actions = el("div", null, "research-action-row");
      actions.append(button("查看引用原文", event => busy(event.currentTarget, "knowledge-message", () => showOriginal(match.document_id, match))), button("核验原文引用", event => busy(event.currentTarget, "knowledge-message", async () => {
        const checked = await request(`${knowledgePrefix}/citations/check`, {method: "POST", body: {citations: [{document_id: match.document_id, chunk_id: match.chunk_id, revision: match.revision, content_hash: match.content_hash, quote: match.text}], as_of: knowledgeAsOf}});
        message("knowledge-message", checked.status === "PASS" ? "PASS · 引用与该版本原文完全对应；金融事实仍需独立核验。" : `UNVERIFIED · ${checked.results?.[0]?.reason || "引用未获支持"}`, checked.status !== "PASS");
      }), true));
      if (match.source_url) actions.append(safeLink(match.source_url, "原始来源"));
      card.append(actions); output.append(card);
    }
  }
  function initializeKnowledge() {
    const root = byId("knowledge-workspace"); if (!root) return;
    root.append(notice("knowledge-message"));
    const intake = section("上传或登记原始资料");
    intake.append(el("p", "支持 UTF-8 TXT、Markdown 与可提取文本的 PDF，文件不超过 8 MiB；扫描 PDF 需先识别文字。来源及公告时点为必填项。"));
    const form = el("div", null, "research-form-grid");
    form.append(field("knowledge-title", "资料标题"), field("knowledge-source", "来源名称"), field("knowledge-source-url", "原文链接（可选）", {type: "url"}), field("knowledge-published", "公告时点", {type: "datetime-local"}), field("knowledge-subject", "标的（可选）"), field("knowledge-period", "报告期（可选）"), field("knowledge-kind", "资料类型", {tag: "select", options: {ANNOUNCEMENT: "公告", FINANCIAL_REPORT: "财报", RESEARCH_REPORT: "研报", METHOD: "指标说明", PAPER: "论文", OTHER: "其他"}}), field("knowledge-visibility", "可见范围", {tag: "select", options: {PRIVATE: "个人资料", PUBLIC: "公开资料（管理员）"}}));
    intake.append(form);
    const file = field("knowledge-file", "文件（有文件时以文件为准）", {type: "file"}); file.querySelector("input").accept = ".txt,.md,.pdf"; intake.append(file, field("knowledge-text", "原文内容（无文件时填写）", {tag: "textarea"}));
    const upload = button("上传并建立索引", event => busy(event.currentTarget, "knowledge-message", async () => {
      const published = byId("knowledge-published").value;
      if (!published) throw new Error("请填写资料公告时点。");
      const metadata = {title: byId("knowledge-title").value.trim(), source: byId("knowledge-source").value.trim(), published_at: new Date(published).toISOString(), visibility: byId("knowledge-visibility").value, kind: byId("knowledge-kind").value};
      for (const [key, id] of Object.entries({source_url: "knowledge-source-url", subject: "knowledge-subject", period: "knowledge-period"})) if (byId(id).value.trim()) metadata[key] = byId(id).value.trim();
      if (!metadata.title || !metadata.source) throw new Error("请填写标题与来源名称。");
      const selected = byId("knowledge-file").files[0];
      let result;
      if (selected) {
        if (!selected.size || selected.size > 8 * 1024 * 1024) throw new Error("上传文件必须介于 1 字节和 8 MiB 之间。");
        const body = new FormData(); body.append("file", selected); body.append("metadata", JSON.stringify(metadata));
        result = await request(`${knowledgePrefix}/upload`, {method: "POST", body});
      } else result = await request(`${knowledgePrefix}/documents`, {method: "POST", body: {...metadata, text: byId("knowledge-text").value}});
      await loadKnowledge();
      message("knowledge-message", `资料已登记 · 修订 ${result.revision} · ${result.chunk_count} 片段 · 向量 ${result.embedding_status}；资料真实性尚未核验。`);
    }), true); upload.id = "knowledge-upload"; intake.append(upload); root.append(intake);
    const search = section("检索与原文引用");
    const filters = el("div", null, "research-form-grid"); filters.append(field("knowledge-query", "问题或关键词"), field("knowledge-search-subject", "标的过滤（可选）"), field("knowledge-search-period", "报告期过滤（可选）"), field("knowledge-as-of", "历史截止时点（可选）", {type: "datetime-local"})); search.append(filters);
    const searchButton = button("检索资料", event => busy(event.currentTarget, "knowledge-message", async () => {
      byId("knowledge-matches").replaceChildren(); byId("knowledge-original").hidden = true;
      const body = {query: byId("knowledge-query").value.trim(), limit: 10};
      if (!body.query) throw new Error("请输入检索关键词。");
      for (const [key, id] of Object.entries({subject: "knowledge-search-subject", period: "knowledge-search-period"})) if (byId(id).value.trim()) body[key] = byId(id).value.trim();
      if (byId("knowledge-as-of").value) body.as_of = new Date(byId("knowledge-as-of").value).toISOString();
      renderKnowledgeMatches(await request(`${knowledgePrefix}/search`, {method: "POST", body})); message("knowledge-message", "检索完成；相关资料仍须逐项核验。");
    }), true); searchButton.id = "knowledge-search"; search.append(searchButton); const matches = el("div"); matches.id = "knowledge-matches"; search.append(matches); root.append(search);
    const catalog = section("当前账户可见资料"); const actions = el("div", null, "research-action-row"); actions.append(button("刷新资料", event => busy(event.currentTarget, "knowledge-message", loadKnowledge)));
    const rebuild = button("重建向量索引", event => busy(event.currentTarget, "knowledge-message", async () => {
      const result = await request(`${knowledgePrefix}/indexes/rebuild`, {method: "POST"}); message("knowledge-message", result.status === "CALCULATED" ? `索引已更新，${result.indexed} 片段；召回质量需另行评测。` : "向量服务不可用；关键词检索仍可使用。", result.status !== "CALCULATED");
    }), true); rebuild.id = "knowledge-rebuild"; rebuild.hidden = true; actions.append(rebuild); catalog.append(actions); const documents = el("div"); documents.id = "knowledge-documents"; catalog.append(documents); root.append(catalog);
    const original = section("引用原文"); original.id = "knowledge-original"; original.hidden = true; root.append(original);
    byId("knowledge-visibility").querySelector('option[value="PUBLIC"]').disabled = true;
  }
  const RESEARCH_OPERATIONS = Object.freeze({MARKET_DATA: "行情", COMPANY_DATA: "财务", INDUSTRY_DATA: "行业", MACRO_DATA: "宏观", FUND_DATA: "基金", CONVERTIBLE_BOND_DATA: "可转债"});
  let researchDraft = [{node_id: "market-1", operation: "MARKET_DATA", subject: "600519", required_fields: ["price"], dependencies: []}];
  let currentRun = null;
  let currentRunOwner = null;
  let runPoll = null;
  let runSequence = 0;
  let templateAvailable = false;
  let researchSubmitting = false;
  let stockReportObserver = null;
  const terminalRun = run => !["QUEUED", "RUNNING"].includes(run?.status);
  function stopRunPolling() { if (runPoll) clearTimeout(runPoll); runPoll = null; }
  function researchTimePayload() {
    const value = byId("research-as-of").value;
    if (!value) return {};
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) throw new Error("历史截止时点无效。");
    return {as_of: date.toISOString()};
  }
  function importResearchTime(value) {
    if (value == null) { byId("research-as-of").value = ""; return; }
    if (typeof value !== "string" || !/(Z|[+-]\d{2}:\d{2})$/.test(value)) throw new Error("as_of 必须为带时区的 ISO 时点。");
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) throw new Error("as_of 时点无效。");
    byId("research-as-of").value = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }
  async function submitResearch(path, body) {
    if (researchSubmitting) throw new Error("研究提交正在处理，请等待返回。");
    researchSubmitting = true;
    const sequence = ++runSequence;
    stopRunPolling(); currentRun = null; currentRunOwner = null;
    byId("research-run-result").replaceChildren(); byId("research-run-id").value = ""; byId("research-cancel").disabled = true;
    const controls = [byId("research-submit"), byId("research-template-submit")];
    controls.forEach(control => { if (control) control.disabled = true; });
    try {
      const run = await request(path, {method: "POST", body});
      if (sequence !== runSequence) return;
      renderResearchRun(run); message("research-message", "任务已提交；排队状态不计为实际执行。"); scheduleRunPolling();
    } finally { researchSubmitting = false; controls.forEach(control => { if (control) control.disabled = readOnly() || (control.id === "research-template-submit" && !templateAvailable); }); }
  }
  async function loadResearchTemplate() {
    templateAvailable = false; byId("research-template-submit").disabled = true;
    if (readOnly()) { byId("research-template-info").textContent = "只读页面快照不执行 LIVE 模板。"; return; }
    const data = await request("/api/v1/research/templates");
    const template = data.items?.find(item => item.template_id === "live-equity-basic.v1" && item.data_mode === "LIVE");
    if (!template) { byId("research-template-info").textContent = "LIVE 股票模板暂不可用。"; return; }
    templateAvailable = true;
    byId("research-template-info").textContent = `${template.name} · ${template.template_id} · ${template.nodes.map(node => `${node.node_id}：${node.operation}（${node.required_fields.join("、")}）`).join("；")}`;
    byId("research-template-submit").disabled = readOnly() || researchSubmitting;
  }
  function renderResearchDraft() {
    const output = byId("research-node-editor"); output.replaceChildren();
    const rows = researchDraft.map((item, index) => {
      const editor = (key, value, list = false) => {
        const input = el("input"); input.value = list ? (value || []).join(", ") : value || "";
        input.setAttribute("aria-label", `节点 ${index + 1} ${key}`);
        input.addEventListener("input", () => { item[key] = list ? input.value.split(/[,，\n]/).map(value => value.trim()).filter(Boolean) : input.value.trim(); });
        return input;
      };
      const operation = el("select"); operation.setAttribute("aria-label", `节点 ${index + 1} operation`);
      for (const [key, name] of Object.entries(RESEARCH_OPERATIONS)) { const option = el("option", name); option.value = key; operation.append(option); }
      operation.value = item.operation; operation.addEventListener("change", () => { item.operation = operation.value; });
      const remove = button("移除", () => { researchDraft.splice(index, 1); renderResearchDraft(); }); remove.disabled = researchDraft.length <= 1;
      return [editor("node_id", item.node_id), operation, editor("subject", item.subject), editor("query", item.query), editor("required_fields", item.required_fields, true), editor("dependencies", item.dependencies, true), remove];
    });
    output.append(table(["节点标识", "能力", "标的", "查询语句（可选）", "必需字段", "前置节点", "操作"], rows));
    byId("research-draft-count").textContent = `${researchDraft.length} / 32 个节点`;
  }
  function renderResearchRun(run) {
    currentRun = run;
    currentRunOwner = owner();
    byId("research-run-id").value = run.run_id;
    const output = byId("research-run-result"); output.replaceChildren();
    output.append(el("h3", `任务 ${run.status}`), el("p", `LIVE · ${run.verification_status} · 任务 ${run.run_id} · 开始 ${run.created_at} · 完成 ${run.finished_at || "尚未完成"} · ${run.elapsed_ms == null ? "耗时尚未确定" : `${run.elapsed_ms} ms`}`, "research-data-meta"));
    output.append(el("p", "单源观察尚未独立核验；任务完成不等于金融事实验证通过，不构成交易指令。运行记录保存在当前服务进程，重启后不可恢复。", "research-data-meta"));
    if (run.as_of) output.append(el("p", `研究截止时点 ${run.as_of}；该时点之后的观察不能作为本次研究证据。`, "research-data-meta"));
    byId("research-cancel").disabled = terminalRun(run) || readOnly();
    for (const result of run.nodes || []) {
      const card = el("article", null, "research-result-card");
      card.append(el("h4", `${result.node_id} · ${result.status}`), el("p", `${result.provider || "提供方尚未返回"} · ${result.provider_ms == null ? "尚无节点耗时" : `${result.provider_ms} ms`} · ${result.verification_status || "NOT_VERIFIED"}`, "research-data-meta"));
      if (result.missing_fields?.length) card.append(el("p", `缺失字段：${result.missing_fields.join("、")}`, "notice"));
      if (result.error_codes?.length) card.append(el("p", `节点原因：${result.error_codes.join("、")}`, "notice error"));
      if (result.observations?.length) card.append(table(["字段／期间", "观察值／单位", "观察时点", "实际来源", "核验状态"], result.observations.map(item => [`${item.metric} / ${item.period || "未提供"}`, `${item.value} / ${item.unit || "单位未提供"}`, item.observed_at || "未提供", item.actual_source, item.verification_status])));
      else card.append(el("p", "当前没有可展示的观察值。", "empty-state"));
      const evidence = el("details"); evidence.append(el("summary", "证据与原始字段"), el("pre", JSON.stringify(result, null, 2), "research-original-text")); card.append(evidence); output.append(card);
    }
  }
  async function loadRuntime() {
    const status = await request("/api/v1/research/runtime");
    byId("research-runtime").textContent = `当前进程：实际执行 ${status.active} · 排队 ${status.waiting} · 峰值 ${status.peak_active} · 上限 ${status.global_limit}；Provider 活动 ${status.provider_active} · 模型活动 ${status.model_active}。计数范围 ${status.scope}，不表示已经完成 100 任务真实容量验收。`;
  }
  async function refreshResearchRun() {
    const runId = byId("research-run-id").value.trim(); if (!runId) throw new Error("请提交任务或填写任务标识。");
    const sequence = ++runSequence;
    const run = await request(`/api/v1/research/runs/${encodeURIComponent(runId)}`);
    if (sequence !== runSequence) return;
    renderResearchRun(run);
    await loadRuntime();
  }
  function scheduleRunPolling() {
    stopRunPolling();
    if (readOnly() || !currentRun || terminalRun(currentRun) || window.location.hash !== "#live-research" || document.hidden) return;
    runPoll = setTimeout(async () => {
      try { await refreshResearchRun(); scheduleRunPolling(); }
      catch (error) { message("research-message", error.message, true); stopRunPolling(); }
    }, 1500);
  }
  function initializeResearch() {
    const root = byId("live-research-workspace"); if (!root) return;
    root.append(notice("research-message"));
    const editor = section("节点与依赖编辑");
    editor.append(el("p", "每个节点填写标的、必需字段和前置节点标识，多个字段或依赖以逗号分隔。环路、重复标识及未知依赖由服务端拒绝。默认内容仅为输入示例。"));
    const controls = el("div", null, "research-action-row");
    controls.append(button("添加节点", () => {
      if (researchDraft.length >= 32) { message("research-message", "单次研究最多 32 个节点。", true); return; }
      let index = researchDraft.length + 1; while (researchDraft.some(item => item.node_id === `node-${index}`)) index++;
      researchDraft.push({node_id: `node-${index}`, operation: "MARKET_DATA", subject: "", required_fields: ["price"], dependencies: []}); renderResearchDraft();
    }), Object.assign(el("span", null, "status-chip"), {id: "research-draft-count"}), field("research-budget", "任务预算（秒）", {type: "number", value: "60"}), field("research-as-of", "历史截止时点（本地时间，可选）", {type: "datetime-local"}));
    controls.querySelector("input").min = "1"; controls.querySelector("input").max = "60"; editor.append(controls);
    editor.append(el("p", "截止时点留空表示当前研究。填写后由服务器拦截未来信息；实时观察晚于历史截止时点时应保留缺失或不可用状态。", "research-data-meta"));
    const nodes = el("div"); nodes.id = "research-node-editor"; editor.append(nodes);
    const importer = el("details"); importer.append(el("summary", "导入结构化研究 JSON"), field("research-json", "研究请求 JSON（nodes、budget_seconds、as_of 可选）", {tag: "textarea"}));
    const importButton = button("应用 JSON 到编辑表", () => {
      try {
        const draft = parseJSON("research-json");
        if (!Array.isArray(draft.nodes) || !draft.nodes.length || draft.nodes.length > 32 || draft.nodes.some(item => !item || typeof item !== "object" || !Array.isArray(item.required_fields) || (item.dependencies != null && !Array.isArray(item.dependencies)))) throw new Error("JSON 需要 1 至 32 个有效节点及字段数组。");
        importResearchTime(draft.as_of);
        researchDraft = draft.nodes.map(item => ({...item, dependencies: item.dependencies || []}));
        byId("research-budget").value = String(draft.budget_seconds ?? 60); renderResearchDraft(); message("research-message", "已载入编辑表，尚未提交。");
      } catch (error) { message("research-message", error.message, true); }
    }); importer.append(importButton); editor.append(importer);
    const submit = button("提交 LIVE 研究", event => busy(event.currentTarget, "research-message", async () => {
      const nodes = researchDraft.map(item => { const result = {...item}; if (!result.query) delete result.query; return result; });
      await submitResearch("/api/v1/research/runs", {nodes, budget_seconds: Number(byId("research-budget").value), ...researchTimePayload()});
    }), true); submit.id = "research-submit"; editor.append(submit); root.append(editor);
    const template = section("LIVE 股票基础模板");
    template.append(el("p", "按 A 股代码启动服务器提供的研究模板，仅复用已批准能力与字段，不包含行情或财务示例数值。与节点编辑共用上方任务预算和历史截止时点。"), field("research-template-subject", "A 股代码（可带 .SH／.SZ／.BJ）", {value: "600519"}));
    const templateInfo = el("p", "正在读取服务器模板。", "research-data-meta"); templateInfo.id = "research-template-info"; templateInfo.setAttribute("aria-live", "polite"); template.append(templateInfo);
    const templateSubmit = button("按目标启动 LIVE 股票模板", event => busy(event.currentTarget, "research-message", async () => {
      if (!templateAvailable) throw new Error("LIVE 股票模板暂不可用。");
      const subject = byId("research-template-subject").value.trim(); if (!subject) throw new Error("请输入研究目标。");
      await submitResearch("/api/v1/research/runs/from-template", {subject, template_id: "live-equity-basic.v1", budget_seconds: Number(byId("research-budget").value), ...researchTimePayload()});
    }), true); templateSubmit.id = "research-template-submit"; templateSubmit.disabled = true; template.append(templateSubmit); root.append(template);
    const runtime = section("运行状态"); const state = el("p"); state.id = "research-runtime"; runtime.append(state);
    const actions = el("div", null, "research-action-row"); actions.append(field("research-run-id", "任务标识"));
    const refresh = button("刷新任务", event => busy(event.currentTarget, "research-message", async () => { await refreshResearchRun(); scheduleRunPolling(); message("research-message", "任务状态已更新。"); })); refresh.id = "research-refresh";
    const cancel = button("取消任务", event => busy(event.currentTarget, "research-message", async () => {
      if (!currentRun || currentRunOwner !== owner()) throw new Error("请先读取当前账户任务。");
      stopRunPolling(); runSequence++;
      const run = await request(`/api/v1/research/runs/${encodeURIComponent(currentRun.run_id)}`, {method: "DELETE"}); renderResearchRun(run); await loadRuntime(); message("research-message", "任务取消结果已返回。");
    }), true); cancel.id = "research-cancel"; cancel.disabled = true; actions.append(refresh, cancel, button("刷新运行计数", event => busy(event.currentTarget, "research-message", loadRuntime))); runtime.append(actions); root.append(runtime);
    const result = section("节点与观察证据"); result.id = "research-run-result"; root.append(result);
    const stockReport = section("当前对话的个股详细报告"); stockReport.id = "research-stock-report"; stockReport.hidden = true;
    const reportContent = el("div"); reportContent.id = "research-stock-report-content"; stockReport.append(reportContent); root.append(stockReport); renderResearchDraft();
  }
  const ALGORITHMS = Object.freeze({regime: "两状态波动模型", covariance: "常相关协方差收缩", "five-factors": "Fama–French 五因子"});
  let algorithmResult = null;
  let algorithmKind = "regime";
  let algorithmChart = null;
  let algorithmResize = null;
  let algorithmSequence = 0;
  function destroyAlgorithmChart() { algorithmResize?.disconnect(); algorithmResize = null; algorithmChart?.remove(); algorithmChart = null; }
  function renderAlgorithmChart() {
    const container = byId("algorithm-chart"); if (!container) return;
    destroyAlgorithmChart(); container.replaceChildren();
    const data = algorithmResult;
    if (!data || data.status !== "CALCULATED" || algorithmKind === "covariance") return;
    const rows = data.series || [];
    if (!rows.length) { container.append(el("p", "该结果没有可展示的序列。", "empty-state")); return; }
    if (!window.LightweightCharts) { container.append(el("p", "图表组件未能加载。")); return; }
    const colors = ["#d97706", "#2563eb", "#16a34a", "#8b5cf6", "#dc2626"];
    const css = getComputedStyle(document.body);
    container.style.height = "320px";
    algorithmChart = window.LightweightCharts.createChart(container, {width: container.clientWidth, height: 320, layout: {background: {type: "solid", color: css.getPropertyValue("--surface").trim()}, textColor: css.getPropertyValue("--text-secondary").trim()}, timeScale: {timeVisible: false}, grid: {vertLines: {color: css.getPropertyValue("--border-subtle").trim()}, horzLines: {color: css.getPropertyValue("--border-subtle").trim()}}});
    const chart = algorithmChart;
    const fields = algorithmKind === "regime" ? ["low_variance", "high_variance"] : ["MKT_RF", "SMB", "HML", "RMW", "CMA"];
    try {
      fields.forEach((key, index) => {
        const series = chart.addSeries(window.LightweightCharts.LineSeries, {title: key, color: colors[index], lineWidth: 2, priceFormat: {type: "price", precision: 6, minMove: .000001}});
        series.setData(rows.map(row => ({time: algorithmKind === "five-factors" ? `${row.time}-01` : row.time, value: row[key]})));
      });
      chart.timeScale().fitContent();
      algorithmResize = new ResizeObserver(entries => { const width = Math.floor(entries[0]?.contentRect.width || 0); if (width > 0 && algorithmChart === chart) { chart.applyOptions({width}); chart.timeScale().fitContent(); } }); algorithmResize.observe(container);
    } catch {
      destroyAlgorithmChart(); container.replaceChildren(el("p", "算法序列未通过图表格式校验，请查看原始结果。", "notice error"));
    }
  }
  function renderMatrix(data, correlation = false) {
    const matrix = correlation ? data.correlation : data.covariance;
    const output = byId("algorithm-matrix"); output.replaceChildren();
    output.append(el("h4", correlation ? "相关矩阵（后端计算值）" : "收缩协方差矩阵（后端计算值）"));
    output.append(table(["资产", ...data.assets], matrix.map((row, index) => [data.assets[index], ...row.map(value => {
      const cell = el("span", Number(value).toPrecision(6), value >= 0 ? "research-matrix-positive" : "research-matrix-negative"); return cell;
    })])));
  }
  function renderAlgorithmResult(data) {
    algorithmResult = data;
    const output = byId("algorithm-output"); output.replaceChildren();
    output.append(el("h3", `${ALGORITHMS[algorithmKind]} · ${data.status}`), el("p", `${data.source} · 时点 ${data.as_of} · ${data.method_version} · 输入快照 ${data.input_snapshot_id}`, "research-data-meta"));
    if (data.status !== "CALCULATED") {
      const descriptions = {INSUFFICIENT_RETURNS: "收益样本不足", DEGENERATE_TRAINING_RETURNS: "训练收益退化为常数", RESEARCH_DEPENDENCY_UNAVAILABLE: "研究算法依赖不可用", MODEL_NOT_CONVERGED: "模型未收敛", INSUFFICIENT_ASSETS: "资产数不足", INSUFFICIENT_ALIGNED_RETURNS: "共同日期的收益样本不足", ZERO_VARIANCE_ASSET: "存在零方差资产", FUNDAMENTAL_FIELDS_MISSING: "缺少五因子财务字段", INSUFFICIENT_FORMATION_UNIVERSE: "分组形成集合不足", EMPTY_2X3_PORTFOLIO: "存在空的 2×3 分组", RISK_FREE_RETURN_MISSING: "缺少无风险收益", FINANCIAL_POINT_IN_TIME_INVALID: "财报公告时点不符合形成期约束", MONTHS_MUST_BE_NONEMPTY_SORTED_UNIQUE: "月度记录须非空、排序且唯一", FORMATION_MEMBER_RETURN_MISSING: "形成集合成员缺少月度收益"};
      output.append(el("p", `不可计算：${descriptions[data.reason] || "输入或数值条件不满足"}（${data.reason || "原因未提供"}）${data.missing_fields?.length ? `；缺失 ${data.missing_fields.join("、")}` : ""}`, "notice error"));
    } else {
      output.append(el("p", data.interpretation || "仅对输入集合计算，未证明原始数据真实或全市场覆盖。"));
      if (algorithmKind === "regime") output.append(el("p", `训练 ${data.training_start} 至 ${data.training_end} · 全部样本 ${data.sample_count} · 样本外 ${data.out_of_sample_count} · 状态为低／高条件方差概率（0–1），不直接代表牛熊。`, "research-data-meta"));
      else if (algorithmKind === "five-factors") output.append(el("p", `集合 ${data.universe_id} · 范围 ${data.scope} · 全集合声明 ${data.universe_complete ? "由输入提供方声明完整" : "未声明完整"} · 收益单位为小数比例；月度图以月首日期定位。`, "research-data-meta"));
      else {
        output.append(el("p", `共同样本 ${data.sample_count} · ${data.input_start} 至 ${data.input_end} · 收缩强度 ${data.shrinkage} · 目标 ${data.target} · 单位 ${data.covariance_unit}`, "research-data-meta"));
        const actions = el("div", null, "research-action-row"); actions.append(button("协方差矩阵", () => renderMatrix(data)), button("相关矩阵", () => renderMatrix(data, true))); output.append(actions);
        const matrix = el("div"); matrix.id = "algorithm-matrix"; output.append(matrix); renderMatrix(data);
      }
    }
    const graph = el("div"); graph.id = "algorithm-chart"; graph.setAttribute("aria-label", "算法结果时间序列"); output.append(graph); renderAlgorithmChart();
    const raw = el("details"); raw.append(el("summary", "完整计算结果与方法参数"), el("pre", JSON.stringify(data, null, 2), "research-original-text")); output.append(raw);
  }
  function algorithmTemplate(kind) {
    const common = {source: "填写实际数据来源", as_of: new Date().toISOString()};
    if (kind === "regime") return {...common, training_size: 252, returns: []};
    if (kind === "covariance") return {...common, series: {"资产标识A": [], "资产标识B": []}};
    return {...common, monetary_unit: "CNY", universe_id: "填写形成集合标识", universe_complete: false, fundamentals: [], months: []};
  }
  function initializeAlgorithms() {
    const root = byId("algorithm-workspace"); if (!root) return;
    root.append(notice("algorithm-message"));
    const input = section("结构化输入");
    input.append(field("algorithm-kind", "算法", {tag: "select", options: ALGORITHMS}), el("p", "收益采用小数比例，例如 1% 写为 0.01。输入来源与时点须真实可复核；字段缺失时保留不可计算状态。此处不自动生成行情或财务数据。"));
    input.append(field("algorithm-file", "导入 JSON 文件（可选）", {type: "file"}));
    const payload = field("algorithm-json", "算法请求 JSON", {tag: "textarea"}); payload.querySelector("textarea").rows = 13; input.append(payload);
    const controls = el("div", null, "research-action-row");
    controls.append(button("载入空输入结构", () => { byId("algorithm-json").value = JSON.stringify(algorithmTemplate(byId("algorithm-kind").value), null, 2); message("algorithm-message", "已载入字段结构；请填写真实数据，尚未计算。"); }));
    const compute = button("执行确定性计算", event => busy(event.currentTarget, "algorithm-message", async () => {
      destroyAlgorithmChart(); byId("algorithm-output").replaceChildren(); algorithmResult = null;
      const sequence = ++algorithmSequence;
      const kind = byId("algorithm-kind").value;
      const result = await request(`/api/v1/research/algorithms/${kind}`, {method: "POST", body: parseJSON("algorithm-json")});
      if (sequence !== algorithmSequence || byId("algorithm-kind").value !== kind) return;
      algorithmKind = kind; renderAlgorithmResult(result); message("algorithm-message", result.status === "CALCULATED" ? "CALCULATED · 结果来自确定性算法；来源真实性需另行核验。" : "UNAVAILABLE · 未满足算法输入或拟合条件。", result.status !== "CALCULATED");
    }), true); compute.id = "algorithm-compute"; controls.append(compute); input.append(controls);
    const contract = el("details"); contract.append(el("summary", "输入字段与数据缺口"), table(["算法", "输入结构", "最低条件", "时点与覆盖"], [
      ["两状态模型", "returns: [{time,value}]；training_size", "训练窗口至少 252；收益日期排序唯一", "as_of 之后的收益拒绝；只展示训练窗口末端起的过滤概率"],
      ["协方差收缩", "series: {资产标识: [{time,value}]} ", "至少 2 资产、60 个共同日期；非零方差", "严格按日期交集对齐；不填补缺失收益"],
      ["五因子年度", "monetary_unit: CNY；fundamentals：security_id、formation_year、fiscal_year、published_at；两期市值、账面权益、收入、成本、费用、利息、两期资产", "全部财务字段及统一人民币单位必需；2×3 分组不能为空", "前一年财报在形成年 6 月末前已公告"],
      ["五因子月度", "months: [{month,risk_free_return,securities:[{security_id,total_return,beginning_market_cap}]}]；universe_id", "形成集合成员有月收益、期初市值及无风险收益", "7 月重组；输入集合不能冒充全市场或官方美国因子"],
    ])); input.append(contract); root.append(input);
    const output = section("计算结果"); output.id = "algorithm-output"; root.append(output);
    byId("algorithm-kind").addEventListener("change", () => { algorithmSequence++; algorithmResult = null; destroyAlgorithmChart(); output.replaceChildren(); message("algorithm-message", "算法已切换；请确认输入结构后重新计算。"); });
    byId("algorithm-file").accept = ".json,application/json";
    byId("algorithm-file").addEventListener("change", async event => {
      const file = event.target.files[0]; if (!file) return;
      try { if (file.size > 8 * 1024 * 1024) throw new Error("JSON 文件不得超过 8 MiB。"); const text = await file.text(); JSON.parse(text); byId("algorithm-json").value = text; message("algorithm-message", "JSON 已载入；尚未提交计算。"); }
      catch (error) { message("algorithm-message", error.message || "JSON 文件格式无效。", true); }
    });
  }
  initializeKnowledge();
  initializeResearch();
  initializeAlgorithms();
  document.addEventListener("prism:research-open", event => {
    const data = event.detail;
    if (!data || !RESEARCH_OPERATIONS[data.operation] || typeof data.subject !== "string") return;
    researchDraft = [{node_id: "linked-1", operation: data.operation, subject: data.subject, required_fields: data.required_fields || ["price"], dependencies: [], ...(data.query ? {query: data.query} : {})}];
    byId("research-template-subject").value = data.subject;
    renderResearchDraft(); message("research-message", `已载入 ${data.subject} 的研究输入，尚未提交。行业指数不代表成分股集合。`);
  });
  document.addEventListener("prism:stock-report-open", event => {
    const content = event.detail?.content;
    if (!(content instanceof Element)) return;
    stockReportObserver?.disconnect();
    byId("research-stock-report").querySelector("h3").textContent = `${event.detail.subject || "当前对话"} · 个股详细报告`;
    const update = () => { byId("research-stock-report-content").replaceChildren(content.cloneNode(true)); byId("research-stock-report").hidden = false; };
    update(); stockReportObserver = new MutationObserver(update); stockReportObserver.observe(content, {childList: true, subtree: true, characterData: true});
  });

  function activate() {
    if (viewOwner !== owner()) resetAccountResults();
    stopRunPolling();
    if (window.location.hash === "#research-algorithms") renderAlgorithmChart(); else destroyAlgorithmChart();
    if (window.location.hash === "#research-knowledge") loadKnowledge().catch(error => message("knowledge-message", error.message, true));
    if (window.location.hash === "#live-research") {
      if (currentRunOwner && currentRunOwner !== owner()) { currentRun = null; currentRunOwner = null; byId("research-run-result").replaceChildren(); byId("research-run-id").value = ""; byId("research-cancel").disabled = true; }
      loadRuntime().catch(error => message("research-message", error.message, true));
      loadResearchTemplate().catch(error => { byId("research-template-info").textContent = error.message; });
      if (currentRun) refreshResearchRun().then(scheduleRunPolling).catch(error => message("research-message", error.message, true));
    }
  }
  window.addEventListener("hashchange", activate);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopRunPolling(); else if (window.location.hash === "#live-research") activate(); });
  function resetAccountResults() {
    viewOwner = owner();
    accountEpoch++; knowledgeSequence++; runSequence++; algorithmSequence++;
    templateAvailable = false; byId("research-template-submit").disabled = true;
    stopRunPolling(); currentRun = null; currentRunOwner = null; knowledgeDocuments = []; knowledgeMatches = []; knowledgeAsOf = null; algorithmResult = null; destroyAlgorithmChart();
    stockReportObserver?.disconnect(); stockReportObserver = null; byId("research-stock-report-content").replaceChildren(); byId("research-stock-report").hidden = true;
    for (const id of ["knowledge-documents", "knowledge-matches", "knowledge-original", "research-run-result", "algorithm-output"]) byId(id)?.replaceChildren();
    byId("research-run-id").value = ""; byId("research-cancel").disabled = true;
  }
  byId("load-events")?.addEventListener("click", resetAccountResults);
  let dark = document.body.classList.contains("prism-theme-dark");
  const themeObserver = new MutationObserver(() => { const next = document.body.classList.contains("prism-theme-dark"); if (next !== dark) { dark = next; renderAlgorithmChart(); } }); themeObserver.observe(document.body, {attributes: true, attributeFilter: ["class"]});
  window.addEventListener("pagehide", () => { stopRunPolling(); destroyAlgorithmChart(); stockReportObserver?.disconnect(); themeObserver.disconnect(); });
  activate();
})();
