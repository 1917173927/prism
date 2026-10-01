import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

// Run against a static, isolated server. Snapshot mode never calls live APIs.
const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:4179/static/index.html";
const executablePath = process.env.PRISM_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const target = new URL(baseUrl);
  target.searchParams.set("pages", "1");
  await page.goto(target.href, {waitUntil: "networkidle0"});
  await page.waitForFunction(() => !document.body.classList.contains("questionnaire-pending"));
  target.hash = "profile";
  await page.goto(target.href, {waitUntil: "networkidle0"});
  await page.reload({waitUntil: "networkidle0"});
  await page.waitForFunction(() => !document.body.classList.contains("questionnaire-pending") && document.querySelector("#profile").dataset.activeSubpage === "profile-results");
  assert.equal(await page.evaluate(() => window.location.hash), "#profile", "Completed questionnaire must retain explicit old profile route on reload");
  const routes = {
    "profile-results": "profile", "profile-questionnaire": "profile", "profile-preferences": "profile",
    "holdings-management": "overview", "holdings-report": "overview",
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
      const result = await page.evaluate(({route, parent}) => ({
        selected: document.querySelector(`#workspace-page-tabs a[href="#${route}"]`)?.getAttribute("aria-current"),
        otherVisible: [...document.querySelectorAll(`#${parent} [data-subpage]`)].filter(node => node.dataset.subpage !== route && node.getBoundingClientRect().height > 0).map(node => node.dataset.subpage),
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }), {route, parent});
      assert.equal(result.selected, "page", `${width}: ${route}`);
      assert.deepEqual(result.otherVisible, [], `${width}: ${route}`);
      assert.equal(result.overflow, false, `${width}: ${route} page overflow`);
    }
  }
  await page.setViewport({width: 1024, height: 768});
  await page.evaluate(() => { window.location.hash = "profile-results"; });
  await page.waitForFunction(() => document.querySelector("#profile").dataset.activeSubpage === "profile-results");
  await page.evaluate(() => window.scrollTo(0, 250));
  await page.waitForFunction(() => window.scrollY >= 200);
  const savedScroll = await page.evaluate(() => window.scrollY);
  await page.click('#workspace-page-tabs a[href="#profile-preferences"]');
  await page.waitForFunction(() => document.querySelector("#profile").dataset.activeSubpage === "profile-preferences" && window.scrollY === 0);
  await page.click('#workspace-page-tabs a[href="#profile-results"]');
  await page.waitForFunction(saved => Math.abs(window.scrollY - saved) < 2, {}, savedScroll);
  await page.goBack();
  await page.waitForFunction(() => document.querySelector("#profile").dataset.activeSubpage === "profile-preferences");
  for (const [legacy, canonical] of Object.entries({profile: "profile-results", overview: "holdings-report", portfolio: "holdings-management", market: "market-quotes"})) {
    await page.evaluate(route => { window.location.hash = route; }, legacy);
    await page.waitForFunction(({canonical, routes}) => document.getElementById(routes[canonical])?.dataset.activeSubpage === canonical, {}, {canonical, routes});
  }
  await page.click('.nav-section-primary a[href="#skill-store"]');
  await page.waitForSelector("#skill-store:not([hidden])");
  assert.equal(await page.$eval('.nav-section-primary a[href="#skill-store"]', node => node.getAttribute("aria-current")), "location");
  assert.deepEqual(errors, []);
  if (process.env.PRISM_TEST_SCREENSHOT) await page.screenshot({path: process.env.PRISM_TEST_SCREENSHOT, fullPage: true});
  process.stdout.write("Research navigation browser checks passed at 1440, 1024 and 390 pixels.\n");
} finally {
  await browser.close();
}
