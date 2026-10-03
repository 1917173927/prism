import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import {mkdir, mkdtemp, readFile, writeFile} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8019";
const executablePath = process.env.PRISM_TEST_BROWSER || "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const root = fileURLToPath(new URL("../../", import.meta.url));
const output = path.join(root, "output/portfolio-disclosure");
await mkdir(output, {recursive: true});
const browserDirectory = await mkdtemp(path.join(output, "browser-"));
const temporaryDirectory = path.join(browserDirectory, "temporary");
await mkdir(temporaryDirectory);
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: path.join(browserDirectory, "profile"), env: {...process.env, TMPDIR: temporaryDirectory}});
const evidence = {requests: [], geometries: [], checks: []};

try {
  const page = await browser.newPage();
  page.setDefaultTimeout(60000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    const pathname = new URL(response.url()).pathname;
    if (pathname.includes("portfolio")) evidence.requests.push({path: pathname, method: response.request().method(), status: response.status()});
  });
  const waitResponse = (pathname, method = "GET") => page.waitForResponse(response =>
    new URL(response.url()).pathname === pathname && response.request().method() === method);
  const visible = selector => page.$eval(selector, node => node.getClientRects().length > 0);
  const text = selector => page.$eval(selector, node => node.textContent.trim());
  const amount = value => `¥ ${Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  async function api(pathname, method = "GET", body = undefined) {
    return page.evaluate(async ({pathname, method, body}) => {
      const response = await fetch(pathname, {method,
        headers: {"X-Owner-ID": document.documentElement.dataset.prismOwner, "Content-Type": "application/json"},
        ...(body === undefined ? {} : {body: JSON.stringify(body)})});
      const data = await response.json();
      if (!response.ok) throw new Error(`${pathname}: ${response.status} ${JSON.stringify(data)}`);
      return data;
    }, {pathname, method, body});
  }
  async function more(button) {
    await page.click("#portfolio-page-more > summary");
    await page.click(button);
  }
  async function waitReport(count) {
    await page.waitForFunction(expected => document.querySelector("#overview-position-count").textContent === String(expected)
      && !document.querySelector("#portfolio-report-card").hidden
      && !document.querySelector("#portfolio-source-line").hidden, {}, count);
    return api("/api/v1/advisor/portfolio/report");
  }
  async function confirmProfile() {
    const context = await api("/api/v1/auth/context");
    const template = await api("/api/v1/advisor/profile/questionnaire-template");
    const answers = template.questions.map(question => question.question_type === "SCORE"
      ? {question_id: question.question_id, score: 3}
      : {question_id: question.question_id, selected_option_ids: [question.options[0].option_id]});
    await api("/api/v1/advisor/profile/questionnaire/confirm", "POST", {
      schema_version: "questionnaire-confirmation-request.v1", owner_id: context.owner_id,
      confirmed_at: new Date().toISOString(), answers});
  }

  await page.setViewport({width: 1440, height: 900});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  assert.equal(new URL(page.url()).pathname, "/login");
  const password = randomUUID() + randomUUID();
  await page.click("#register-tab");
  await page.type("#username", `portfolio-ui-${Date.now()}`);
  await page.type("#password", password);
  await page.type("#confirmation", password);
  await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  await page.waitForSelector("body:not(.questionnaire-pending)");
  await page.waitForFunction(() => document.documentElement.dataset.prismMode === "LIVE");
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await page.click("#welcome-later");
  const home = await page.$eval("#home-navigation", node => ({height: node.getBoundingClientRect().height, x: node.getBoundingClientRect().x}));
  await page.click('.nav-section-primary a[href="#overview"]');
  await page.waitForSelector("#portfolio-empty:not([hidden])");
  assert.equal(await visible("#home-history-sidebar"), false);
  assert.equal(await visible("#workspace-page-tabs"), false);
  assert.equal(await visible("#portfolio-page-more"), false);
  assert.equal(await visible("#portfolio-position-rows"), false);
  assert.equal(await page.$$eval("#overview button.primary", nodes => nodes.filter(node => node.getClientRects().length).length), 1);
  assert.deepEqual(await page.$eval("#home-navigation", node => ({height: node.getBoundingClientRect().height, x: node.getBoundingClientRect().x})), home);
  evidence.checks.push("空持仓单一入口与共用导航");
  console.log(evidence.checks.at(-1));

  await page.click("#portfolio-empty [data-open-portfolio]");
  await page.waitForSelector("#portfolio-modal[open]");
  assert.equal(await page.$$eval('.portfolio-modal-tabs [role="tab"]', nodes => nodes.length), 3);
  await page.focus("#tab-btn-ocr");
  await page.keyboard.press("End");
  assert.equal(await page.$eval("#tab-btn-manual", node => node.getAttribute("aria-selected")), "true");
  await page.keyboard.press("ArrowLeft");
  assert.equal(await page.$eval("#tab-btn-text", node => node.getAttribute("aria-selected")), "true");
  await page.type("#portfolio-natural-textarea", "持有100股贵州茅台，买入均价1400元，现金50000元");
  const parsed = waitResponse("/api/v1/copilot/parse-portfolio", "POST");
  const saved = waitResponse("/api/v1/copilot/validate-portfolio-ocr", "POST");
  await page.click("#btn-parse-portfolio");
  const parsedResponse = await parsed;
  assert.equal(parsedResponse.status(), 200);
  const parsedData = await parsedResponse.json();
  assert.equal(parsedData.status, "SUCCESS", JSON.stringify(parsedData));
  assert.equal((await saved).status(), 200);
  await page.waitForFunction(() => !document.querySelector("#portfolio-modal").open);
  let report = await waitReport(1);
  assert.equal(report.data_mode, "LIVE");
  assert.equal(report.profile, null);
  assert.equal(await text("#overview-portfolio-aum"), amount(report.holdings_value_cny));
  assert.equal(await text("#overview-benchmark-val"), amount(report.cumulative_pnl_cny));
  assert.match(await text("#portfolio-analysis-status-title"), /投资者画像/);
  assert.equal(await visible("#portfolio-profile-entry"), true);
  assert.equal(await visible("#portfolio-analysis-retry"), false);
  assert.equal(await visible("#portfolio-empty"), false);
  assert.equal(await page.$$eval("#portfolio-report-card .portfolio-key-figures dd", nodes => nodes.length), 2);
  assert.equal(await page.$$eval("#portfolio-report-card svg.portfolio-asset-pie", nodes => nodes.length), 1);
  assert.equal(await page.$$eval("#overview table", nodes => nodes.filter(node => node.getClientRects().length).length), 0);
  evidence.checks.push("文字解析、保存与报告金额一致；缺失画像可见");
  console.log(evidence.checks.at(-1));

  await page.click("#portfolio-details-entry");
  assert.equal(await page.$$eval("#portfolio-analysis-drawer .portfolio-disclosure[open]", nodes => nodes.length), 0);
  await page.click("#portfolio-risk-details > summary");
  assert.match(await text("#portfolio-report-concentration-summary"), /集中度指数/);
  await page.click("#portfolio-pnl-details > summary");
  await page.waitForFunction(() => !document.querySelector("#portfolio-risk-details").open);
  assert.equal(await page.$$eval("#portfolio-analysis-drawer .portfolio-disclosure[open]", nodes => nodes.length), 1);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector("#portfolio-analysis-drawer").open);
  await page.waitForFunction(() => !document.body.classList.contains("portfolio-dialog-open"));
  assert.equal(await page.evaluate(() => document.activeElement.id), "portfolio-details-entry");
  assert.equal(await page.$eval("body", node => node.classList.contains("portfolio-dialog-open")), false);
  await more("#portfolio-manage-entry");
  assert.equal(await page.$eval("#portfolio-holdings-details", node => node.open), true);
  await page.click("#portfolio-position-rows button");
  await page.waitForSelector("#portfolio-diagnosis-drawer[open]");
  assert.match(await text("#portfolio-diagnosis-code"), /600519.SH/);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector("#portfolio-diagnosis-drawer").open);
  assert.equal(await page.$eval("#portfolio-analysis-drawer", node => node.open), true);
  assert.equal(await page.$eval("body", node => node.classList.contains("portfolio-dialog-open")), true);
  await page.click("#portfolio-add-entry");
  assert.equal(await page.$eval("#tab-btn-manual", node => node.getAttribute("aria-selected")), "true");
  await page.type('#manual-position-form [name="code"]', "002185");
  await page.type('#manual-position-form [name="quantity"]', "100");
  await page.type('#manual-position-form [name="cost"]', "15.3");
  const replacement = waitResponse("/api/v1/advisor/portfolio/current", "PUT");
  await page.click('#manual-position-form [type="submit"]');
  assert.equal((await replacement).status(), 200);
  report = await waitReport(2);
  assert.ok(report.positions.some(position => position.asset_id === "002185.SZ"));
  await page.click("#portfolio-add-entry");
  await page.type('#manual-position-form [name="code"]', "002185");
  await page.type('#manual-position-form [name="quantity"]', "100");
  await page.type('#manual-position-form [name="cost"]', "15.3");
  await page.click('#manual-position-form [type="submit"]');
  await page.waitForFunction(() => document.querySelector("#manual-position-error").textContent.includes("已在持仓中"));
  assert.equal((await api("/api/v1/advisor/portfolio/report")).position_count, 2);
  await page.click("#manual-position-cancel");
  await page.click("#portfolio-details-close");
  evidence.checks.push("折叠互斥、焦点恢复、单项诊断、手动添加及重复持仓拦截");
  console.log(evidence.checks.at(-1));

  await confirmProfile();
  const startupHealth = waitResponse("/api/v1/advisor/portfolio-health", "POST");
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("body:not(.questionnaire-pending):not(.questionnaire-required)");
  assert.equal((await startupHealth).status(), 200);
  report = await waitReport(2);
  assert.ok(report.profile);
  assert.equal(await visible("#portfolio-profile-entry"), false);
  if (report.concentration.single_asset_verdict === "OVERBOUND") {
    assert.equal(await visible("#portfolio-attention-entry"), true);
    assert.notEqual(await text("#portfolio-report-headline"), "当前组合在已确认规则下未发现明显超限");
  }
  console.log("读取已保存画像与持仓，准备更新分析");
  const refreshed = waitResponse("/api/v1/advisor/portfolio/refresh", "POST");
  await more("#btn-run-full-overview-check");
  const refreshResponse = await refreshed;
  console.log("后端已返回持仓更新响应");
  assert.equal(refreshResponse.status(), 200);
  const refreshData = await refreshResponse.json();
  console.log("已读取持仓更新结果");
  assert.ok(["COMPLETE", "REVIEW_REQUIRED"].includes(refreshData.status));
  evidence.refreshStatus = refreshData.status;
  await page.waitForFunction(() => !document.querySelector("#btn-run-full-overview-check").disabled);
  report = await waitReport(2);
  assert.equal(await text("#overview-portfolio-aum"), amount(report.holdings_value_cny));
  await more("#portfolio-report-info-entry");
  const reportTime = await page.evaluate(value => new Date(value).toLocaleString("zh-CN"), report.source_as_of);
  assert.ok((await text("#portfolio-report-meta")).includes(reportTime));
  await page.click("#portfolio-details-close");
  const session = await browser.target().createCDPSession();
  await session.send("Browser.setDownloadBehavior", {behavior: "allowAndName", downloadPath: output, eventsEnabled: true});
  const downloaded = new Promise((resolve, reject) => {
    const timer = setTimeout(() => { session.off("Browser.downloadProgress", progress); reject(new Error("报告下载未完成")); }, 10000);
    function progress(event) {
      if (!["completed", "canceled"].includes(event.state)) return;
      clearTimeout(timer);
      session.off("Browser.downloadProgress", progress);
      if (event.state === "completed") resolve(event);
      else reject(new Error("报告下载已取消"));
    }
    session.on("Browser.downloadProgress", progress);
  });
  await more("#portfolio-export");
  const download = await downloaded;
  const exported = await readFile(path.join(output, download.guid), "utf8");
  assert.ok(exported.includes(report.report_id));
  assert.ok(exported.includes("600519.SH"));
  await session.detach();
  evidence.checks.push("画像对照、真实刷新与报告导出");
  console.log(evidence.checks.at(-1));

  for (const section of ["portfolio-optimization", "portfolio-rebalancing", "scenario-simulation"]) {
    await page.click("#portfolio-details-entry");
    await page.click("#portfolio-more-details > summary");
    await page.click(`.portfolio-tool-links a[href="#${section}"]`);
    await page.waitForSelector(`#${section}:not([hidden])`);
    await page.waitForFunction(() => !document.querySelector("#portfolio-analysis-drawer").open
      && !document.body.classList.contains("portfolio-dialog-open"));
    await page.click('.nav-section-primary a[href="#overview"]');
    await waitReport(2);
  }
  evidence.checks.push("更多分析的三个业务入口与返回导航");
  console.log(evidence.checks.at(-1));

  for (const width of [320, 390, 768, 1440]) {
    await page.setViewport({width, height: 900});
    assert.equal(await visible("#home-history-show"), false);
    const geometry = await page.evaluate(() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth, cardWidth: document.querySelector("#portfolio-report-card").getBoundingClientRect().width}));
    assert.ok(geometry.documentWidth <= width + 1 && geometry.bodyWidth <= width + 1, JSON.stringify(geometry));
    await page.click("#portfolio-details-entry");
    const drawer = await page.$eval("#portfolio-analysis-drawer", node => ({left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right, width: node.getBoundingClientRect().width, scrollWidth: node.scrollWidth}));
    assert.ok(drawer.left >= 0 && drawer.right <= width + 1 && drawer.scrollWidth <= drawer.width + 1, JSON.stringify(drawer));
    await page.click("#portfolio-holdings-details > summary");
    assert.equal(await page.$eval("#portfolio-analysis-drawer", node => node.scrollWidth <= node.clientWidth), true);
    await page.click("#portfolio-details-close");
    evidence.geometries.push({...geometry, drawer});
  }
  evidence.checks.push("四种窗口尺寸的主页面与详情窗口");
  console.log(evidence.checks.at(-1));

  await page.setViewport({width: 1440, height: 900});
  await more("#portfolio-import-entry");
  const ocrResponse = waitResponse("/api/v1/advisor/portfolio/ocr", "POST");
  await (await page.$("#portfolio-ocr-file-input")).uploadFile(path.join(root, "app/api/static/sample_holding.png"));
  const ocr = await ocrResponse;
  assert.equal(ocr.status(), 200);
  const ocrData = await ocr.json();
  assert.ok(ocrData.positions.length > 0);
  await page.waitForSelector(".ocr-confirm-actions button");
  const confirmation = waitResponse("/api/v1/advisor/portfolio/ocr/confirm", "POST");
  await page.click(".ocr-confirm-actions button");
  assert.equal((await confirmation).status(), 200);
  await page.waitForFunction(() => !document.querySelector("#portfolio-modal").open);
  report = await waitReport(ocrData.positions.length);
  assert.equal(report.data_mode, "LIVE");
  evidence.checks.push("实际图片 OCR、确认保存与报告更新");
  console.log(evidence.checks.at(-1));

  await more("#portfolio-manage-entry");
  const initialCount = report.position_count;
  for (let remaining = initialCount - 1; remaining >= 0; remaining--) {
    const removed = waitResponse("/api/v1/advisor/portfolio/current", "PUT");
    await page.click("#portfolio-position-rows tr:first-child button:last-child");
    assert.equal((await removed).status(), 200);
    await page.waitForFunction(count => document.querySelector("#overview-position-count").textContent === String(count), {}, remaining);
  }
  await page.click("#portfolio-details-close");
  assert.equal(await visible("#portfolio-empty"), true);
  assert.equal(await visible("#portfolio-page-more"), false);
  await page.click('.nav-section-primary a[href="#copilot"]');
  assert.equal(await visible("#home-history-sidebar"), true);
  await page.click('.nav-section-primary a[href="#market"]');
  assert.equal(await visible(".market-sidebar-panel"), true);
  assert.deepEqual(errors, []);
  evidence.checks.push("删除全部持仓、首页与大盘导航恢复、无页面错误");
  await writeFile(path.join(output, "verification.json"), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({checks: evidence.checks, geometries: evidence.geometries, requests: evidence.requests.length}));
} finally {
  await browser.close();
}
