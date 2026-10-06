import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import {mkdir, mkdtemp, writeFile} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8022";
const executablePath = process.env.PRISM_TEST_BROWSER || "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const tradeFile = process.env.PRISM_TEST_TRADE_FILE;
const root = fileURLToPath(new URL("../../", import.meta.url));
const output = path.join(root, "output/trading-style-layout");
await mkdir(output, {recursive: true});
const directory = await mkdtemp(path.join(output, "browser-"));
const temporary = path.join(directory, "temporary");
await mkdir(temporary);
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: path.join(directory, "profile"), env: {...process.env, TEMP: temporary, TMP: temporary, TMPDIR: temporary}});
const evidence = {checks: [], geometries: [], requests: [], importChecked: false, marketRefreshChecked: false};

try {
  const page = await browser.newPage();
  page.setDefaultTimeout(60000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    const pathname = new URL(response.url()).pathname;
    if (pathname.includes("/trading-style/") || pathname.includes("/trading-history/")) {
      evidence.requests.push({path: pathname, method: response.request().method(), status: response.status()});
    }
  });
  const record = message => { evidence.checks.push(message); console.log(message); };
  const visible = selector => page.$eval(selector, node => node.checkVisibility());
  const waitResponse = (pathname, method = "GET") => page.waitForResponse(response =>
    new URL(response.url()).pathname === pathname && response.request().method() === method);
  async function click(selector) {
    await page.waitForSelector(selector, {visible: true});
    await page.$eval(selector, node => node.scrollIntoView({block: "center", behavior: "instant"}));
    await page.waitForFunction(selector => {
      const node = document.querySelector(selector), rect = node.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return node === hit || node.contains(hit);
    }, {}, selector);
    await page.click(selector);
  }
  async function api(pathname) {
    return page.evaluate(async pathname => {
      const response = await fetch(pathname, {headers: {"X-Owner-ID": document.documentElement.dataset.prismOwner}});
      const data = await response.json();
      if (!response.ok) throw new Error(`${pathname}: ${response.status} ${JSON.stringify(data)}`);
      return data;
    }, pathname);
  }
  async function checkWidths(stage, populated = false) {
    for (const width of [1440, 1024, 768, 600, 390, 320]) {
      await page.setViewport({width, height: 1000, deviceScaleFactor: 1});
      const geometry = await page.evaluate(() => {
        const dialog = document.querySelector("#trade-import-dialog");
        const rect = dialog.open ? dialog.getBoundingClientRect() : null;
        const title = document.querySelector(".trading-style-hero strong");
        const metric = document.querySelector(".trading-style-metrics strong");
        return {width: innerWidth, documentWidth: document.body.scrollWidth,
          dialog: rect ? {left: rect.left, right: rect.right, height: rect.height} : null,
          titleSize: title ? parseFloat(getComputedStyle(title).fontSize) : null,
          metricSize: metric ? parseFloat(getComputedStyle(metric).fontSize) : null};
      });
      evidence.geometries.push({stage, ...geometry});
      assert.ok(geometry.documentWidth <= width + 1, JSON.stringify({stage, ...geometry}));
      if (geometry.dialog) {
        assert.ok(geometry.dialog.left >= 0 && geometry.dialog.right <= width, JSON.stringify(geometry));
        assert.ok(geometry.dialog.height <= 1000, JSON.stringify(geometry));
      }
      if (populated) assert.ok(geometry.titleSize > geometry.metricSize, JSON.stringify(geometry));
    }
  }

  await page.setViewport({width: 1440, height: 1000});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  assert.equal(new URL(page.url()).pathname, "/login");
  const password = randomUUID() + randomUUID();
  await page.click("#register-tab");
  await page.type("#username", `trade-ui-${Date.now()}`);
  await page.type("#password", password);
  await page.type("#confirmation", password);
  await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  await page.waitForSelector("body:not(.questionnaire-pending)");
  assert.equal((await api("/api/v1/auth/context")).enabled, true);
  evidence.dataMode = (await api("/api/v1/runtime/data-mode")).data.data_mode;
  assert.equal(evidence.dataMode, "LIVE");
  await page.waitForSelector("#questionnaire-welcome[open]");
  await page.click("#welcome-later");

  const workspaceResponses = [
    waitResponse("/api/v1/advisor/trading-style/profile"),
    waitResponse("/api/v1/advisor/trading-history/trades"),
    waitResponse("/api/v1/advisor/trading-style/insights"),
  ];
  const workspaceResults = await Promise.all([
    ...workspaceResponses,
    page.evaluate(() => { location.hash = "portfolio-style"; }),
  ]);
  await page.waitForSelector("#trading-style:not([hidden])");
  for (const response of workspaceResults.slice(0, 3)) assert.equal(response.status(), 200);
  assert.equal(await visible("#trade-style-empty"), true);
  for (const selector of ["#trading-style-summary", "#trading-style-more", "#trade-style-insights", "#open-trade-import"]) {
    assert.equal(await visible(selector), false, selector);
  }
  assert.equal(await page.$$eval("#trading-style button.primary", nodes => nodes.filter(node => node.getClientRects().length).length), 1);
  await checkWidths("empty");
  record("空账户显示导入入口，六种页面宽度检查通过");

  await page.click("#empty-trade-import");
  assert.equal(await page.$eval("#trade-import-dialog", node => node.open), true);
  assert.equal(await page.$eval("#preview-trade-import", node => node.disabled), true);
  assert.equal(await page.evaluate(() => document.activeElement.id), "close-trade-import");
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.id), "trade-import-files");
  assert.equal(await page.$eval(".trade-file-picker", node => getComputedStyle(node).outlineWidth), "2px");
  for (const selector of ["#close-trade-import", ".trade-file-picker", "#preview-trade-import", "#empty-trade-import"]) {
    const height = await page.$eval(selector, node => node.getBoundingClientRect().height);
    assert.ok(height >= 44, JSON.stringify({selector, height}));
  }
  const dialogText = await page.$eval("#trade-import-dialog", node => node.innerText);
  assert.doesNotMatch(dialogText, /PASS|REVIEW_REQUIRED|OVERBOUND|HHI|FIFO|CSV|XLSX|限制边界|不构成/);
  await checkWidths("import");
  await page.keyboard.press("Escape");
  assert.equal(await page.$eval("#trade-import-dialog", node => node.open), false);
  assert.equal(await page.evaluate(() => document.activeElement.id), "empty-trade-import");
  await page.click("#empty-trade-import");
  await page.click("#close-trade-import");
  assert.equal(await page.$eval("#trade-import-dialog", node => node.open), false);
  record("导入弹窗、无文件按钮状态、键盘关闭与焦点恢复检查通过");

  await page.click("#empty-trade-import");
  await (await page.$("#trade-import-files")).uploadFile(path.join(root, "README.md"));
  assert.equal(await page.$eval("#trade-import-file-status", node => node.innerText), "README.md");
  assert.equal(await page.$eval("#preview-trade-import", node => node.disabled), false);
  const invalidFileResponse = waitResponse("/api/v1/advisor/trading-history/import/preview", "POST");
  await page.click("#preview-trade-import");
  assert.equal((await invalidFileResponse).status(), 422);
  await page.waitForSelector("#trade-import-error:not([hidden])");
  assert.equal(await page.$eval("#trade-import-error", node => node.innerText), "请选择 CSV 或 XLSX 表格");
  assert.equal(await page.$eval("#trade-import-files", node => node.disabled), false);
  assert.equal(await page.$eval("#preview-trade-import", node => node.innerText), "开始分析");
  await (await page.$("#trade-import-files")).uploadFile();
  assert.equal(await visible("#trade-import-error"), false);
  assert.equal(await visible("#trade-import-file-status"), false);
  assert.equal(await page.$eval("#preview-trade-import", node => node.disabled), true);
  await page.click("#close-trade-import");
  record("文件选择、真实接口拒绝无效格式、错误提示和重新选择检查通过");

  if (tradeFile) {
    await page.setViewport({width: 1440, height: 1000});
    await page.click("#empty-trade-import");
    await (await page.$("#trade-import-files")).uploadFile(path.resolve(tradeFile));
    assert.equal(await page.$eval("#preview-trade-import", node => node.disabled), false);
    const previewResponse = waitResponse("/api/v1/advisor/trading-history/import/preview", "POST");
    await page.click("#preview-trade-import");
    const previewResult = await previewResponse;
    assert.equal(previewResult.status(), 200);
    const preview = await previewResult.json();
    assert.ok(preview.accepted_count > 0);
    await page.waitForSelector("#trade-mapping-panel:not([hidden])");
    assert.equal(await visible("#trade-import-start"), false);
    assert.doesNotMatch(await page.$eval("#trade-preview-rows", node => node.innerText), /PASS|REVIEW_REQUIRED|OVERBOUND/);
    await checkWidths("review");

    const confirmationResponse = waitResponse("/api/v1/advisor/trading-history/imports", "POST");
    await page.click("#confirm-trade-import");
    const confirmation = await confirmationResponse;
    assert.equal(confirmation.status(), 200);
    const result = await confirmation.json();
    await page.waitForFunction(() => !document.querySelector("#trade-import-dialog").open);
    await page.waitForSelector("#trade-style-insights:not([hidden]) .trade-guidance-list li");
    await page.waitForFunction(() => document.querySelector("#trade-market-securities").getAttribute("aria-busy") === "false");
    assert.equal(await visible("#trade-style-empty"), false);
    assert.equal(await visible("#trading-style-summary"), true);
    assert.equal(await page.$eval(".trading-style-hero strong", node => node.textContent), result.style_profile.primary_style);
    assert.equal(await page.$$(".trading-style-metrics .trading-style-metric").then(nodes => nodes.length), 2);
    assert.equal(await page.$$(".trade-guidance-list li").then(nodes => nodes.length), 3);
    assert.equal(await page.$eval("#trading-style-more", node => node.open), false);
    assert.equal(await visible(".trade-history-table"), false);
    assert.doesNotMatch(await page.$eval("#trading-style", node => node.innerText), /PASS|REVIEW_REQUIRED|OVERBOUND|HHI|FIFO|限制边界|不构成/);
    await checkWidths("analysis", true);

    await page.setViewport({width: 1440, height: 1000});
    await page.click("#trading-style-more > summary");
    await page.click("#trade-history-details > summary");
    await page.waitForSelector("#trade-history-rows .trade-row-actions");
    const trades = await api("/api/v1/advisor/trading-history/trades?cursor=0&limit=50");
    assert.equal(await page.$$("#trade-history-rows .trade-row-actions").then(nodes => nodes.length), trades.items.length);
    assert.doesNotMatch(await page.$eval("#trade-history-rows", node => node.innerText), /ACTIVE|WITHDRAWN/);
    await page.click("#trade-history-rows .trade-row-actions button");
    assert.equal(await page.$eval("#trade-edit-dialog", node => node.open), true);
    await page.click("#trade-edit-cancel");

    const first = trades.items[0];
    await page.type("#trade-filter-security", first.security_code || first.security_name);
    const filteredResponse = waitResponse("/api/v1/advisor/trading-history/trades");
    await page.click("#apply-trade-filters");
    assert.equal((await filteredResponse).status(), 200);
    await page.click("#trade-advanced-filters > summary");
    await checkWidths("history", true);

    const insights = await api("/api/v1/advisor/trading-style/insights");
    assert.equal(await page.$eval("#trade-market-details", node => node.hidden), insights.securities.length === 0);
    if (insights.securities.length) {
      await page.setViewport({width: 1440, height: 1000});
      await click("#trade-market-details > summary");
      const insightsResponse = waitResponse("/api/v1/advisor/trading-style/insights");
      await click("#refresh-trade-market");
      const refreshed = await insightsResponse;
      assert.equal(refreshed.status(), 200);
      const refreshedData = await refreshed.json();
      await page.waitForFunction(() => document.querySelector("#trade-market-securities").getAttribute("aria-busy") === "false");
      assert.ok(refreshedData.primary_style, JSON.stringify({style: refreshedData.primary_style, securities: refreshedData.securities.length}));
      assert.equal(await page.$$("#trade-market-securities tr").then(nodes => nodes.length), insights.securities.length);
      await checkWidths("market", true);
      evidence.marketRefreshChecked = true;
      record("历史成交包含重点标的，行情刷新检查通过");
    }
    evidence.importChecked = true;
    record("真实文件导入、结果层级、交易筛选与编辑弹窗检查通过");
  }

  await page.setViewport({width: 1440, height: 1000});
  await page.click(tradeFile ? "#open-trade-import" : "#empty-trade-import");
  await page.evaluate(() => { window.location.hash = "profile"; });
  await page.waitForSelector("#trading-style[hidden]");
  assert.equal(await visible("#trading-style"), false);
  assert.equal(await page.$eval("#trade-import-dialog", node => node.open), false);
  assert.deepEqual(errors, []);
  record("离开页面关闭导入弹窗，页面运行错误检查通过");
  await writeFile(path.join(output, "verification.json"), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({checks: evidence.checks.length, importChecked: evidence.importChecked}));
} finally {
  await browser.close();
}
