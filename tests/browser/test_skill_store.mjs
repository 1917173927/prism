import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

// Requires research_platform_server.py; never run mutations against a user database.
const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8020/";
const executablePath = process.env.PRISM_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(baseUrl, {waitUntil: "networkidle0"});
  await page.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await page.click("#welcome-later");
  await page.click('.nav-section-primary a[href="#skill-store"]');
  await page.waitForSelector('[data-skill-id="hithink-market-query"]');
  assert.equal(await page.$eval("#skill-import-panel", node => node.hidden), false);
  for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {
    await page.setViewport({width, height});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false, `${width} page overflow`);
  }
  await page.setViewport({width: 1024, height: 768});
  await page.type("#skill-store-search", "不存在的能力");
  assert.match(await page.$eval("#skill-store-catalog", node => node.textContent), /没有能力版本/);
  await page.$eval("#skill-store-search", node => { node.value = ""; node.dispatchEvent(new Event("input", {bubbles: true})); });
  const metadata = {skill_id: "browser-test-market", version: "1.0.0", name: "浏览器验证行情", operation: "MARKET_DATA", endpoint: "/v1/query2data"};
  await page.click("#skill-import-panel summary");
  await page.type("#skill-metadata-input", JSON.stringify(metadata));
  await page.click("#skill-register-button");
  await page.waitForSelector('[data-skill-id="browser-test-market"]');
  await page.waitForFunction(() => document.querySelector("#skill-store-message").textContent.includes("等待验证"));
  assert.match(await page.$eval('[data-skill-id="browser-test-market"]', node => node.textContent), /待验证/);
  await page.click('[data-skill-id="browser-test-market"] button');
  await page.waitForSelector("#skill-store-detail:not([hidden])");
  await page.click('#skill-store-detail button:nth-of-type(1)');
  await page.waitForFunction(() => document.querySelector("#skill-store-message").textContent.includes("验证通过"));
  assert.match(await page.$eval('[data-skill-id="browser-test-market"]', node => node.textContent), /已安装/);
  const checkbox = '[data-skill-id="browser-test-market"] input[type="checkbox"]';
  if (!(await page.$eval(checkbox, node => node.checked))) {
    await page.click(checkbox);
    await page.waitForFunction(() => document.querySelector("#skill-store-message").textContent.includes("个人能力选择已保存"));
  }
  await page.click(checkbox);
  await page.waitForFunction(() => document.querySelector("#skill-store-message").textContent.includes("个人能力选择已保存"));
  assert.equal(await page.$eval(checkbox, node => node.checked), false);
  const isolation = await page.evaluate(async () => {
    const body = await fetch("/api/v1/skills", {headers: {"X-Owner-ID": "browser-other-user"}}).then(response => response.json());
    return body.items.find(item => item.skill_id === "browser-test-market").personal_enabled;
  });
  assert.equal(isolation, true);
  await page.click("#skill-store-personal");
  assert.equal(await page.$('[data-skill-id="browser-test-market"]'), null);
  const ordinary = await browser.newPage();
  await ordinary.setRequestInterception(true);
  ordinary.on("request", request => {
    if (new URL(request.url()).pathname === "/api/v1/auth/context") request.respond({status: 200, contentType: "application/json", body: JSON.stringify({enabled: true, admin: false, owner_id: "browser-ordinary-user"})});
    else request.continue();
  });
  await ordinary.goto(baseUrl, {waitUntil: "networkidle0"});
  await ordinary.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
  if (await ordinary.$eval("#questionnaire-welcome", node => node.open)) await ordinary.click("#welcome-later");
  await ordinary.click('.nav-section-primary a[href="#skill-store"]');
  await ordinary.waitForSelector('[data-skill-id="hithink-market-query"]');
  assert.equal(await ordinary.$eval("#skill-import-panel", node => node.hidden), true);
  await ordinary.click('[data-skill-id="hithink-market-query"] button');
  assert.equal(await ordinary.$$("#skill-store-detail button").then(items => items.length), 0);
  await ordinary.close();
  await page.click("#skill-store-public");
  await page.click('[data-skill-id="browser-test-market"] button');
  // Advance the server revision outside the UI, then verify stale changes surface a conflict and refresh.
  await page.evaluate(async () => {
    const item = await fetch("/api/v1/skills/browser-test-market/1.0.0", {headers: {"X-Owner-ID": "demo-owner"}}).then(response => response.json());
    await fetch("/api/v1/skills/browser-test-market/1.0.0", {method: "PATCH", headers: {"Content-Type": "application/json", "X-Owner-ID": "demo-owner"}, body: JSON.stringify({action: "disable", expected_revision: item.revision})});
  });
  await page.click('#skill-store-detail button:nth-of-type(1)');
  await page.waitForFunction(() => document.querySelector("#skill-store-message").textContent.includes("版本已变化"));
  assert.match(await page.$eval("#skill-store-detail", node => node.textContent), /全局启用/);
  await page.click('#skill-store-detail button:nth-of-type(1)');
  await page.waitForFunction(() => document.querySelector("#skill-store-message").textContent.includes("状态已更新"));
  await page.click('#skill-store-detail button:nth-of-type(2)');
  await page.waitForFunction(() => document.querySelector("#skill-store-message").textContent.includes("已卸载"));
  assert.match(await page.$eval('[data-skill-id="browser-test-market"]', node => node.textContent), /已卸载/);
  await page.click("#skill-store-installed");
  assert.equal(await page.$('[data-skill-id="browser-test-market"]'), null);
  assert.deepEqual(errors, []);
  if (process.env.PRISM_TEST_SCREENSHOT) await page.screenshot({path: process.env.PRISM_TEST_SCREENSHOT, fullPage: true});
  process.stdout.write("Skill store real-API checks passed: search, install, verify, owner selection, stale revision, enable and uninstall.\n");
} finally { await browser.close(); }
