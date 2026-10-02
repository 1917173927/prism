import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8017";
const executablePath = process.env.PRISM_TEST_BROWSER || (
  process.platform === "win32"
    ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    : "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
);

const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  args: ["--no-sandbox"],
});

try {
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
      const location = message.location().url;
      consoleErrors.push(location ? `${message.text()} @ ${location}` : message.text());
    }
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body.questionnaire-required");
  await page.evaluate(() => { window.location.hash = "profile"; });
  await page.waitForSelector("#profile:not([hidden])");

  assert.equal(await page.$eval("#profile", (node) => node.hidden), false);
  assert.match(await page.$eval("#questionnaire-progress-text", (node) => node.textContent), /18/);

  await page.evaluate(() => { window.location.hash = "copilot"; });
  await page.waitForSelector("#copilot:not([hidden])");
  assert.equal(await page.$eval("#profile", (node) => node.hidden), true);
  await page.evaluate(() => { window.location.hash = "profile"; });
  await page.waitForSelector("#profile:not([hidden])");

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
  const widths = await page.evaluate(() => ({
    composer: document.querySelector(".copilot-query-box").getBoundingClientRect().width,
    tools: getComputedStyle(document.querySelector("#agent-feature-tools")).display,
    profile: getComputedStyle(document.querySelector("#agent-profile-rail")).display,
  }));
  assert.ok(widths.composer >= 600 && widths.composer <= 760, JSON.stringify(widths));
  assert.equal(widths.tools, "none");
  assert.equal(widths.profile, "none");

  await page.evaluate(() => { window.location.hash = "profile"; });
  await page.waitForSelector("#profile:not([hidden]) .profile-result-identity h4");
  assert.ok((await page.$eval(".profile-result-identity h4", (node) => node.textContent.trim())).length > 0);
  const recommendedFeatureCount = await page.$$(".profile-feature-card").then((nodes) => nodes.length);
  assert.ok(recommendedFeatureCount >= 1 && recommendedFeatureCount <= 3);
  assert.match(await page.$eval(".profile-compliance-fixed", (node) => node.textContent), /不构成投资建议/);
  await page.evaluate(() => { window.location.hash = "copilot"; });
  await page.waitForSelector("#copilot:not([hidden])");

  await page.click("#persona-switcher-bar > summary");
  await page.click("#home-context-trigger");
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

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("#copilot:not([hidden])");
  assert.equal(await page.$eval("#copilot-natural-input", (node) => node.getBoundingClientRect().width <= innerWidth), true);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);

  assert.deepEqual(consoleErrors, []);
  process.stdout.write("Browser checks passed.\n");
} finally {
  await browser.close();
}
