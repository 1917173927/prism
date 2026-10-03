import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import puppeteer from "puppeteer-core";

const executablePath = process.env.PRISM_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
// Serve app/api with a localhost-only static test server; no backend is required.
const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8023/";
const temporary = await fs.mkdtemp(path.join(os.tmpdir(), "prism-human-review-test-"));
const browser = await puppeteer.launch({executablePath, headless: true, args: ["--no-sandbox"]});
try {
  const page = await browser.newPage(); const errors = [], apiRequests = [], dialogs = [];
  page.on("pageerror", error => errors.push(error.message)); page.on("dialog", dialog => {dialogs.push(dialog.message()); dialog.dismiss();});
  page.on("request", request => {if (new URL(request.url()).pathname.startsWith("/api/")) apiRequests.push(request.url());});
  const session = await page.createCDPSession(); await session.send("Browser.setDownloadBehavior", {behavior: "allow", downloadPath: temporary});
  await page.goto(new URL("/static/research-quality-review.html", baseUrl).href, {waitUntil: "networkidle0"});
  const pack = JSON.parse(await fs.readFile("app/api/static/research-quality-review-demo.json", "utf8"));
  pack.items[0].source_documents[0].text += "\n<script>alert('untrusted review source')</script>";
  const imported = path.join(temporary, "import.json"); await fs.writeFile(imported, JSON.stringify(pack));
  await (await page.$("#import-file")).uploadFile(imported); await page.waitForSelector("#workspace:not([hidden])");
  assert.match(await page.$eval("#question", node => node.textContent), /场景：MISSING/);
  assert.equal(await page.$$("#documents script").then(items => items.length), 0);
  await page.type("#reviewer", "browser-demo-reviewer");
  const label = async (claim, key, value) => page.select(`[data-claim-id="${claim}"] select[data-label-key="${key}"]`, value);
  const basis = async (claim, text) => page.type(`[data-claim-id="${claim}"] textarea[data-label-key="basis"]`, text);
  const itemLabel = async (key, value) => page.select(`#question-labels select[data-label-key="${key}"]`, value);
  await label("opening-time", "support", "SUPPORTED"); await label("opening-time", "citation_support", "SUPPORTED"); await basis("opening-time", "notice-1明确记载工作日09:00开放。");
  await label("sunday", "support", "UNSUPPORTED"); await label("sunday", "citation_support", "UNSUPPORTED"); await basis("sunday", "notice-1没有周日安排，不能从工作日推断。");
  await itemLabel("answerability", "INSUFFICIENT"); await itemLabel("refusal", "NOT_REFUSED"); await itemLabel("isolation_time", "PASS"); await page.type('#question-labels textarea[data-label-key="notes"]', "资料只支持工作日问题，周日回答无依据。合成练习未见隔离及时点错误。");
  await page.type("#relevant-evidence", "notice-1"); await page.click("#next");
  await label("missing-arrangement", "support", "SUPPORTED"); await label("missing-arrangement", "citation_support", "SUPPORTED"); await basis("missing-arrangement", "通知未说明周末安排。");
  await itemLabel("answerability", "INSUFFICIENT"); await itemLabel("refusal", "REASONABLE"); await itemLabel("isolation_time", "PASS"); await page.type('#question-labels textarea[data-label-key="notes"]', "通知不能回答周六开放时间，拒答合理。");
  await page.$$eval("#question-labels button", buttons => buttons.find(button => button.textContent.includes("确认此题无相关证据")).click());
  await page.click("#previous");
  assert.equal(await page.$eval('[data-claim-id="sunday"] select[data-label-key="support"]', node => node.value), "UNSUPPORTED");
  for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {await page.setViewport({width, height}); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${width} overflow`);}
  if (process.env.PRISM_TEST_SCREENSHOT) await page.screenshot({path: process.env.PRISM_TEST_SCREENSHOT, fullPage: true});
  await page.click("#export-json");
  const output = path.join(temporary, "quality-review-non-financial-operation-demo.v1.json");
  for (let index = 0; index < 30; index++) {if (await fs.access(output).then(() => true, () => false)) break; await new Promise(resolve => setTimeout(resolve, 100));}
  const exported = JSON.parse(await fs.readFile(output, "utf8")); assert.equal(exported.reviewer, "browser-demo-reviewer"); assert.deepEqual(exported.items[1].relevant_evidence_ids, []);
  const summaryPath = path.join(temporary, "summary.json");
  const result = spawnSync(path.resolve(".venv/Scripts/python.exe"), ["tools/summarize_research_quality_review.py", "--input", output, "--output", summaryPath], {encoding: "utf8"});
  assert.equal(result.status, 0, result.stderr);
  const summary = JSON.parse(await fs.readFile(summaryPath, "utf8"));
  assert.equal(summary.financial_gate, "NOT_APPLICABLE_SYNTHETIC"); assert.equal(summary.metrics.unsupported_atomic_fact_rate.numerator, 1); assert.equal(summary.metrics.unsupported_atomic_fact_rate.denominator, 3);
  assert.equal(summary.metrics.citation_support_rate.numerator, 2); assert.equal(summary.metrics.critical_numeric_consistency.status, "N/A"); assert.equal(summary.pending_annotations.length, 0);
  assert.equal(summary.sample_coverage.question_count, 2); assert.equal(summary.sample_coverage.minimum_questions, 100); assert.equal(summary.sample_coverage.missing_scenarios.length, 5);
  await (await page.$("#import-file")).uploadFile(path.resolve("app/api/static/research-quality-review-real-template.json"));
  await page.waitForFunction(() => document.querySelector("#dataset-meta").textContent.includes("REAL_CORPUS"));
  assert.match(await page.$eval("#question", node => node.textContent), /场景：NORMAL/);
  assert.equal(await page.$eval('[data-claim-id="real-claim-1"] select[data-label-key="numeric_consistency"]', node => node.value), "");
  assert.equal(await page.$eval('[data-claim-id="real-claim-1"] select[data-label-key="numeric_source_verified"]', node => node.value), "");
  assert.equal(await page.$eval("#reviewer", node => node.value), "");
  assert.deepEqual(errors, []); assert.deepEqual(dialogs, []); assert.deepEqual(apiRequests, []);
  process.stdout.write("Human review browser passed: import, literal source rendering, per-claim/question labels, navigation persistence, export, deterministic summary, three viewports, zero API requests. Synthetic labels cannot pass financial gate.\n");
} finally {
  await browser.close();
  // The test created only direct files in this exact temporary directory.
  for (const file of await fs.readdir(temporary)) await fs.unlink(path.join(temporary, file));
  await fs.rmdir(temporary);
}
