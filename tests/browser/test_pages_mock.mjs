import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:4173/?pages=1";
const executablePath = process.env.PRISM_TEST_BROWSER || (
  process.platform === "win32"
    ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    : "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
);

const browser = await puppeteer.launch({ executablePath, headless: true, args: ["--no-sandbox"] });
try {
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", message => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) consoleErrors.push(message.text());
  });
  page.on("pageerror", error => consoleErrors.push(error.message));
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.PRISM_PAGES_MOCK === true && document.querySelector("#copilot:not([hidden])") && !document.body.classList.contains("questionnaire-pending"), { timeout: 15000 });

  assert.equal(await page.$eval("#pages-demo-badge", node => node.textContent.includes("Mock 演示")), true);
  assert.equal(await page.$eval("body", node => node.classList.contains("dev-mode")), true);
  assert.equal(await page.$eval("body", node => node.classList.contains("questionnaire-required")), false);
  assert.ok((await page.$$("#nav-expert-items .nav-item")).length >= 5);
  assert.match(await page.$eval("#profile-summary-content", node => node.textContent), /稳健成长型投资者/);
  assert.match(await page.$eval("#portfolio-content", node => node.textContent), /贵州茅台/);

  const visit = async (id, marker) => {
    await page.evaluate(value => { window.location.hash = value; }, id);
    await page.waitForSelector(`#${id}:not([hidden])`);
    if (marker) await page.waitForFunction((selector, text) => document.querySelector(selector)?.textContent.includes(text), {}, `#${id}`, marker);
  };

  await visit("market", "上证指数");
  await visit("research-tracks", "四轨道研究矩阵");
  await page.click("#run-research-matrix");
  await page.waitForFunction(() => document.querySelector("#research-matrix-content")?.textContent.includes("发现"));
  await visit("stock-research", "股票研究");
  await page.click("#run-stock-research");
  await page.waitForFunction(() => document.querySelector("#stock-research-content")?.textContent.includes("已验证的财务事实"));
  await visit("fund-research", "ETF / 基金研究");
  await page.click("#run-fund-research");
  await page.waitForFunction(() => document.querySelector("#fund-research-content")?.textContent.includes("确定性基金风险摘要"));
  await visit("convertible-bond-research", "可转债研究");
  await page.click("#run-convertible-bond-research");
  await page.waitForFunction(() => document.querySelector("#convertible-bond-research-content")?.textContent.includes("转股溢价率"));
  await visit("portfolio-optimization", "组合目标结构");
  await page.click("#run-portfolio-optimization");
  await page.waitForFunction(() => document.querySelector("#portfolio-optimization-content")?.textContent.includes("当前 → 确定性目标权重"));
  await visit("scenario-simulation", "情景模拟与压力分析");
  await page.click("#run-scenario-simulation");
  await page.waitForFunction(() => document.querySelector("#scenario-simulation-content")?.textContent.includes("基线 vs 模拟关键指标差分对比"));
  await visit("evaluation-dashboard", "分析质量");
  await page.click("#run-evaluation-suite");
  await page.waitForFunction(() => document.querySelector("#evaluation-summary-content")?.textContent.includes("92.00"));
  await visit("dev-assist", "研发辅助");
  await page.$eval("#dev-assist-prd", node => { node.value = "展示一个组合分析页面"; });
  await page.$eval("#dev-assist-technical", node => { node.value = "使用静态页面和确定性计算"; });
  await page.click("#run-dev-assist");
  await page.waitForFunction(() => document.querySelector("#dev-assist-output")?.textContent.includes("完善后的技术方案"));
  await visit("copilot", "投资研究会话");
  await page.click('#copilot-quick-tags button[data-intent="CHECK_PORTFOLIO"]');
  await page.waitForFunction(() => document.querySelector("#copilot-decision-output")?.textContent.includes("暂无明显问题"));
  await page.$eval("#copilot-natural-input", node => { node.value = "请说明当前组合风险"; });
  await page.click("#copilot-submit-query");
  await page.waitForFunction(() => document.querySelector("#copilot-chat-messages")?.textContent.includes("Pages 演示回复"));

  assert.deepEqual(consoleErrors, []);
  process.stdout.write("Pages Mock browser checks passed.\n");
} finally {
  await browser.close();
}
