import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import {mkdir, mkdtemp, writeFile} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8000";
const executablePath = process.env.PRISM_TEST_BROWSER || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const repoRoot = fileURLToPath(new URL("../../", import.meta.url));
const outputDirectory = path.join(repoRoot, "output");
await mkdir(outputDirectory, {recursive: true});
const browserDirectory = await mkdtemp(path.join(outputDirectory, "market-sidebar-browser-"));
const temporaryDirectory = path.join(browserDirectory, "temporary");
await mkdir(temporaryDirectory);
const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  userDataDir: path.join(browserDirectory, "profile"),
  env: {...process.env, TMPDIR: temporaryDirectory},
  args: ["--no-sandbox"],
});

try {
  const page = await browser.newPage();
  const pageErrors = [];
  const analyses = [];
  page.on("pageerror", error => pageErrors.push(error.message));

  function waitForAnalysis(market, indexId, interval = "1d") {
    return page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === `/api/v1/market/analysis/${market}/${indexId}`
        && url.searchParams.get("interval") === interval;
    }, {timeout: 60000});
  }

  async function readAnalysis(response) {
    assert.equal(response.status(), 200);
    const data = await response.json();
    analyses.push({market: data.market, indexId: data.index_id, interval: data.interval,
      status: data.status, source: data.source, bars: data.bars.length});
    return data;
  }

  async function navigate(section) {
    await page.click(`.nav-section-primary a[href="#${section}"]`);
    await page.waitForSelector(`#${section}:not([hidden])`);
  }

  async function geometry() {
    return page.evaluate(() => {
      const rect = selector => {
        const {x, y, width, height, bottom} = document.querySelector(selector).getBoundingClientRect();
        return {x, y, width, height, bottom};
      };
      return {navigation: rect("#home-navigation"), brand: rect(".brand"),
        actions: rect("#home-navigation-actions"), sidebar: rect("#home-history-sidebar"),
        chart: rect("#market-kline"), footer: rect(".market-chart-footer"),
        overflow: document.documentElement.scrollWidth > innerWidth + 1};
    });
  }

  async function waitForSidebar(collapsed) {
    await page.waitForFunction(expected => {
      const sidebar = document.querySelector("#home-history-sidebar");
      const positioned = sidebar.getBoundingClientRect().left >= 0
        && (innerWidth <= 760 || Math.abs(document.querySelector(".main").getBoundingClientRect().left - sidebar.getBoundingClientRect().right) < 1);
      return document.body.classList.contains("home-history-collapsed") === expected
        && getComputedStyle(sidebar).visibility === (expected ? "hidden" : "visible")
        && (expected || positioned);
    }, {}, collapsed);
  }

  const initialAnalysis = waitForAnalysis("CN", "sse-composite");
  await page.setViewport({width: 1440, height: 900});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  if (new URL(page.url()).pathname === "/login") {
    const password = randomUUID() + randomUUID();
    await page.click("#register-tab");
    await page.type("#username", `market-ui-${Date.now()}`);
    await page.type("#password", password);
    await page.type("#confirmation", password);
    await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  }
  await page.waitForSelector("body:not(.questionnaire-pending)");
  await page.evaluate(() => document.querySelector("#questionnaire-welcome").close());
  const initialData = await readAnalysis(await initialAnalysis);
  assert.ok(initialData.bars.length > 20, JSON.stringify(analyses));
  const catalog = await page.evaluate(async () => {
    const context = await fetch("/api/v1/auth/context").then(response => response.json());
    const response = await fetch("/api/v1/market/catalog", {headers: {"X-Owner-ID": context.owner_id}});
    if (!response.ok) throw new Error(`指数目录请求失败：${response.status}`);
    return response.json();
  });
  const homeGeometry = await geometry();
  await navigate("market");
  await page.waitForSelector("#market-kline canvas");
  const expandedGeometry = await geometry();
  assert.equal(expandedGeometry.navigation.height, homeGeometry.navigation.height);
  assert.equal(expandedGeometry.navigation.y, homeGeometry.navigation.y);
  assert.equal(expandedGeometry.brand.x, homeGeometry.brand.x);
  assert.equal(expandedGeometry.actions.x, homeGeometry.actions.x);
  assert.equal(expandedGeometry.sidebar.width, 248);
  assert.equal(expandedGeometry.sidebar.y, expandedGeometry.navigation.bottom);
  assert.ok(expandedGeometry.chart.x > expandedGeometry.sidebar.width);
  assert.ok(expandedGeometry.chart.y < 360, JSON.stringify(expandedGeometry));
  assert.ok(expandedGeometry.chart.bottom < 900, JSON.stringify(expandedGeometry));
  assert.ok(expandedGeometry.footer.y >= expandedGeometry.chart.bottom);
  assert.equal(expandedGeometry.chart.height, 420);
  assert.equal(expandedGeometry.overflow, false);
  assert.equal(await page.$eval(".nav-section-primary", node => node.parentElement.id), "home-primary-navigation");
  assert.equal(await page.$eval('.nav-item[href="#market"]', node => node.getAttribute("aria-current")), "location");
  assert.equal(await page.$eval("#market-index-options", node => node.closest(".sidebar").id), "home-history-sidebar");
  assert.equal(await page.$eval(".chat-history-panel", node => getComputedStyle(node).display), "none");
  assert.equal(await page.$eval("#market-index-options", node => node.children.length), catalog.filter(item => item.market === "CN").length);
  assert.equal(await page.$eval("#market-data-meta", (node, source) => node.textContent.includes(source), initialData.source), true);

  const canvas = await page.$("#market-kline canvas");
  await page.click("#market-sidebar-hide");
  await waitForSidebar(true);
  await page.waitForFunction(previousWidth => document.querySelector("#market-kline").getBoundingClientRect().width > previousWidth + 240,
    {}, expandedGeometry.chart.width);
  assert.equal(await page.$eval("#home-history-sidebar", node => node.inert), true);
  assert.equal(await page.$eval("#home-history-show", node => node.getAttribute("aria-label")), "展开指数");
  assert.equal(await canvas.evaluate(node => node === document.querySelector("#market-kline canvas")), true);
  const collapsedGeometry = await geometry();
  assert.equal(await page.evaluate(() => {
    const button = document.querySelector("#home-history-show").getBoundingClientRect();
    const heading = document.querySelector(".market-result-heading").getBoundingClientRect();
    return button.bottom <= heading.top;
  }), true);
  await page.click("#home-history-show");
  await waitForSidebar(false);
  await page.waitForFunction(previousWidth => Math.abs(document.querySelector("#market-kline").getBoundingClientRect().width - previousWidth) < 1,
    {}, expandedGeometry.chart.width);
  assert.equal(await page.$eval("#home-history-sidebar", node => node.inert), false);
  assert.equal(await canvas.evaluate(node => node === document.querySelector("#market-kline canvas")), true);

  const changedAnalysis = waitForAnalysis("CN", "szse-component");
  await page.click('[data-market-index="szse-component"]');
  const changedData = await readAnalysis(await changedAnalysis);
  assert.ok(changedData.bars.length > 20, JSON.stringify(analyses));
  await page.waitForFunction(() => document.querySelector("#market-result-content h3")?.textContent.startsWith("深证成指"));
  assert.equal(await page.$eval('[data-market-index="szse-component"]', node => node.getAttribute("aria-pressed")), "true");
  await page.waitForSelector("#market-kline canvas");
  const chartRect = (await geometry()).chart;
  await page.mouse.move(chartRect.x + chartRect.width / 2, chartRect.y + 100);
  await page.waitForFunction(() => document.querySelector("#market-crosshair-info").textContent.includes("成交量"));
  await page.click('[data-market-range="6"]');
  await page.click("#market-fit-chart");
  for (const indicator of ["macd", "kdj"]) {
    await page.click(`[data-market-indicator="${indicator}"]`);
    assert.equal((await geometry()).chart.height, 550);
    assert.equal(await page.$eval(`[data-market-indicator="${indicator}"]`, node => node.getAttribute("aria-pressed")), "true");
    await page.click(`[data-market-indicator="${indicator}"]`);
    assert.equal((await geometry()).chart.height, 420);
  }
  await page.click('[data-market-indicator="boll"]');
  assert.equal(await page.$eval('[data-market-indicator="boll"]', node => node.getAttribute("aria-pressed")), "false");
  await page.click('[data-market-indicator="boll"]');

  const monthlyAnalysis = waitForAnalysis("CN", "szse-component", "1M");
  await page.click('[data-market-interval="1M"]');
  const monthlyData = await readAnalysis(await monthlyAnalysis);
  assert.equal(monthlyData.interval, "1M");
  assert.ok(monthlyData.bars.length > 0);
  await page.waitForSelector("#market-kline canvas");
  const dailyAnalysis = waitForAnalysis("CN", "szse-component");
  await page.click('[data-market-interval="1d"]');
  await readAnalysis(await dailyAnalysis);

  const latestAnalysis = waitForAnalysis("CN", "chinext");
  await page.click('[data-market-index="csi-300"]');
  await page.click('[data-market-index="chinext"]');
  const latestData = await readAnalysis(await latestAnalysis);
  assert.ok(latestData.bars.length > 20);
  await page.waitForFunction(() => document.querySelector("#market-result-content h3")?.textContent.startsWith("创业板指"));
  assert.equal(await page.$eval("#market-index-input", node => node.value), "chinext");
  const refreshAnalysis = waitForAnalysis("CN", "chinext");
  await page.click("#market-assess-button");
  await readAnalysis(await refreshAnalysis);
  await page.waitForSelector("#market-kline canvas");

  await page.click("#persona-switcher-bar > summary");
  await page.click("#home-context-trigger");
  await page.waitForSelector("#copilot.context-open:not([hidden])");
  await page.click("#home-context-close");
  await navigate("market");
  await page.click("#market-followup-button");
  await page.waitForSelector("#copilot:not([hidden])");
  assert.equal(await page.$eval("#copilot-natural-input", node => node.value.includes("创业板指")), true);
  await navigate("market");

  await page.click("#market-sidebar-hide");
  await waitForSidebar(true);
  await navigate("copilot");
  await waitForSidebar(false);
  assert.equal(await page.$eval(".market-sidebar-panel", node => getComputedStyle(node).display), "none");
  assert.equal(await page.$eval(".chat-history-panel", node => getComputedStyle(node).display), "grid");
  await page.click("#home-history-hide");
  await waitForSidebar(true);
  await navigate("market");
  await waitForSidebar(true);
  await page.click("#home-history-show");
  await waitForSidebar(false);
  await navigate("overview");
  assert.equal(await page.$eval("body", node => node.classList.contains("portfolio-active")), true);
  assert.equal(await page.$eval("#home-history-sidebar", node => node.inert), true);
  assert.equal(await page.$eval("#home-history-sidebar", node => getComputedStyle(node).display), "none");
  assert.equal(await page.$eval(".nav-section-primary", node => node.parentElement.id), "home-primary-navigation");
  await navigate("market");
  await waitForSidebar(false);

  const desktopWidths = [];
  for (const width of [1024, 2200]) {
    await page.setViewport({width, height: 900});
    const current = await geometry();
    assert.equal(current.sidebar.width, 248);
    assert.equal(current.overflow, false);
    desktopWidths.push({width, chart: current.chart});
  }
  await page.emulateMediaFeatures([{name: "prefers-reduced-motion", value: "reduce"}]);
  await page.click("#market-sidebar-hide");
  assert.equal(await page.$eval(".sidebar", node => node.getAnimations().length), 0);
  assert.equal(await page.$eval(".main", node => node.getBoundingClientRect().left), 0);
  await page.click("#home-history-show");
  await page.emulateMediaFeatures([]);

  await page.setViewport({width: 390, height: 844});
  await waitForSidebar(true);
  const mobileGeometry = await geometry();
  assert.equal(mobileGeometry.navigation.height, 104);
  assert.equal(mobileGeometry.overflow, false);
  await page.click("#home-history-show");
  await waitForSidebar(false);
  assert.equal(await page.$eval(".market-region-tabs", node => node.closest(".sidebar").id), "home-history-sidebar");
  assert.equal(await page.$eval("#market-index-options", node => getComputedStyle(node).display), "grid");
  const mobileAnalysis = waitForAnalysis("CN", "sse-composite");
  await page.click('[data-market-index="sse-composite"]');
  await waitForSidebar(true);
  await readAnalysis(await mobileAnalysis);
  await page.waitForSelector("#market-kline canvas");
  await page.click("#home-history-show");
  await waitForSidebar(false);
  await page.keyboard.press("Escape");
  await waitForSidebar(true);
  await page.click("#home-history-show");
  await waitForSidebar(false);
  await page.click("#home-history-backdrop", {offset: {x: 360, y: 30}});
  await waitForSidebar(true);

  for (const market of ["HK", "US", "CN"]) {
    await page.click("#home-history-show");
    await waitForSidebar(false);
    const first = catalog.find(item => item.market === market);
    const marketAnalysis = waitForAnalysis(market, first.index_id);
    await page.click(`[data-market-region="${market}"]`);
    await readAnalysis(await marketAnalysis);
    assert.equal(await page.$eval("#market-index-options", node => node.children.length), catalog.filter(item => item.market === market).length);
    assert.equal(await page.$eval("#market-industries-section", node => node.hidden), market !== "CN");
    await page.keyboard.press("Escape");
    await waitForSidebar(true);
  }
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("body.market-active:not(.questionnaire-pending)");
  await page.evaluate(() => document.querySelector("#questionnaire-welcome").close());
  await waitForSidebar(true);
  assert.equal(await page.$eval("#home-history-show", node => node.textContent.trim()), "展开指数");
  assert.deepEqual(pageErrors, []);
  await writeFile(path.join(outputDirectory, "market-sidebar-verification.json"), JSON.stringify({
    homeGeometry, expandedGeometry, collapsedGeometry, desktopWidths, mobileGeometry, analyses, pageErrors,
  }, null, 2));
  process.stdout.write("大盘侧栏、共用导航与实际行情图表检查通过。\n");
} finally {
  await browser.close();
}
