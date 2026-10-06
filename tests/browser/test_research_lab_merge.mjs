import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

// Writes use the explicitly isolated local acceptance database.
assert.equal(process.env.PRISM_TEST_ISOLATED, "1");
const base = process.env.PRISM_TEST_BASE_URL;
assert.ok(base && ["127.0.0.1", "localhost"].includes(new URL(base).hostname));
const output = path.resolve("output/pr-sync-20261006/research-lab-browser");
await fs.mkdir(output, {recursive: true});
const profile = await fs.mkdtemp(path.join(output, "profile-"));
const browser = await puppeteer.launch({
  executablePath: process.env.PRISM_TEST_BROWSER,
  headless: true, userDataDir: profile,
});
const evidence = {checks: [], geometry: [], pageErrors: []};
try {
  const page = await browser.newPage();
  page.on("pageerror", error => evidence.pageErrors.push(error.message));
  await page.setViewport({width: 1440, height: 1000});
  await page.goto(base, {waitUntil: "domcontentloaded"});
  await page.waitForSelector("body:not(.questionnaire-pending)");
  if (await page.$eval("#questionnaire-welcome", node => node.open)) await page.click("#welcome-later");
  const navigate = async hash => {
    await page.evaluate(hash => { location.hash = hash; }, hash);
    await page.waitForFunction(hash => location.hash === `#${hash}`, {}, hash);
  };
  const fill = async (selector, value) => page.$eval(selector, (node, value) => {
    node.value = value;
    node.dispatchEvent(new Event("input", {bubbles: true}));
    node.dispatchEvent(new Event("change", {bubbles: true}));
  }, value);
  const read = async url => page.evaluate(async url => {
    const response = await fetch(url, {headers: {"X-Owner-ID": document.documentElement.dataset.prismOwner}});
    if (!response.ok) throw new Error(`Acceptance read failed: ${response.status}`);
    return response.json();
  }, url);

  await navigate("research-workbench");
  await page.waitForFunction(() => document.getElementById("lab-h-system").options.length > 0);
  await page.waitForFunction(() => document.getElementById("lab-h-list").childElementCount > 0);
  await fill("#lab-h-name", "");
  await page.click("#lab-h-save");
  await page.waitForFunction(() => !document.getElementById("lab-message-live-research").hidden && document.getElementById("lab-message-live-research").classList.contains("error"));
  evidence.checks.push("研究工作台默认路由加载订阅并显示输入错误");

  await navigate("skill-store");
  await page.waitForSelector("#lab-method-generate", {visible: true});
  const before = (await read("/api/v1/personal-research/systems")).items.length;
  const generated = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/research-lab/drafts" && response.request().method() === "POST");
  await page.click("#lab-method-generate");
  assert.equal((await generated).status(), 200);
  await page.waitForSelector("#lab-method-confirm", {visible: true});
  assert.equal((await read("/api/v1/personal-research/systems")).items.length, before, "草稿不能自动安装");
  const name = `合并验收盈利方法-${Date.now()}`;
  await fill("#lab-method-name", name);
  const confirmed = page.waitForResponse(response => new URL(response.url()).pathname.endsWith("/confirm") && response.request().method() === "POST");
  await page.click("#lab-method-confirm");
  assert.equal((await confirmed).status(), 200);
  await page.waitForFunction(() => document.getElementById("lab-message-skill-store").textContent.includes("已保存"));
  assert.ok((await read("/api/v1/personal-research/systems")).items.some(item => item.name === name));
  evidence.checks.push("自然语言草稿经用户确认后实际保存为个人研究方法");

  const pages = [
    ["skill-store", "method-builder-workspace"],
    ["live-research", "hypothesis-workspace"],
    ["research-knowledge", "announcement-impact-workspace"],
    ["scenario-simulation", "shadow-experiment-workspace"],
    ["portfolio-rebalancing", "funding-goal-workspace"],
  ];
  for (const viewport of [{width: 1440, height: 1000}, {width: 1024, height: 768}, {width: 390, height: 844}]) {
    await page.setViewport(viewport);
    for (const [route, mount] of pages) {
      await navigate(route);
      await page.waitForFunction(mount => document.getElementById(mount).checkVisibility(), {}, mount);
      const geometry = await page.evaluate(mount => ({
        width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        inputs: document.getElementById(mount).querySelectorAll("input, select, textarea, button").length,
        title: document.getElementById(mount).querySelector("h3")?.textContent,
        // Chart vendor SVGs reuse local clip-path/logo IDs; application controls must remain unique.
        duplicateIds: [...document.querySelectorAll("[id]")].filter(node => !node.closest("svg")).map(node => node.id).filter((id, index, all) => all.indexOf(id) !== index),
      }), mount);
      assert.ok(geometry.inputs > 0, mount);
      assert.ok(geometry.scrollWidth <= geometry.width, `${route}: ${JSON.stringify(geometry)}`);
      assert.deepEqual(geometry.duplicateIds, []);
      evidence.geometry.push({route, viewport, ...geometry});
    }
    await navigate("research-workbench");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: path.join(output, `research-${viewport.width}.png`)});
  }
  const memoryRequest = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/advisor/investment-memory" && response.request().method() === "GET");
  await navigate("portfolio-style");
  await page.waitForSelector("#investment-memory-workspace", {visible: true});
  assert.equal((await memoryRequest).status(), 200);
  evidence.checks.push("五项创新功能在三种视口可达，长期记忆入口保留");
  assert.deepEqual(evidence.pageErrors, []);
  evidence.passed = true;
  console.log(JSON.stringify({passed: true, checks: evidence.checks, viewportChecks: evidence.geometry.length}));
} finally {
  await fs.writeFile(path.join(output, "evidence.json"), JSON.stringify(evidence, null, 2));
  await browser.close();
}
