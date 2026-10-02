import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import path from "node:path";
import {fileURLToPath} from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8874";
const executablePath = process.env.PRISM_TEST_BROWSER || (
  process.platform === "win32"
    ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    : "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
);
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
const repoRoot = fileURLToPath(new URL("../../", import.meta.url));

try {
  const page = await browser.newPage();
  const apiRequests = [];
  const apiResponses = [];
  const pageErrors = [];
  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/v1/")) apiRequests.push({method: request.method(), path});
  });
  page.on("response", response => {
    if (new URL(response.url()).pathname.startsWith("/api/v1/")) {
      apiResponses.push({method: response.request().method(), path: new URL(response.url()).pathname, status: response.status()});
    }
  });
  page.on("pageerror", error => pageErrors.push(error.message));
  const isModelSettingsRead = response => response.request().method() === "GET"
    && new URL(response.url()).pathname === "/api/v1/user/model-settings";
  let historyStartup = page.waitForResponse(isModelSettingsRead, {timeout: 60000});
  await page.setViewport({width: 1440, height: 900});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  if (new URL(page.url()).pathname === "/login") {
    const password = randomUUID() + randomUUID();
    await page.click("#register-tab");
    await page.type("#username", `home-ui-${Date.now()}`);
    await page.type("#password", password);
    await page.type("#confirmation", password);
    await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  }
  await page.waitForSelector("body:not(.questionnaire-pending)");
  const session = await page.evaluate(async () => {
    const response = await fetch("/api/v1/auth/context");
    return response.json();
  });
  assert.equal(session.enabled, true);
  const ownerId = session.owner_id;
  assert.equal((await historyStartup).status(), 200);

  if (await page.$eval("body", body => body.classList.contains("questionnaire-required"))) {
    const status = await page.evaluate(async ownerId => {
      const headers = {"X-Owner-ID": ownerId};
      const template = await fetch("/api/v1/advisor/profile/questionnaire-template", {headers}).then(response => response.json());
      const answers = template.questions.map(question => question.question_type === "SCORE"
        ? {question_id: question.question_id, score: 3}
        : {question_id: question.question_id, selected_option_ids: [question.options[0].option_id]});
      const response = await fetch("/api/v1/advisor/profile/questionnaire/confirm", {
        method: "POST",
        headers: {...headers, "Content-Type": "application/json"},
        body: JSON.stringify({schema_version: "questionnaire-confirmation-request.v1", owner_id: ownerId, confirmed_at: new Date().toISOString(), answers}),
      });
      return response.status;
    }, ownerId);
    assert.equal(status, 200);
    historyStartup = page.waitForResponse(isModelSettingsRead);
    await page.reload({waitUntil: "domcontentloaded"});
    await page.waitForSelector("body:not(.questionnaire-pending):not(.questionnaire-required)");
  }

  await page.waitForSelector("body.copilot-active #copilot:not([hidden])");
  assert.equal((await historyStartup).status(), 200);
  const conversationCreateCount = () => apiRequests.filter(request => request.method === "POST"
    && request.path === "/api/v1/copilot/conversations").length;
  assert.equal(conversationCreateCount(), 0);
  assert.equal(await page.$$("#chat-session-list .chat-session-item").then(nodes => nodes.length), 0);
  assert.equal(await page.$eval("#chat-session-search", node => node.value), "");
  assert.equal(await page.$eval("#chat-session-search", node => node.getAttribute("placeholder")), "搜索对话");
  assert.equal(await page.$eval("#chat-session-search", node => node.matches(":placeholder-shown")), true);
  const home = await page.evaluate(() => {
    const rect = selector => document.querySelector(selector).getBoundingClientRect();
    const visible = selector => getComputedStyle(document.querySelector(selector)).display !== "none";
    return {
      actionTop: rect(".sidebar-conversation-actions").top,
      navTop: rect("#home-primary-navigation").top,
      headerBottom: rect("#home-navigation").bottom,
      sidebarBottom: rect(".sidebar").bottom,
      sidebarTop: rect(".sidebar").top,
      historyTop: rect(".sidebar .chat-history-panel").top,
      titleCenter: rect("#copilot-hero-title").x + rect("#copilot-hero-title").width / 2,
      inputCenter: rect(".copilot-query-box").x + rect(".copilot-query-box").width / 2,
      inputWidth: rect(".copilot-query-box").width,
      inputTop: rect(".copilot-query-box").top,
      toolsVisible: visible("#agent-feature-tools"),
      contextVisible: visible("#agent-profile-rail"),
      sidebarVisible: visible(".sidebar-conversation-actions"),
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      font: getComputedStyle(document.querySelector("#copilot-natural-input")).fontFamily,
      titleWeight: getComputedStyle(document.querySelector("#copilot-hero-title")).fontWeight,
      contextInsideConversation: Boolean(document.querySelector(".conversation-main #home-context-trigger")),
    };
  });
  assert.ok(home.navTop < home.actionTop && home.actionTop < home.historyTop, JSON.stringify(home));
  assert.equal(home.sidebarTop, home.headerBottom);
  assert.equal(home.sidebarBottom, 900);
  assert.ok(Math.abs(home.titleCenter - home.inputCenter) < 2, JSON.stringify(home));
  assert.ok(home.inputWidth >= 600 && home.inputWidth <= 760, JSON.stringify(home));
  assert.equal(home.sidebarVisible, true);
  assert.equal(home.toolsVisible, false);
  assert.equal(home.contextVisible, false);
  assert.equal(home.horizontalOverflow, false);
  assert.ok(home.inputTop > 300 && home.inputTop < 500, JSON.stringify(home));
  assert.match(home.font, /ui-sans-serif/);
  assert.equal(home.titleWeight, "600");
  assert.equal(home.contextInsideConversation, false);
  assert.equal(await page.$eval("#home-model-label", node => node.textContent), "API 配置");

  async function checkSidebarOrder() {
    const geometry = await page.evaluate(() => {
      const sidebar = document.querySelector(".sidebar");
      const newChat = document.querySelector("#new-chat-session").getBoundingClientRect();
      const search = document.querySelector(".sidebar-chat-search").getBoundingClientRect();
      const hide = document.querySelector("#home-history-hide").getBoundingClientRect();
      const headings = [...sidebar.querySelectorAll("h2, h3")]
        .filter(node => node.getClientRects().length > 0)
        .map(node => ({text: node.textContent, top: node.getBoundingClientRect().top}));
      return {newTop: newChat.top, newBottom: newChat.bottom, searchTop: search.top, searchBottom: search.bottom,
        hideTop: hide.top, hideBottom: hide.bottom, hideLeft: hide.left, newRight: newChat.right, headings};
    });
    assert.equal(geometry.headings.length, 1, JSON.stringify(geometry));
    assert.equal(geometry.headings[0].text, "历史对话");
    assert.ok(geometry.newBottom <= geometry.searchTop && geometry.searchBottom <= geometry.headings[0].top, JSON.stringify(geometry));
    assert.ok(geometry.hideLeft >= geometry.newRight && geometry.hideTop >= geometry.newTop
      && geometry.hideBottom <= geometry.newBottom, JSON.stringify(geometry));
  }

  async function checkHistoryEditLayout() {
    const geometry = await page.$eval("#chat-session-list .chat-session-item", node => {
      const button = node.querySelector(".chat-session-rename");
      const style = getComputedStyle(button);
      const letters = [...button.textContent].map((text, index) => {
        const range = document.createRange();
        range.setStart(button.firstChild, index);
        range.setEnd(button.firstChild, index + 1);
        const box = range.getBoundingClientRect();
        return {top: box.top, left: box.left, right: box.right};
      });
      const edit = button.getBoundingClientRect();
      const remove = node.querySelector(".chat-session-delete").getBoundingClientRect();
      const title = node.querySelector(".chat-session-select strong").getBoundingClientRect();
      return {letters, whiteSpace: style.whiteSpace, titleRight: title.right,
        editLeft: edit.left, editRight: edit.right, removeLeft: remove.left};
    });
    assert.equal(geometry.whiteSpace, "nowrap");
    assert.equal(geometry.letters.length, 2);
    assert.equal(geometry.letters[0].top, geometry.letters[1].top, JSON.stringify(geometry));
    assert.ok(geometry.letters[1].left >= geometry.letters[0].right - 1, JSON.stringify(geometry));
    assert.ok(geometry.titleRight <= geometry.editLeft && geometry.editRight <= geometry.removeLeft, JSON.stringify(geometry));
  }

  await checkSidebarOrder();

  const suggestions = await page.$eval("#copilot-quick-tags", node => {
    const prompt = node.querySelector(".quick-tag-chip");
    const style = getComputedStyle(prompt);
    return {count: node.querySelectorAll("li").length, text: prompt.textContent,
      top: node.getBoundingClientRect().top, borderWidth: style.borderWidth,
      background: style.backgroundColor, radius: style.borderRadius, collapsible: Boolean(node.closest("details"))};
  });
  assert.equal(suggestions.count, 3);
  assert.equal(suggestions.borderWidth, "0px");
  assert.equal(suggestions.background, "rgba(0, 0, 0, 0)");
  assert.equal(suggestions.radius, "0px");
  assert.equal(suggestions.collapsible, false);
  assert.ok(suggestions.top > await page.$eval(".copilot-query-box", node => node.getBoundingClientRect().bottom));
  await page.click("#copilot-quick-tags .quick-tag-chip");
  assert.equal(await page.$eval("#copilot-natural-input", node => node.value), suggestions.text);
  assert.equal(await page.$eval(".copilot-query-box", node => node.getBoundingClientRect().top), home.inputTop);
  assert.equal(conversationCreateCount(), 0);
  assert.equal(apiRequests.some(request => request.path === "/api/v1/copilot/chat"), false);
  await page.$eval("#copilot-natural-input", node => { node.value = ""; });

  await page.click("#home-history-hide");
  await page.waitForFunction(() => {
    const left = document.querySelector(".main").getBoundingClientRect().left;
    return left > 0 && left < 248;
  });
  assert.equal(await page.$eval(".sidebar", node => node.inert), true);
  await page.waitForFunction(() => getComputedStyle(document.querySelector(".sidebar")).visibility === "hidden"
    && document.querySelector(".main").getBoundingClientRect().left === 0);
  const collapsed = await page.evaluate(() => ({
    sidebarVisibility: getComputedStyle(document.querySelector(".sidebar")).visibility,
    sidebarRight: document.querySelector(".sidebar").getBoundingClientRect().right,
    mainLeft: document.querySelector(".main").getBoundingClientRect().left,
    headerWidth: document.querySelector("#home-navigation").getBoundingClientRect().width,
  }));
  assert.equal(collapsed.sidebarVisibility, "hidden");
  assert.equal(collapsed.sidebarRight, 0);
  assert.equal(collapsed.mainLeft, 0);
  assert.equal(collapsed.headerWidth, 1440);
  await page.click("#home-history-show");
  await page.waitForFunction(() => {
    const left = document.querySelector(".main").getBoundingClientRect().left;
    return left > 0 && left < 248;
  });
  await page.waitForFunction(() => document.querySelector(".main").getBoundingClientRect().left === 248);
  assert.equal(await page.$eval(".sidebar", node => node.inert), false);
  await page.evaluate(() => {
    document.querySelector("#home-history-hide").click();
    document.querySelector("#home-history-show").click();
  });
  await page.waitForFunction(() => document.querySelector(".main").getBoundingClientRect().left === 248);
  await page.emulateMediaFeatures([{name: "prefers-reduced-motion", value: "reduce"}]);
  await page.click("#home-history-hide");
  assert.equal(await page.$eval(".sidebar", node => node.getAnimations().length), 0);
  assert.equal(await page.$eval(".main", node => node.getBoundingClientRect().left), 0);
  await page.click("#home-history-show");
  await page.emulateMediaFeatures([{name: "prefers-reduced-motion", value: "no-preference"}]);

  async function checkMenuGeometry(selector) {
    const geometry = await page.evaluate(selector => {
      const menu = document.querySelector(selector).getBoundingClientRect();
      const composer = document.querySelector(".copilot-query-box").getBoundingClientRect();
      return {width: menu.width, height: menu.height, left: menu.left, right: menu.right, top: menu.top, bottom: menu.bottom,
        intersectsInput: menu.left < composer.right && menu.right > composer.left && menu.top < composer.bottom && menu.bottom > composer.top,
        viewportWidth: innerWidth, viewportHeight: innerHeight};
    }, selector);
    assert.ok(geometry.width <= 232 && geometry.height <= 300, JSON.stringify(geometry));
    assert.ok(geometry.left >= 0 && geometry.right <= geometry.viewportWidth, JSON.stringify(geometry));
    assert.ok(geometry.top >= 0 && geometry.bottom <= geometry.viewportHeight, JSON.stringify(geometry));
    assert.equal(geometry.intersectsInput, false, JSON.stringify(geometry));
  }

  await page.click("#agent-feature-trigger");
  await page.waitForSelector("#agent-feature-tools.is-open");
  assert.equal(await page.$$("#agent-feature-popover [data-feature-id]").then(nodes => nodes.length), 6);
  await checkMenuGeometry("#agent-feature-tools");
  assert.equal(await page.$eval(".copilot-query-box", node => node.getBoundingClientRect().top), home.inputTop);
  await page.keyboard.press("ArrowDown");
  assert.equal(await page.evaluate(() => document.activeElement.dataset.featureId), "market");
  await page.keyboard.press("End");
  assert.equal(await page.evaluate(() => document.activeElement.dataset.featureId), "optimization");
  await page.keyboard.press("Escape");
  await page.type("#copilot-natural-input", "检查财务趋势");
  await page.click("#agent-feature-trigger");
  await page.click('[data-feature-id="stock"]');
  assert.equal(await page.$eval("#agent-feature-tools", node => getComputedStyle(node).display), "none");
  assert.equal(await page.$eval("#agent-feature-config-dialog", node => node.open), false);
  assert.equal(await page.$eval("#home-selected-tool-label", node => node.textContent), "个股分析");
  assert.equal(await page.$eval("#copilot-natural-input", node => node.value), "检查财务趋势");
  assert.equal(apiResponses.some(response => response.path === "/api/v1/copilot/chat"), false);
  await page.click("#home-selected-tool-config");
  assert.equal(await page.$eval("#agent-feature-config-dialog", node => node.open), true);
  await page.type('#agent-feature-fields input[name="target"]', "600251.SH");
  assert.match(await page.$eval("#copilot-natural-input", node => node.value), /600251.SH/);
  await page.keyboard.press("Escape");
  assert.equal(await page.$eval("#agent-feature-config-dialog", node => node.open), false);
  assert.equal(await page.$eval("#home-selected-tool", node => node.hidden), false);
  await page.click("#home-selected-tool-clear");
  assert.equal(await page.$eval("#home-selected-tool", node => node.hidden), true);

  await page.click("#persona-switcher-bar > summary");
  await page.click("#home-context-trigger");
  assert.equal(await page.$eval("#agent-profile-rail", node => getComputedStyle(node).display), "grid");
  await page.click("#home-context-close");
  assert.equal(await page.$eval("#agent-profile-rail", node => getComputedStyle(node).display), "none");
  await page.click("#home-model-trigger");
  assert.equal(await page.$eval("#llm-config-modal", node => getComputedStyle(node).display), "flex");
  await page.click("#close-llm-config-modal-btn");

  await page.click("#home-upload-trigger");
  assert.equal(await page.$$("#home-upload-menu button").then(nodes => nodes.length), 1);
  await checkMenuGeometry("#home-upload-menu");
  await page.keyboard.press("Escape");
  assert.equal(await page.$eval("#home-upload-menu", node => node.hidden), true);
  const uploadInput = await page.$("#home-upload-input");
  await uploadInput.uploadFile(path.join(repoRoot, "app/api/static/index.html"));
  await page.waitForSelector("#home-upload-status:not([hidden])");
  assert.equal(apiResponses.some(response => response.path === "/api/v1/advisor/portfolio/ocr"), false);
  if (process.env.PRISM_TEST_UPLOAD_FILE) {
    await page.click("#home-upload-trigger");
    const [chooser] = await Promise.all([page.waitForFileChooser(), page.click("#home-upload-select")]);
    const [ocrResponse] = await Promise.all([
      page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/advisor/portfolio/ocr", {timeout: 60000}),
      chooser.accept([process.env.PRISM_TEST_UPLOAD_FILE]),
    ]);
    assert.equal(ocrResponse.status(), 200);
    const ocr = await ocrResponse.json();
    assert.equal(ocr.original_image_persisted, false);
    assert.equal(ocr.owner_id, ownerId);
    assert.ok(Array.isArray(ocr.positions));
    await page.waitForSelector("#home-upload-trigger:not([disabled])");
    assert.equal(await page.$eval("#home-upload-filename", node => node.textContent), path.basename(process.env.PRISM_TEST_UPLOAD_FILE));
    await page.click("#close-portfolio-modal-btn");
    await page.click("#home-upload-review");
    assert.equal(await page.$eval("#portfolio-modal", node => getComputedStyle(node).display), "flex");
    await page.click("#close-portfolio-modal-btn");
    await page.click("#home-upload-remove");
    assert.equal(await page.$eval("#home-upload-file", node => node.hidden), true);
  }

  await page.type("#chat-session-search", "未发送的草稿");
  await page.click("#new-chat-session");
  await page.type("#copilot-natural-input", "尚未发送的问题");
  await page.click("#new-chat-session");
  assert.equal(await page.$eval("#chat-session-search", node => node.value), "");
  assert.equal(await page.$eval("#copilot-natural-input", node => node.value), "");
  assert.equal(conversationCreateCount(), 0);
  assert.equal(await page.$$("#chat-session-list .chat-session-item").then(nodes => nodes.length), 0);
  await page.click("#copilot-submit-query");
  assert.equal(conversationCreateCount(), 0);
  assert.equal(apiRequests.some(request => request.path === "/api/v1/copilot/chat"), false);

  const question = "请用一句话说明你的用途。";
  async function checkChatResponse(response, conversationId) {
    const request = JSON.parse(response.request().postData());
    assert.notEqual(request.model_mode, "MOCK");
    assert.equal(request.message, question);
    assert.equal(request.conversation_id, conversationId);
    if (response.status() === 409) {
      assert.equal((await response.json()).error_code, "MODEL_NOT_CONFIGURED");
      await page.waitForFunction(() => document.querySelector("#copilot-chat-messages").textContent.includes("API Key"));
    } else assert.equal(response.status(), 200);
    await page.waitForSelector("#copilot-submit-query:not([disabled])", {timeout: 60000});
  }
  await page.type("#copilot-natural-input", question);
  const [createdResponse, firstChatResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/v1/copilot/conversations"),
    page.waitForResponse(response => response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/v1/copilot/chat", {timeout: 30000}),
    page.click("#copilot-submit-query"),
  ]);
  assert.equal(createdResponse.status(), 201);
  const created = await createdResponse.json();
  assert.equal(created.title, question);
  await checkChatResponse(firstChatResponse, created.conversation_id);
  assert.equal(conversationCreateCount(), 1);
  await page.type("#copilot-natural-input", question);
  const [secondChatResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/v1/copilot/chat", {timeout: 30000}),
    page.click("#copilot-submit-query"),
  ]);
  await checkChatResponse(secondChatResponse, created.conversation_id);
  assert.equal(conversationCreateCount(), 1);
  await page.waitForFunction(() => document.querySelectorAll("#chat-session-list .chat-session-item").length === 1);
  await page.click("#new-chat-session");
  assert.equal(conversationCreateCount(), 1);
  assert.equal(await page.$$("#chat-session-list .chat-session-item.is-active").then(nodes => nodes.length), 0);
  historyStartup = page.waitForResponse(isModelSettingsRead);
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("body.copilot-active #copilot:not([hidden])");
  assert.equal((await historyStartup).status(), 200);
  assert.equal(conversationCreateCount(), 1);
  assert.equal(await page.$$("#chat-session-list .chat-session-item").then(nodes => nodes.length), 1);
  const selectedRow = await page.$("#chat-session-list .chat-session-item");
  await Promise.all([
    page.waitForResponse(response => response.request().method() === "GET"
      && new URL(response.url()).pathname === `/api/v1/copilot/conversations/${created.conversation_id}`),
    page.click("#chat-session-list .chat-session-select"),
  ]);
  await page.waitForFunction(node => !node.isConnected, {}, selectedRow);
  await selectedRow.dispose();
  await page.waitForSelector("#chat-session-list .chat-session-item.is-active");
  await checkHistoryEditLayout();
  await page.click("#chat-session-list .chat-session-rename");
  await page.waitForSelector("#chat-session-list .chat-session-title-input");
  await page.$eval("#chat-session-list .chat-session-title-input", node => { node.value = "新对话"; });
  await page.click("#chat-session-list .chat-session-edit-save");
  await page.waitForFunction(() => document.querySelector("#chat-session-list .chat-session-select strong")?.textContent === "新对话");
  await checkHistoryEditLayout();
  const title = `首页接口核对-${Date.now()}`;
  await page.click("#chat-session-list .chat-session-item:first-child .chat-session-rename");
  await page.waitForSelector("#chat-session-list .chat-session-title-input");
  await page.$eval("#chat-session-list .chat-session-title-input", (node, value) => { node.value = value; node.dispatchEvent(new Event("input", {bubbles: true})); }, title);
  await page.click("#chat-session-list .chat-session-edit-save");
  await page.waitForFunction(value => document.querySelector("#chat-session-list")?.textContent.includes(value), {}, title);
  await checkHistoryEditLayout();
  await page.type("#chat-session-search", title);
  assert.equal(await page.$eval("#chat-session-search", node => node.matches(":placeholder-shown")), false);
  assert.equal(await page.$$("#chat-session-list .chat-session-item").then(nodes => nodes.length), 1);
  await page.waitForFunction(value => document.querySelector("#active-chat-title")?.textContent === value, {}, title);
  const loadedStatus = await page.evaluate(async (id, ownerId) => {
    const response = await fetch(`/api/v1/copilot/conversations/${id}`, {headers: {"X-Owner-ID": ownerId}});
    return response.status;
  }, created.conversation_id, ownerId);
  assert.equal(loadedStatus, 200);
  const [removedResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "DELETE"
      && new URL(response.url()).pathname.startsWith("/api/v1/copilot/conversations/")),
    page.click("#chat-session-list .chat-session-delete"),
  ]);
  assert.equal(removedResponse.status(), 200);
  assert.equal(new URL(removedResponse.url()).pathname, `/api/v1/copilot/conversations/${created.conversation_id}`);
  await page.waitForFunction(() => document.querySelectorAll("#chat-session-list .chat-session-item").length === 0);
  assert.equal(conversationCreateCount(), 1);
  assert.equal(await page.$eval("#chat-session-search", node => node.value), "");
  assert.equal(await page.$$("#copilot-chat-messages .chat-msg").then(nodes => nodes.length), 0);
  assert.equal(await page.$eval("#chat-session-search", node => node.matches(":placeholder-shown")), true);

  await page.click("#agent-feature-trigger");
  await page.waitForSelector("#agent-feature-tools.is-open");
  await page.click('a[href="#overview"]');
  await page.waitForSelector("body:not(.copilot-active) #overview:not([hidden])");
  assert.equal(await page.$eval(".sidebar-conversation-actions", node => getComputedStyle(node).display), "none");
  assert.equal(await page.$eval(".nav-section-primary", node => node.parentElement.className), "nav-list");
  assert.equal(await page.$eval("#persona-switcher-bar", node => node.parentElement.className), "topbar");
  await page.click('a[href="#copilot"]');
  await page.waitForSelector("body.copilot-active #copilot:not([hidden])");
  assert.equal(await page.$eval("#agent-feature-tools", node => getComputedStyle(node).display), "none");
  assert.equal(await page.$eval(".nav-section-primary", node => node.parentElement.id), "home-primary-navigation");

  for (const width of [1024, 2200]) {
    await page.setViewport({width, height: 900});
    await checkSidebarOrder();
    await page.click("#agent-feature-trigger");
    await checkMenuGeometry("#agent-feature-tools");
    await page.keyboard.press("Escape");
  }

  await page.setViewport({width: 390, height: 844});
  await page.waitForFunction(() => document.body.classList.contains("home-history-collapsed")
    && getComputedStyle(document.querySelector(".sidebar")).visibility === "hidden");
  const mobile = await page.evaluate(() => ({
    inputWidth: document.querySelector(".copilot-query-box").getBoundingClientRect().width,
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
    sidebarVisible: getComputedStyle(document.querySelector(".sidebar")).visibility !== "hidden",
    promptsBottom: document.querySelector("#copilot-quick-tags").getBoundingClientRect().bottom,
  }));
  assert.ok(mobile.inputWidth <= 390, JSON.stringify(mobile));
  assert.equal(mobile.horizontalOverflow, false);
  assert.equal(mobile.sidebarVisible, false);
  assert.ok(mobile.promptsBottom < 844, JSON.stringify(mobile));
  await page.click("#home-history-show");
  await page.waitForFunction(() => document.querySelector(".sidebar").getBoundingClientRect().left === 0);
  assert.equal(await page.$eval(".sidebar", node => getComputedStyle(node).visibility), "visible");
  await checkSidebarOrder();
  await page.click("#new-chat-session");
  await page.waitForFunction(() => getComputedStyle(document.querySelector(".sidebar")).visibility === "hidden");
  assert.equal(conversationCreateCount(), 1);
  await page.click("#agent-feature-trigger");
  await checkMenuGeometry("#agent-feature-tools");
  await page.keyboard.press("Escape");
  await page.click("#home-upload-trigger");
  await checkMenuGeometry("#home-upload-menu");
  await page.keyboard.press("Escape");

  await page.click("#home-history-show");
  await page.waitForFunction(() => document.querySelector(".sidebar").getBoundingClientRect().left === 0);
  await page.click("#new-chat-session");
  await page.waitForFunction(() => getComputedStyle(document.querySelector(".sidebar")).visibility === "hidden");
  await page.type("#copilot-natural-input", question);
  const [chatSessionResponse, chatResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/v1/copilot/conversations"),
    page.waitForResponse(response => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/v1/copilot/chat", {timeout: 30000}),
    page.click("#copilot-submit-query"),
  ]);
  assert.equal(chatSessionResponse.status(), 201);
  const chatSession = await chatSessionResponse.json();
  await checkChatResponse(chatResponse, chatSession.conversation_id);
  assert.equal(conversationCreateCount(), 2);
  assert.ok(await page.$$("#copilot-chat-messages .chat-msg").then(nodes => nodes.length) >= 2);
  assert.equal(await page.$eval(".agent-home-heading", node => getComputedStyle(node).display), "none");
  assert.equal(await page.$eval(".home-quick-prompts", node => getComputedStyle(node).display), "none");
  await page.click("#agent-feature-trigger");
  await checkMenuGeometry("#agent-feature-tools");
  await page.keyboard.press("Escape");
  const chatOverflow = await page.evaluate(() => ({
    composerRight: document.querySelector(".copilot-query-box").getBoundingClientRect().right,
    sendRight: document.querySelector("#copilot-submit-query").getBoundingClientRect().right,
    viewportWidth: innerWidth,
  }));
  assert.ok(chatOverflow.composerRight <= chatOverflow.viewportWidth && chatOverflow.sendRight <= chatOverflow.viewportWidth, JSON.stringify(chatOverflow));
  await page.click("#home-history-show");
  await page.waitForFunction(() => document.querySelector(".sidebar").getBoundingClientRect().left === 0);
  await checkHistoryEditLayout();
  const [finalChatDelete] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "DELETE"
      && new URL(response.url()).pathname === `/api/v1/copilot/conversations/${chatSession.conversation_id}`),
    page.click("#chat-session-list .chat-session-delete"),
  ]);
  assert.equal(finalChatDelete.status(), 200);
  await page.waitForFunction(() => document.querySelectorAll("#chat-session-list .chat-session-item").length === 0
    && getComputedStyle(document.querySelector(".sidebar")).visibility === "hidden");
  assert.equal(conversationCreateCount(), 2);

  await page.click("#home-history-show");
  await page.waitForFunction(() => document.querySelector(".sidebar").getBoundingClientRect().left === 0);
  const previousChatRequests = apiRequests.filter(request => request.path === "/api/v1/copilot/chat").length;
  const [pendingSessionResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/v1/copilot/conversations"),
    page.evaluate(question => {
      document.querySelector("#copilot-natural-input").value = question;
      document.querySelector("#copilot-submit-query").click();
      document.querySelector("#new-chat-session").click();
    }, question),
  ]);
  assert.equal(pendingSessionResponse.status(), 201);
  const pendingSession = await pendingSessionResponse.json();
  await page.waitForSelector("#copilot-submit-query:not([disabled])");
  assert.equal(conversationCreateCount(), 3);
  assert.equal(apiRequests.filter(request => request.path === "/api/v1/copilot/chat").length, previousChatRequests);
  assert.equal(await page.$$("#copilot-chat-messages .chat-msg").then(nodes => nodes.length), 0);
  assert.equal(await page.$$("#chat-session-list .chat-session-item.is-active").then(nodes => nodes.length), 0);
  assert.equal(await page.$eval("#copilot-natural-input", node => node.value), "");
  const pendingDeleteStatus = await page.evaluate(async (id, ownerId) => {
    const response = await fetch(`/api/v1/copilot/conversations/${id}`, {method: "DELETE", headers: {"X-Owner-ID": ownerId}});
    return response.status;
  }, pendingSession.conversation_id, ownerId);
  assert.equal(pendingDeleteStatus, 200);

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
