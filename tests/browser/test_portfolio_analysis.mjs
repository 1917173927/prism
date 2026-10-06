import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import {mkdir, mkdtemp, readFile, writeFile} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import puppeteer from "puppeteer-core";

const root = fileURLToPath(new URL("../../", import.meta.url));
const baseUrl = process.env.PRISM_TEST_BASE_URL;
const executablePath = process.env.PRISM_TEST_BROWSER;
assert.ok(baseUrl && executablePath, "请指定本地服务地址与 Chromium 路径");
const sample = JSON.parse(await readFile(path.resolve(process.env.PRISM_TEST_SAMPLE_FILE), "utf8"));
const tradeFile = path.resolve(process.env.PRISM_TEST_TRADE_FILE);
const output = path.join(root, "output/portfolio-analysis-integration");
await mkdir(output, {recursive: true});
const directory = await mkdtemp(path.join(output, "browser-"));
const temporary = path.join(directory, "temporary");
await mkdir(temporary);
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: path.join(directory, "profile"), env: {...process.env, TEMP: temporary, TMP: temporary, TMPDIR: temporary}});
const evidence = {checks: [], geometries: [], requests: [], pageErrors: []};

try {
  const page = await browser.newPage();
  page.setDefaultTimeout(60000);
  page.on("pageerror", error => { evidence.pageErrors.push(error.message); console.error(error.message); });
  page.on("response", response => {
    const pathname = new URL(response.url()).pathname;
    if (/portfolio|trading-style|trading-history/.test(pathname) && pathname.startsWith("/api/")) {
      evidence.requests.push({path: pathname, method: response.request().method(), status: response.status()});
    }
  });
  const record = message => { evidence.checks.push(message); console.log(message); };
  const visible = selector => page.$eval(selector, node => node.checkVisibility());
  const text = selector => page.$eval(selector, node => node.textContent.trim());
  const amount = value => `¥ ${Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  const waitResponse = (pathname, method = "GET") => page.waitForResponse(response =>
    new URL(response.url()).pathname === pathname && response.request().method() === method);
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
  async function click(selector) {
    await page.waitForSelector(selector, {visible: true});
    await page.$eval(selector, node => node.scrollIntoView({block: "center", behavior: "instant"}));
    const pointer = await page.evaluate(async selector => {
      await new Promise(requestAnimationFrame);
      const node = document.querySelector(selector), rect = node.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return {reachable: node === hit || node.contains(hit), hit: hit?.id || hit?.tagName,
        target: selector, top: rect.top, bottom: rect.bottom, dialogs: [...document.querySelectorAll("dialog[open]")].map(node => node.id)};
    }, selector);
    assert.equal(pointer.reachable, true, JSON.stringify(pointer));
    await page.click(selector);
  }
  async function route(hash, selector) {
    await page.evaluate(hash => { location.hash = hash; }, hash);
    await page.waitForSelector(selector, {visible: true});
  }
  async function waitPortfolio(count) {
    await page.waitForFunction(count => document.querySelector("#overview-position-count").textContent === String(count)
      && !document.querySelector("#portfolio-report-headline").textContent.includes("正在读取"), {}, count);
    return api("/api/v1/advisor/portfolio/report");
  }
  async function checkWidths(stage) {
    for (const width of [320, 390, 640, 768, 1024, 1440, 1920]) {
      await page.setViewport({width, height: 1000, deviceScaleFactor: 1});
      const geometry = await page.evaluate(() => {
        const card = document.querySelector("#portfolio-report-card");
        const bounds = card.checkVisibility() ? card.getBoundingClientRect() : null;
        const panels = [...document.querySelectorAll(".portfolio-analysis-panel")].filter(node => node.checkVisibility());
        const overflows = [...document.querySelectorAll("#overview table, #overview .table-wrap, #overview .portfolio-fact, #overview .portfolio-analysis-tabs")]
          .filter(node => node.checkVisibility() && node.scrollWidth > node.clientWidth + 1)
          .map(node => ({id: node.id, className: node.className, clientWidth: node.clientWidth, scrollWidth: node.scrollWidth}));
        const dialogs = [...document.querySelectorAll("dialog[open]")].map(node => {
          const rect = node.getBoundingClientRect(); return {id: node.id, left: rect.left, right: rect.right, height: rect.height};
        });
        const heading = selector => {
          const node = document.querySelector(selector);
          if (!node.checkVisibility()) return null;
          const rect = node.getBoundingClientRect();
          return {left: rect.left, right: rect.right, centerY: rect.top + rect.height / 2};
        };
        return {width: innerWidth, documentWidth: document.documentElement.scrollWidth,
          cardCenter: bounds ? bounds.left + bounds.width / 2 : null,
          pageBounds: heading("#overview"), title: heading("#overview-title"),
          detailsTitle: heading("#portfolio-details-title"), more: heading("#portfolio-page-more > summary"),
          panels: panels.map(node => ({id: node.id, width: node.getBoundingClientRect().width})), overflows, dialogs};
      });
      evidence.geometries.push({stage, ...geometry});
      assert.ok(geometry.documentWidth <= width + 1, JSON.stringify({stage, ...geometry}));
      assert.deepEqual(geometry.overflows, [], JSON.stringify({stage, ...geometry}));
      if (geometry.cardCenter != null) assert.ok(Math.abs(geometry.cardCenter - width / 2) <= 1, JSON.stringify(geometry));
      assert.ok(Math.abs(geometry.title.left - geometry.pageBounds.left) <= 1, JSON.stringify({stage, ...geometry}));
      if (geometry.detailsTitle) assert.ok(Math.abs(geometry.detailsTitle.left - geometry.title.left) <= 1, JSON.stringify({stage, ...geometry}));
      if (geometry.more) {
        assert.ok(Math.abs(geometry.more.right - geometry.pageBounds.right) <= 1, JSON.stringify({stage, ...geometry}));
        assert.ok(Math.abs(geometry.more.centerY - geometry.title.centerY) <= 1, JSON.stringify({stage, ...geometry}));
        assert.ok(geometry.more.left >= geometry.title.right, JSON.stringify({stage, ...geometry}));
      }
      for (const dialog of geometry.dialogs) assert.ok(dialog.left >= 0 && dialog.right <= width + 1 && dialog.height <= 1000, JSON.stringify(dialog));
    }
    await page.setViewport({width: 1440, height: 1000});
  }
  async function menuAction(selector) {
    await click("#portfolio-page-more > summary"); await click(selector);
  }

  await page.setViewport({width: 1440, height: 1000});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  assert.equal(new URL(page.url()).pathname, "/login");
  const password = randomUUID() + randomUUID();
  await page.click("#register-tab");
  await page.type("#username", `portfolio-ui-${Date.now()}`);
  await page.type("#password", password); await page.type("#confirmation", password);
  await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  await page.waitForSelector("body:not(.questionnaire-pending)");
  const context = await api("/api/v1/auth/context"); assert.equal(context.enabled, true);
  assert.equal((await api("/api/v1/runtime/data-mode")).data.data_mode, "LIVE");
  await page.waitForSelector("#questionnaire-welcome[open]"); await click("#welcome-later");
  await click('.nav-section-primary a[href="#overview"]');
  await page.waitForSelector("#portfolio-empty", {visible: true});
  assert.equal(await visible("#portfolio-report-card"), false);
  await checkWidths("empty");
  await click("#portfolio-empty [data-open-portfolio]");
  await page.waitForSelector("#portfolio-modal[open]"); await checkWidths("portfolio-import");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.body.classList.contains("portfolio-dialog-open"));
  const emptyTradeRecords = waitResponse("/api/v1/advisor/trading-history/trades");
  await click("#portfolio-empty-style-entry");
  assert.equal((await (await emptyTradeRecords).json()).total, 0);
  await page.waitForSelector("#trade-style-empty", {visible: true});
  assert.equal(await visible("#trade-history-details"), false);
  await click("#empty-trade-import"); await checkWidths("trade-import");
  await page.keyboard.press("Escape");
  assert.equal(await page.$eval("#trade-import-dialog", node => node.open), false);
  record("空账户入口、持仓与交易导入窗口、滚动恢复检查通过");

  await api("/api/v1/advisor/portfolio/current", "PUT", {owner_id: context.owner_id, data_mode: "LIVE", positions: sample.positions, cash_cny: sample.cash_cny});
  await route("overview", "#overview");
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("body:not(.questionnaire-pending)"); await waitPortfolio(sample.positions.length);
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await click("#welcome-later");
  await click("#portfolio-details-entry");
  await page.waitForSelector("#portfolio-risk-details", {visible: true});
  assert.equal(await visible("#portfolio-profile-entry"), true);
  assert.equal(await visible("#portfolio-report-card"), false);
  assert.equal(await page.$eval("#portfolio-analysis-details", node => node.tagName), "SECTION");
  assert.equal(await page.$eval("body", node => node.classList.contains("portfolio-dialog-open")), false);
  record("持仓使用本地文件，缺少风险问卷时保留真实操作入口");

  const template = await api("/api/v1/advisor/profile/questionnaire-template");
  const answers = template.questions.map(question => question.question_type === "SCORE"
    ? {question_id: question.question_id, score: sample.questionnaire.score}
    : {question_id: question.question_id, selected_option_ids: [question.options[Math.min(sample.questionnaire.option_index, question.options.length - 1)].option_id]});
  await api("/api/v1/advisor/profile/questionnaire/confirm", "POST", {
    schema_version: "questionnaire-confirmation-request.v1", owner_id: context.owner_id, confirmed_at: new Date().toISOString(), answers});
  await route("overview", "#portfolio-report-card");
  await page.reload({waitUntil: "domcontentloaded"});
  const report = await waitPortfolio(sample.positions.length);
  const summary = await api("/api/v1/advisor/portfolio/summary");
  assert.equal(await text("#overview-portfolio-aum"), amount(summary.holdings_value_cny));
  assert.equal(await text("#overview-benchmark-val"), amount(summary.pnl_cny));
  const typography = await page.$$eval(".portfolio-key-figures dd", nodes => nodes.map(node => {
    const style = getComputedStyle(node); return {font: style.fontFamily, weight: style.fontWeight, tracking: style.letterSpacing};
  }));
  for (const style of typography) { assert.match(style.font, /monospace/); assert.equal(style.weight, "500"); assert.equal(style.tracking, "normal"); }
  await checkWidths("overview");
  await click("#portfolio-details-entry");
  await page.waitForSelector("#portfolio-risk-details", {visible: true});
  assert.equal(await page.$eval("#portfolio-risk-reference", node => node.open), false);
  assert.doesNotMatch(await page.$eval("#portfolio-risk-details", node => node.innerText), /PASS|OVERBOUND|UNDERBOUND|REVIEW_REQUIRED|CALCULATED|FIFO|HHI|C[1-5]|不构成|仅供参考/);
  const top = report.positions.find(position => position.asset_name === report.concentration.top_asset_name);
  assert.match(await text(".portfolio-top-holding"), new RegExp((Number(top.market_value_cny) / Number(report.total_value_cny) * 100).toFixed(2).replace(".", "\\.")));
  assert.ok(await page.$eval(".portfolio-asset-name", node => parseFloat(getComputedStyle(node).fontSize) >= 21));
  await checkWidths("risk");
  if (!(await page.$eval("#portfolio-risk-reference", node => node.hidden))) {
    await click("#portfolio-risk-reference > summary"); await checkWidths("risk-expanded");
  }
  await click("#portfolio-tab-profit"); await page.waitForSelector("#portfolio-pnl-details", {visible: true});
  assert.equal(await text("#portfolio-details-pnl"), amount(summary.pnl_cny));
  assert.equal(await text("#overview-pnl-val"), amount(summary.daily_pnl_cny));
  const rows = await page.$$eval(".portfolio-detail-figures > div", nodes => nodes.map(node => {
    const rect = node.getBoundingClientRect(); return {left: rect.left, top: rect.top, bottom: rect.bottom};
  }));
  assert.equal(rows.length, 3); assert.ok(rows[1].top >= rows[0].bottom && rows[2].top >= rows[1].bottom);
  await checkWidths("profit");
  await click("#portfolio-profit-breakdown > summary");
  assert.equal(await page.$$("#portfolio-position-profits .portfolio-fact").then(nodes => nodes.length), report.positions.length);
  await checkWidths("profit-expanded");
  record("原有金额样式、居中概览、风险与收益逐层展开及七种窗口宽度检查通过");

  await click("#portfolio-tab-style"); await page.waitForSelector("#trade-style-empty", {visible: true});
  await click("#empty-trade-import"); await (await page.$("#trade-import-files")).uploadFile(tradeFile);
  const previewResponse = waitResponse("/api/v1/advisor/trading-history/import/preview", "POST");
  await click("#preview-trade-import");
  const preview = await previewResponse; assert.equal(preview.status(), 200);
  assert.equal((await preview.json()).accepted_count, sample.trades.length);
  await page.waitForSelector("#trade-mapping-panel", {visible: true});
  const confirmedResponse = waitResponse("/api/v1/advisor/trading-history/imports", "POST");
  await click("#confirm-trade-import");
  const confirmed = await confirmedResponse; assert.equal(confirmed.status(), 200);
  const imported = await confirmed.json();
  await page.waitForFunction(() => !document.querySelector("#trade-import-dialog").open);
  await page.waitForSelector(".trading-style-hero strong", {visible: true});
  await page.waitForFunction(() => document.querySelector("#trade-market-securities").getAttribute("aria-busy") === "false");
  assert.equal(await text(".trading-style-hero strong"), imported.style_profile.primary_style);
  assert.equal(await page.$$(".trading-style-metrics .trading-style-metric").then(nodes => nodes.length), 2);
  assert.equal(await page.$eval("#trading-style-more", node => node.open), false);
  assert.equal(await page.$eval("#trade-style-insights", node => node.open), false);
  assert.equal(await page.$eval("#trade-history-details", node => node.open), false);
  assert.doesNotMatch(await page.$eval("#trading-style", node => node.innerText), /PASS|OVERBOUND|REVIEW_REQUIRED|CALCULATED|FIFO|HHI|C[1-5]|不构成|仅供参考/);
  assert.equal(await page.$$('.nav-section-primary a[href="#trading-style"]').then(nodes => nodes.length), 0);
  await checkWidths("style");
  await click("#trading-style-more > summary");
  const insights = await api("/api/v1/advisor/trading-style/insights");
  assert.equal(await page.$$("#portfolio-trade-relations tr").then(nodes => nodes.length), insights.securities.length);
  const relations = await page.$$eval("#portfolio-trade-relations tr", nodes => nodes.map(node => [...node.children].map(cell => cell.textContent)));
  for (let index = 0; index < insights.securities.length; index++) {
    const history = insights.securities[index].history;
    const position = report.positions.find(item => item.asset_id === history.security_code);
    assert.equal(relations[index][1], `${(Number(position.market_value_cny) / Number(report.total_value_cny) * 100).toFixed(2)}%`);
    assert.equal(relations[index][2], `${Number(history.gross_amount_share_pct).toFixed(2)}%`);
  }
  await checkWidths("style-relations");
  if (insights.securities.length) {
    await click("#trade-market-details > summary");
    assert.equal(await page.$$("#trade-market-securities tr").then(nodes => nodes.length), insights.securities.length);
    await checkWidths("style-market");
  }
  await click("#trade-style-insights > summary"); await checkWidths("style-guidance");
  await click("#portfolio-trade-relations .portfolio-holding-link");
  await page.waitForSelector("#portfolio-holdings-details", {visible: true});
  await page.waitForSelector("#portfolio-position-rows details[open]");
  const linkedAsset = await page.$eval("#portfolio-position-rows details[open]", node => node.dataset.asset);
  assert.equal(linkedAsset, insights.securities[0].history.security_code);
  assert.equal(await page.$$("#portfolio-position-rows details[open]").then(nodes => nodes.length), 1);
  await checkWidths("holdings");
  await click('#portfolio-position-rows details[open] .portfolio-holding-actions button:first-child');
  await page.waitForSelector("#portfolio-diagnosis-drawer[open]");
  assert.match(await text("#portfolio-diagnosis-code"), new RegExp(linkedAsset.replace(".", "\\.")));
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.body.classList.contains("portfolio-dialog-open"));
  await click('#portfolio-position-rows details[open] .portfolio-holding-actions button:nth-child(2)');
  await page.waitForSelector("#portfolio-style-details", {visible: true});
  await page.waitForFunction(() => document.querySelector("#trade-history-rows").innerText.includes(document.querySelector("#trade-filter-security").value));
  assert.equal(await page.$eval("#trade-filter-security", node => node.value), linkedAsset);
  assert.equal(await page.$eval("#trade-history-details", node => node.open), true);
  await click("#trade-advanced-filters > summary"); await checkWidths("trade-history");
  record("真实交易文件导入、风格结果、持仓关联、诊断与成交记录筛选检查通过");

  const trades = await api(`/api/v1/advisor/trading-history/trades?cursor=0&limit=50&security=${encodeURIComponent(linkedAsset)}`);
  const firstTrade = trades.items[0];
  await click("#trade-history-rows .trade-row-actions button:first-child");
  await page.waitForSelector("#trade-edit-dialog[open]");
  const newFee = String(Number(firstTrade.fee_cny) + 1);
  await page.$eval("#trade-edit-fee", (node, value) => { node.value = value; }, newFee);
  const editedResponse = waitResponse(`/api/v1/advisor/trading-history/trades/${encodeURIComponent(firstTrade.trade_id)}`, "PATCH");
  await click('#trade-edit-dialog button[type="submit"]');
  const edited = await editedResponse; assert.equal(edited.status(), 200);
  const editedResult = await edited.json();
  await page.waitForFunction(() => !document.querySelector("#trade-edit-dialog").open);
  await page.waitForFunction(({tradeId, revision}) => [...document.querySelectorAll("#trade-history-rows tr")]
    .some(node => node.dataset.tradeId === tradeId && node.dataset.revision === String(revision)), {},
    {tradeId: firstTrade.trade_id, revision: editedResult.trade.revision});
  await page.waitForFunction(() => document.querySelector("#trade-market-securities").getAttribute("aria-busy") === "false");
  assert.equal(Number((await api(`/api/v1/advisor/trading-history/trades?cursor=0&limit=50&security=${encodeURIComponent(linkedAsset)}`)).items[0].fee_cny), Number(newFee));
  page.once("dialog", dialog => dialog.accept());
  const withdrawnResponse = waitResponse(`/api/v1/advisor/trading-history/trades/${encodeURIComponent(firstTrade.trade_id)}`, "DELETE");
  await click("#trade-history-rows .trade-row-actions button:nth-child(2)"); assert.equal((await withdrawnResponse).status(), 200);
  await page.waitForSelector("#trade-history-rows .trade-row-withdrawn .trade-row-actions button");
  const restoredResponse = waitResponse(`/api/v1/advisor/trading-history/trades/${encodeURIComponent(firstTrade.trade_id)}/restore`, "POST");
  await click("#trade-history-rows .trade-row-withdrawn .trade-row-actions button"); assert.equal((await restoredResponse).status(), 200);
  await page.waitForFunction(() => !document.querySelector("#trade-history-rows .trade-row-withdrawn"));
  record("交易编辑、撤销与恢复使用真实接口，保存结果检查通过");

  await click("#portfolio-tab-risk"); await page.waitForSelector("#portfolio-risk-details", {visible: true});
  await page.focus("#portfolio-tab-risk"); await page.keyboard.press("ArrowRight");
  await page.waitForSelector("#portfolio-pnl-details", {visible: true});
  assert.equal(await page.evaluate(() => document.activeElement.id), "portfolio-tab-profit");
  await page.goBack(); await page.waitForSelector("#portfolio-risk-details", {visible: true});
  await page.goForward(); await page.waitForSelector("#portfolio-pnl-details", {visible: true});
  await click("#portfolio-details-close"); await page.waitForSelector("#portfolio-report-card", {visible: true});
  assert.equal(await page.evaluate(() => document.activeElement.id), "portfolio-details-entry");
  await route("trading-style", "#portfolio-style-details");
  await route("holdings-management", "#portfolio-holdings-details");
  await page.reload({waitUntil: "domcontentloaded"}); await waitPortfolio(sample.positions.length);
  await page.waitForSelector("#portfolio-holdings-details", {visible: true});
  assert.equal(await page.$$("#portfolio-position-rows details[open]").then(nodes => nodes.length), 0);
  await click("#portfolio-add-entry"); await page.waitForSelector("#portfolio-modal[open]");
  await route("profile", "#profile");
  assert.equal(await page.$eval("#portfolio-modal", node => node.open), false);
  assert.equal(await page.$eval("body", node => node.classList.contains("portfolio-dialog-open")), false);
  await route("portfolio-style", "#portfolio-style-details");
  await page.waitForSelector("#open-trade-import", {visible: true}); await click("#open-trade-import");
  await route("portfolio-risk", "#portfolio-risk-details");
  assert.equal(await page.$eval("#trade-import-dialog", node => node.open), false);
  await click("#portfolio-details-close");
  await page.waitForSelector("#portfolio-report-card", {visible: true});
  record("键盘栏目切换、前进后退、刷新、旧地址与窗口关闭检查通过");

  const session = await browser.target().createCDPSession();
  await session.send("Browser.setDownloadBehavior", {behavior: "allowAndName", downloadPath: output, eventsEnabled: true});
  const downloaded = new Promise((resolve, reject) => {
    const timer = setTimeout(() => { session.off("Browser.downloadProgress", progress); reject(new Error("报告下载未完成")); }, 10000);
    function progress(event) {
      if (event.state !== "completed") return;
      clearTimeout(timer); session.off("Browser.downloadProgress", progress); resolve(event);
    }
    session.on("Browser.downloadProgress", progress);
  });
  await menuAction("#portfolio-export");
  const download = await downloaded;
  const exported = await readFile(path.join(output, download.guid), "utf8");
  const exportTitle = await page.evaluate(html => new DOMParser().parseFromString(html, "text/html").title, exported);
  assert.equal(exportTitle, "Prism 持仓正式报告"); await session.detach();
  await menuAction("#portfolio-manage-entry"); await page.waitForSelector("#portfolio-holdings-details", {visible: true});
  await click("#portfolio-position-rows details:first-child > summary");
  const removedResponse = waitResponse("/api/v1/advisor/portfolio/current", "PUT");
  await click("#portfolio-position-rows details:first-child .portfolio-holding-actions button:nth-child(3)");
  assert.equal((await removedResponse).status(), 200);
  await page.waitForFunction(count => document.querySelector("#overview-position-count").textContent === String(count), {}, sample.positions.length - 1);
  await api("/api/v1/advisor/portfolio/current", "PUT", {owner_id: context.owner_id, data_mode: "LIVE", positions: [], cash_cny: "0"});
  await route("overview", "#overview"); await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("#portfolio-empty", {visible: true});
  assert.equal(await visible("#portfolio-page-more"), false);
  await click("#portfolio-empty-style-entry"); await page.waitForSelector(".trading-style-hero strong", {visible: true});
  assert.deepEqual(evidence.pageErrors, []);
  record("报告下载、持仓删除、空持仓中的交易风格与页面运行检查通过");
  await writeFile(path.join(output, "verification.json"), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({checks: evidence.checks.length, geometryStates: evidence.geometries.length, pageErrors: evidence.pageErrors.length}));
} finally {
  await browser.close();
}
