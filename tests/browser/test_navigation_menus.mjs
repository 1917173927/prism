import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8000";
const executablePath = process.env.PRISM_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const browser = await puppeteer.launch({executablePath, headless: true});

try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.setViewport({width: 1440, height: 900});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  if (new URL(page.url()).pathname === "/login") {
    const password = randomUUID() + randomUUID();
    await page.click("#register-tab");
    await page.type("#username", `navigation-${Date.now()}`);
    await page.type("#password", password);
    await page.type("#confirmation", password);
    await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  }
  await page.waitForSelector("body:not(.questionnaire-pending)");
  if (await page.$eval("body", node => node.classList.contains("questionnaire-required"))) {
    const status = await page.evaluate(async () => {
      const context = await fetch("/api/v1/auth/context").then(response => response.json());
      const headers = {"X-Owner-ID": context.owner_id};
      const template = await fetch("/api/v1/advisor/profile/questionnaire-template", {headers}).then(response => response.json());
      const answers = template.questions.map(question => question.question_type === "SCORE"
        ? {question_id: question.question_id, score: 3}
        : {question_id: question.question_id, selected_option_ids: [question.options[0].option_id]});
      const response = await fetch("/api/v1/advisor/profile/questionnaire/confirm", {
        method: "POST", headers: {...headers, "Content-Type": "application/json"},
        body: JSON.stringify({schema_version: "questionnaire-confirmation-request.v1", owner_id: context.owner_id, confirmed_at: new Date().toISOString(), answers}),
      });
      return response.status;
    });
    assert.equal(status, 200);
    await page.reload({waitUntil: "domcontentloaded"});
  }
  await page.waitForSelector("body.copilot-active:not(.questionnaire-pending):not(.questionnaire-required)");
  process.stdout.write("页面初始化完成。\n");
  const account = "#persona-switcher-bar";
  const settings = ".topbar-more-menu";
  const isOpen = selector => page.$eval(selector, node => node.open);
  async function moveTo(selector) {
    const box = await page.$eval(selector, node => {
      const rect = node.getBoundingClientRect();
      return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
    });
    await page.mouse.move(box.x, box.y, {steps: 12});
  }
  for (const width of [1440, 768, 390]) {
    process.stdout.write(`检查页面宽度 ${width}px。\n`);
    await page.setViewport({width, height: 900});
    await moveTo(`${account} > summary`);
    assert.equal(await isOpen(account), true);
    await moveTo(`${settings} > summary`);
    assert.equal(await isOpen(settings), true);
    assert.equal(await isOpen(account), false);
    await moveTo(`${account} > summary`);
    assert.equal(await isOpen(account), true);
    assert.equal(await isOpen(settings), false);
    await page.click(`${account} > summary`);
    assert.equal(await isOpen(account), true);
    assert.deepEqual(await page.$$eval(`${account} .profile-actions-panel button`, nodes => nodes.map(node => node.id)), ["btn-custom-profile-chip"]);
    await moveTo("#btn-custom-profile-chip");
    assert.equal(await isOpen(account), true);
    await page.mouse.move(10, 880);
    assert.equal(await isOpen(account), false);

    await moveTo(`${settings} > summary`);
    assert.equal(await isOpen(settings), true);
    for (const id of ["open-profile-modal-btn", "open-portfolio-modal-btn", "home-context-trigger"]) {
      assert.equal(await page.$eval(`#${id}`, node => node.closest("details").classList.contains("topbar-more-menu")), true);
      assert.equal(await page.$eval(`#${id}`, node => node.getClientRects().length > 0), true);
    }
    await moveTo("#open-profile-modal-btn");
    assert.equal(await isOpen(settings), true);
    await page.mouse.move(10, 880);
    assert.equal(await isOpen(settings), false);

    // 键盘切换期间两个菜单保持互斥。
    await page.focus(`${account} > summary`);
    await page.keyboard.press("Enter");
    assert.equal(await isOpen(account), true);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    assert.equal(await isOpen(settings), true);
    assert.equal(await isOpen(account), false);
    await page.keyboard.press("Escape");
    assert.equal(await isOpen(settings), false);
    await page.click(`${settings} > summary`);
    await page.click("body", {offset: {x: 10, y: 880}});
    assert.equal(await isOpen(settings), false);

    await page.click(`${settings} > summary`);
    await page.click("#open-profile-modal-btn");
    assert.equal(await page.$eval("#profile-edit-modal", node => node.open), true);
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => document.activeElement.matches(".topbar-more-menu > summary"));
    await page.click(`${settings} > summary`);
    await page.click("#open-portfolio-modal-btn");
    assert.equal(await page.$eval("#portfolio-modal", node => node.open), true);
    await page.click("#close-portfolio-modal-btn");
    await page.click(`${settings} > summary`);
    await page.click("#home-context-trigger");
    assert.equal(await page.$eval("#copilot", node => node.classList.contains("context-open")), true);
    assert.equal(await isOpen(settings), false);
    await page.click("#home-context-close");
  }
  await page.setViewport({width: 390, height: 900, hasTouch: true, isMobile: true});
  await page.waitForSelector("body.copilot-active:not(.questionnaire-pending):not(.questionnaire-required)");
  await page.mouse.move(10, 880);
  async function tapSummary(selector) {
    const position = await page.$eval(`${selector} > summary`, node => {
      const rect = node.getBoundingClientRect();
      return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
    });
    await page.touchscreen.tap(position.x, position.y);
  }
  await tapSummary(account);
  assert.equal(await isOpen(account), true);
  await tapSummary(settings);
  assert.equal(await isOpen(settings), true);
  assert.equal(await isOpen(account), false);
  await tapSummary(settings);
  assert.equal(await isOpen(settings), false);
  assert.deepEqual(errors, []);
  process.stdout.write("账户和设置菜单交互检查通过。\n");
} finally {
  await browser.close();
}
