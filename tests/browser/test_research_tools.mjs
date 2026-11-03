import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import puppeteer from "puppeteer-core";

// Use research_platform_server.py. Synthetic inputs prove UI/API behavior only.
const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8021/";
const executablePath = process.env.PRISM_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
const temporary = await fs.mkdtemp(path.join(os.tmpdir(), "prism-ui-test-"));
try {
  const page = await browser.newPage();
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  await page.setViewport({width: 1024, height: 768});
  await page.goto(baseUrl, {waitUntil: "networkidle0"});
  await page.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await page.click("#welcome-later");
  const fill = async (id, value) => page.$eval(`#${id}`, (node, value) => { node.value = value; node.dispatchEvent(new Event("input", {bubbles: true})); node.dispatchEvent(new Event("change", {bubbles: true})); }, value);
  const navigate = async hash => { await page.click(`.nav-section-primary a[href="#${hash}"]`); await page.waitForSelector(`#${hash}:not([hidden])`); };
  await navigate("research-knowledge");
  const filePath = path.join(temporary, "evidence.txt");
  await fs.writeFile(filePath, "browser-library-evidence\n\nOriginal statement for exact attributed citation checks.\n<script>alert('untrusted document')</script>", "utf8");
  await fill("knowledge-title", "Browser test original document"); await fill("knowledge-source", "Synthetic browser test corpus");
  await fill("knowledge-source-url", "https://example.com/browser-test-document"); await fill("knowledge-published", "2026-01-01T09:00"); await fill("knowledge-subject", "browser-test-subject");
  await (await page.$("#knowledge-file")).uploadFile(filePath);
  await page.click("#knowledge-upload");
  await page.waitForFunction(() => document.querySelector("#knowledge-message").textContent.includes("资料已登记"));
  await fill("knowledge-query", "browser-library-evidence"); await fill("knowledge-search-subject", "browser-test-subject");
  await page.click("#knowledge-search");
  await page.waitForSelector("#knowledge-matches .research-result-card");
  assert.match(await page.$eval("#knowledge-matches", node => node.innerText), /关键词检索/);
  assert.match(await page.$eval("#knowledge-matches", node => node.innerText), /事实尚未核验/);
  assert.doesNotMatch(await page.$eval("#knowledge-matches", node => node.innerText), /KEYWORD_ONLY|RETRIEVED_UNVERIFIED|SQLITE_FTS5_BIGRAM/);
  assert.equal(await page.$$("#knowledge-matches script").then(items => items.length), 0);
  await page.click("#knowledge-matches .research-result-card button:nth-of-type(1)");
  await page.waitForSelector("#knowledge-original:not([hidden]) pre");
  assert.match(await page.$eval("#knowledge-original", node => node.textContent), /Original statement/);
  await page.click("#knowledge-matches .research-result-card button:nth-of-type(2)");
  await page.waitForFunction(() => document.querySelector("#knowledge-message").textContent.includes("金融事实仍需独立核验"));
  const otherUser = await page.evaluate(async () => fetch("/api/v1/research/knowledge/search", {method: "POST", headers: {"Content-Type": "application/json", "X-Owner-ID": "unrelated-browser-user"}, body: JSON.stringify({query: "browser-library-evidence", limit: 10})}).then(response => response.json()));
  assert.equal(otherUser.matches.length, 0);
  await fill("knowledge-as-of", "2025-12-31T09:00"); await page.click("#knowledge-search");
  await page.waitForFunction(() => document.querySelector("#knowledge-matches").textContent.includes("没有匹配资料"));

  await page.click('.nav-section-primary a[href="#market"]');
  await page.click('.workspace-page-tabs a[href="#market-sectors"]');
  await page.waitForSelector("#market-stock-research-code", {visible: true});
  await fill("market-stock-research-code", "600519.SH");
  await page.click("#market-stock-research-open");
  await page.waitForSelector("#live-research:not([hidden])");
  assert.equal(await page.$eval("#research-advanced-settings", node => node.open), false);
  assert.equal(await page.$eval("#research-template-subject", node => node.value), "600519.SH");
  await page.click("#research-advanced-settings > summary");
  assert.equal(await page.$eval('#research-node-editor input[aria-label="研究步骤 1 研究标的"]', node => node.value), "600519.SH");
  assert.match(await page.$eval("#research-message", node => node.textContent), /尚未提交/);
  await page.click("#research-submit");
  await page.waitForFunction(() => document.querySelector("#research-run-result").innerText.includes("研究任务 · 已完成"));
  assert.match(await page.$eval("#research-run-result", node => node.innerText), /单一来源，尚未独立核验/);
  assert.doesNotMatch(await page.$eval("#research-run-result", node => node.innerText), /SINGLE_SOURCE_UNVERIFIED|wencai_skillhub_provider/);
  assert.match(await page.$eval("#research-run-result", node => node.textContent), /isolated browser-test stub/);
  assert.match(await page.$eval("#research-run-result", node => node.textContent), /123\.45/);
  await page.waitForFunction(() => !document.querySelector("#research-template-submit").disabled);
  assert.match(await page.$eval("#research-template-info", node => node.innerText), /行情.*最新价.*财务.*营业收入.*净利润/);
  assert.doesNotMatch(await page.$eval("#research-template-info", node => node.innerText), /live-equity-basic|financials|MARKET_DATA|net_profit/);
  assert.equal(await page.$eval("#research-template-record pre", node => JSON.parse(node.textContent).template_id), "live-equity-basic.v1");
  await fill("research-as-of", "2025-12-31T09:00"); await page.click("#research-submit");
  await page.waitForFunction(() => document.querySelector("#research-run-result").textContent.includes("FUTURE_OBSERVATION"));
  assert.match(await page.$eval("#research-run-result", node => node.innerText), /研究任务 · 未完成/);
  assert.match(await page.$eval("#research-run-result", node => node.innerText), /数据时点晚于本次研究截止时间/);
  assert.doesNotMatch(await page.$eval("#research-run-result", node => node.textContent), /123\.45/);
  await fill("research-template-subject", "600519.SH"); await page.click("#research-template-submit");
  await page.waitForFunction(() => document.querySelector("#research-run-result").textContent.includes("FUTURE_OBSERVATION"));
  assert.match(await page.$eval("#research-run-result", node => node.textContent), /quote.*FAILED/s);
  assert.match(await page.$eval("#research-run-result", node => node.innerText), /研究任务 · 未完成/);
  assert.doesNotMatch(await page.$eval("#research-run-result", node => node.textContent), /123\.45/);
  await fill("research-as-of", "2099-01-01T09:00"); await page.click("#research-template-submit");
  await page.waitForFunction(() => document.querySelector("#research-message").textContent.includes("不能晚于服务器当前时间"));
  assert.equal(await page.$eval("#research-run-result", node => node.textContent), "");
  await page.click("#research-submit");
  await page.waitForFunction(() => document.querySelector("#research-message").textContent.includes("不能晚于服务器当前时间"));
  assert.equal(await page.$eval("#research-run-result", node => node.textContent), "");
  await fill("research-as-of", "");
  await page.$eval('#research-node-editor input[aria-label="研究步骤 1 查询语句"]', node => { node.value = "browser-slow"; node.dispatchEvent(new Event("input", {bubbles: true})); });
  await page.click("#research-submit");
  await page.waitForFunction(() => !document.querySelector("#research-cancel").disabled);
  await page.click("#research-cancel");
  await page.waitForFunction(() => document.querySelector("#research-run-result").innerText.includes("研究任务 · 已取消"));
  assert.match(await page.$eval("#research-run-result", node => node.textContent), /CANCELLED/);
  const imported = {nodes: [{node_id: "a", operation: "MARKET_DATA", subject: "600519", required_fields: ["price"], dependencies: ["b"]}, {node_id: "b", operation: "MARKET_DATA", subject: "600519", required_fields: ["price"], dependencies: ["a"]}], budget_seconds: 60};
  await page.click("#research-json-import > summary"); await fill("research-json", JSON.stringify(imported));
  await page.click("#research-json-import button"); await page.click("#research-submit");
  await page.waitForFunction(() => document.querySelector("#research-message").textContent.includes("输入未通过校验"));

  await navigate("research-algorithms");
  assert.equal(await page.$eval("#algorithm-input-settings", node => node.open), false);
  await page.click("#algorithm-input-settings > summary");
  const algorithm = async (kind, input) => { await page.select("#algorithm-kind", kind); await fill("algorithm-json", JSON.stringify(input)); await page.click("#algorithm-compute"); await page.waitForFunction(() => !document.querySelector("#algorithm-compute").disabled); };
  const common = {source: "Synthetic browser-test returns; not real market evidence", as_of: "2026-09-30T00:00:00Z"};
  await algorithm("regime", {...common, training_size: 252, returns: []});
  assert.match(await page.$eval("#algorithm-output", node => node.innerText), /收益样本不足/);
  assert.match(await page.$eval("#algorithm-output", node => node.textContent), /INSUFFICIENT_RETURNS/);
  const points = Array.from({length: 300}, (_, index) => ({time: new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10), value: (index % 70 < 35 ? .003 : .03) * Math.sin(index * 1.9187) + .002 * Math.cos(index * 2.361)}));
  await algorithm("regime", {...common, training_size: 252, returns: points});
  assert.match(await page.$eval("#algorithm-output", node => node.innerText), /市场波动环境 · 已计算/);
  assert.doesNotMatch(await page.$eval("#algorithm-output", node => node.innerText), /CALCULATED|gaussian-hmm/);
  assert.ok((await page.$$("#algorithm-chart canvas")).length > 0);
  await algorithm("covariance", {...common, series: {A: points.slice(0, 80), B: points.slice(0, 80).map((point, index) => ({...point, value: point.value * .3 + Math.cos(index) * .001}))}});
  assert.match(await page.$eval("#algorithm-output", node => node.innerText), /资产联动风险 · 已计算/);
  assert.equal(await page.$eval("#algorithm-matrix-details", node => node.open), false);
  assert.equal(await page.$$("#algorithm-matrix tbody tr").then(items => items.length), 2);
  await algorithm("five-factors", {...common, monetary_unit: "CNY", universe_id: "synthetic-six-stock-universe", universe_complete: false, fundamentals: [], months: [{month: "2026-07", risk_free_return: .001, securities: []}]});
  assert.match(await page.$eval("#algorithm-output", node => node.innerText), /分组形成集合不足/);
  assert.match(await page.$eval("#algorithm-output", node => node.textContent), /INSUFFICIENT_FORMATION_UNIVERSE/);
  // Independent test fixture has all six size/feature portfolios populated.
  const fundamentals = [1, 2, 3, 1, 2, 3].map((rank, index) => ({security_id: `S${index}`, formation_year: 2026, fiscal_year: 2025, published_at: "2026-04-01T00:00:00Z", market_cap_december: 100, market_cap_june: index < 3 ? 100 : 1000, book_equity: rank * 10, revenue: rank * rank * 10 + 10, cost_of_goods_sold: 5, selling_general_administrative: 3, interest_expense: 2, total_assets: 100 + rank * 10, prior_total_assets: 100}));
  const months = ["2026-07", "2026-08"].map(month => ({month, risk_free_return: .001, securities: fundamentals.map((row, index) => ({security_id: row.security_id, total_return: .002 + index * .003, beginning_market_cap: row.market_cap_june}))}));
  await algorithm("five-factors", {...common, monetary_unit: "CNY", universe_id: "synthetic-six-stock-universe", universe_complete: false, fundamentals, months});
  assert.match(await page.$eval("#algorithm-output", node => node.innerText), /市场风格因素 · 已计算/);
  assert.match(await page.$eval("#algorithm-output", node => node.textContent), /INPUT_UNIVERSE/);
  assert.ok((await page.$$("#algorithm-chart canvas")).length > 0);
  for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {
    await page.setViewport({width, height});
    for (const hash of ["research-knowledge", "live-research", "research-algorithms"]) {
      await navigate(hash);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false, `${width} ${hash} overflow`);
    }
  }
  await page.setViewport({width: 1440, height: 1000});
  if (process.env.PRISM_TEST_SCREENSHOT_DIR) {
    await fs.mkdir(process.env.PRISM_TEST_SCREENSHOT_DIR, {recursive: true});
    await navigate("research-knowledge"); await fill("knowledge-as-of", ""); await page.click("#knowledge-search"); await page.waitForSelector("#knowledge-matches .research-result-card");
    for (const hash of ["research-knowledge", "live-research", "research-algorithms"]) { await navigate(hash); await page.screenshot({path: path.join(process.env.PRISM_TEST_SCREENSHOT_DIR, `${hash}.png`), fullPage: true}); }
  }
  assert.deepEqual(errors, []);
  process.stdout.write("Research tools API/browser checks passed: upload, temporal/owner isolation, exact quotes, LIVE states/cancel/template, historical and future cutoff guards, DAG rejection and three algorithm views. Synthetic results are not real-data acceptance.\n");
} finally { await browser.close(); await fs.unlink(path.join(temporary, "evidence.txt")).catch(() => {}); await fs.rmdir(temporary); }
