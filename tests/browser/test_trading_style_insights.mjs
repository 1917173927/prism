import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8017";
const executablePath = process.env.PRISM_TEST_BROWSER || (
  process.platform === "win32"
    ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    : "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
);

const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});

try {
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.setViewport({width: 1440, height: 1000, deviceScaleFactor: 1});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});

  const importStatus = await page.evaluate(async () => {
    const owner = "demo-owner";
    const values = [
      ["2026-09-09T09:25:00+08:00", "600519.SH", "贵州茅台", "BUY", 100, 1480],
      ["2026-09-09T13:14:00+08:00", "300750.SZ", "宁德时代", "BUY", 300, 255],
      ["2026-09-09T13:21:00+08:00", "600036.SH", "招商银行", "BUY", 1000, 42],
      ["2026-09-10T09:30:00+08:00", "600519.SH", "贵州茅台", "SELL", 100, 1490],
      ["2026-09-10T10:05:00+08:00", "300750.SZ", "宁德时代", "SELL", 300, 260],
      ["2026-09-14T10:42:00+08:00", "600036.SH", "招商银行", "SELL", 1000, 43],
      ["2026-09-14T10:43:00+08:00", "600519.SH", "贵州茅台", "BUY", 50, 1500],
    ];
    const rows = values.map(([traded_at, security_code, security_name, side, quantity, price_cny], index) => ({
      traded_at, security_code, security_name, side, quantity: String(quantity), price_cny: String(price_cny),
      gross_amount_cny: String(quantity * price_cny), asset_type: "STOCK", source_row: index + 2,
    }));
    const response = await fetch("/api/v1/advisor/trading-history/imports", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Owner-ID": owner},
      body: JSON.stringify({
        schema_version: "trade-import-confirm-request.v1", owner_id: owner, source_type: "CSV",
        source_digest: "e".repeat(64), file_count: 1, rows,
      }),
    });
    return response.status;
  });
  assert.equal(importStatus, 200);

  await page.evaluate(() => { window.location.hash = "trading-style"; });
  await page.waitForSelector("#trading-style:not([hidden])");
  await page.waitForSelector("#trade-style-insights:not([hidden]) .trade-guidance-list li");
  await page.waitForFunction(() => document.querySelectorAll(".trade-security-card").length === 3);
  assert.equal(await page.$$(".trade-guidance-list li").then((nodes) => nodes.length), 3);
  assert.match(await page.$eval("#trade-guidance-maturity", (node) => node.textContent), /初步建议/);
  assert.match(await page.$eval("#trade-market-status", (node) => node.textContent), /PASS|REVIEW_REQUIRED/);
  assert.match(await page.$eval(".trade-guidance-disclaimer", (node) => node.textContent), /不包含个股买卖方向/);

  await page.click("#refresh-trade-market");
  await page.waitForFunction(() => !document.querySelector("#refresh-trade-market").disabled);
  await page.setViewport({width: 390, height: 844, deviceScaleFactor: 1});
  assert.equal(await page.$eval("body", (node) => node.scrollWidth <= innerWidth), true);
  assert.equal(await page.$eval("#trade-style-insights", (node) => getComputedStyle(node).gridTemplateColumns.split(" ").length), 1);
  assert.deepEqual(consoleErrors, []);
  process.stdout.write("Trading-style insight browser checks passed.\n");
} finally {
  await browser.close();
}
