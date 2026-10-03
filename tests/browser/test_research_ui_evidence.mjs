import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

// Only run against the isolated temporary-storage test server.
const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8022/";
const evidenceDir = process.env.PRISM_TEST_EVIDENCE_DIR || path.resolve("docs/submission/test-evidence/research-ui");
const executablePath = process.env.PRISM_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
const evidence = {created_at: new Date().toISOString(), server: baseUrl, browser: await browser.version(), python: ".venv Python 3.12.12", source: "isolated temporary SQLite, disabled live financial/model providers; synthetic calculations only", real_data_acceptance: false, viewports: [], console: [], failed_resources: [], readonly: {}, transitions: {}};
await fs.mkdir(evidenceDir, {recursive: true});
try {
  const page = await browser.newPage();
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (["error", "warning"].includes(message.type())) evidence.console.push({level: message.type(), text: message.text()}); });
  page.on("response", response => {if (response.status() >= 400) evidence.failed_resources.push({path: new URL(response.url()).pathname, status: response.status()});});
  const fill = async (id, value) => page.$eval(`#${id}`, (node, value) => {node.value = value; node.dispatchEvent(new Event("input", {bubbles: true})); node.dispatchEvent(new Event("change", {bubbles: true}));}, value);
  const navigate = async hash => { await page.evaluate(hash => {location.hash = hash;}, hash); await page.waitForSelector(`#${hash}:not([hidden])`); };
  await page.goto(baseUrl, {waitUntil: "networkidle0"});
  await page.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await page.click("#welcome-later");
  await navigate("research-knowledge");
  await fill("knowledge-query", "browser-library-evidence"); await page.click("#knowledge-search");
  await page.waitForFunction(() => !document.querySelector("#knowledge-search").disabled);
  await navigate("live-research");
  assert.equal(await page.$eval("#research-advanced-settings", node => node.open), false);
  await page.click("#research-advanced-settings > summary"); await page.click("#research-submit");
  await page.waitForFunction(() => document.querySelector("#research-run-result").innerText.includes("研究任务 · 已完成"));
  await page.click("#research-advanced-settings > summary");
  await navigate("research-algorithms");
  assert.equal(await page.$eval("#algorithm-input-settings", node => node.open), false);
  await page.click("#algorithm-input-settings > summary");
  await page.select("#algorithm-kind", "covariance");
  const points = Array.from({length: 80}, (_, index) => ({time: new Date(Date.UTC(2025, 0, index + 1)).toISOString().slice(0, 10), value: Math.sin(index * 1.9187) * .01}));
  const covariance = {source: "Synthetic UI evidence fixture; not real financial evidence", as_of: "2026-09-30T00:00:00Z", series: {A: points, B: points.map((point, index) => ({...point, value: point.value * .5 + Math.cos(index) * .002}))}};
  await fill("algorithm-json", JSON.stringify(covariance)); await page.click("#algorithm-compute");
  await page.waitForFunction(() => !document.querySelector("#algorithm-compute").disabled);
  assert.match(await page.$eval("#algorithm-output", node => node.innerText), /资产联动风险 · 已计算/);

  // Test a delayed old algorithm response against an intervening selector change.
  await page.setRequestInterception(true);
  let releaseRequest, arrivedRequest;
  const arrived = new Promise(resolve => {arrivedRequest = resolve;});
  const intercept = request => {
    if (request.url().endsWith("/algorithms/regime") && request.method() === "POST") {releaseRequest = () => request.continue(); arrivedRequest();}
    else request.continue();
  };
  page.on("request", intercept);
  await page.select("#algorithm-kind", "regime"); await fill("algorithm-json", JSON.stringify({source: "Synthetic stale-response fixture", as_of: "2026-09-30T00:00:00Z", training_size: 252, returns: []}));
  await page.click("#algorithm-compute"); await arrived;
  await page.select("#algorithm-kind", "covariance"); await releaseRequest();
  await page.waitForFunction(() => !document.querySelector("#algorithm-compute").disabled);
  assert.equal(await page.$eval("#algorithm-output", node => node.textContent), "");
  evidence.transitions.stale_algorithm_response_suppressed = true;
  page.off("request", intercept); await page.setRequestInterception(false);

  // A hidden chart is destroyed, then recreated from the original computed data.
  await page.select("#algorithm-kind", "regime");
  const returns = Array.from({length: 300}, (_, index) => ({time: new Date(Date.UTC(2025, 0, index + 1)).toISOString().slice(0, 10), value: (index % 70 < 35 ? .003 : .03) * Math.sin(index * 1.9187) + .002 * Math.cos(index * 2.361)}));
  await fill("algorithm-json", JSON.stringify({source: "Synthetic UI evidence fixture; not real financial evidence", as_of: "2026-09-30T00:00:00Z", training_size: 252, returns}));
  await page.click("#algorithm-compute"); await page.waitForSelector("#algorithm-chart canvas");
  await navigate("research-knowledge"); assert.equal((await page.$$("#algorithm-chart canvas")).length, 0);
  await navigate("research-algorithms"); await page.waitForSelector("#algorithm-chart canvas"); evidence.transitions.hidden_chart_destroyed_and_recreated = true;
  for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {
    await page.setViewport({width, height});
    for (const hash of ["research-knowledge", "live-research", "research-algorithms"]) {
      await navigate(hash);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      assert.equal(overflow, false, `${width} ${hash} overflow`);
      evidence.viewports.push({width, height, hash: `#${hash}`, overflow, browser_page_errors: errors.length, browser_console_errors: evidence.console.filter(message => message.level === "error").length});
      if (width !== 1024) {
        const filename = `${hash}-${width}.png`;
        await page.screenshot({path: path.join(evidenceDir, filename), fullPage: width === 390});
        evidence.viewports.at(-1).screenshot = filename;
      }
    }
  }

  const snapshot = await browser.newPage(); const snapshotRequests = [];
  snapshot.on("pageerror", error => errors.push(error.message));
  snapshot.on("request", request => { if (new URL(request.url()).pathname.startsWith("/api/")) snapshotRequests.push({method: request.method(), path: new URL(request.url()).pathname}); });
  const snapshotUrl = new URL(baseUrl); snapshotUrl.searchParams.set("pages", "1");
  await snapshot.goto(snapshotUrl.href, {waitUntil: "networkidle0"});
  await snapshot.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
  const readonlyRoutes = [];
  for (const hash of ["research-knowledge", "live-research", "research-algorithms"]) {
    await snapshot.click(`.nav-section-primary a[href="#${hash}"]`);
    await snapshot.waitForSelector(`#${hash}:not([hidden])`);
    readonlyRoutes.push({hash: `#${hash}`, write_controls_disabled: await snapshot.$$eval(`#${hash} [data-write]`, nodes => nodes.every(node => node.disabled))});
    if (hash === "research-knowledge") {
      await snapshot.$eval("#knowledge-query", node => {node.value = "readonly probe";}); await snapshot.click("#knowledge-search");
      assert.equal(await snapshot.$eval("#knowledge-search", node => node.disabled), true);
    }
  }
  assert.ok(readonlyRoutes.every(route => route.write_controls_disabled));
  assert.equal(snapshotRequests.filter(request => request.method !== "GET").length, 0);
  evidence.readonly = {mode: "?pages=1", routes: readonlyRoutes, api_requests: snapshotRequests, mutating_api_requests: 0, search_post_control_disabled: true};
  evidence.transitions.legacy_refresh = [];
  for (const [legacy, canonical, root] of [["profile", "profile-results", "profile"], ["overview", "holdings-report", "overview"], ["portfolio", "holdings-management", "overview"], ["market", "market-quotes", "market"]]) {
    const url = new URL(snapshotUrl); url.hash = legacy; await snapshot.goto(url.href, {waitUntil: "networkidle0"}); await snapshot.reload({waitUntil: "networkidle0"});
    await snapshot.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
    const actual = await snapshot.evaluate(root => ({hash: location.hash, resolved_subpage: document.getElementById(root)?.dataset.activeSubpage}), root);
    assert.equal(actual.resolved_subpage, canonical);
    assert.equal(actual.hash, `#${legacy}`);
    evidence.transitions.legacy_refresh.push({requested_hash: `#${legacy}`, ...actual, passed: true});
  }
  const unassessed = await browser.newPage(); unassessed.on("pageerror", error => errors.push(error.message));
  const profileUrl = new URL(baseUrl); profileUrl.hash = "profile";
  await unassessed.goto(profileUrl.href, {waitUntil: "networkidle0"}); await unassessed.reload({waitUntil: "networkidle0"});
  await unassessed.waitForFunction(() => !document.body.classList.contains("questionnaire-pending") && document.querySelector("#profile").dataset.activeSubpage === "profile-questionnaire");
  assert.equal(await unassessed.evaluate(() => location.hash), "#profile");
  evidence.transitions.uncompleted_questionnaire_refresh = {hash: "#profile", resolved_subpage: "profile-questionnaire", passed: true};
  assert.deepEqual(errors, []);
  evidence.browser_page_errors = errors; evidence.passed = true;
  await fs.writeFile(path.join(evidenceDir, "summary.json"), JSON.stringify(evidence, null, 2) + "\n");
  process.stdout.write("Research UI evidence passed: three viewports, read-only routes, legacy reload, stale-response suppression and hidden-chart recreation.\n");
} finally { await browser.close(); }
