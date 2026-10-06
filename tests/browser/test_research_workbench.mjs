import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8896";
const artifactRoot = path.resolve("output/research-workbench-integration");
await fs.mkdir(artifactRoot, {recursive: true});
const browserProfile = await fs.mkdtemp(path.join(artifactRoot, "browser-profile-"));
const browser = await puppeteer.launch({
  executablePath: process.env.PRISM_TEST_BROWSER || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  headless: true,
  userDataDir: browserProfile,
  args: ["--no-sandbox"],
});
const evidence = {checks: [], responses: [], geometry: [], limitations: []};
let page;
try {
  const context = await browser.createBrowserContext();
  page = await context.newPage();
  const errors = [];
  evidence.pageErrors = errors;
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    const pathname = new URL(response.url()).pathname;
    if (pathname.startsWith("/api/v1/")) evidence.responses.push({path: pathname, method: response.request().method(), status: response.status()});
  });
  await page.setCacheEnabled(false);
  await page.setViewport({width: 1440, height: 1000});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  if (new URL(page.url()).pathname === "/login") {
    const password = randomUUID() + randomUUID();
    await page.click("#register-tab");
    await page.type("#username", `research-workbench-${Date.now()}`);
    await page.type("#password", password);
    await page.type("#confirmation", password);
    await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  }
  await page.waitForSelector("body:not(.questionnaire-pending)", {timeout: 30000});
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await page.click("#welcome-later");
  assert.equal(await page.evaluate(() => window.PRISM_PAGES_SNAPSHOT === true), false);
  const fill = async (id, value) => page.$eval(`#${id}`, (node, value) => { node.value = value; node.dispatchEvent(new Event("input", {bubbles: true})); node.dispatchEvent(new Event("change", {bubbles: true})); }, value);
  const navigate = async route => {
    await page.evaluate(route => { location.hash = route; }, route);
    await page.waitForFunction(route => document.getElementById(route).checkVisibility(), {}, route);
  };
  const waitClosed = id => page.waitForFunction(id => !document.getElementById(id).open, {}, id);
  const closeToolsOutside = async () => {
    const bounds = await page.$eval("#research-tools-dialog", node => { const rect = node.getBoundingClientRect(); return {left: rect.left, top: rect.top}; });
    await page.mouse.click(Math.max(1, bounds.left / 2), Math.max(80, bounds.top + 120));
    await waitClosed("research-tools-dialog");
  };
  await page.click('.nav-item[href="#research-workbench"]');
  await page.waitForSelector("#research-workbench:not([hidden])");
  assert.equal(await page.$$('.nav-item[href="#research-workbench"]').then(items => items.length), 1);
  assert.equal(await page.$$('.nav-item:is([href="#research-knowledge"], [href="#live-research"], [href="#research-algorithms"])').then(items => items.length), 0);
  await page.waitForFunction(() => !document.getElementById("research-template-submit").disabled);
  assert.equal(await page.$eval("#live-research", node => node.checkVisibility()), true);
  assert.equal(await page.$eval("#research-run-result", node => node.checkVisibility()), false);
  evidence.typography = await page.$eval("#live-research .rw-task-summary dd", node => { const style = getComputedStyle(node); return {fontSize: style.fontSize, fontWeight: style.fontWeight, lineHeight: style.lineHeight, color: style.color, fontFamily: style.fontFamily}; });
  const bodyFont = await page.$eval("body", node => getComputedStyle(node).fontFamily);
  assert.equal(evidence.typography.fontFamily, bodyFont);
  assert.ok((await page.$$eval(".rw-task-summary dd", nodes => nodes.map(node => { const style = getComputedStyle(node); return {fontFamily: style.fontFamily, fontSize: parseFloat(style.fontSize)}; }))).every(style => style.fontFamily === bodyFont && style.fontSize >= 15));
  evidence.checks.push("统一入口与默认任务");

  await page.focus("#research-tab-live");
  await page.keyboard.press("ArrowRight");
  await page.waitForSelector("#research-knowledge:not([hidden])");
  assert.equal(await page.evaluate(() => document.activeElement.id), "research-tab-knowledge");
  await page.keyboard.press("End");
  await page.waitForSelector("#research-algorithms:not([hidden])");
  await page.keyboard.press("Home");
  await page.waitForSelector("#live-research:not([hidden])");
  evidence.checks.push("任务标签键盘操作");
  await navigate("research-workbench");
  await page.click("#research-tab-knowledge");
  await page.waitForSelector("#research-knowledge:not([hidden])");
  await page.evaluate(() => history.back());
  await page.waitForFunction(() => location.hash === "#research-workbench" && document.getElementById("live-research").checkVisibility());
  await page.evaluate(() => history.forward());
  await page.waitForFunction(() => location.hash === "#research-knowledge" && document.getElementById("research-knowledge").checkVisibility());
  await navigate("live-research");
  evidence.checks.push("浏览器前进与返回");

  await fill("research-template-subject", "600519.SH");
  await page.click("#research-parameter-trigger");
  await fill("research-budget", "30");
  await page.click('#research-parameter-form button[type="submit"]');
  await waitClosed("research-parameter-dialog");
  assert.match(await page.$eval("#research-parameter-summary", node => node.textContent), /30 秒/);
  await page.click("#research-parameter-trigger");
  await fill("research-budget", "15");
  await page.keyboard.press("Escape");
  await waitClosed("research-parameter-dialog");
  assert.equal(await page.$eval("#research-budget", node => node.value), "30");
  await page.click("#research-tab-knowledge");
  await page.waitForSelector("#research-knowledge:not([hidden])");
  await page.click("#research-tab-live");
  await page.waitForSelector("#live-research:not([hidden])");
  assert.equal(await page.$eval("#research-template-subject", node => node.value), "600519.SH");
  evidence.checks.push("参数应用、取消与任务输入保留");

  await page.click("#research-tools-trigger");
  assert.equal(await page.$eval("#research-tools-maintenance", node => node.open), false);
  assert.equal(await page.$eval("#research-tool-task", node => node.checkVisibility()), false);
  await page.click("#research-tool-custom");
  await page.type('#research-node-editor input[aria-label="研究步骤 1 研究标的"]', "600519.SH");
  assert.equal(await page.$eval("#research-node-editor details", node => node.open), false);
  await page.click('#research-node-editor input[aria-label="研究步骤 1 研究标的"]');
  assert.equal(await page.$eval("#research-tools-dialog", node => node.open), true);
  const inside = await page.$eval('#research-node-editor input[aria-label="研究步骤 1 研究标的"]', node => { const rect = node.getBoundingClientRect(); return {x: rect.left + 12, y: rect.top + 14}; });
  await page.mouse.move(inside.x, inside.y); await page.mouse.down(); await page.mouse.move(20, inside.y); await page.mouse.up();
  assert.equal(await page.$eval("#research-tools-dialog", node => node.open), true);
  await closeToolsOutside();
  assert.equal(await page.evaluate(() => document.activeElement.id), "research-tools-trigger");
  assert.equal(await page.$eval("body", node => node.classList.contains("research-dialog-open")), false);
  await page.click("#research-tools-trigger"); await page.click("#research-tool-custom");
  assert.equal(await page.$eval('#research-node-editor input[aria-label="研究步骤 1 研究标的"]', node => node.value), "600519.SH");
  await page.click("#research-add-node");
  assert.equal(await page.$$(".rw-node-card").then(items => items.length), 2);
  await page.click(".rw-node-card:last-child .rw-node-heading button");
  assert.equal(await page.$$(".rw-node-card").then(items => items.length), 1);
  await page.click("#research-tools-back");
  assert.equal(await page.$eval("#research-tools-menu", node => node.checkVisibility()), true);
  await page.keyboard.press("Escape"); await waitClosed("research-tools-dialog");
  evidence.checks.push("工具分组、节点编辑、外部关闭、内部拖动、Escape、焦点恢复");

  await page.click("#research-tools-trigger"); await page.click("#research-tool-materials");
  const documentPath = path.resolve("docs/plans/2026-10-04-research-workbench-ui.md");
  const documentText = await fs.readFile(documentPath, "utf8");
  const published = (await fs.stat(documentPath)).mtime;
  const localPublished = new Date(published.getTime() - published.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  await fill("knowledge-title", "研究工作台界面实施说明");
  await fill("knowledge-source", "Prism 项目文档");
  await fill("knowledge-published", localPublished);
  await page.select("#knowledge-kind", "METHOD");
  await (await page.$("#knowledge-file")).uploadFile(documentPath);
  await page.click("#knowledge-upload");
  await page.waitForFunction(() => document.getElementById("knowledge-message").textContent.includes("资料已登记"), {timeout: 30000});
  await closeToolsOutside();
  await navigate("research-knowledge");
  await fill("knowledge-query", "研究工作台");
  await page.click("#knowledge-search");
  await page.waitForSelector("#knowledge-matches .research-result-card", {timeout: 30000});
  assert.equal(await page.$eval("#knowledge-matches .research-result-card details", node => node.open), false);
  await page.click("#knowledge-matches .research-result-card > .research-action-row button");
  await page.waitForSelector("#knowledge-original-dialog[open]");
  assert.equal(await page.$eval("#knowledge-original > h3", node => node.textContent), "研究工作台界面实施说明");
  assert.equal(await page.$eval("#knowledge-original > pre", node => node.textContent), documentText);
  await page.keyboard.press("Escape"); await waitClosed("knowledge-original-dialog");
  await page.click("#knowledge-matches .research-result-card details > summary");
  await page.click("#knowledge-matches .research-result-card details button");
  await page.waitForFunction(() => document.getElementById("knowledge-message").textContent.includes("引用与该版本原文完全对应"));
  await page.click("#knowledge-filter-trigger");
  await fill("knowledge-search-period", "2026");
  await page.click("#knowledge-filter-trigger");
  assert.equal(await page.$eval("#knowledge-filters", node => node.checkVisibility()), false);
  assert.match(await page.$eval("#knowledge-filter-summary", node => node.textContent), /2026/);
  evidence.checks.push("真实项目文档上传、检索、原文核对、引用核验与筛选");

  await navigate("research-algorithms");
  assert.equal(await page.$eval("#algorithm-compute", node => node.disabled), true);
  for (const [kind, purpose, result] of [["regime", "状态", "概率曲线"], ["covariance", "相关性", "相关矩阵"], ["five-factors", "Fama", "因子序列"]]) {
    await page.select("#algorithm-kind", kind);
    assert.match(await page.$eval("#algorithm-purpose", node => node.textContent), new RegExp(purpose));
    assert.match(await page.$eval("#algorithm-result-description", node => node.textContent), new RegExp(result));
  }
  await page.click("#algorithm-input-trigger");
  assert.equal(await page.$eval("#research-algorithm-input-slot details", node => node.open), false);
  await fill("algorithm-json", "{}");
  await page.click('[data-close-research-dialog="research-algorithm-input-dialog"].rw-primary');
  await waitClosed("research-algorithm-input-dialog");
  const algorithmResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/research/algorithms/five-factors" && response.request().method() === "POST");
  await page.click("#algorithm-compute");
  assert.equal((await algorithmResponse).status(), 422);
  await page.waitForFunction(() => document.getElementById("algorithm-message").classList.contains("error"));
  assert.equal(await page.$eval("#algorithm-output", node => node.checkVisibility()), false);
  evidence.checks.push("三种算法说明、数据编辑及真实接口输入校验");

  await navigate("live-research");
  const templateResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/research/runs/from-template" && response.request().method() === "POST");
  await page.click("#research-template-submit");
  assert.equal((await templateResponse).status(), 202);
  await page.waitForSelector("#research-run-result:not([hidden])", {timeout: 30000});
  await page.waitForFunction(() => ["研究未完成", "研究完成", "研究已取消"].includes(document.querySelector("#research-run-result > h3")?.textContent), {timeout: 30000});
  assert.equal(await page.$eval("#research-cancel", node => node.hidden), true);
  const runId = await page.$eval("#research-run-id", node => node.value);
  assert.ok(runId);
  await page.click("#research-tools-trigger");
  await page.click("#research-tools-maintenance > summary"); await page.click("#research-tool-task");
  await page.click("#research-load-run"); await waitClosed("research-tools-dialog");
  assert.equal(await page.$eval("#research-run-id", node => node.value), runId);
  assert.equal(await page.$eval("#research-run-result details", node => node.open), false);
  evidence.checks.push("真实模板任务提交、终态轮询与读取任务");
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("body:not(.questionnaire-pending)", {timeout: 30000});
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await page.click("#welcome-later");
  await page.waitForFunction(() => !document.getElementById("research-template-submit").disabled, {timeout: 15000});
  evidence.checks.push("原研究链接直接刷新");

  for (const [width, height] of [[1440, 1000], [1024, 900], [390, 844]]) {
    await page.setViewport({width, height});
    for (const route of ["live-research", "research-knowledge", "research-algorithms"]) {
      await navigate(route);
      const geometry = await page.evaluate(() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth, cardWidth: document.querySelector(".rw-card").getBoundingClientRect().width}));
      assert.ok(geometry.scrollWidth <= geometry.width, JSON.stringify({route, ...geometry}));
      assert.ok(geometry.cardWidth <= geometry.width, JSON.stringify({route, ...geometry}));
      evidence.geometry.push({route, ...geometry});
    }
    await page.click("#research-tools-trigger");
    await page.waitForSelector("#research-tools-dialog[open]");
    const bounds = await page.$eval("#research-tools-dialog", node => { const rect = node.getBoundingClientRect(); return {left: rect.left, right: rect.right, width: innerWidth}; });
    assert.ok(bounds.left >= 0 && bounds.right <= bounds.width, JSON.stringify(bounds));
    await closeToolsOutside();
  }
  evidence.checks.push("1440、1024、390 像素宽度与侧栏关闭");
  await page.setViewport({width: 1440, height: 1000});
  await page.click(".topbar-more-menu > summary");
  await page.click("#theme-toggle");
  await page.waitForSelector("body.prism-theme-dark");
  const darkColors = await page.evaluate(() => ({body: getComputedStyle(document.body).color, tab: getComputedStyle(document.querySelector('.rw-task-tab[aria-selected="true"]')).color, background: getComputedStyle(document.querySelector('.rw-task-tab[aria-selected="true"]')).backgroundColor}));
  assert.equal(darkColors.tab, darkColors.body);
  assert.notEqual(darkColors.tab, darkColors.background);
  if (!(await page.$eval(".topbar-more-menu", node => node.open))) await page.click(".topbar-more-menu > summary");
  await page.click("#theme-toggle");
  await page.waitForSelector("body:not(.prism-theme-dark)");
  if (await page.$eval(".topbar-more-menu", node => node.open)) await page.click(".topbar-more-menu > summary");
  evidence.checks.push("研究区域主题切换");
  await navigate("copilot");
  await page.click("#home-model-trigger");
  await page.waitForFunction(() => getComputedStyle(document.getElementById("llm-config-modal")).display !== "none");
  await page.select("#llm-provider-select", "openai");
  assert.match(await page.$eval("#llm-base-url-input", node => node.value), /openai/);
  assert.ok(await page.$eval("#llm-model-input", node => node.value));
  await page.select("#llm-provider-select", "deepseek");
  assert.match(await page.$eval("#llm-base-url-input", node => node.value), /deepseek/);
  await page.click("#close-llm-config-modal-btn");
  assert.equal(await page.$eval("#copilot-natural-input", node => node.checkVisibility()), true);
  await fill("copilot-natural-input", "请说明研究工作台可以处理哪些任务。");
  const chatResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/copilot/chat" && response.request().method() === "POST");
  await page.click("#copilot-submit-query");
  evidence.chatStatus = (await chatResponse).status();
  await page.waitForFunction(() => !document.getElementById("copilot-submit-query").disabled, {timeout: 30000});
  evidence.checks.push("原对话入口、模型服务切换与配置弹窗");
  evidence.limitations.push("本次使用独立数据库与受控测试资料；真实模型回答、真实金融输入及上游配额未重新验收。");
  assert.deepEqual(errors, []);
  evidence.pageErrors = errors;
  evidence.browser = await browser.version();
  evidence.passed = true;
  await fs.writeFile(path.join(artifactRoot, "browser-evidence.json"), JSON.stringify(evidence, null, 2) + "\n");
  process.stdout.write(JSON.stringify({passed: true, checks: evidence.checks, geometry: evidence.geometry, limitations: evidence.limitations}, null, 2) + "\n");
} finally {
  try {
    if (page && !page.isClosed()) evidence.endState = await page.evaluate(() => ({url: location.href, route: location.hash, dialogs: [...document.querySelectorAll("dialog[open]")].map(node => node.id), modelDialogDisplay: document.getElementById("llm-config-modal") ? getComputedStyle(document.getElementById("llm-config-modal")).display : null}));
    await fs.writeFile(path.join(artifactRoot, "browser-evidence.json"), JSON.stringify(evidence, null, 2) + "\n");
  } finally { await browser.close(); }
}
