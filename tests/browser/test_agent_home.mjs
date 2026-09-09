import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8017";
const outputDir = path.resolve("output/agent-home");
await fs.mkdir(outputDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  args: ["--no-sandbox"],
});

try {
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body.questionnaire-required");

  assert.equal(await page.$eval("#profile", (node) => node.hidden), false);
  assert.equal(await page.$eval(".sidebar", (node) => getComputedStyle(node).display), "none");
  assert.match(await page.$eval("#questionnaire-progress-text", (node) => node.textContent), /19/);

  await page.evaluate(() => { window.location.hash = "copilot"; });
  await page.waitForFunction(() => window.location.hash === "#profile");
  assert.equal(await page.$eval("#profile", (node) => node.hidden), false);
  assert.equal(await page.$eval("#copilot", (node) => node.hidden), true);
  await page.screenshot({ path: path.join(outputDir, "first-entry-questionnaire.png"), fullPage: true });

  const confirmationStatus = await page.evaluate(async () => {
    const ownerId = "demo-owner";
    const template = await fetch("/api/v1/advisor/profile/questionnaire-template", {
      headers: { "X-Owner-ID": ownerId },
    }).then((response) => response.json());
    const answers = template.questions.map((question) => question.question_type === "SCORE"
      ? { question_id: question.question_id, score: 3 }
      : { question_id: question.question_id, selected_option_ids: [question.options[0].option_id] });
    const response = await fetch("/api/v1/advisor/profile/questionnaire/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Owner-ID": ownerId },
      body: JSON.stringify({
        schema_version: "questionnaire-confirmation-request.v1",
        owner_id: ownerId,
        confirmed_at: new Date().toISOString(),
        answers,
      }),
    });
    return response.status;
  });
  assert.equal(confirmationStatus, 200);

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("body:not(.questionnaire-pending):not(.questionnaire-required)");
  await page.waitForSelector("#copilot:not([hidden])");
  assert.equal(await page.$$("#copilot .copilot-task-card").then((nodes) => nodes.length), 0);
  const widths = await page.$eval("#agent-home-grid", (grid) => {
    const [conversation, rail] = grid.children;
    return {
      conversation: conversation.getBoundingClientRect().width,
      rail: rail.getBoundingClientRect().width,
    };
  });
  assert.ok(widths.conversation > widths.rail * 2.2, JSON.stringify(widths));

  await page.click("#start-conversation-profile-update");
  for (let step = 0; step < 4; step += 1) {
    await page.waitForSelector(".conversation-profile-card .conversation-profile-options button");
    const cards = await page.$$(".conversation-profile-card");
    const buttons = await cards.at(-1).$$(".conversation-profile-options button");
    await buttons[0].click();
  }
  const cards = await page.$$(".conversation-profile-card");
  const confirmationButtons = await cards.at(-1).$$(".conversation-profile-options button");
  await confirmationButtons[0].click();
  await page.waitForFunction(() => localStorage.getItem("prism_conversation_profile_v1") !== null);
  assert.match(await page.$eval("#behavior-profile-content", (node) => node.textContent), /对话补充/);
  await page.screenshot({ path: path.join(outputDir, "agent-home-desktop.png"), fullPage: true });

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("#copilot:not([hidden])");
  assert.equal(await page.$eval("#agent-home-grid", (node) => getComputedStyle(node).gridTemplateColumns.split(" ").length), 1);
  assert.equal(await page.$eval("#copilot-natural-input", (node) => node.getBoundingClientRect().width <= innerWidth), true);
  await page.screenshot({ path: path.join(outputDir, "agent-home-mobile.png"), fullPage: true });

  assert.deepEqual(consoleErrors, []);
  process.stdout.write(`Browser checks passed. Screenshots: ${outputDir}\n`);
} finally {
  await browser.close();
}
