import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8874";
const executablePath = process.env.PRISM_TEST_BROWSER || (
  process.platform === "win32"
    ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    : "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
);
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});

try {
  const page = await browser.newPage();
  const apiResponses = [];
  const pageErrors = [];
  page.on("response", response => {
    if (new URL(response.url()).pathname.startsWith("/api/v1/")) {
      apiResponses.push({method: response.request().method(), path: new URL(response.url()).pathname, status: response.status()});
    }
  });
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.setViewport({width: 1440, height: 900});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  await page.waitForSelector("body:not(.questionnaire-pending)");

  if (await page.$eval("body", body => body.classList.contains("questionnaire-required"))) {
    const status = await page.evaluate(async () => {
      const headers = {"X-Owner-ID": "demo-owner"};
      const template = await fetch("/api/v1/advisor/profile/questionnaire-template", {headers}).then(response => response.json());
      const answers = template.questions.map(question => question.question_type === "SCORE"
        ? {question_id: question.question_id, score: 3}
        : {question_id: question.question_id, selected_option_ids: [question.options[0].option_id]});
      const response = await fetch("/api/v1/advisor/profile/questionnaire/confirm", {
        method: "POST",
        headers: {...headers, "Content-Type": "application/json"},
        body: JSON.stringify({schema_version: "questionnaire-confirmation-request.v1", owner_id: "demo-owner", confirmed_at: new Date().toISOString(), answers}),
      });
      return response.status;
    });
    assert.equal(status, 200);
    await page.reload({waitUntil: "domcontentloaded"});
    await page.waitForSelector("body:not(.questionnaire-pending):not(.questionnaire-required)");
  }

  await page.waitForSelector("body.copilot-active #copilot:not([hidden])");
  await page.waitForFunction(() => document.querySelector("#home-context-trigger").textContent !== "当前上下文：A股 · 查看分析资料");
  const home = await page.evaluate(() => {
    const rect = selector => document.querySelector(selector).getBoundingClientRect();
    const visible = selector => getComputedStyle(document.querySelector(selector)).display !== "none";
    return {
      actionTop: rect(".sidebar-conversation-actions").top,
      navTop: rect(".nav-list").top,
      historyTop: rect(".sidebar .chat-history-panel").top,
      titleCenter: rect("#copilot-hero-title").x + rect("#copilot-hero-title").width / 2,
      inputCenter: rect(".copilot-query-box").x + rect(".copilot-query-box").width / 2,
      inputWidth: rect(".copilot-query-box").width,
      toolsVisible: visible("#agent-feature-tools"),
      contextVisible: visible("#agent-profile-rail"),
      sidebarVisible: visible(".sidebar-conversation-actions"),
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
    };
  });
  assert.ok(home.actionTop < home.navTop && home.navTop < home.historyTop, JSON.stringify(home));
  assert.ok(Math.abs(home.titleCenter - home.inputCenter) < 2, JSON.stringify(home));
  assert.ok(home.inputWidth >= 600 && home.inputWidth <= 760, JSON.stringify(home));
  assert.equal(home.sidebarVisible, true);
  assert.equal(home.toolsVisible, false);
  assert.equal(home.contextVisible, false);
  assert.equal(home.horizontalOverflow, false);

  await page.click("#agent-feature-trigger");
  await page.waitForSelector("#agent-feature-tools.is-open");
  assert.equal(await page.$$("#agent-feature-popover [data-feature-id]").then(nodes => nodes.length), 6);
  await page.click('[data-feature-id="stock"]');
  assert.equal(await page.$eval("#agent-feature-config", node => node.hidden), false);
  assert.equal(apiResponses.some(response => response.path === "/api/v1/copilot/chat"), false);
  await page.keyboard.press("Escape");
  assert.equal(await page.$eval("#agent-feature-tools", node => getComputedStyle(node).display), "none");

  await page.click("#home-context-trigger");
  assert.equal(await page.$eval("#agent-profile-rail", node => getComputedStyle(node).display), "grid");
  await page.click("#home-context-close");
  assert.equal(await page.$eval("#agent-profile-rail", node => getComputedStyle(node).display), "none");
  await page.click("#home-model-trigger");
  assert.equal(await page.$eval("#llm-config-modal", node => getComputedStyle(node).display), "flex");
  await page.click("#close-llm-config-modal-btn");

  const initialCount = await page.$$("#chat-session-list .chat-session-item").then(nodes => nodes.length);
  const [createdResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/v1/copilot/conversations"),
    page.click("#new-chat-session"),
  ]);
  assert.equal(createdResponse.status(), 201);
  const created = await createdResponse.json();
  await page.waitForFunction(count => document.querySelectorAll("#chat-session-list .chat-session-item").length === Math.min(count + 1, 50), {}, initialCount);
  const title = `首页接口核对-${Date.now()}`;
  await page.click("#chat-session-list .chat-session-item:first-child .chat-session-rename");
  await page.waitForSelector("#chat-session-list .chat-session-title-input");
  await page.$eval("#chat-session-list .chat-session-title-input", (node, value) => { node.value = value; node.dispatchEvent(new Event("input", {bubbles: true})); }, title);
  await page.click("#chat-session-list .chat-session-edit-save");
  await page.waitForFunction(value => document.querySelector("#chat-session-list")?.textContent.includes(value), {}, title);
  await page.type("#chat-session-search", title);
  assert.equal(await page.$$("#chat-session-list .chat-session-item").then(nodes => nodes.length), 1);
  await page.waitForFunction(value => document.querySelector("#active-chat-title")?.textContent === value, {}, title);
  const loadedStatus = await page.evaluate(async id => {
    const response = await fetch(`/api/v1/copilot/conversations/${id}`, {headers: {"X-Owner-ID": "demo-owner"}});
    return response.status;
  }, created.conversation_id);
  assert.equal(loadedStatus, 200);
  const [removedResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "DELETE"
      && new URL(response.url()).pathname.startsWith("/api/v1/copilot/conversations/")),
    page.click("#chat-session-list .chat-session-delete"),
  ]);
  assert.equal(removedResponse.status(), 200);
  assert.equal(new URL(removedResponse.url()).pathname, `/api/v1/copilot/conversations/${created.conversation_id}`);
  await page.waitForFunction(() => document.querySelectorAll("#chat-session-list .chat-session-item").length === 0);
  await page.$eval("#chat-session-search", node => { node.value = ""; node.dispatchEvent(new Event("input", {bubbles: true})); });

  await page.click("#agent-feature-trigger");
  await page.waitForSelector("#agent-feature-tools.is-open");
  await page.click('a[href="#overview"]');
  await page.waitForSelector("body:not(.copilot-active) #overview:not([hidden])");
  assert.equal(await page.$eval(".sidebar-conversation-actions", node => getComputedStyle(node).display), "none");
  await page.click('a[href="#copilot"]');
  await page.waitForSelector("body.copilot-active #copilot:not([hidden])");
  assert.equal(await page.$eval("#agent-feature-tools", node => getComputedStyle(node).display), "none");

  await page.setViewport({width: 390, height: 844});
  const mobile = await page.evaluate(() => ({
    inputWidth: document.querySelector(".copilot-query-box").getBoundingClientRect().width,
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
    sidebarVisible: getComputedStyle(document.querySelector(".sidebar-conversation-actions")).display !== "none",
  }));
  assert.ok(mobile.inputWidth <= 390, JSON.stringify(mobile));
  assert.equal(mobile.horizontalOverflow, false);
  assert.equal(mobile.sidebarVisible, true);

  for (const [method, path] of [
    ["GET", "/api/v1/copilot/conversations"],
    ["POST", "/api/v1/copilot/conversations"],
    ["PATCH", apiResponses.find(response => response.method === "PATCH" && response.path.startsWith("/api/v1/copilot/conversations/"))?.path],
    ["DELETE", apiResponses.find(response => response.method === "DELETE" && response.path.startsWith("/api/v1/copilot/conversations/"))?.path],
    ["GET", "/api/v1/advisor/session-truth"],
    ["GET", "/api/v1/user/model-settings"],
  ]) {
    assert.ok(apiResponses.some(response => response.method === method && response.path === path && response.status < 300), `${method} ${path}: ${JSON.stringify(apiResponses)}`);
  }
  assert.deepEqual(pageErrors, []);
  process.stdout.write("对话首页与现有接口检查通过。\n");
} finally {
  await browser.close();
}
