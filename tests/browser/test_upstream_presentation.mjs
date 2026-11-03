import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL;
const owner = process.env.PRISM_TEST_OWNER_ID;
const executablePath = process.env.PRISM_TEST_BROWSER;
assert.ok(baseUrl && owner && executablePath);
assert.equal(process.env.PRISM_TEST_ISOLATED, "1");
const output = path.resolve("output/upstream-presentation");
await fs.mkdir(output, {recursive: true});
const upstreamCss = ["styles.css", "prism-v2.css", "research-platform.css", "research-workbench.css"]
  .map(file => execFileSync("git", ["-c", `safe.directory=${process.cwd()}`, "show",
    `upstream/main:app/api/static/${file}`], {encoding: "utf8"})).join("\n");
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: await fs.mkdtemp(path.join(output, "profile-"))});
const report = [];
try {
  const page = await browser.newPage();
  const reference = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.evaluateOnNewDocument(owner => {
    localStorage.setItem("prism_custom_user_profile_v2", JSON.stringify({ownerId: owner}));
    document.addEventListener("DOMContentLoaded", () => {
      document.getElementById("owner-id").value = owner;
    }, {once: true});
  }, owner);
  const selectors = ["body", "#home-history-sidebar", "#nav-store", "#new-chat-session",
                     "#copilot-natural-input", "#copilot-submit-query"];
  const properties = ["color", "backgroundColor", "fontFamily", "fontSize", "fontWeight",
    "lineHeight", "borderTopColor", "borderTopLeftRadius", "paddingTop", "paddingRight"];
  for (const width of [1440, 1024, 390]) {
    await page.setViewport({width, height: 900});
    await reference.setViewport({width, height: 900});
    await page.goto(`${baseUrl}/?dev=0#copilot`, {waitUntil: "networkidle0"});
    await page.waitForSelector("body.copilot-active:not(.questionnaire-pending)");
    // Compare settled visual states, rather than a route-change transition frame.
    const settled = "*,*::before,*::after{transition:none!important;animation:none!important}";
    await page.addStyleTag({content: settled});
    const activeId = await page.evaluate(() => document.activeElement?.id);
    const snapshot = await page.evaluate(css => {
      const copy = document.documentElement.cloneNode(true);
      copy.querySelectorAll("script,style,link[rel=stylesheet]").forEach(node => node.remove());
      const style = document.createElement("style");
      style.textContent = css;
      copy.querySelector("head").append(style);
      return "<!doctype html>" + copy.outerHTML;
    }, upstreamCss);
    await reference.setContent(snapshot, {waitUntil: "domcontentloaded"});
    await reference.addStyleTag({content: settled});
    if (activeId) await reference.evaluate(id => document.getElementById(id)?.focus(), activeId);
    const styles = target => target.evaluate(({selectors, properties}) => Object.fromEntries(
      selectors.map(selector => {
        const element = document.querySelector(selector);
        if (!element) throw Error(`missing visual contract: ${selector}`);
        const style = getComputedStyle(element);
        return [selector, Object.fromEntries(properties.map(property => [property, style[property]]))];
      })), {selectors, properties});
    const actual = await styles(page);
    const expected = await styles(reference);
    assert.deepEqual(actual, expected, `upstream appearance diverged at ${width}px`);
    const business = await page.evaluate(() => {
      const ids = ["method-builder-workspace", "personal-system-workspace", "hypothesis-workspace",
        "announcement-impact-workspace", "investment-memory-workspace", "shadow-experiment-workspace",
        "personal-rebalancing-workspace", "funding-goal-workspace"];
      const mounts = Object.fromEntries(ids.map(id => [id, !!document.getElementById(id)?.children.length]));
      const local = document.querySelector(".personal-workbench");
      const style = getComputedStyle(local);
      return {mounts, localBodyFont: style.getPropertyValue("--font-body").trim(),
        pageFontToken: getComputedStyle(document.body).getPropertyValue("--font-body").trim(),
        overflow: document.documentElement.scrollWidth > innerWidth};
    });
    assert.ok(Object.values(business.mounts).every(Boolean));
    assert.equal(business.localBodyFont, "14px");
    assert.equal(business.pageFontToken, "", "local component tokens must not override upstream page styling");
    assert.equal(business.overflow, false);
    await page.screenshot({path: path.join(output, `${width}.png`), fullPage: false});
    report.push({width, selectors: selectors.length, properties: properties.length, business, styles: actual});
  }
  assert.deepEqual(errors, []);
  await fs.writeFile(path.join(output, "verification.json"), JSON.stringify({report, errors}, null, 2));
  console.log("PASS: upstream computed appearance at 1440/1024/390px; eight local business mounts; scoped fonts; no overflow or page errors");
} finally {
  await browser.close();
}
