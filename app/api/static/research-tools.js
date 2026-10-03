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
  const STATUS_TEXT = Object.freeze({CALCULATED: "已计算", PASS: "核对通过", UNAVAILABLE: "暂不可用", FAILED: "未完成", QUEUED: "排队中", RUNNING: "进行中", COMPLETED: "已完成", CANCELED: "已取消", CANCELLED: "已取消", PARTIAL: "资料不完整", SUCCESS: "资料已返回", EMPTY: "未找到资料", NOT_VERIFIED: "尚未核验", UNVERIFIED: "尚未核验", OBSERVED_UNVERIFIED: "观察值待核验", RETRIEVED_UNVERIFIED: "资料待核验", SINGLE_SOURCE_UNVERIFIED: "单一来源，尚未独立核验", NO_VERIFIABLE_OBSERVATION: "暂无可核验数据"});
  const customerStatus = value => STATUS_TEXT[value] || "状态待确认";
  const METRIC_TEXT = Object.freeze({price: "最新价", revenue: "营业收入", net_profit: "净利润", pe: "市盈率", nav: "单位净值", value: "指标数值", source: "数据来源", subject_identity: "标的身份", symbol: "证券代码", observed_at: "数据时点", market_cap: "总市值", volume: "成交量", amount: "成交额", turnover_rate: "换手率"});
  const METRIC_SUFFIX = Object.freeze({unit: "计量单位", observed_at: "数据时点", period: "报告期", eligible_observation: "截止时点前的数据", eligible_period: "截止时点前的报告期", period_unrecognized: "可识别的报告期"});
  function customerMetric(value) {
    const [metric, suffix] = String(value || "").split(".");
    const name = METRIC_TEXT[metric] || (metric === "WENCAI_SKILLHUB_API_KEY" ? "数据服务连接信息（由管理员配置）" : /\p{Script=Han}/u.test(metric) ? metric : "数据项说明见原始记录");
    return suffix ? `${name}的${METRIC_SUFFIX[suffix] || "补充信息"}` : name;
  }
  const REASON_TEXT = Object.freeze({TIMEOUT: "数据请求超时", RATE_LIMITED: "数据请求过于频繁", QUOTA_EXHAUSTED: "数据服务额度不足", AUTH_FAILED: "数据服务认证失败", PERMISSION_DENIED: "没有数据访问权限", TRANSPORT_ERROR: "数据连接失败", INVALID_RESPONSE: "返回的数据格式无效", UNSUPPORTED_OPERATION: "暂不支持该类研究", CANCELLED: "操作已取消", INTERNAL_ERROR: "服务处理失败", RESEARCH_CAPACITY: "研究容量已满", DEPENDENCY_INCOMPLETE: "前置研究尚未完成", FUTURE_OBSERVATION: "数据时点晚于本次研究截止时间", FUTURE_REPORTING_PERIOD: "报告期晚于本次研究截止时间", DOCUMENT_UNAVAILABLE: "资料已删除或不可访问", DOCUMENT_VERSION_CHANGED: "资料版本已更新，请重新检索", FUTURE_PUBLICATION: "资料发布晚于指定截止时间", CHUNK_UNAVAILABLE: "引用片段已失效", CHUNK_INTEGRITY_FAILED: "引用片段未通过完整性检查", QUOTE_NOT_SUPPORTED: "引用文字与原文不符"});
  const customerReason = value => REASON_TEXT[value] || "尚未满足数据或核验条件，具体原因可查看原始记录";
  const customerTime = value => {
    if (!value) return "尚未提供";
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", {hour12: false}) : "时间格式待核对";
  };
  const customerUnit = value => ({CNY: "元", RMB: "元", USD: "美元", HKD: "港元", PCT: "%", percent: "%", ratio: "比例", shares: "股", "CNY/share": "元/股", points: "点"}[value] || (/\p{Script=Han}|[%‰]/u.test(value || "") ? value : value ? "单位见原始记录" : "单位未提供"));
  const customerSource = value => ({wencai_skillhub_provider: "同花顺问财数据服务", fixture_wencai_provider: "演示数据服务", static_market_provider: "静态样例数据", "Fuyao structured financial data API": "扶摇金融数据服务", "Fuyao financial statements and indicators": "扶摇财务报表与指标", "Tencent public quote snapshot": "腾讯公开行情", "Sina public quote snapshot": "新浪公开行情"}[value] || (/^[A-Za-z0-9_.:-]+$/.test(value || "") ? "来源名称见原始记录" : value || "来源尚未提供"));
  const embeddingText = value => value === "AVAILABLE" ? "语义索引已准备" : value === "UNAVAILABLE" ? "关键词检索可用，语义索引未准备" : "索引状态待确认";
  function rawDetails(title, data) {
    const details = el("details");
    details.append(el("summary", title), el("pre", JSON.stringify(data, null, 2), "research-original-text"));
    return details;
  }
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
    output.append(el("h3", original.title), el("p", `${customerSource(original.source)} · 发布 ${customerTime(original.published_at)} · 第 ${result.revision} 版`, "research-data-meta"));
    if (original.source_url) output.append(safeLink(original.source_url, "打开原始来源"));
    if (match) output.append(el("p", `引用位置：${match.page == null ? "页码未提供" : `第 ${match.page} 页`} · 第 ${match.paragraph} 段`, "research-data-meta"));
    const text = el("pre", original.text, "research-original-text"); output.append(text);
    output.append(rawDetails("版本与引用定位记录", {document_id: documentId, revision: result.revision, content_hash: result.content_hash, source: original.source, published_at: original.published_at, ...(match ? {chunk_id: match.chunk_id, page: match.page, paragraph: match.paragraph} : {})}));
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
    else output.append(table(["资料", "标的／期间", "发布时间", "可见范围", "资料版本与检索准备"], knowledgeDocuments.map(item => {
      const title = button(item.title, event => busy(event.currentTarget, "knowledge-message", () => showOriginal(item.document_id)));
      return [title, [item.subject, item.period].filter(Boolean).join(" / ") || "未限定", customerTime(item.published_at), item.visibility === "PUBLIC" ? "公开" : "个人", `第 ${item.revision} 版 · ${item.chunk_count} 个片段 · ${embeddingText(item.embedding_status)}`];
    })));
    message("knowledge-message", readOnly() ? "页面快照只读，上传与检索操作不可用。" : "");
  }
  function renderKnowledgeMatches(data) {
    const output = byId("knowledge-matches"); output.replaceChildren();
    knowledgeMatches = data.matches || [];
    knowledgeAsOf = data.as_of;
    const mode = data.mode === "HYBRID_RRF" ? "关键词与语义联合检索" : data.mode === "KEYWORD_ONLY" ? "关键词检索" : "检索方式待确认";
    const coverage = data.quality_gate === "COMPLETE_ELIGIBLE_CORPUS" ? "已搜索全部符合条件的资料" : "资料范围受限，可能遗漏相关内容";
    const reasons = {LOCAL_EMBEDDING_UNAVAILABLE: "语义检索暂不可用，本次使用关键词检索。", PARTIAL_EMBEDDING_COVERAGE: "部分资料尚未建立语义索引。", HYBRID_RELEASE_GATE_DISABLED: "语义检索尚未通过启用条件，本次使用关键词检索。"};
    output.append(el("p", `${mode} · ${coverage} · 候选 ${data.candidate_count} 个片段 · 用时 ${data.elapsed_ms} 毫秒`, "research-data-meta"));
    if (data.degraded_reason) output.append(el("p", reasons[data.degraded_reason] || "检索服务存在限制，具体信息可查看检索记录。", "research-data-meta"));
    output.append(rawDetails("检索方式与运行记录", {mode: data.mode, fulltext_backend: data.fulltext_backend, fulltext_reason: data.fulltext_reason, quality_gate: data.quality_gate, degraded_reason: data.degraded_reason, candidate_count: data.candidate_count, elapsed_ms: data.elapsed_ms}));
    if (!knowledgeMatches.length) output.append(el("p", "没有匹配资料；缺少依据时不生成金融结论。", "empty-state"));
    for (const match of knowledgeMatches) {
      const card = el("article", null, "research-result-card");
      card.append(el("h4", match.title), el("span", "相关资料 · 事实尚未核验", "status-chip"), el("p", `${customerSource(match.source)} · 发布 ${customerTime(match.published_at)} · 第 ${match.revision} 版 · ${match.subject || "标的未限定"} · ${match.period || "期间未限定"}`, "research-data-meta"), el("blockquote", match.text));
      const actions = el("div", null, "research-action-row");
      actions.append(button("查看引用原文", event => busy(event.currentTarget, "knowledge-message", () => showOriginal(match.document_id, match))), button("核验原文引用", event => busy(event.currentTarget, "knowledge-message", async () => {
        const checked = await request(`${knowledgePrefix}/citations/check`, {method: "POST", body: {citations: [{document_id: match.document_id, chunk_id: match.chunk_id, revision: match.revision, content_hash: match.content_hash, quote: match.text}], as_of: knowledgeAsOf}});
        message("knowledge-message", checked.status === "PASS" ? "引用与该版本原文完全对应；金融事实仍需独立核验。" : `引用尚未核对通过：${customerReason(checked.results?.[0]?.reason)}。`, checked.status !== "PASS");
      }), true));
      if (match.source_url) actions.append(safeLink(match.source_url, "原始来源"));
      card.append(actions, rawDetails("原始引用定位与检索状态", match)); output.append(card);
    }
  }
  function initializeKnowledge() {
    const root = byId("knowledge-workspace"); if (!root) return;
    root.append(notice("knowledge-message"));
    const intake = section("上传或登记原始资料");
    intake.append(el("p", "支持文本、Markdown 与可提取文字的 PDF；文件不超过 8 MiB。扫描版 PDF 需先识别文字，来源名称和发布时间为必填项。"));
    const form = el("div", null, "research-form-grid");
    form.append(field("knowledge-title", "资料标题"), field("knowledge-source", "来源名称"), field("knowledge-source-url", "原文链接（可选）", {type: "url"}), field("knowledge-published", "发布时间（本地时间）", {type: "datetime-local"}), field("knowledge-subject", "标的（可选）"), field("knowledge-period", "报告期（可选）"), field("knowledge-kind", "资料类型", {tag: "select", options: {ANNOUNCEMENT: "公告", FINANCIAL_REPORT: "财报", RESEARCH_REPORT: "研报", METHOD: "指标说明", PAPER: "论文", OTHER: "其他"}}), field("knowledge-visibility", "可见范围", {tag: "select", options: {PRIVATE: "个人资料", PUBLIC: "公开资料（管理员）"}}));
    intake.append(form);
    const file = field("knowledge-file", "文件（有文件时以文件为准）", {type: "file"}); file.querySelector("input").accept = ".txt,.md,.pdf"; intake.append(file, field("knowledge-text", "原文内容（无文件时填写）", {tag: "textarea"}));
    const upload = button("上传并建立索引", event => busy(event.currentTarget, "knowledge-message", async () => {
      const published = byId("knowledge-published").value;
      if (!published) throw new Error("请填写资料发布时间。");
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
      message("knowledge-message", `资料已登记 · 第 ${result.revision} 版 · ${result.chunk_count} 个片段 · ${embeddingText(result.embedding_status)}；资料真实性尚未核验。`);
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
    const rebuild = button("更新语义检索索引", event => busy(event.currentTarget, "knowledge-message", async () => {
      const result = await request(`${knowledgePrefix}/indexes/rebuild`, {method: "POST"}); message("knowledge-message", result.status === "CALCULATED" ? `索引已更新，${result.indexed} 个片段；检索质量需另行评测。` : "语义检索服务暂不可用；关键词检索仍可使用。", result.status !== "CALCULATED");
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
    if (typeof value !== "string" || !/(Z|[+-]\d{2}:\d{2})$/.test(value)) throw new Error("历史截止时间必须包含时区，例如 2026-09-30T16:00:00+08:00。");
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) throw new Error("历史截止时间无效。");
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
      renderResearchRun(run); message("research-message", "任务已提交，可在下方查看研究进度与结果。"); scheduleRunPolling();
    } finally { researchSubmitting = false; controls.forEach(control => { if (control) control.disabled = readOnly() || (control.id === "research-template-submit" && !templateAvailable); }); }
  }
  async function loadResearchTemplate() {
    templateAvailable = false; byId("research-template-submit").disabled = true;
    if (readOnly()) { byId("research-template-info").textContent = "当前为只读页面，不能启动真实资料研究。"; return; }
    const data = await request("/api/v1/research/templates");
    const template = data.items?.find(item => item.template_id === "live-equity-basic.v1" && item.data_mode === "LIVE");
    if (!template) { byId("research-template-info").textContent = "股票基础研究暂不可用。"; return; }
    templateAvailable = true;
    byId("research-template-info").textContent = `研究内容：${template.nodes.map(node => `${RESEARCH_OPERATIONS[node.operation] || "研究资料"}（${node.required_fields.map(customerMetric).join("、")}）`).join("；")}。返回的数据仍需核对来源与时点。`;
    byId("research-template-record").replaceChildren(el("pre", JSON.stringify(template, null, 2), "research-original-text"));
    byId("research-template-submit").disabled = readOnly() || researchSubmitting;
  }
  function renderResearchDraft() {
    const output = byId("research-node-editor"); output.replaceChildren();
    const rows = researchDraft.map((item, index) => {
      const editor = (key, value, list = false) => {
        const input = el("input"); input.value = list ? (value || []).join(", ") : value || "";
        const labels = {node_id: "步骤标识", subject: "研究标的", query: "查询语句", required_fields: "必需字段", dependencies: "前置步骤"};
        input.setAttribute("aria-label", `研究步骤 ${index + 1} ${labels[key]}`);
        input.addEventListener("input", () => { item[key] = list ? input.value.split(/[,，\n]/).map(value => value.trim()).filter(Boolean) : input.value.trim(); });
        return input;
      };
      const operation = el("select"); operation.setAttribute("aria-label", `研究步骤 ${index + 1} 研究内容`);
      for (const [key, name] of Object.entries(RESEARCH_OPERATIONS)) { const option = el("option", name); option.value = key; operation.append(option); }
      operation.value = item.operation; operation.addEventListener("change", () => { item.operation = operation.value; });
      const remove = button("移除", () => { researchDraft.splice(index, 1); renderResearchDraft(); }); remove.disabled = researchDraft.length <= 1;
      return [editor("node_id", item.node_id), operation, editor("subject", item.subject), editor("query", item.query), editor("required_fields", item.required_fields, true), editor("dependencies", item.dependencies, true), remove];
    });
    output.append(table(["步骤标识", "研究内容", "标的", "查询语句（可选）", "接口必需字段", "前置步骤", "操作"], rows));
    byId("research-draft-count").textContent = `${researchDraft.length} / 32 个步骤`;
  }
  function renderResearchRun(run) {
    currentRun = run;
    currentRunOwner = owner();
    byId("research-run-id").value = run.run_id;
    const output = byId("research-run-result"); output.replaceChildren();
    const mode = run.is_synthetic === true ? "演示样例研究" : run.data_mode === "LIVE" ? "真实资料研究" : "研究来源模式待确认";
    output.append(el("h3", `研究任务 · ${customerStatus(run.status)}`), el("p", `${mode} · ${customerStatus(run.verification_status)} · 开始 ${customerTime(run.created_at)} · ${run.finished_at ? `完成 ${customerTime(run.finished_at)}` : "尚未结束"} · ${run.elapsed_ms == null ? "耗时尚未确定" : `用时 ${run.elapsed_ms} 毫秒`}`, "research-data-meta"));
    output.append(el("p", "单一来源的数据尚未独立核验；研究完成不等于金融事实已核验，也不构成交易指令。服务重启后无法恢复此任务，请及时保存研究结果。", "research-data-meta"));
    if (run.as_of) output.append(el("p", `研究截止时间 ${customerTime(run.as_of)}；该时间之后的数据不能作为本次研究证据。`, "research-data-meta"));
    byId("research-cancel").disabled = terminalRun(run) || readOnly();
    for (const [index, result] of (run.nodes || []).entries()) {
      const card = el("article", null, "research-result-card");
      const content = RESEARCH_OPERATIONS[result.capability_snapshot?.operation];
      card.append(el("h4", `研究步骤 ${index + 1}${content ? ` · ${content}` : ""} · ${customerStatus(result.status)}`), el("p", `数据服务：${customerSource(result.provider)} · ${result.provider_ms == null ? "尚无步骤耗时" : `用时 ${result.provider_ms} 毫秒`} · ${customerStatus(result.verification_status || "NOT_VERIFIED")}`, "research-data-meta"));
      if (result.missing_fields?.length) card.append(el("p", `待补资料：${result.missing_fields.map(customerMetric).join("、")}`, "notice"));
      if (result.error_codes?.length) card.append(el("p", `未完成原因：${result.error_codes.map(customerReason).join("；")}`, "notice error"));
      if (result.observations?.length) card.append(table(["数据项／报告期", "数值／单位", "数据时点", "实际来源", "核验状态"], result.observations.map(item => [`${customerMetric(item.metric)} / ${item.period || "未提供"}`, `${item.value} / ${customerUnit(item.unit)}`, customerTime(item.observed_at), customerSource(item.actual_source), customerStatus(item.verification_status)])));
      else card.append(el("p", "当前没有可展示的观察值。", "empty-state"));
      card.append(rawDetails("证据定位与原始数据", result)); output.append(card);
    }
    output.append(rawDetails("完整任务记录与追踪编号", run));
  }
  async function loadRuntime() {
    const status = await request("/api/v1/research/runtime");
    const scope = status.scope === "SINGLE_PROCESS" ? "当前服务" : "统计范围待确认";
    byId("research-runtime").textContent = `${scope}：正在执行 ${status.active} 项 · 排队 ${status.waiting} 项 · 同时执行上限 ${status.global_limit} 项。`;
    byId("research-runtime-record").replaceChildren(el("p", `同时执行峰值 ${status.peak_active} 项 · 数据服务请求 ${status.provider_active} 项 · 模型调用 ${status.model_active} 项。运行计数不表示已完成真实容量验收。`, "research-data-meta"), el("pre", JSON.stringify(status, null, 2), "research-original-text"));
  }
  async function refreshResearchRun() {
    const runId = byId("research-run-id").value.trim(); if (!runId) throw new Error("请先开始研究，或填写已有任务的追踪编号。");
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
    const template = section("开始股票研究");
    template.append(el("p", "输入 A 股代码，获取行情与财务资料。研究结果保留数据来源、发布时间和资料缺口，不能直接作为交易指令。"));
    const basic = el("div", null, "research-form-grid");
    basic.append(field("research-template-subject", "研究目标（A 股代码）", {value: "600519"}), field("research-budget", "完成时限（秒，含排队）", {type: "number", value: "60"}), field("research-as-of", "历史截止时间（本地时间，可选）", {type: "datetime-local"}));
    const budget = basic.querySelector('input[type="number"]'); budget.min = "1"; budget.max = "60";
    template.append(basic, el("p", "截止时间留空表示研究当前资料；填写后，晚于该时间的信息不会作为研究依据。支持带交易所后缀的股票代码，例如 600519.SH。", "research-data-meta"));
    const templateInfo = el("p", "正在准备股票研究。", "research-data-meta"); templateInfo.id = "research-template-info"; templateInfo.setAttribute("aria-live", "polite"); template.append(templateInfo);
    const templateSubmit = button("开始研究", event => busy(event.currentTarget, "research-message", async () => {
      if (!templateAvailable) throw new Error("股票基础研究暂不可用。");
      const subject = byId("research-template-subject").value.trim(); if (!subject) throw new Error("请输入研究目标。");
      await submitResearch("/api/v1/research/runs/from-template", {subject, template_id: "live-equity-basic.v1", budget_seconds: Number(byId("research-budget").value), ...researchTimePayload()});
    }), true); templateSubmit.id = "research-template-submit"; templateSubmit.disabled = true; template.append(templateSubmit);
    const templateDetails = el("details"); templateDetails.append(el("summary", "股票研究的步骤与原始配置"));
    const templateRecord = el("div"); templateRecord.id = "research-template-record"; templateDetails.append(templateRecord); template.append(templateDetails); root.append(template);
    const advanced = el("details"); advanced.id = "research-advanced-settings"; advanced.append(el("summary", "高级设置：自定义研究步骤"));
    const editor = section("自定义研究步骤");
    editor.append(el("p", "仅在标准股票研究不满足需求时使用。每个步骤配置研究标的、接口必需字段与前置步骤，多个字段或步骤标识以逗号分隔。服务端会检查循环、重复标识及未知依赖。此处填写的数据结构不会自动产生行情或财务数值。"));
    const controls = el("div", null, "research-action-row");
    controls.append(button("添加研究步骤", () => {
      if (researchDraft.length >= 32) { message("research-message", "单次研究最多 32 个步骤。", true); return; }
      let index = researchDraft.length + 1; while (researchDraft.some(item => item.node_id === `node-${index}`)) index++;
      researchDraft.push({node_id: `node-${index}`, operation: "MARKET_DATA", subject: "", required_fields: ["price"], dependencies: []}); renderResearchDraft();
    }), Object.assign(el("span", null, "status-chip"), {id: "research-draft-count"}));
    editor.append(controls, el("p", "与标准研究共用上方的完成时限和历史截止时间。", "research-data-meta"));
    const nodes = el("div"); nodes.id = "research-node-editor"; editor.append(nodes);
    const importer = el("details"); importer.id = "research-json-import"; importer.append(el("summary", "导入结构化研究 JSON"), field("research-json", "研究请求 JSON（nodes、budget_seconds、as_of 可选）", {tag: "textarea"}));
    const importButton = button("应用 JSON 到编辑表", () => {
      try {
        const draft = parseJSON("research-json");
        if (!Array.isArray(draft.nodes) || !draft.nodes.length || draft.nodes.length > 32 || draft.nodes.some(item => !item || typeof item !== "object" || !Array.isArray(item.required_fields) || (item.dependencies != null && !Array.isArray(item.dependencies)))) throw new Error("JSON 需要 1 至 32 个有效节点及字段数组。");
        importResearchTime(draft.as_of);
        researchDraft = draft.nodes.map(item => ({...item, dependencies: item.dependencies || []}));
        byId("research-budget").value = String(draft.budget_seconds ?? 60); renderResearchDraft(); message("research-message", "已载入编辑表，尚未提交。");
      } catch (error) { message("research-message", error.message, true); }
    }); importer.append(importButton); editor.append(importer);
    const submit = button("启动自定义研究", event => busy(event.currentTarget, "research-message", async () => {
      const nodes = researchDraft.map(item => { const result = {...item}; if (!result.query) delete result.query; return result; });
      await submitResearch("/api/v1/research/runs", {nodes, budget_seconds: Number(byId("research-budget").value), ...researchTimePayload()});
    }), true); submit.id = "research-submit"; editor.append(submit); advanced.append(editor); root.append(advanced);
    const runtime = section("研究进度"); const state = el("p"); state.id = "research-runtime"; runtime.append(state);
    const lookup = el("details"); lookup.append(el("summary", "查找已有研究任务"), field("research-run-id", "研究任务追踪编号")); runtime.append(lookup);
    const actions = el("div", null, "research-action-row");
    const refresh = button("刷新任务", event => busy(event.currentTarget, "research-message", async () => { await refreshResearchRun(); scheduleRunPolling(); message("research-message", "任务状态已更新。"); })); refresh.id = "research-refresh";
    const cancel = button("取消任务", event => busy(event.currentTarget, "research-message", async () => {
      if (!currentRun || currentRunOwner !== owner()) throw new Error("请先读取当前账户任务。");
      stopRunPolling(); runSequence++;
      const run = await request(`/api/v1/research/runs/${encodeURIComponent(currentRun.run_id)}`, {method: "DELETE"}); renderResearchRun(run); await loadRuntime(); message("research-message", "任务取消结果已返回。");
    }), true); cancel.id = "research-cancel"; cancel.disabled = true; actions.append(refresh, cancel, button("刷新服务状态", event => busy(event.currentTarget, "research-message", loadRuntime))); runtime.append(actions);
    const runtimeDetails = el("details"); runtimeDetails.append(el("summary", "服务运行明细")); const runtimeRecord = el("div"); runtimeRecord.id = "research-runtime-record"; runtimeDetails.append(runtimeRecord); runtime.append(runtimeDetails); root.append(runtime);
    const result = section("研究结果与依据"); result.id = "research-run-result"; root.append(result);
    const stockReport = section("当前对话的个股详细报告"); stockReport.id = "research-stock-report"; stockReport.hidden = true;
    const reportContent = el("div"); reportContent.id = "research-stock-report-content"; stockReport.append(reportContent); root.append(stockReport); renderResearchDraft();
  }
  const ALGORITHMS = Object.freeze({regime: "市场波动环境", covariance: "资产联动风险", "five-factors": "市场风格因素"});
  const ALGORITHM_FIELDS = Object.freeze({low_variance: "低波动状态概率", high_variance: "高波动状态概率", MKT_RF: "市场超额收益", SMB: "规模因素", HML: "价值因素", RMW: "盈利因素", CMA: "投资因素"});
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
        const series = chart.addSeries(window.LightweightCharts.LineSeries, {title: ALGORITHM_FIELDS[key], color: colors[index], lineWidth: 2, priceFormat: {type: "price", precision: 6, minMove: .000001}});
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
    output.append(el("h4", correlation ? "资产相关程度" : "资产波动与联动矩阵"));
    output.append(table(["资产", ...data.assets], matrix.map((row, index) => [data.assets[index], ...row.map(value => {
      const cell = el("span", Number(value).toPrecision(6), value >= 0 ? "research-matrix-positive" : "research-matrix-negative"); return cell;
    })])));
  }
  function renderAlgorithmResult(data) {
    algorithmResult = data;
    const output = byId("algorithm-output"); output.replaceChildren();
    output.append(el("h3", `${ALGORITHMS[algorithmKind]} · ${customerStatus(data.status)}`), el("p", `研究截止时点 ${data.as_of} · 仅分析本次导入的资料`, "research-data-meta"));
    if (data.status !== "CALCULATED") {
      const descriptions = {INSUFFICIENT_RETURNS: "收益样本不足", DEGENERATE_TRAINING_RETURNS: "训练收益退化为常数", RESEARCH_DEPENDENCY_UNAVAILABLE: "研究算法依赖不可用", MODEL_NOT_CONVERGED: "模型未收敛", INSUFFICIENT_ASSETS: "资产数不足", INSUFFICIENT_ALIGNED_RETURNS: "共同日期的收益样本不足", ZERO_VARIANCE_ASSET: "存在零方差资产", FUNDAMENTAL_FIELDS_MISSING: "缺少五因子财务字段", INSUFFICIENT_FORMATION_UNIVERSE: "分组形成集合不足", EMPTY_2X3_PORTFOLIO: "存在空的 2×3 分组", RISK_FREE_RETURN_MISSING: "缺少无风险收益", FINANCIAL_POINT_IN_TIME_INVALID: "财报公告时点不符合形成期约束", MONTHS_MUST_BE_NONEMPTY_SORTED_UNIQUE: "月度记录须非空、排序且唯一", FORMATION_MEMBER_RETURN_MISSING: "形成集合成员缺少月度收益"};
      output.append(el("p", `暂无法分析：${descriptions[data.reason] || "资料或计算条件未满足"}。请补充或核对输入资料；具体字段可在计算明细中查看。`, "notice error"));
    } else {
      output.append(el("p", data.interpretation || "仅对输入集合计算，未证明原始数据真实或全市场覆盖。"));
      if (algorithmKind === "regime") output.append(el("p", `使用 ${data.sample_count} 条历史收益分析。图中 0–1 表示状态概率，1 代表 100%；高波动表示起伏较大，不代表上涨或下跌概率。`, "research-data-meta"));
      else if (algorithmKind === "five-factors") output.append(el("p", "观察市场、规模、价值、盈利和投资特征的表现。图中收益采用小数比例，0.01 代表 1%；本结果没有进行个人持仓收益归因。", "research-data-meta"));
      else {
        output.append(el("p", `输入包含 ${data.assets.length} 项资产、${data.sample_count} 个共同交易日。资产同时波动时，增加持仓数量不一定能降低组合风险；当前结果仅对应所导入的资产。`, "research-data-meta"));
        const details = el("details"); details.id = "algorithm-matrix-details"; details.append(el("summary", "查看资产联动矩阵与计算说明"), el("p", `观察期 ${data.input_start} 至 ${data.input_end}。协方差矩阵描述波动与共同变化，相关矩阵描述标准化的联动程度。`));
        const actions = el("div", null, "research-action-row"); actions.append(button("波动与联动矩阵", () => renderMatrix(data)), button("相关程度矩阵", () => renderMatrix(data, true))); details.append(actions);
        const matrix = el("div"); matrix.id = "algorithm-matrix"; details.append(matrix); output.append(details); renderMatrix(data);
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
    const input = section("准备分析资料");
    input.append(field("algorithm-kind", "分析内容", {tag: "select", options: ALGORITHMS}), el("p", "市场波动环境帮助了解价格起伏；资产联动帮助检查分散配置；市场风格帮助观察不同公司特征的表现。请选择分析内容并导入相关资料，缺少数据时不会生成结果。"));
    const importDetails = el("details"); importDetails.id = "algorithm-input-settings"; importDetails.append(el("summary", "导入数据与计算设置"));
    importDetails.append(el("p", "收益采用小数比例，例如 1% 写为 0.01。输入来源与时点须可核对；本页面不会自动生成行情或财务数据。"), field("algorithm-file", "导入数据文件（JSON 格式）", {type: "file"}));
    const payload = field("algorithm-json", "数据内容（JSON 格式）", {tag: "textarea"}); payload.querySelector("textarea").rows = 13; importDetails.append(payload);
    const controls = el("div", null, "research-action-row");
    controls.append(button("载入空输入结构", () => { byId("algorithm-json").value = JSON.stringify(algorithmTemplate(byId("algorithm-kind").value), null, 2); message("algorithm-message", "已载入字段结构；请填写真实数据，尚未计算。"); }));
    const compute = button("开始分析", event => busy(event.currentTarget, "algorithm-message", async () => {
      destroyAlgorithmChart(); byId("algorithm-output").replaceChildren(); algorithmResult = null;
      const sequence = ++algorithmSequence;
      const kind = byId("algorithm-kind").value;
      const result = await request(`/api/v1/research/algorithms/${kind}`, {method: "POST", body: parseJSON("algorithm-json")});
      if (sequence !== algorithmSequence || byId("algorithm-kind").value !== kind) return;
      algorithmKind = kind; renderAlgorithmResult(result); message("algorithm-message", result.status === "CALCULATED" ? "分析已完成；计算完成不等于原始资料已经核验。" : "暂无法分析，请补充或核对资料。", result.status !== "CALCULATED");
    }), true); compute.id = "algorithm-compute"; controls.append(compute); importDetails.append(controls);
    const contract = el("details"); contract.append(el("summary", "输入字段与数据缺口"), table(["算法", "输入结构", "最低条件", "时点与覆盖"], [
      ["两状态模型", "returns: [{time,value}]；training_size", "训练窗口至少 252；收益日期排序唯一", "as_of 之后的收益拒绝；只展示训练窗口末端起的过滤概率"],
      ["协方差收缩", "series: {资产标识: [{time,value}]} ", "至少 2 资产、60 个共同日期；非零方差", "严格按日期交集对齐；不填补缺失收益"],
      ["五因子年度", "monetary_unit: CNY；fundamentals：security_id、formation_year、fiscal_year、published_at；两期市值、账面权益、收入、成本、费用、利息、两期资产", "全部财务字段及统一人民币单位必需；2×3 分组不能为空", "前一年财报在形成年 6 月末前已公告"],
      ["五因子月度", "months: [{month,risk_free_return,securities:[{security_id,total_return,beginning_market_cap}]}]；universe_id", "形成集合成员有月收益、期初市值及无风险收益", "7 月重组；输入集合不能冒充全市场或官方美国因子"],
    ])); importDetails.append(contract); input.append(importDetails); root.append(input);
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
