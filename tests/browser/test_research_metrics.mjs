import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";
const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:4179/static/index.html";
const executablePath = process.env.PRISM_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const target = new URL(baseUrl); target.searchParams.set("pages", "1");
  await page.goto(target.href, {waitUntil: "networkidle0"});
  await page.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
  await page.evaluate(() => { window.location.hash = "market-risk"; });
  await page.waitForSelector('#market[data-active-subpage="market-risk"]');
  const metric = {value: 0, unit: "%", status: "CALCULATED", missing_reason: null, method_version: "test-metrics.v1", parameters: {window: 20}, sample_count: 21, input_start: "2026-09-01", input_end: "2026-09-03", source: "<img src=x onerror=alert(1)>", snapshot_id: "test-snapshot", series: [{time: "2026-09-01", value: 0}, {time: "2026-09-02", value: 1}, {time: "2026-09-03", value: 0}]};
  const data = {research_interval: "1d", interval: "1M", input_snapshot_id: "test-snapshot", research_metrics: {
    daily_return: metric, momentum_20: {...metric, value: null, status: "UNAVAILABLE", missing_reason: "INSUFFICIENT_HISTORY", series: []},
    realized_volatility_20: metric, current_drawdown: {...metric, value: -.25}, maximum_drawdown: {...metric, value: -.5},
  }};
  await page.evaluate(data => document.dispatchEvent(new CustomEvent("prism:market-analysis", {detail: {data}})), data);
  assert.match(await page.$eval('[data-research-metric="daily_return"] strong', node => node.textContent), /^0\.0000%$/);
  assert.equal(await page.$eval('[data-research-metric="momentum_20"] strong', node => node.textContent), "—");
  assert.match(await page.$eval("#research-metric-cards", node => node.textContent), /INSUFFICIENT_HISTORY/);
  assert.match(await page.$eval("#research-metric-cards", node => node.textContent), /test-snapshot/);
  assert.equal(await page.$$("#research-metric-cards img").then(items => items.length), 0);
  assert.ok((await page.$$("#research-metric-chart canvas")).length > 0);
  for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {
    await page.setViewport({width, height});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false);
  }
  await page.click('[data-research-metric="momentum_20"]');
  assert.equal(await page.$$("#research-metric-chart canvas").then(items => items.length), 0);
  assert.match(await page.$eval("#research-metric-chart", node => node.textContent), /INSUFFICIENT_HISTORY/);
  await page.evaluate(() => document.dispatchEvent(new CustomEvent("prism:market-analysis", {detail: {status: "LOADING"}})));
  assert.equal(await page.$$("#research-metric-cards strong").then(items => items.length), 0);
  assert.match(await page.$eval("#research-metric-cards", node => node.textContent), /上一结果已失效/);
  await page.evaluate(() => document.dispatchEvent(new CustomEvent("prism:market-analysis", {detail: {data: {research_metrics: {}}}})));
  assert.equal(await page.$eval("#research-metrics-status", node => node.textContent), "UNAVAILABLE");
  assert.equal(await page.$eval('[data-research-metric="daily_return"] strong', node => node.textContent), "—");
  assert.deepEqual(errors, []);
  process.stdout.write("Research metrics browser checks passed: zero, missing, metadata, chart, refresh invalidation and responsive layout.\n");
} finally { await browser.close(); }
