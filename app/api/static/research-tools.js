/* 账户资料、研究任务与确定性算法界面。 */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const owner = () => byId("owner-id")?.value.trim() || "demo-owner";
  const readOnly = () => window.PRISM_PAGES_SNAPSHOT === true;
  let accountEpoch = 0;
  let viewOwner = owner();
  let administrator = false;
  const researchRoutes = ["live-research", "research-knowledge", "research-algorithms"];
  const toolNames = ["custom", "materials", "task", "diagnostics"];
  let activeResearchTask = "live-research";
  let activeResearchTool = "custom";
  let appliedResearchParameters = {budget_seconds: "60", as_of: ""};
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
  function action(text, callback, {primary = false, quiet = false, write = false} = {}) {
    const control = button(text, callback, write);
    control.classList.add("rw-button");
    if (primary) control.classList.add("rw-primary");
    if (quiet) control.classList.add("rw-quiet");
    return control;
  }
  function disclosure(title, ...content) {
    const details = el("details", null, "rw-disclosure");
    const body = el("div", null, "rw-disclosure-content");
    body.append(...content); details.append(el("summary", title), body);
    return details;
  }
  function toolNotice(id) {
    const result = notice(`${id}-tool-${document.querySelectorAll(`[data-research-message="${id}"]`).length}`);
    result.dataset.researchMessage = id;
    return result;
  }
  function message(id, text, failure = false) {
    const outputs = [byId(id), ...document.querySelectorAll(`[data-research-message="${id}"]`)];
    for (const output of outputs) {
      if (!output) continue;
      output.textContent = text;
      output.className = failure ? "notice error" : "notice";
      output.hidden = !text;
    }
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
    finally {
      control.disabled = control.dataset.write === "true" && readOnly();
      if (control.id === "algorithm-compute") updateAlgorithmInputState();
      if (control.id === "research-template-submit") control.disabled = readOnly() || researchSubmitting || !templateAvailable;
      if (control.id === "research-cancel") control.disabled = readOnly() || terminalRun(currentRun);
    }
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

  function updateWorkbenchResults() {
    const panel = byId(activeResearchTask);
    const results = panel.querySelector(".rw-results");
    byId("research-workbench").classList.toggle("rw-has-results", [...results.children].some(node => !node.hidden && node.childElementCount > 0));
  }
  function showResearchDialog(id) {
    const dialog = byId(id);
    if (!dialog.open) dialog.showModal();
    document.body.classList.add("research-dialog-open");
  }
  function restoreResearchParameters() {
    byId("research-budget").value = appliedResearchParameters.budget_seconds;
    byId("research-as-of").value = appliedResearchParameters.as_of;
  }
  function applyResearchParameters() {
    appliedResearchParameters = {budget_seconds: byId("research-budget").value, as_of: byId("research-as-of").value};
    const summary = byId("research-parameter-summary"); summary.replaceChildren();
    if (appliedResearchParameters.as_of) summary.append(el("span", appliedResearchParameters.as_of.replace("T", " ")));
    if (appliedResearchParameters.budget_seconds !== "60") summary.append(el("span", `${appliedResearchParameters.budget_seconds} 秒预算`));
    summary.hidden = summary.childElementCount === 0;
  }
  function showResearchParameters() {
    restoreResearchParameters(); showResearchDialog("research-parameter-dialog");
    byId("research-parameter-trigger").setAttribute("aria-expanded", "true");
  }
  function showResearchToolsMenu(focus = false) {
    for (const name of toolNames) byId(`research-tool-pane-${name}`).hidden = true;
    byId("research-tools-menu").hidden = false; byId("research-tools-back").hidden = true;
    byId("research-tools-title").textContent = "研究工具"; byId("research-tools-dialog").scrollTop = 0;
    if (focus) byId(`research-tool-${activeResearchTool}`).focus({preventScroll: true});
  }
  function selectResearchTool(name) {
    activeResearchTool = name;
    for (const item of toolNames) byId(`research-tool-pane-${item}`).hidden = item !== name;
    byId("research-tools-menu").hidden = true; byId("research-tools-back").hidden = false;
    byId("research-tools-title").textContent = byId(`research-tool-${name}`).querySelector("strong").textContent;
    byId("research-tools-title").focus({preventScroll: true}); byId("research-tools-dialog").scrollTop = 0;
  }
  function openResearchTools(name = null) {
    showResearchToolsMenu(); byId("research-tools-maintenance").open = false;
    showResearchDialog("research-tools-dialog"); byId("research-tools-trigger").setAttribute("aria-expanded", "true");
    if (name) selectResearchTool(name); else byId("research-tool-custom").focus({preventScroll: true});
  }
  function initializeWorkbench() {
    const tabs = [...document.querySelectorAll("[data-research-route]")];
    tabs.forEach(tab => {
      tab.addEventListener("click", () => { window.location.hash = tab.dataset.researchRoute; });
      tab.addEventListener("keydown", event => {
        let index = researchRoutes.indexOf(tab.dataset.researchRoute);
        if (event.key === "ArrowRight") index = (index + 1) % researchRoutes.length;
        else if (event.key === "ArrowLeft") index = (index - 1 + researchRoutes.length) % researchRoutes.length;
        else if (event.key === "Home") index = 0;
        else if (event.key === "End") index = researchRoutes.length - 1;
        else return;
        event.preventDefault(); window.location.hash = researchRoutes[index]; tabs[index].focus({preventScroll: true});
      });
    });
    byId("research-tools-trigger").addEventListener("click", () => openResearchTools());
    byId("research-tools-back").addEventListener("click", () => showResearchToolsMenu(true));
    document.querySelectorAll("[data-research-tool]").forEach(control => control.addEventListener("click", () => {
      const name = control.dataset.researchTool; selectResearchTool(name);
      if (name === "materials") busy(control, "knowledge-message", loadKnowledge);
      if (name === "diagnostics") busy(control, "research-message", async () => { await loadRuntime(); message("research-message", ""); });
    }));
    document.querySelectorAll("[data-close-research-dialog]").forEach(control => control.addEventListener("click", () => byId(control.dataset.closeResearchDialog).close()));
    document.querySelectorAll(".rw-dialog").forEach(dialog => dialog.addEventListener("close", () => {
      document.body.classList.toggle("research-dialog-open", Boolean(document.querySelector(".rw-dialog[open]")));
      if (dialog.id === "research-tools-dialog") byId("research-tools-trigger").setAttribute("aria-expanded", "false");
      if (dialog.id === "research-parameter-dialog") { restoreResearchParameters(); byId("research-parameter-trigger").setAttribute("aria-expanded", "false"); }
      if (dialog.id === "research-algorithm-input-dialog") byId("algorithm-input-trigger").setAttribute("aria-expanded", "false");
    }));
    byId("research-parameter-form").addEventListener("submit", event => { event.preventDefault(); applyResearchParameters(); byId("research-parameter-dialog").close(); });
    const dialog = byId("research-tools-dialog"); let startedOutside = false;
    const outside = event => {
      const bounds = dialog.getBoundingClientRect();
      return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
    };
    dialog.addEventListener("pointerdown", event => { startedOutside = event.target === dialog && outside(event); });
    dialog.addEventListener("click", event => {
      if (startedOutside && event.target === dialog && outside(event)) dialog.close();
      startedOutside = false;
    });
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
    const text = el("pre", original.text, "research-original-text"); output.append(text);
    const record = el("div"); record.append(rawDetails("版本定位记录", {document_id: documentId, revision: result.revision, content_hash: result.content_hash}));
    if (match) record.append(el("p", `引用位置：${match.page == null ? "页码未提供" : `第 ${match.page} 页`} · 第 ${match.paragraph} 段`, "research-data-meta"));
    output.append(disclosure("原文记录与引用位置", record));
    output.hidden = false;
    showResearchDialog("knowledge-original-dialog");
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
    message("knowledge-message", readOnly() ? "当前页面只读。" : "");
  }
  function renderKnowledgeMatches(data) {
    const output = byId("knowledge-matches"); output.replaceChildren();
    knowledgeMatches = data.matches || [];
    knowledgeAsOf = data.as_of;
    output.hidden = false;
    output.append(el("h3", `检索结果 · ${knowledgeMatches.length} 条`));
    if (!knowledgeMatches.length) output.append(el("p", "没有匹配资料。可以调整关键词或筛选范围。", "empty-state"));
    for (const match of knowledgeMatches) {
      const card = el("article", null, "research-result-card");
      card.append(el("h4", match.title), el("span", "原文片段 · 待核验", "status-chip"), el("p", `${customerSource(match.source)} · 发布 ${customerTime(match.published_at)} · 第 ${match.revision} 版`, "research-data-meta"), el("blockquote", match.text));
      const actions = el("div", null, "research-action-row");
      actions.append(action("查看引用原文", event => busy(event.currentTarget, "knowledge-message", () => showOriginal(match.document_id, match))));
      const check = action("核验原文引用", event => busy(event.currentTarget, "knowledge-message", async () => {
        const checked = await request(`${knowledgePrefix}/citations/check`, {method: "POST", body: {citations: [{document_id: match.document_id, chunk_id: match.chunk_id, revision: match.revision, content_hash: match.content_hash, quote: match.text}], as_of: knowledgeAsOf}});
        message("knowledge-message", checked.status === "PASS" ? "引用与该版本原文完全对应；金融事实仍需独立核验。" : `引用尚未核对通过：${customerReason(checked.results?.[0]?.reason)}。`, checked.status !== "PASS");
      }), {write: true});
      if (match.source_url) actions.append(safeLink(match.source_url, "原始来源"));
      card.append(actions, disclosure("查看引用详情", check, el("pre", JSON.stringify(match, null, 2), "research-original-text"))); output.append(card);
    }
    const mode = data.mode === "HYBRID_RRF" ? "关键词与语义联合检索" : data.mode === "KEYWORD_ONLY" ? "关键词检索" : "检索方式待确认";
    const coverage = data.quality_gate === "COMPLETE_ELIGIBLE_CORPUS" ? "已搜索全部符合条件的资料" : "资料范围受限，可能遗漏相关内容";
    output.append(disclosure("检索方式与运行信息", el("p", `${mode} · ${coverage} · 候选 ${data.candidate_count} 个片段 · 用时 ${data.elapsed_ms} 毫秒`, "research-data-meta"), rawDetails("原始检索记录", {mode: data.mode, fulltext_backend: data.fulltext_backend, quality_gate: data.quality_gate, degraded_reason: data.degraded_reason})));
    updateWorkbenchResults();
  }
  function initializeKnowledge() {
    const root = byId("knowledge-workspace"); if (!root) return;
    root.append(notice("knowledge-message"));
    const intake = el("div"); intake.append(toolNotice("knowledge-message"));
    const form = el("div", null, "rw-form-grid");
    form.append(field("knowledge-title", "资料标题"), field("knowledge-source", "来源名称"), field("knowledge-published", "公告时间", {type: "datetime-local"}), field("knowledge-kind", "资料类型", {tag: "select", options: {ANNOUNCEMENT: "公告", FINANCIAL_REPORT: "财报", RESEARCH_REPORT: "研报", METHOD: "指标说明", PAPER: "论文", OTHER: "其他"}}));
    intake.append(form);
    const file = field("knowledge-file", "资料文件", {type: "file"}); file.querySelector("input").accept = ".txt,.md,.pdf";
    file.append(el("small", "TXT、Markdown 或可提取文本的 PDF，最大 8 MiB。")); file.style.marginTop = "18px";
    const extra = el("div", null, "rw-form-grid"); extra.append(field("knowledge-source-url", "原文链接", {type: "url"}), field("knowledge-visibility", "可见范围", {tag: "select", options: {PRIVATE: "个人资料", PUBLIC: "公开资料（管理员）"}}), field("knowledge-subject", "标的"), field("knowledge-period", "报告期"));
    intake.append(file, disclosure("直接填写原文", field("knowledge-text", "原文内容", {tag: "textarea"})), disclosure("补充资料信息", extra));
    const upload = action("添加资料并建立索引", event => busy(event.currentTarget, "knowledge-message", async () => {
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
    }), {primary: true, write: true}); upload.id = "knowledge-upload";
    const intakeActions = el("div", null, "rw-tool-actions"); intakeActions.append(upload); intake.append(intakeActions); byId("research-materials-slot").append(intake);
    const search = el("form"); search.addEventListener("submit", event => event.preventDefault());
    const row = el("div", null, "rw-input-row"); row.append(field("knowledge-query", "问题或关键词"));
    const filters = el("div", null, "rw-form-grid rw-filters"); filters.id = "knowledge-filters"; filters.hidden = true;
    filters.append(field("knowledge-search-subject", "标的"), field("knowledge-search-period", "报告期"), field("knowledge-as-of", "历史截止时点", {type: "datetime-local"})); filters.lastElementChild.classList.add("rw-wide");
    const searchButton = action("检索资料", event => busy(event.currentTarget, "knowledge-message", async () => {
      byId("knowledge-matches").replaceChildren(); byId("knowledge-matches").hidden = true; byId("knowledge-original").hidden = true;
      const body = {query: byId("knowledge-query").value.trim(), limit: 10};
      if (!body.query) throw new Error("请输入检索关键词。");
      for (const [key, id] of Object.entries({subject: "knowledge-search-subject", period: "knowledge-search-period"})) if (byId(id).value.trim()) body[key] = byId(id).value.trim();
      if (byId("knowledge-as-of").value) body.as_of = new Date(byId("knowledge-as-of").value).toISOString();
      renderKnowledgeMatches(await request(`${knowledgePrefix}/search`, {method: "POST", body})); message("knowledge-message", "");
    }), {primary: true, write: true}); searchButton.id = "knowledge-search"; searchButton.type = "submit"; row.append(searchButton);
    const meta = el("div", null, "rw-input-meta");
    const filterButton = action("筛选条件", () => { filters.hidden = !filters.hidden; filterButton.setAttribute("aria-expanded", String(!filters.hidden)); }, {quiet: true}); filterButton.id = "knowledge-filter-trigger"; filterButton.setAttribute("aria-controls", "knowledge-filters"); filterButton.setAttribute("aria-expanded", "false");
    const filterSummary = el("span", null, "rw-filter-summary"); filterSummary.id = "knowledge-filter-summary"; meta.append(filterButton, filterSummary);
    filters.querySelectorAll("input").forEach(input => input.addEventListener("input", () => { filterSummary.textContent = [...filters.querySelectorAll("input")].map(node => node.value.trim().replace("T", " ")).filter(Boolean).join(" · "); }));
    search.append(row, meta, filters); root.prepend(search);
    byId("knowledge-query").placeholder = "例如：营业收入增长的原因"; byId("knowledge-query").required = true;
    const matches = el("div"); matches.id = "knowledge-matches"; matches.hidden = true; byId("knowledge-results-slot").append(matches);
    const catalog = el("div"); const actions = el("div", null, "rw-tool-actions"); actions.append(action("刷新资料", event => busy(event.currentTarget, "knowledge-message", loadKnowledge)));
    const rebuild = action("重建向量索引", event => busy(event.currentTarget, "knowledge-message", async () => {
      const result = await request(`${knowledgePrefix}/indexes/rebuild`, {method: "POST"}); message("knowledge-message", result.status === "CALCULATED" ? `索引已更新，${result.indexed} 片段；召回质量需另行评测。` : "向量服务不可用；关键词检索仍可使用。", result.status !== "CALCULATED");
    }), {write: true}); rebuild.id = "knowledge-rebuild"; rebuild.hidden = true; actions.append(rebuild); catalog.append(actions); const documents = el("div"); documents.id = "knowledge-documents"; catalog.append(documents); intake.append(disclosure("资料目录", catalog));
    const original = el("div"); original.id = "knowledge-original"; original.hidden = true; byId("knowledge-original-slot").append(original);
    byId("knowledge-visibility").querySelector('option[value="PUBLIC"]').disabled = true;
  }
  const RESEARCH_OPERATIONS = Object.freeze({MARKET_DATA: "行情", COMPANY_DATA: "财务", INDUSTRY_DATA: "行业", MACRO_DATA: "宏观", FUND_DATA: "基金", CONVERTIBLE_BOND_DATA: "可转债"});
  let researchDraft = [{node_id: "market-1", operation: "MARKET_DATA", subject: "", required_fields: ["price"], dependencies: []}];
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
    byId("research-run-result").replaceChildren(); byId("research-run-result").hidden = true; byId("research-run-actions").hidden = true;
    byId("research-run-id").value = ""; byId("research-cancel").disabled = true; updateWorkbenchResults();
    const controls = [byId("research-submit"), byId("research-template-submit")];
    controls.forEach(control => { if (control) control.disabled = true; });
    try {
      const run = await request(path, {method: "POST", body});
      if (sequence !== runSequence) return;
      renderResearchRun(run); byId("research-tools-dialog").close(); window.location.hash = "live-research"; message("research-message", ""); scheduleRunPolling();
    } finally { researchSubmitting = false; controls.forEach(control => { if (control) control.disabled = readOnly() || (control.id === "research-template-submit" && !templateAvailable); }); }
  }
  async function loadResearchTemplate() {
    templateAvailable = false; byId("research-template-submit").disabled = true;
    if (readOnly()) { byId("research-template-info").textContent = "当前为只读页面，不能启动真实资料研究。"; return; }
    const data = await request("/api/v1/research/templates");
    const template = data.items?.find(item => item.template_id === "live-equity-basic.v1" && item.data_mode === "LIVE");
    if (!template) { byId("research-template-info").textContent = "股票研究模板暂不可用。"; message("research-message", "股票研究模板暂不可用。", true); return; }
    templateAvailable = true;
    byId("research-template-info").textContent = `研究内容：${template.nodes.map(node => `${RESEARCH_OPERATIONS[node.operation] || "研究资料"}（${node.required_fields.map(customerMetric).join("、")}）`).join("；")}。返回的数据仍需核对来源与时点。`;
    byId("research-template-record").replaceChildren(el("pre", JSON.stringify(template, null, 2), "research-original-text"));
    byId("research-template-submit").disabled = readOnly() || researchSubmitting;
  }
  function renderResearchDraft() {
    const output = byId("research-node-editor"); output.replaceChildren();
    researchDraft.forEach((item, index) => {
      const editor = (key, value, list = false) => {
        const labels = {node_id: "步骤标识", subject: "研究标的", query: "查询语句", required_fields: "必需字段", dependencies: "前置步骤"};
        const wrapper = el("label", null, "research-form-field"); wrapper.append(el("span", labels[key]));
        const input = el("input"); input.value = list ? (value || []).join(", ") : value || "";
        input.setAttribute("aria-label", `研究步骤 ${index + 1} ${labels[key]}`);
        input.addEventListener("input", () => { item[key] = list ? input.value.split(/[,，\n]/).map(value => value.trim()).filter(Boolean) : input.value.trim(); });
        wrapper.append(input); return wrapper;
      };
      const operation = el("select"); operation.setAttribute("aria-label", `研究步骤 ${index + 1} 研究内容`);
      for (const [key, name] of Object.entries(RESEARCH_OPERATIONS)) { const option = el("option", name); option.value = key; operation.append(option); }
      operation.value = item.operation; operation.addEventListener("change", () => { item.operation = operation.value; });
      const remove = action("移除节点", () => { researchDraft.splice(index, 1); renderResearchDraft(); }, {quiet: true}); remove.disabled = researchDraft.length <= 1;
      const card = el("article", null, "rw-node-card");
      const heading = el("header", null, "rw-node-heading"); heading.append(el("h3", `节点 ${index + 1}`), remove);
      const primary = el("div", null, "rw-form-grid"); const operationField = el("label", null, "research-form-field"); operationField.append(el("span", "数据类型"), operation);
      primary.append(operationField, editor("subject", item.subject));
      const extra = el("div", null, "rw-form-grid"); extra.append(editor("required_fields", item.required_fields, true), editor("query", item.query), editor("node_id", item.node_id), editor("dependencies", item.dependencies, true));
      card.append(heading, primary, disclosure("查询字段与节点依赖", extra)); output.append(card);
    });
    byId("research-draft-count").textContent = `${researchDraft.length} / 32 个节点`;
    byId("research-add-node").disabled = researchDraft.length >= 32;
  }
  function renderResearchRun(run) {
    currentRun = run;
    currentRunOwner = owner();
    byId("research-run-id").value = run.run_id;
    const output = byId("research-run-result"); output.replaceChildren();
    output.hidden = false;
    const statuses = {QUEUED: "研究排队中", RUNNING: "正在研究", COMPLETED: "研究完成", FAILED: "研究未完成", CANCELLED: "研究已取消"};
    output.append(el("h3", statuses[run.status] || customerStatus(run.status)), el("p", `开始 ${customerTime(run.created_at)}${run.finished_at ? ` · 完成 ${customerTime(run.finished_at)}` : ""}`, "research-data-meta"));
    output.append(el("p", run.is_synthetic === true ? "演示样例研究，不能用于证明真实数据能力。" : "单一来源的数据尚未独立核验；研究完成不等于金融事实已核验，也不构成交易指令。", "research-data-meta"));
    byId("research-run-actions").hidden = false;
    byId("research-cancel").disabled = terminalRun(run) || readOnly();
    byId("research-cancel").hidden = terminalRun(run);
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
    const {nodes, ...metadata} = run;
    output.append(disclosure("任务记录与核验说明", el("p", "单源观察仍待核验；任务记录保存在当前服务进程。", "research-data-meta"), el("pre", JSON.stringify(metadata, null, 2), "research-original-text")));
    updateWorkbenchResults();
  }
  async function loadRuntime() {
    const status = await request("/api/v1/research/runtime");
    const output = byId("research-runtime"); output.replaceChildren();
    const counts = el("dl", null, "rw-runtime-list");
    for (const [label, value] of [["实际执行", status.active], ["正在排队", status.waiting], ["执行峰值", status.peak_active], ["全局上限", status.global_limit], ["数据服务活动", status.provider_active], ["模型活动", status.model_active]]) counts.append(el("dt", label), el("dd", value));
    output.append(counts, disclosure("详细运行信息", el("pre", JSON.stringify(status, null, 2), "research-original-text")));
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
    if (readOnly() || !currentRun || terminalRun(currentRun) || activeResearchTask !== "live-research" || byId("research-workbench").hidden || document.hidden) return;
    runPoll = setTimeout(async () => {
      try { await refreshResearchRun(); scheduleRunPolling(); }
      catch (error) { message("research-message", error.message, true); stopRunPolling(); }
    }, 1500);
  }
  function initializeResearch() {
    const root = byId("live-research-workspace"); if (!root) return;
    root.append(notice("research-message"));
    const editor = el("div"); editor.append(toolNotice("research-message"));
    const templateRecord = el("div"); templateRecord.id = "research-template-record";
    editor.append(disclosure("基础研究模板与字段", templateRecord));
    const controls = el("div", null, "rw-tool-actions");
    const add = action("添加节点", () => {
      if (researchDraft.length >= 32) { message("research-message", "单次研究最多 32 个节点。", true); return; }
      let index = researchDraft.length + 1; while (researchDraft.some(item => item.node_id === `node-${index}`)) index++;
      researchDraft.push({node_id: `node-${index}`, operation: "MARKET_DATA", subject: "", required_fields: ["price"], dependencies: []}); renderResearchDraft();
    }); add.id = "research-add-node";
    controls.append(add, Object.assign(el("span"), {id: "research-draft-count"}), action("研究参数", showResearchParameters, {quiet: true}));
    const parameters = byId("research-parameter-fields"); parameters.append(field("research-budget", "任务预算（秒）", {type: "number", value: "60"}), field("research-as-of", "历史截止时点", {type: "datetime-local"}), el("small", "按本地时间填写，留空表示当前研究。"));
    byId("research-budget").min = "1"; byId("research-budget").max = "60"; byId("research-budget").required = true;
    const nodes = el("div"); nodes.id = "research-node-editor"; editor.append(nodes);
    const importButton = action("应用到编辑表", () => {
      try {
        const draft = parseJSON("research-json");
        if (!Array.isArray(draft.nodes) || !draft.nodes.length || draft.nodes.length > 32 || draft.nodes.some(item => !item || typeof item !== "object" || !Array.isArray(item.required_fields) || (item.dependencies != null && !Array.isArray(item.dependencies)))) throw new Error("JSON 需要 1 至 32 个有效节点及字段数组。");
        importResearchTime(draft.as_of);
        researchDraft = draft.nodes.map(item => ({...item, dependencies: item.dependencies || []}));
        byId("research-budget").value = String(draft.budget_seconds ?? 60); applyResearchParameters(); renderResearchDraft(); message("research-message", "已载入编辑表，尚未提交。");
      } catch (error) { message("research-message", error.message, true); }
    }); importButton.id = "research-import-json";
    const submit = action("开始自定义研究", event => busy(event.currentTarget, "research-message", async () => {
      const nodes = researchDraft.map(item => { const result = {...item}; if (!result.query) delete result.query; return result; });
      await submitResearch("/api/v1/research/runs", {nodes, budget_seconds: Number(byId("research-budget").value), ...researchTimePayload()});
    }), {primary: true, write: true}); submit.id = "research-submit";
    controls.append(submit); editor.append(controls, disclosure("导入研究 JSON", field("research-json", "研究请求 JSON", {tag: "textarea"}), importButton)); byId("research-custom-slot").append(editor);
    const template = el("form"); const row = el("div", null, "rw-input-row");
    row.append(field("research-template-subject", "A 股证券代码"));
    const templateSubmit = action("开始研究", () => {}, {primary: true, write: true});
    template.addEventListener("submit", event => { event.preventDefault(); busy(templateSubmit, "research-message", async () => {
      if (!templateAvailable) throw new Error("LIVE 股票模板暂不可用。");
      const subject = byId("research-template-subject").value.trim(); if (!subject) throw new Error("请输入研究目标。");
      await submitResearch("/api/v1/research/runs/from-template", {subject, template_id: "live-equity-basic.v1", budget_seconds: Number(byId("research-budget").value), ...researchTimePayload()});
    }); }); templateSubmit.id = "research-template-submit"; templateSubmit.type = "submit"; templateSubmit.disabled = true; row.append(templateSubmit);
    const meta = el("div", null, "rw-input-meta"); const trigger = action("参数", showResearchParameters, {quiet: true}); trigger.id = "research-parameter-trigger"; trigger.setAttribute("aria-haspopup", "dialog"); trigger.setAttribute("aria-controls", "research-parameter-dialog"); trigger.setAttribute("aria-expanded", "false");
    const summary = el("span", null, "rw-parameter-summary"); summary.id = "research-parameter-summary"; summary.hidden = true; meta.append(trigger, summary); template.append(row, meta); root.prepend(template);
    byId("research-template-subject").placeholder = "例如 600519 或 600519.SH"; byId("research-template-subject").required = true;
    const task = el("div"); task.append(toolNotice("research-message"), field("research-run-id", "任务标识"));
    const read = action("读取任务", event => busy(event.currentTarget, "research-message", async () => { await refreshResearchRun(); byId("research-tools-dialog").close(); window.location.hash = "live-research"; scheduleRunPolling(); message("research-message", ""); }), {primary: true}); read.id = "research-load-run";
    const taskActions = el("div", null, "rw-tool-actions"); taskActions.append(read); task.append(taskActions, disclosure("任务保存说明", el("p", "研究任务保存在当前服务进程中，服务重启后记录不可恢复。"))); byId("research-task-slot").append(task);
    const runtime = el("div"); runtime.append(toolNotice("research-message")); const state = el("div"); state.id = "research-runtime"; runtime.append(state);
    const runtimeActions = el("div", null, "rw-tool-actions"); runtimeActions.append(action("刷新运行计数", event => busy(event.currentTarget, "research-message", loadRuntime))); runtime.append(runtimeActions); byId("research-runtime-slot").append(runtime);
    const actions = el("div", null, "rw-run-actions"); actions.id = "research-run-actions"; actions.hidden = true;
    const refresh = action("刷新任务", event => busy(event.currentTarget, "research-message", async () => { await refreshResearchRun(); scheduleRunPolling(); message("research-message", ""); })); refresh.id = "research-refresh";
    const cancel = action("取消任务", event => busy(event.currentTarget, "research-message", async () => {
      if (!currentRun || currentRunOwner !== owner()) throw new Error("请先读取当前账户任务。");
      stopRunPolling(); runSequence++;
      const run = await request(`/api/v1/research/runs/${encodeURIComponent(currentRun.run_id)}`, {method: "DELETE"}); renderResearchRun(run); await loadRuntime(); message("research-message", "任务取消结果已返回。");
    }), {write: true}); cancel.id = "research-cancel"; cancel.disabled = true; cancel.hidden = true; actions.append(refresh, cancel);
    const result = el("div"); result.id = "research-run-result"; result.hidden = true; byId("research-results-slot").append(actions, result);
    const stockReport = section("当前对话的个股详细报告"); stockReport.id = "research-stock-report"; stockReport.hidden = true;
    const reportContent = el("div"); reportContent.id = "research-stock-report-content"; stockReport.append(reportContent); byId("research-results-slot").append(stockReport); renderResearchDraft();
  }
  const ALGORITHMS = Object.freeze({regime: "市场波动环境", covariance: "资产联动风险", "five-factors": "市场风格因素"});
  const ALGORITHM_FIELDS = Object.freeze({low_variance: "低波动状态概率", high_variance: "高波动状态概率", MKT_RF: "市场超额收益", SMB: "规模因素", HML: "价值因素", RMW: "盈利因素", CMA: "投资因素"});
  let algorithmResult = null;
  let algorithmKind = "regime";
  let algorithmChart = null;
  let algorithmResize = null;
  let algorithmSequence = 0;
  let algorithmSubmitting = false;
  const ALGORITHM_DESCRIPTIONS = Object.freeze({
    regime: {purpose: "根据历史收益计算低波动、高波动两种状态的概率。", input: "按日期排列的收益序列与训练窗口。", result: "低波动、高波动的状态概率曲线。"},
    covariance: {purpose: "根据多项资产的历史收益，计算资产之间的协方差与相关性。", input: "至少两项资产在共同日期上的收益序列。", result: "收缩协方差矩阵与相关矩阵。"},
    "five-factors": {purpose: "根据形成集合的财务数据与月度收益，计算 Fama–French 五因子。", input: "形成集合、年度财务字段与月度收益。", result: "市场、规模、价值、盈利与投资五项因子序列。"},
  });
  function updateAlgorithmInputState() {
    const ready = Boolean(byId("algorithm-json").value.trim());
    byId("algorithm-compute").disabled = readOnly() || algorithmSubmitting || !ready;
    byId("algorithm-input-trigger").textContent = ready ? "查看或编辑数据" : "直接填写数据";
  }
  function updateAlgorithmDescription() {
    const kind = byId("algorithm-kind").value;
    const description = ALGORITHM_DESCRIPTIONS[kind];
    byId("algorithm-purpose").textContent = description.purpose;
    byId("algorithm-data-description").textContent = description.input;
    byId("algorithm-result-description").textContent = description.result;
    byId("research-algorithm-input-title").textContent = `${ALGORITHMS[kind]} · 输入数据`;
  }
  function destroyAlgorithmChart() { algorithmResize?.disconnect(); algorithmResize = null; algorithmChart?.remove(); algorithmChart = null; }
  function renderAlgorithmChart() {
    const container = byId("algorithm-chart"); if (!container) return;
    destroyAlgorithmChart(); container.replaceChildren();
    const data = algorithmResult;
    if (!data || data.status !== "CALCULATED" || algorithmKind === "covariance" || activeResearchTask !== "research-algorithms" || byId("research-workbench").hidden) return;
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
    output.append(el("h4", correlation ? "相关矩阵" : "收缩协方差矩阵"));
    output.append(table(["资产", ...data.assets], matrix.map((row, index) => [data.assets[index], ...row.map(value => {
      const cell = el("span", Number(value).toPrecision(6), value >= 0 ? "research-matrix-positive" : "research-matrix-negative"); return cell;
    })])));
  }
  function renderAlgorithmResult(data) {
    algorithmResult = data;
    const output = byId("algorithm-output"); output.replaceChildren(); output.hidden = false;
    output.append(el("h3", `${ALGORITHMS[algorithmKind]} · ${customerStatus(data.status)}`));
    const record = el("div"); record.append(el("p", `${data.source} · 时点 ${data.as_of} · ${data.method_version} · 输入快照 ${data.input_snapshot_id}`, "research-data-meta"));
    if (data.status !== "CALCULATED") {
      const descriptions = {INSUFFICIENT_RETURNS: "收益样本不足", DEGENERATE_TRAINING_RETURNS: "训练收益退化为常数", RESEARCH_DEPENDENCY_UNAVAILABLE: "研究算法依赖不可用", MODEL_NOT_CONVERGED: "模型未收敛", INSUFFICIENT_ASSETS: "资产数不足", INSUFFICIENT_ALIGNED_RETURNS: "共同日期的收益样本不足", ZERO_VARIANCE_ASSET: "存在零方差资产", FUNDAMENTAL_FIELDS_MISSING: "缺少五因子财务字段", INSUFFICIENT_FORMATION_UNIVERSE: "分组形成集合不足", EMPTY_2X3_PORTFOLIO: "存在空的 2×3 分组", RISK_FREE_RETURN_MISSING: "缺少无风险收益", FINANCIAL_POINT_IN_TIME_INVALID: "财报公告时点不符合形成期约束", MONTHS_MUST_BE_NONEMPTY_SORTED_UNIQUE: "月度记录须非空、排序且唯一", FORMATION_MEMBER_RETURN_MISSING: "形成集合成员缺少月度收益"};
      output.append(el("p", `暂无法分析：${descriptions[data.reason] || "资料或计算条件未满足"}。请补充或核对输入资料；具体字段可在计算明细中查看。`, "notice error"));
    } else {
      if (data.interpretation) record.append(el("p", data.interpretation));
      if (algorithmKind === "regime") output.append(el("p", `使用 ${data.sample_count} 条历史收益分析。图中 0–1 表示状态概率，1 代表 100%；高波动表示起伏较大，不代表上涨或下跌概率。`, "research-data-meta"));
      else if (algorithmKind === "five-factors") output.append(el("p", "观察市场、规模、价值、盈利和投资特征的表现。图中收益采用小数比例，0.01 代表 1%；本结果没有进行个人持仓收益归因。", "research-data-meta"));
      else {
        output.append(el("p", `输入包含 ${data.assets.length} 项资产、${data.sample_count} 个共同交易日。资产同时波动时，增加持仓数量不一定能降低组合风险；当前结果仅对应所导入的资产。`, "research-data-meta"));
        const actions = el("div", null, "research-action-row"); actions.append(action("协方差矩阵", () => renderMatrix(data)), action("相关矩阵", () => renderMatrix(data, true))); output.append(actions);
        const matrix = el("div"); matrix.id = "algorithm-matrix"; output.append(matrix); renderMatrix(data);
      }
    }
    const graph = el("div"); graph.id = "algorithm-chart"; graph.setAttribute("aria-label", "算法结果时间序列"); output.append(graph); renderAlgorithmChart();
    record.append(el("pre", JSON.stringify(data, null, 2), "research-original-text")); output.append(disclosure("数据来源、计算条件与完整结果", record)); updateWorkbenchResults();
  }
  function algorithmTemplate(kind) {
    const common = {source: "填写实际数据来源", as_of: new Date().toISOString()};
    if (kind === "regime") return {...common, training_size: 252, returns: []};
    if (kind === "covariance") return {...common, series: {"资产标识A": [], "资产标识B": []}};
    return {...common, monetary_unit: "CNY", universe_id: "填写形成集合标识", universe_complete: false, fundamentals: [], months: []};
  }
  function initializeAlgorithms() {
    const root = byId("algorithm-workspace"); if (!root) return;
    const row = el("div", null, "rw-algorithm-row"); row.append(field("algorithm-kind", "计算方法", {tag: "select", options: ALGORITHMS}));
    const file = el("input"); file.id = "algorithm-file"; file.type = "file"; file.accept = ".json,application/json"; file.hidden = true;
    row.append(action("导入数据", () => file.click()));
    const compute = action("开始计算", event => busy(event.currentTarget, "algorithm-message", async () => {
      algorithmSubmitting = true; updateAlgorithmInputState();
      try {
        destroyAlgorithmChart(); byId("algorithm-output").replaceChildren(); byId("algorithm-output").hidden = true; algorithmResult = null; updateWorkbenchResults();
        const sequence = ++algorithmSequence;
        const kind = byId("algorithm-kind").value;
        const result = await request(`/api/v1/research/algorithms/${kind}`, {method: "POST", body: parseJSON("algorithm-json")});
        if (sequence !== algorithmSequence || byId("algorithm-kind").value !== kind) return;
        algorithmKind = kind; renderAlgorithmResult(result); message("algorithm-message", "");
      } finally { algorithmSubmitting = false; }
    }), {primary: true, write: true}); compute.id = "algorithm-compute"; row.append(compute);
    const meta = el("div", null, "rw-input-meta");
    const trigger = action("直接填写数据", () => { showResearchDialog("research-algorithm-input-dialog"); trigger.setAttribute("aria-expanded", "true"); }, {quiet: true}); trigger.id = "algorithm-input-trigger"; trigger.setAttribute("aria-haspopup", "dialog"); trigger.setAttribute("aria-controls", "research-algorithm-input-dialog"); trigger.setAttribute("aria-expanded", "false");
    const fileLabel = el("span", null, "rw-file-label"); fileLabel.id = "algorithm-file-label"; fileLabel.hidden = true; meta.append(trigger, fileLabel);
    root.append(row, file, meta, notice("algorithm-message"));
    const input = byId("research-algorithm-input-slot");
    const payload = field("algorithm-json", "输入 JSON", {tag: "textarea"}); payload.querySelector("textarea").rows = 13;
    input.append(payload, action("载入空输入结构", () => { byId("algorithm-json").value = JSON.stringify(algorithmTemplate(byId("algorithm-kind").value), null, 2); file.value = ""; fileLabel.hidden = true; updateAlgorithmInputState(); message("algorithm-message", "已载入字段结构，请填写数据。"); }), el("p", "收益采用小数比例，例如 1% 写为 0.01。填写数据来源与截止时点。", "research-data-meta"));
    input.append(disclosure("输入字段与计算条件", table(["算法", "输入结构", "最低条件", "时点与覆盖"], [
      ["两状态模型", "returns: [{time,value}]；training_size", "训练窗口至少 252；收益日期排序唯一", "as_of 之后的收益拒绝；只展示训练窗口末端起的过滤概率"],
      ["协方差收缩", "series: {资产标识: [{time,value}]} ", "至少 2 资产、60 个共同日期；非零方差", "使用日期交集；不填补缺失收益"],
      ["五因子年度", "monetary_unit: CNY；fundamentals：security_id、formation_year、fiscal_year、published_at；两期市值、账面权益、收入、成本、费用、利息、两期资产", "全部财务字段及统一人民币单位必需；2×3 分组不能为空", "前一年财报在形成年 6 月末前已公告"],
      ["五因子月度", "months: [{month,risk_free_return,securities:[{security_id,total_return,beginning_market_cap}]}]；universe_id", "形成集合成员有月收益、期初市值及无风险收益", "7 月重组；输入集合不能冒充全市场或官方美国因子"],
    ])));
    const output = el("div"); output.id = "algorithm-output"; output.hidden = true; byId("algorithm-results-slot").append(output);
    byId("algorithm-json").addEventListener("input", updateAlgorithmInputState);
    byId("algorithm-kind").addEventListener("change", () => { algorithmSequence++; algorithmResult = null; destroyAlgorithmChart(); output.replaceChildren(); output.hidden = true; updateAlgorithmDescription(); updateAlgorithmInputState(); updateWorkbenchResults(); message("algorithm-message", byId("algorithm-json").value.trim() ? "计算方法已切换，请检查输入字段。" : ""); });
    file.addEventListener("change", async event => {
      const selected = event.target.files[0]; if (!selected) return;
      try { if (selected.size > 8 * 1024 * 1024) throw new Error("JSON 文件不得超过 8 MiB。"); const text = await selected.text(); JSON.parse(text); byId("algorithm-json").value = text; fileLabel.textContent = selected.name; fileLabel.hidden = false; updateAlgorithmInputState(); message("algorithm-message", ""); }
      catch (error) { message("algorithm-message", error.message || "JSON 文件格式无效。", true); }
    });
    updateAlgorithmDescription(); updateAlgorithmInputState();
  }
  initializeKnowledge();
  initializeResearch();
  initializeAlgorithms();
  initializeWorkbench();
  document.addEventListener("prism:research-open", event => {
    const data = event.detail;
    if (!data || !RESEARCH_OPERATIONS[data.operation] || typeof data.subject !== "string") return;
    researchDraft = [{node_id: "linked-1", operation: data.operation, subject: data.subject, required_fields: data.required_fields || ["price"], dependencies: [], ...(data.query ? {query: data.query} : {})}];
    byId("research-template-subject").value = data.subject;
    renderResearchDraft(); message("research-message", `已载入 ${data.subject} 的研究输入。`); window.location.hash = "live-research"; openResearchTools("custom");
  });
  document.addEventListener("prism:stock-report-open", event => {
    const content = event.detail?.content;
    if (!(content instanceof Element)) return;
    stockReportObserver?.disconnect();
    byId("research-stock-report").querySelector("h3").textContent = `${event.detail.subject || "当前对话"} · 个股详细报告`;
    const update = () => { byId("research-stock-report-content").replaceChildren(content.cloneNode(true)); byId("research-stock-report").hidden = false; updateWorkbenchResults(); };
    update(); stockReportObserver = new MutationObserver(update); stockReportObserver.observe(content, {childList: true, subtree: true, characterData: true});
  });

  function activate() {
    if (viewOwner !== owner()) resetAccountResults();
    stopRunPolling();
    const route = window.location.hash.slice(1);
    if (route !== "research-workbench" && !researchRoutes.includes(route)) {
      destroyAlgorithmChart(); document.querySelectorAll(".rw-dialog[open]").forEach(dialog => dialog.close()); return;
    }
    activeResearchTask = researchRoutes.includes(route) ? route : "live-research";
    for (const id of researchRoutes) byId(id).hidden = id !== activeResearchTask;
    document.querySelectorAll("[data-research-route]").forEach(tab => { const selected = tab.dataset.researchRoute === activeResearchTask; tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1; });
    updateWorkbenchResults();
    if (document.body.classList.contains("questionnaire-pending")) return;
    if (activeResearchTask === "research-algorithms") renderAlgorithmChart(); else destroyAlgorithmChart();
    if (activeResearchTask === "research-knowledge") loadKnowledge().catch(error => message("knowledge-message", error.message, true));
    if (activeResearchTask === "live-research") {
      if (currentRunOwner && currentRunOwner !== owner()) { currentRun = null; currentRunOwner = null; byId("research-run-result").replaceChildren(); byId("research-run-id").value = ""; byId("research-cancel").disabled = true; }
      if (!templateAvailable) loadResearchTemplate().catch(error => { byId("research-template-info").textContent = error.message; message("research-message", error.message, true); });
      if (currentRun) refreshResearchRun().then(scheduleRunPolling).catch(error => message("research-message", error.message, true));
    }
  }
  window.addEventListener("hashchange", activate);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopRunPolling(); else if (!byId("research-workbench").hidden && activeResearchTask === "live-research") activate(); });
  function resetAccountResults() {
    viewOwner = owner();
    accountEpoch++; knowledgeSequence++; runSequence++; algorithmSequence++;
    templateAvailable = false; byId("research-template-submit").disabled = true;
    stopRunPolling(); currentRun = null; currentRunOwner = null; knowledgeDocuments = []; knowledgeMatches = []; knowledgeAsOf = null; algorithmResult = null; destroyAlgorithmChart();
    stockReportObserver?.disconnect(); stockReportObserver = null; byId("research-stock-report-content").replaceChildren(); byId("research-stock-report").hidden = true;
    for (const id of ["knowledge-documents", "knowledge-matches", "knowledge-original", "research-run-result", "algorithm-output"]) byId(id)?.replaceChildren();
    for (const id of ["knowledge-matches", "knowledge-original", "research-run-result", "research-run-actions", "algorithm-output"]) byId(id).hidden = true;
    document.querySelectorAll(".rw-dialog[open]").forEach(dialog => dialog.close());
    for (const id of ["knowledge-message", "research-message", "algorithm-message"]) message(id, "");
    byId("research-run-id").value = ""; byId("research-cancel").disabled = true;
    updateAlgorithmInputState(); updateWorkbenchResults();
  }
  byId("load-events")?.addEventListener("click", resetAccountResults);
  let dark = document.body.classList.contains("prism-theme-dark");
  let workspacePending = document.body.classList.contains("questionnaire-pending");
  const themeObserver = new MutationObserver(() => {
    const nextPending = document.body.classList.contains("questionnaire-pending");
    if (workspacePending && !nextPending) { workspacePending = false; activate(); }
    const next = document.body.classList.contains("prism-theme-dark");
    if (next !== dark) { dark = next; renderAlgorithmChart(); }
  }); themeObserver.observe(document.body, {attributes: true, attributeFilter: ["class"]});
  window.addEventListener("pagehide", () => { stopRunPolling(); destroyAlgorithmChart(); stockReportObserver?.disconnect(); themeObserver.disconnect(); });
  activate();
})();
