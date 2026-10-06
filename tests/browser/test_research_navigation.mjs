import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL;
const executablePath = process.env.PRISM_TEST_BROWSER;
assert.ok(baseUrl && executablePath, "请指定独立验证服务和 Chromium 路径。");
assert.equal(process.env.PRISM_TEST_ISOLATED, "1", "账户注册需要独立数据库。");
const directory = path.resolve("output/personal-center-optimization");
const temporary = path.join(directory, "temporary");
await fs.mkdir(temporary, {recursive: true});
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: await fs.mkdtemp(path.join(directory, "navigation-profile-")),
  env: {...process.env, TEMP: temporary, TMP: temporary, TMPDIR: temporary}});
const evidence = {checks: [], states: []};
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  assert.equal(new URL(page.url()).pathname, "/login");
  await page.click("#register-tab");
  const password = randomUUID() + randomUUID();
  await page.type("#username", `profile-navigation-${Date.now()}`);
  await page.type("#password", password);
  await page.type("#confirmation", password);
  await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  await page.waitForSelector("#questionnaire-welcome[open]");
  await page.click("#welcome-later");
  const routes = {
    "profile-results": "profile", "profile-questionnaire": "profile", "profile-preferences": "profile",
    "portfolio-holdings": "overview", "holdings-report": "overview",
    "market-quotes": "market", "market-risk": "market", "market-sectors": "market",
  };
  for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {
    await page.setViewport({width, height});
    for (const [route, parent] of Object.entries(routes)) {
      await page.evaluate(route => { window.location.hash = route; }, route);
      await page.waitForFunction(({route, parent}) => {
        const root = document.getElementById(parent);
        return !root.hidden && root.dataset.activeSubpage === route;
      }, {}, {route, parent});
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const result = await page.evaluate(({route, parent}) => ({
        selected: document.querySelector(`#workspace-page-tabs a[href="#${route}"]`)?.getAttribute("aria-current"),
        tabsVisible: document.querySelector("#workspace-page-tabs").getClientRects().length > 0,
        otherVisible: [...document.querySelectorAll(`#${parent} [data-subpage]`)].filter(node => node.dataset.subpage !== (route === "profile-preferences" ? "profile-results" : route) && node.getClientRects().length > 0).map(node => node.dataset.subpage),
        settingsOpen: document.querySelector("#profile-display-dialog").open,
        scrollLocked: document.body.classList.contains("profile-settings-open"),
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }), {route, parent});
      assert.equal(result.tabsVisible, parent === "market", `${width}: ${route}`);
      if (parent === "market") assert.equal(result.selected, "page", `${width}: ${route}`);
      assert.deepEqual(result.otherVisible, [], `${width}: ${route}`);
      assert.equal(result.settingsOpen, route === "profile-preferences", `${width}: ${route}`);
      assert.equal(result.scrollLocked, result.settingsOpen, `${width}: ${route}`);
      assert.equal(result.overflow, false, `${width}: ${route} page overflow`);
      evidence.states.push({width, route, ...result});
    }
  }
  evidence.checks.push("真实账户与三种宽度下的 24 次页面导航通过");
  await page.setViewport({width: 390, height: 420});
  await page.evaluate(() => { window.location.hash = "profile-results"; });
  await page.waitForFunction(() => document.querySelector("#profile").dataset.activeSubpage === "profile-results");
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.evaluate(() => window.scrollTo(0, 250));
  await page.waitForFunction(() => window.scrollY >= 200);
  const savedScroll = await page.evaluate(() => window.scrollY);
  await page.$eval("#profile-display-settings", node => node.focus({preventScroll: true}));
  await page.keyboard.press("Enter");
  await page.waitForSelector("#profile-display-dialog[open]");
  assert.equal(await page.evaluate(() => scrollY), savedScroll);
  await page.goBack();
  await page.waitForFunction(() => location.hash === "#profile-results" && !document.querySelector("#profile-display-dialog").open);
  await page.goForward();
  await page.waitForSelector("#profile-display-dialog[open]");
  await page.click("#profile-display-close");
  await page.waitForFunction(() => location.hash === "#profile-results" && !document.body.classList.contains("profile-settings-open"));
  await page.waitForFunction(saved => Math.abs(scrollY - saved) < 2, {}, savedScroll);
  assert.equal(await page.$eval("#profile-display-settings", node => node === document.activeElement), true);
  evidence.checks.push("设置弹窗的键盘入口、背景位置、浏览器前进后退和关闭焦点通过");
  await page.setViewport({width: 1440, height: 1000});
  await page.evaluate(() => { location.hash = "profile-preferences"; });
  await page.waitForSelector("#profile-display-dialog[open]");
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("body:not(.questionnaire-pending) #profile-display-dialog[open]");
  assert.equal(await page.$eval("#questionnaire-welcome", node => node.open), false);
  const initialPolicy = await page.$eval('input[name="profile-display-policy-level"]:checked', node => node.value);
  await page.click(`input[name="profile-display-policy-level"][value="${initialPolicy === "80" ? "20" : "80"}"]`);
  await page.mouse.click(5, 5);
  await page.waitForFunction(() => !document.querySelector("#profile-display-dialog").open && location.hash === "#profile-results");
  await page.click("#profile-display-settings");
  await page.waitForSelector("#profile-display-dialog[open]");
  assert.equal(await page.$eval('input[name="profile-display-policy-level"]:checked', node => node.value), initialPolicy);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => location.hash === "#profile-results");
  evidence.checks.push("未测评账户的设置链接刷新、点击遮罩关闭与取消修改通过");
  for (const [legacy, canonical] of Object.entries({profile: "profile-questionnaire", overview: "holdings-report", portfolio: "portfolio-holdings", market: "market-quotes"})) {
    await page.evaluate(route => { window.location.hash = route; }, legacy);
    await page.waitForFunction(({canonical, routes}) => document.getElementById(routes[canonical])?.dataset.activeSubpage === canonical, {}, {canonical, routes});
  }
  await page.click("#nav-copilot");
  await page.waitForSelector("body.copilot-active");
  await page.click("#nav-store");
  await page.waitForSelector("#skill-store:not([hidden])");
  assert.equal(await page.$eval("#nav-store", node => node.getAttribute("aria-current")), "location");
  assert.deepEqual(errors, []);
  evidence.errors = errors;
  await fs.writeFile(path.join(directory, "navigation-verification.json"), JSON.stringify(evidence, null, 2));
  process.stdout.write("页面导航与偏好弹窗检查通过。\n");
} finally {
  await browser.close();
}
