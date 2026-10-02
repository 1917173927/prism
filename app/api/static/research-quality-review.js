/* Standalone review page: in-memory labels with preserved reviewer provenance. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const SCHEMA = "research-quality-review.v1";
  const REVIEW_METHODS = {HUMAN: "人工标注", AGENT_ASSISTED: "Agent 辅助标注", UNREVIEWED: "未评审", UNSPECIFIED: "未指定标注来源"};
  const SCENARIOS = {NORMAL: "正常", MISSING: "缺失", STALE: "过期", CONFLICT: "冲突", ISOLATION: "隔离", INJECTION: "注入"};
  let pack = null, current = 0;
  const node = (tag, text) => {const result = document.createElement(tag); if (text != null) result.textContent = text; return result;};
  const choices = {
    support: {SUPPORTED: "有依据支持", UNSUPPORTED: "无依据／与依据矛盾", UNCERTAIN: "待核验"},
    citation_support: {SUPPORTED: "引用支持此声明", UNSUPPORTED: "引用不支持此声明", UNCERTAIN: "待核验"},
    numeric_consistency: {CONSISTENT: "数字、单位、时点及容差一致", INCONSISTENT: "数字或口径不一致", UNVERIFIED: "尚未核验"},
    numeric_source_verified: {YES: "参考值已经独立核验", NO: "参考值未独立核验", UNCERTAIN: "待核验"},
    answerability: {SUFFICIENT: "依据充分，可回答", INSUFFICIENT: "依据不足", UNCERTAIN: "待核验"},
    refusal: {NOT_REFUSED: "未拒答", REASONABLE: "合理拒答", WRONG: "错误拒答"},
    isolation_time: {PASS: "未见跨用户／时点错误", FAIL: "存在跨用户／时点错误", UNCERTAIN: "待核验"},
  };
  function control(label, target, key, options = null) {
    const wrapper = node("label", label); const input = node(options ? "select" : "textarea");
    input.dataset.labelKey = key;
    if (options) {const empty = node("option", "未标注"); empty.value = ""; input.append(empty); for (const [value, text] of Object.entries(options)) {const option = node("option", text); option.value = value; input.append(option);}}
    input.value = target[key] || "";
    input.addEventListener(options ? "change" : "input", () => {target[key] = input.value || null; updateProgress();}); wrapper.append(input); return wrapper;
  }
  function validate(value) {
    if (!value || value.schema_version !== SCHEMA || !["REAL_CORPUS", "SYNTHETIC_FROZEN"].includes(value.corpus_kind) || typeof value.dataset_id !== "string" || !Array.isArray(value.items) || !value.items.length) throw new Error("评测包格式无效；请使用本页示例或空模板。");
    if (value.review_method != null && (typeof value.review_method !== "string" || !Object.hasOwn(REVIEW_METHODS, value.review_method))) throw new Error("标注来源须为 HUMAN / AGENT_ASSISTED / UNREVIEWED / UNSPECIFIED。");
    value.review_method ??= "UNSPECIFIED";
    const itemIds = new Set();
    for (const item of value.items) {
      if (!item || typeof item.id !== "string" || !item.id || itemIds.has(item.id) || typeof item.question !== "string" || typeof item.answer !== "string" || !Array.isArray(item.source_documents) || !Array.isArray(item.atomic_claims) || !Array.isArray(item.retrieved_evidence_ids) || !(item.relevant_evidence_ids === null || Array.isArray(item.relevant_evidence_ids))) throw new Error("题目字段、标识或证据数组无效。");
      itemIds.add(item.id); const documents = new Set(), claims = new Set();
      if (item.scenario != null && (typeof item.scenario !== "string" || !Object.hasOwn(SCENARIOS, item.scenario))) throw new Error("场景标识无效，须为NORMAL/MISSING/STALE/CONFLICT/ISOLATION/INJECTION或空。");
      for (const doc of item.source_documents) {if (!doc || typeof doc.id !== "string" || !doc.id || documents.has(doc.id) || typeof doc.title !== "string" || typeof doc.text !== "string") throw new Error("原文字段或标识无效。"); documents.add(doc.id);}
      for (const claim of item.atomic_claims) {
        if (!claim || typeof claim.id !== "string" || !claim.id || claims.has(claim.id) || typeof claim.text !== "string" || typeof claim.critical_financial_numeric !== "boolean" || !Array.isArray(claim.citation_ids) || claim.citation_ids.some(id => typeof id !== "string")) throw new Error("原子声明字段或标识无效。");
        claims.add(claim.id); claim.assessment ||= {};
        if (Array.isArray(claim.assessment) || typeof claim.assessment !== "object") throw new Error("声明标注必须是对象。");
      }
      item.annotation ||= {}; if (Array.isArray(item.annotation) || typeof item.annotation !== "object") throw new Error("问题标注必须是对象。");
    }
    return value;
  }
  function updateProgress() {
    const supported = pack.items.flatMap(item => item.atomic_claims).filter(claim => ["SUPPORTED", "UNSUPPORTED"].includes(claim.assessment.support)).length;
    const total = pack.items.reduce((count, item) => count + item.atomic_claims.length, 0);
    $("progress").textContent = `第 ${current + 1}／${pack.items.length} 题 · 依据标签 ${supported}／${total}；此计数不代表完整验收`;
  }
  function render() {
    const item = pack.items[current]; $("item-selector").value = String(current);
    $("message").textContent = `正在标注 ${item.id}。未填写的标签仍为未标注；操作计数不等于质量门槛通过。`;
    $("previous").disabled = current === 0; $("next").disabled = current === pack.items.length - 1;
    $("question").replaceChildren(node("h2", `${item.id} · 问题`), node("p", `场景：${item.scenario ? `${item.scenario} · ${SCENARIOS[item.scenario]}` : "未指定，将阻断金融门槛"}`), node("blockquote", item.question || "问题尚未录入"), node("h3", "待核验回答（原样留存）"), node("pre", item.answer || "回答尚未录入；不会自动生成"));
    $("documents").replaceChildren(node("h2", "冻结原文"));
    for (const doc of item.source_documents) {
      const article = node("article"); article.append(node("h3", `${doc.id} · ${doc.title || "标题待录入"}`), node("p", `来源：${doc.source_url || "未提供"}；公告时点：${doc.published_at || "未提供"}`), node("pre", doc.text || "原文尚未录入")); $("documents").append(article);
    }
    if (!item.source_documents.length) $("documents").append(node("p", "没有原文，不能标记为有依据支持。"));
    $("claims").replaceChildren(node("h2", "逐原子声明标注"));
    if (!item.atomic_claims.length) $("claims").append(node("p", "没有原子声明。须人工确认答案分解完整；不得通过金融门槛。"));
    for (const claim of item.atomic_claims) {
      const article = node("article"); article.dataset.claimId = claim.id;
      article.append(node("h3", claim.id), node("blockquote", claim.text || "声明尚未录入"), node("p", `引用标识：${claim.citation_ids.join("、") || "无"}；关键金融数值：${claim.critical_financial_numeric ? "是" : "否"}`));
      const grid = node("div"); grid.className = "grid"; grid.append(control("原文对声明的支持性", claim.assessment, "support", choices.support));
      if (claim.citation_ids.length) grid.append(control("引用是否确实支持声明", claim.assessment, "citation_support", choices.citation_support));
      if (claim.critical_financial_numeric) grid.append(control("关键数值一致性", claim.assessment, "numeric_consistency", choices.numeric_consistency), control("参考值真实性", claim.assessment, "numeric_source_verified", choices.numeric_source_verified), control("已核验参考值及字段精度／容差依据", claim.assessment, "numeric_reference"));
      grid.append(control("标注依据（原文位置或无依据原因，必填）", claim.assessment, "basis")); article.append(grid); $("claims").append(article);
    }
    $("question-labels").replaceChildren(node("h2", "问题、拒答与检索标注")); const grid = node("div"); grid.className = "grid";
    for (const [key, title] of Object.entries({answerability: "依据是否充分", refusal: "回答或拒答是否合理", isolation_time: "用户隔离及公告／过期时点检查"})) grid.append(control(title, item.annotation, key, choices[key]));
    grid.append(control("问题标注依据（必填）", item.annotation, "notes")); $("question-labels").append(grid);
    const relevant = node("label", "相关证据标识（每行一项，最多 10 项；未标注和确认无相关证据必须区分）");
    const input = node("textarea"); input.id = "relevant-evidence"; input.value = (item.relevant_evidence_ids || []).join("\n");
    input.addEventListener("input", () => {item.relevant_evidence_ids = input.value.trim() ? [...new Set(input.value.split(/\n/).map(value => value.trim()).filter(Boolean))] : null;}); relevant.append(input); $("question-labels").append(relevant);
    const noEvidence = node("button", "确认此题无相关证据"); noEvidence.type = "button"; noEvidence.addEventListener("click", () => {item.relevant_evidence_ids = []; input.value = ""; $("message").textContent = `${item.id} 已确认无相关证据；该题不进入 Recall 分母，但仍须核验拒答是否合理。`;}); $("question-labels").append(noEvidence, node("p", `召回前 10 项（原样顺序）：${item.retrieved_evidence_ids.slice(0, 10).join("、") || "空"}`));
    updateProgress();
  }
  $("import-file").addEventListener("change", async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error("评测包不得超过 8 MiB。");
      const candidate = validate(JSON.parse(await file.text())); pack = candidate; current = 0;
      $("dataset-meta").textContent = `${pack.dataset_id} · ${pack.corpus_kind} · 冻结时点 ${pack.frozen_at || "未冻结"} · ${pack.items.length} 题 · 标注来源 ${pack.review_method}（${REVIEW_METHODS[pack.review_method]}）`;
      $("reviewer-label").textContent = pack.review_method === "HUMAN" ? "人工标注者标识" : pack.review_method === "AGENT_ASSISTED" ? "Agent 辅助标注者标识（不构成人工签署）" : "标注者标识（来源未完成，不构成人工签署）";
      $("reviewer").value = pack.reviewer || ""; $("item-selector").replaceChildren(); pack.items.forEach((item, index) => {const option = node("option", `${index + 1}. ${item.id}`); option.value = String(index); $("item-selector").append(option);});
      $("workspace").hidden = false; $("export-json").disabled = false; render(); $("message").textContent = `已导入，标注来源为 ${pack.review_method}。导出保留此来源，修改标注者不会将 Agent 辅助标注升级为人工签署；所有空标签保持未标注。`;
    } catch (error) {$("message").textContent = `未导入：${error.message}`;}
  });
  $("reviewer").addEventListener("input", event => {pack.reviewer = event.target.value.trim();});
  $("item-selector").addEventListener("change", event => {current = Number(event.target.value); render();});
  $("previous").addEventListener("click", () => {current--; render();}); $("next").addEventListener("click", () => {current++; render();});
  $("export-json").addEventListener("click", () => {
    pack.reviewed_at = new Date().toISOString(); const url = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2) + "\n"], {type: "application/json"}));
    const link = node("a"); link.href = url; link.download = `quality-review-${pack.dataset_id.replace(/[^A-Za-z0-9_.-]/g, "_")}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("message").textContent = "已导出当前标注。导出不代表标注完整或金融门槛通过；请运行汇总工具。";
  });
})();
