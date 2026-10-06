import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL;
const ownerId = process.env.PRISM_TEST_OWNER_ID;
const executablePath = process.env.PRISM_TEST_BROWSER;
assert.ok(baseUrl && ownerId && executablePath, "请指定隔离服务、账户与 Chromium 路径。");
assert.equal(process.env.PRISM_TEST_ISOLATED, "1", "此项检查需要使用独立数据库副本。");

const profileDirectory = path.resolve("output/session-truth-resume-browser");
await fs.mkdir(profileDirectory, {recursive: true});
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: await fs.mkdtemp(path.join(profileDirectory, "profile-"))});

try {
  const page = await browser.newPage();
  page.setDefaultTimeout(120000);
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.evaluateOnNewDocument(owner => {
    localStorage.setItem("prism_custom_user_profile_v2", JSON.stringify({ownerId: owner}));
    document.addEventListener("DOMContentLoaded", () => {
      document.getElementById("owner-id").value = owner;
    }, {once: true});
  }, ownerId);
  await page.setViewport({width: 1440, height: 900});
  await page.goto(`${baseUrl}/?dev=0#copilot`, {waitUntil: "networkidle0"});
  await page.waitForSelector("body.copilot-active:not(.questionnaire-pending) #copilot:not([hidden])");
  assert.equal(await page.$eval("#owner-id", node => node.value), ownerId);

  const initial = await page.evaluate(async owner => {
    const health = await fetch("/api/health").then(response => response.json());
    const truth = await fetch("/api/v1/advisor/session-truth", {headers: {"X-Owner-ID": owner}})
      .then(response => response.json());
    return {health, truth};
  }, ownerId);
  assert.equal(initial.health.data_mode, "LIVE");
  assert.ok(["NOT_LOCKED", "DRIFT_DETECTED"].includes(initial.truth.status));

  await page.click("#new-chat-session");
  await page.type("#copilot-natural-input", "给我一些调仓建议");
  const createdResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/v1/copilot/conversations");
  const firstResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/v1/copilot/chat");
  await page.click("#copilot-submit-query");
  const created = await (await createdResponse).json();
  assert.equal((await firstResponse).status(), 200);
  await page.waitForFunction(() => !document.getElementById("copilot-submit-query").disabled
    && document.querySelector(".chat-msg.assistant .chat-content-box")?.textContent.includes("请先确认当前真实数据模式"));
  const action = await page.$(".chat-msg.assistant .copilot-action-btn.secondary");
  assert.ok(action);
  assert.equal(await page.evaluate(node => node.disabled, action), false);

  await action.click();
  await page.waitForSelector("#truth-confirm-dialog[open]");
  assert.equal(await page.$eval("#truth-confirm-description", node => node.textContent), "确认后将继续回答这条问题。");
  const confirmationResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/v1/advisor/session-truth");
  const resumedResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/v1/copilot/chat");
  await page.click("#commit-session-truth");
  assert.equal((await confirmationResponse).status(), 200);
  assert.equal((await resumedResponse).status(), 200);
  await page.waitForFunction(() => !document.getElementById("copilot-submit-query").disabled
    && document.querySelectorAll(".chat-msg.assistant").length === 2);
  assert.equal(await page.$eval("#truth-confirm-dialog", node => node.open), false);
  assert.equal(await page.$eval(".chat-msg.assistant:last-child .chat-process-label", node => node.textContent), "已思考");
  await page.waitForFunction(() => document.querySelector(".chat-msg.assistant .copilot-action-btn.secondary")?.textContent === "已按新资料继续分析");
  assert.equal(await page.$eval(".chat-msg.assistant .copilot-action-btn.secondary", node => node.disabled), true);

  const result = await page.evaluate(async ({conversationId, owner}) => {
    const headers = {"X-Owner-ID": owner};
    const truth = await fetch("/api/v1/advisor/session-truth", {headers}).then(response => response.json());
    const conversation = await fetch(`/api/v1/copilot/conversations/${conversationId}`, {headers})
      .then(response => response.json());
    return {truth, conversation};
  }, {conversationId: created.conversation_id, owner: ownerId});
  assert.equal(result.truth.status, "LOCKED");
  assert.deepEqual(result.conversation.messages.map(message => message.role),
    ["user", "assistant", "user", "assistant"]);
  assert.equal(result.conversation.messages[2].context_scope,
    `truth:workbench:${result.truth.revision}`);
  assert.notEqual(result.conversation.messages[1].content, result.conversation.messages[3].content);

  const recovery = await page.evaluate(async owner => {
    const headers = {"X-Owner-ID": owner};
    const list = await fetch("/api/v1/copilot/conversations?limit=20", {headers})
      .then(response => response.json());
    for (const [index, item] of list.items.entries()) {
      const conversation = await fetch(`/api/v1/copilot/conversations/${item.conversation_id}`, {headers})
        .then(response => response.json());
      if (conversation.messages.at(-1)?.content === "请先确认当前真实数据模式下的风险问卷与持仓，并锁定分析前提，再执行持仓体检。") {
        return {index, conversationId: item.conversation_id, originalCount: conversation.messages.length};
      }
    }
    return null;
  }, ownerId);
  assert.ok(recovery);
  await page.click(`#chat-session-list .chat-session-item:nth-child(${recovery.index + 1}) .chat-session-select`);
  await page.waitForFunction(() => document.querySelector(".chat-msg.assistant:last-child .copilot-action-btn.secondary")?.textContent === "继续分析");
  const recoveredResponse = page.waitForResponse(response => response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/v1/copilot/chat");
  await page.click(".chat-msg.assistant:last-child .copilot-action-btn.secondary");
  assert.equal((await recoveredResponse).status(), 200);
  await page.waitForFunction(expected => !document.getElementById("copilot-submit-query").disabled
    && document.querySelectorAll(".chat-msg.assistant").length === expected,
  {}, recovery.originalCount / 2 + 1);
  await page.waitForFunction(() => document.querySelector(".chat-msg.assistant .copilot-action-btn.secondary")?.textContent === "已按新资料继续分析");
  assert.equal(await page.$eval("#truth-confirm-dialog", node => node.open), false);
  const recovered = await page.evaluate(async ({conversationId, owner}) => fetch(
    `/api/v1/copilot/conversations/${conversationId}`, {headers: {"X-Owner-ID": owner}}
  ).then(response => response.json()), {conversationId: recovery.conversationId, owner: ownerId});
  assert.equal(recovered.messages.length, recovery.originalCount + 2);
  assert.equal(recovered.messages.at(-2).content, "给我一些调仓建议");
  assert.equal(recovered.messages.at(-1).context_scope, `truth:workbench:${result.truth.revision}`);
  assert.notEqual(recovered.messages.at(-1).content, recovered.messages.at(-3).content);
  assert.deepEqual(pageErrors, []);
  console.log("资料确认与历史对话继续分析检查通过。");
} finally {
  await browser.close();
}
