import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import {mkdir, mkdtemp, writeFile} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL || "http://127.0.0.1:8021";
const executablePath = process.env.PRISM_TEST_BROWSER || "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const root = fileURLToPath(new URL("../../", import.meta.url));
const output = path.join(root, "output/personal-center");
await mkdir(output, {recursive: true});
const directory = await mkdtemp(path.join(output, "browser-"));
const temporary = path.join(directory, "temporary");
await mkdir(temporary);
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: path.join(directory, "profile"), env: {...process.env, TMPDIR: temporary}});
const evidence = {checks: [], geometries: [], requests: []};

try {
  const page = await browser.newPage();
  page.setDefaultTimeout(60000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    const pathname = new URL(response.url()).pathname;
    if (pathname.includes("/profile/") || pathname.includes("display-policy")) {
      evidence.requests.push({path: pathname, method: response.request().method(), status: response.status()});
    }
  });
  const record = message => { evidence.checks.push(message); console.log(message); };
  const visible = selector => page.$eval(selector, node => node.getClientRects().length > 0);
  const text = selector => page.$eval(selector, node => node.textContent.trim());
  const waitResponse = (pathname, method = "GET") => page.waitForResponse(response =>
    new URL(response.url()).pathname === pathname && response.request().method() === method);
  async function api(pathname) {
    return page.evaluate(async pathname => {
      const response = await fetch(pathname, {headers: {"X-Owner-ID": document.documentElement.dataset.prismOwner}});
      const data = await response.json();
      if (!response.ok) throw new Error(`${pathname}: ${response.status} ${JSON.stringify(data)}`);
      return data;
    }, pathname);
  }
  async function navigate(hash) {
    await page.evaluate(hash => { window.location.hash = hash; }, hash);
    await page.waitForFunction(expected => window.location.hash === `#${expected}`, {}, hash);
    if (hash === "profile") await page.waitForSelector("body.profile-active #profile-overview-view:not([hidden])");
    if (hash === "profile-questionnaire") await page.waitForSelector("body.profile-questionnaire-active #profile-questionnaire-view:not([hidden])");
  }
  async function section(index) {
    await page.locator(`#questionnaire-section-tabs li:nth-child(${index + 1}) button`).click();
    await page.waitForFunction(expected => document.querySelector("#questionnaire-section-tabs button[aria-current='step']").textContent.startsWith(`${expected + 1}.`), {}, index);
  }
  async function checkRadar(summary) {
    const values = await page.$$eval("#profile-summary-content .profile-radar-label", nodes =>
      nodes.map(node => ({key: node.dataset.dimension, score: node.querySelector("strong").textContent})));
    assert.equal(values.length, 8);
    assert.deepEqual(values.map(item => item.score), summary.presentation.dimensions.map(item => Number(item.score).toFixed(0)));
    assert.deepEqual(values.map(item => item.key), summary.presentation.dimensions.map(item => item.key));
    assert.equal(await page.$$("#profile-summary-content .profile-radar-dot").then(nodes => nodes.length), 8);
    assert.match(await text("#profile-summary-content svg title"), new RegExp(values[0].score));
  }
  async function geometry(width, height, state) {
    await page.setViewport({width, height});
    await page.evaluate(() => window.scrollTo({top: 0, behavior: "instant"}));
    const measurement = await page.evaluate(() => {
      const rect = node => { const {left, right, top, bottom, width, height} = node.getBoundingClientRect(); return {left, right, top, bottom, width, height}; };
      const radar = document.querySelector("#profile-summary-content .profile-radar-visual");
      return {
        viewport: {width: innerWidth, height: innerHeight},
        documentWidth: document.documentElement.scrollWidth,
        heading: rect(document.querySelector("#profile-title")),
        radar: rect(radar), card: rect(radar.closest(".profile-center-hero")),
        labels: [...radar.querySelectorAll(".profile-radar-label")].map(node => ({...rect(node), fontSize: parseFloat(getComputedStyle(node).fontSize), text: node.textContent})),
        sidebarVisible: document.querySelector("#home-history-sidebar").getClientRects().length > 0,
        tabsVisible: document.querySelector("#workspace-page-tabs").getClientRects().length > 0,
      };
    });
    evidence.geometries.push({state, ...measurement});
    assert.ok(measurement.radar.bottom <= height, JSON.stringify(measurement));
    assert.ok(measurement.radar.top >= measurement.heading.bottom, JSON.stringify(measurement));
    assert.ok(measurement.documentWidth <= width + 1, JSON.stringify(measurement));
    assert.equal(measurement.sidebarVisible, false);
    assert.equal(measurement.tabsVisible, false);
    for (const label of measurement.labels) {
      assert.ok(label.left >= measurement.card.left && label.right <= measurement.card.right, JSON.stringify({width, label, card: measurement.card}));
      assert.ok(label.top >= measurement.card.top && label.bottom <= measurement.card.bottom, JSON.stringify({width, label, card: measurement.card}));
      assert.ok(label.bottom <= height && label.top >= measurement.heading.bottom, JSON.stringify({width, label}));
      assert.ok(label.fontSize >= 11);
    }
  }

  await page.setViewport({width: 1440, height: 900});
  await page.goto(baseUrl, {waitUntil: "domcontentloaded"});
  assert.equal(new URL(page.url()).pathname, "/login");
  const password = randomUUID() + randomUUID();
  await page.click("#register-tab");
  await page.type("#username", `personal-ui-${Date.now()}`);
  await page.type("#password", password);
  await page.type("#confirmation", password);
  await Promise.all([page.waitForNavigation({waitUntil: "domcontentloaded"}), page.click("#submit")]);
  await page.waitForSelector("body:not(.questionnaire-pending)");
  assert.equal((await api("/api/v1/auth/context")).enabled, true);
  await page.waitForSelector("#questionnaire-welcome[open]");
  await page.click("#welcome-start");
  await page.waitForSelector("body.profile-questionnaire-active #questionnaire-questions input");
  const template = await api("/api/v1/advisor/profile/questionnaire-template");
  assert.equal(template.questions.length, 19);
  assert.equal(template.sections.length, 6);
  assert.equal(template.questions.filter(question => question.required !== false).length, 18);
  assert.equal(template.questions.find(question => question.question_id === "Q13").required, false);
  assert.equal(await visible("#profile-overview-view"), false);
  await page.click("#questionnaire-next");
  assert.match(await text("#questionnaire-error"), /Q1/);
  assert.equal(await page.$eval("#questionnaire-confirm", node => node.hidden), true);
  record("真实账户注册、直接进入独立问卷及必答题检查");

  const seenQuestions = [];
  let optionCount = 0;
  for (let index = 0; index < template.sections.length; index += 1) {
    await section(index);
    const current = template.sections[index];
    assert.equal(await text(".questionnaire-section-description"), current.description);
    assert.equal(await text(`#questionnaire-section-tabs li:nth-child(${index + 1}) button`), `${index + 1}. ${current.title}`);
    for (const id of current.question_ids) {
      const question = template.questions.find(item => item.question_id === id);
      const rendered = await page.$eval(`input[name="${id}"]`, input => {
        const fieldset = input.closest("fieldset");
        return {prompt: fieldset.querySelector("legend").textContent,
          options: [...fieldset.querySelectorAll("label")].map(label => ({value: label.querySelector("input").value, type: label.querySelector("input").type, label: label.querySelector("span").textContent}))};
      });
      assert.equal(rendered.prompt, `${id}　${question.prompt}`);
      if (question.question_type === "SCORE") {
        assert.deepEqual(rendered.options.map(option => Number(option.value)), [1, 2, 3, 4, 5]);
        const labels = id === "Q12" ? ["几乎没有影响", "影响较小", "影响一般", "影响较大", "影响非常大"]
          : ["几乎不参考", "少量参考", "适度参考", "较多参考", "高度参考"];
        assert.deepEqual(rendered.options.map(option => option.label), labels);
        await page.click(`input[name="${id}"][value="3"]`);
      } else {
        assert.deepEqual(rendered.options, question.options.map(option => ({value: option.option_id,
          type: question.question_type === "MULTI" ? "checkbox" : "radio", label: option.label})));
        if (id !== "Q13") await page.click(`input[name="${id}"][value="${question.options[0].option_id}"]`);
      }
      if (id !== "Q13") assert.equal(await page.$eval(`input[name="${id}"]:checked`, node => node === document.activeElement), true);
      seenQuestions.push(id);
      optionCount += rendered.options.length;
    }
    if (index === 0) {
      await page.click("#profile-questionnaire-return");
      await page.waitForSelector("#profile-overview-view:not([hidden])");
      assert.equal(await visible("#questionnaire-form"), false);
      assert.equal(await page.$$("#profile-summary-content .profile-radar-value").then(nodes => nodes.length), 0);
      assert.equal(await page.$$("#profile-summary-content .profile-radar-ring").then(nodes => nodes.length), 5);
      for (const [width, height] of [[320, 740], [390, 844], [768, 1024], [1440, 900]]) await geometry(width, height, "未确认");
      await page.reload({waitUntil: "domcontentloaded"});
      await page.waitForSelector("body.profile-active:not(.questionnaire-pending) #profile-summary-content .profile-radar-visual");
      await page.click("#profile-questionnaire-open");
      await page.waitForSelector("#profile-questionnaire-view:not([hidden])");
      for (const id of current.question_ids) assert.equal(await page.$$( `input[name="${id}"]:checked`).then(nodes => nodes.length), 1);
      record("未确认画像使用空坐标、四种宽度的雷达首屏位置与草稿恢复");
    }
    if (index < template.sections.length - 1) await page.click("#questionnaire-next");
  }
  assert.deepEqual(seenQuestions, template.questions.map(question => question.question_id));
  assert.equal(optionCount, 98);
  await page.click('input[name="Q19"][value="none"]');
  assert.deepEqual(await page.$$eval('input[name="Q19"]:checked', nodes => nodes.map(node => node.value)), ["none"]);
  const q19 = template.questions.find(question => question.question_id === "Q19");
  await page.click(`input[name="Q19"][value="${q19.options.find(option => option.option_id !== "none").option_id}"]`);
  assert.equal(await page.$eval('input[name="Q19"][value="none"]', node => node.checked), false);
  assert.equal(await page.$$(".questionnaire-review dt").then(nodes => nodes.length), 19);
  assert.match(await text("#questionnaire-progress-text"), /18 \/ 18/);
  record("原有 19 题、98 个选项、六个部分、Q13 可选与互斥选项完整");

  const previewResponse = waitResponse("/api/v1/advisor/profile/questionnaire/preview", "POST");
  await page.click("#questionnaire-preview");
  const preview = await previewResponse;
  assert.equal(preview.status(), 200);
  const previewBody = await preview.json();
  assert.equal(previewBody.persisted, false);
  await page.waitForSelector("#questionnaire-result:not([hidden]) .profile-radar-value");
  assert.equal((await api("/api/v1/advisor/profile/summary")).questionnaire_snapshot, null);
  await navigate("profile");
  assert.equal(await page.$$("#profile-summary-content .profile-radar-value").then(nodes => nodes.length), 0);
  await navigate("profile-questionnaire");
  const confirmation = waitResponse("/api/v1/advisor/profile/questionnaire/confirm", "POST");
  await page.click("#questionnaire-confirm");
  assert.equal((await confirmation).status(), 200);
  await page.waitForSelector("body.profile-active:not(.profile-questionnaire-active) #profile-summary-content .profile-radar-value");
  const firstSummary = await api("/api/v1/advisor/profile/summary");
  assert.equal(firstSummary.questionnaire_snapshot.snapshot_version, 1);
  assert.equal(firstSummary.presentation.rule_trace.feats.defaulted, true);
  await checkRadar(firstSummary);
  assert.equal(await page.$$("#profile-details-content > details:not([open])").then(nodes => nodes.length), 3);
  assert.equal(await text("#profile-questionnaire-open"), "修改问卷");
  assert.match(await text("#questionnaire-confirmation-status"), /第 1 版/);
  assert.equal(await visible("#questionnaire-form"), false);
  const expectedRating = {CONSERVATIVE: "保守型", BALANCED: "平衡型", GROWTH: "成长型"}[firstSummary.effective_profile.risk_level];
  assert.equal(await text(".profile-center-rating-value"), expectedRating);
  record("服务端预览独立展示、确认保存并返回个人中心、雷达显示真实分数");

  for (let index = 1; index <= 3; index += 1) await page.click(`#profile-details-content > details:nth-child(${index}) > summary`);
  assert.equal(await page.$$("#profile-details-content .profile-key-fact").then(nodes => nodes.length), firstSummary.presentation.key_profile.length);
  assert.equal(await page.$$("#profile-details-content .profile-result-tag").then(nodes => nodes.length), firstSummary.presentation.tags.length);
  assert.equal(await page.$$("#profile-details-content .profile-strategy-list > li").then(nodes => nodes.length), firstSummary.presentation.service_strategy.length);
  assert.deepEqual(await page.$$eval("#profile-details-content .profile-allocation-row strong", nodes => nodes.map(node => node.textContent)), firstSummary.presentation.asset_allocation.map(item => `${Number(item.target_pct).toFixed(0)}%`));
  assert.equal(await page.$$("#profile-details-content .profile-feature-card").then(nodes => nodes.length), firstSummary.presentation.feats.length);
  assert.doesNotMatch(await text("#profile"), /不构成投资建议|双轨汇总|评级如何确定|DEFAULT · Q13/);
  for (const [width, height] of [[320, 740], [390, 844], [768, 1024], [1440, 900]]) await geometry(width, height, "已确认且详情展开");
  await page.focus("#profile-details-content > details:first-child > summary");
  await page.keyboard.press("Space");
  assert.equal(await page.$eval("#profile-details-content > details:first-child", node => node.open), false);
  await page.keyboard.press("Enter");
  assert.equal(await page.$eval("#profile-details-content > details:first-child", node => node.open), true);
  record("档案、标签、规则依据、推荐功能及配置数据保留；四种宽度与折叠键盘操作通过");

  await page.click("#profile-display-settings");
  await page.waitForSelector("#profile-display-dialog[open]");
  await page.keyboard.press("Escape");
  assert.equal(await page.$eval("#profile-display-settings", node => node === document.activeElement), true);
  await page.click("#profile-display-settings");
  await page.click('input[name="profile-display-policy-level"][value="80"]');
  const policyResponse = waitResponse("/api/v1/advisor/display-policy", "PATCH");
  await page.click('#profile-display-form button[type="submit"]');
  assert.equal((await policyResponse).status(), 200);
  await page.waitForFunction(() => !document.querySelector("#profile-display-dialog").open);
  assert.equal(await text("#profile-display-level"), "简洁");
  assert.equal((await api("/api/v1/advisor/profile/summary")).questionnaire_snapshot.snapshot_id, firstSummary.questionnaire_snapshot.snapshot_id);
  record("回答设置窗口通过实际接口保存，Escape 返回按钮焦点，问卷版本保持一致");

  await page.click("#profile-questionnaire-open");
  await page.waitForSelector("#profile-questionnaire-view:not([hidden])");
  await section(0);
  const changedQuestion = template.questions.find(question => question.question_id === "Q4");
  const changedOption = changedQuestion.options.at(-1).option_id;
  await page.click(`input[name="Q4"][value="${changedOption}"]`);
  assert.equal(await page.$eval("#questionnaire-confirm", node => node.hidden), true);
  await page.click("#profile-questionnaire-return");
  await page.waitForSelector("#profile-overview-view:not([hidden])");
  await checkRadar(firstSummary);
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForSelector("body.profile-active:not(.questionnaire-pending) #profile-summary-content .profile-radar-value");
  await checkRadar(firstSummary);
  await page.click("#profile-questionnaire-open");
  await page.waitForSelector("#profile-questionnaire-view:not([hidden])");
  await section(0);
  assert.equal(await page.$eval(`input[name="Q4"][value="${changedOption}"]`, node => node.checked), true);
  await section(5);
  const nextPreviewResponse = waitResponse("/api/v1/advisor/profile/questionnaire/preview", "POST");
  await page.click("#questionnaire-preview");
  const nextPreview = await nextPreviewResponse;
  assert.equal(nextPreview.status(), 200);
  const nextPreviewBody = await nextPreview.json();
  await page.waitForFunction(() => !document.querySelector("#questionnaire-form").inert);
  assert.notDeepEqual(nextPreviewBody.presentation.dimensions, firstSummary.presentation.dimensions);
  assert.equal((await api("/api/v1/advisor/profile/summary")).questionnaire_snapshot.snapshot_id, firstSummary.questionnaire_snapshot.snapshot_id);
  await navigate("profile");
  await checkRadar(firstSummary);
  await navigate("profile-questionnaire");
  await section(0);
  await page.click(`input[name="Q4"][value="${changedQuestion.options[0].option_id}"]`);
  assert.equal(await page.$eval("#questionnaire-result", node => node.hidden), true);
  assert.equal(await page.$eval("#questionnaire-confirm", node => node.hidden), true);
  await page.click(`input[name="Q4"][value="${changedOption}"]`);
  await section(5);
  const refreshedPreviewResponse = waitResponse("/api/v1/advisor/profile/questionnaire/preview", "POST");
  await page.click("#questionnaire-preview");
  assert.equal((await refreshedPreviewResponse).status(), 200);
  await page.waitForFunction(() => !document.querySelector("#questionnaire-form").inert && !document.querySelector("#questionnaire-confirm").hidden);
  const secondConfirmation = waitResponse("/api/v1/advisor/profile/questionnaire/confirm", "POST");
  await page.click("#questionnaire-confirm");
  assert.equal((await secondConfirmation).status(), 200);
  await page.waitForSelector("body.profile-active:not(.profile-questionnaire-active) #profile-summary-content .profile-radar-value");
  const secondSummary = await api("/api/v1/advisor/profile/summary");
  assert.equal(secondSummary.questionnaire_snapshot.snapshot_version, 2);
  assert.notEqual(secondSummary.questionnaire_snapshot.snapshot_id, firstSummary.questionnaire_snapshot.snapshot_id);
  await checkRadar(secondSummary);
  record("已确认问卷修改、刷新后的草稿恢复、预览隔离及第二次确认通过");

  await page.click(".profile-holdings-entry");
  await page.waitForSelector("body.portfolio-active #overview:not([hidden])");
  assert.equal(await visible("#home-history-sidebar"), false);
  await page.goBack();
  await page.waitForSelector("body.profile-active #profile-overview-view:not([hidden])");
  await page.click("#profile-details-content > details:first-child > summary");
  await page.click("#profile-details-content .profile-feature-card");
  await page.waitForSelector("body.copilot-active #agent-feature-config-dialog[open]");
  await page.keyboard.press("Escape");
  await navigate("profile");
  await page.click("#refresh-profile-summary");
  await page.waitForFunction(() => !document.querySelector("#refresh-profile-summary").disabled);
  await checkRadar(await api("/api/v1/advisor/profile/summary"));
  record("持仓分析入口、浏览器返回、推荐功能及画像刷新通过");

  await page.click("#profile-questionnaire-open");
  await page.waitForSelector("#profile-questionnaire-view:not([hidden])");
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewport({width, height: 900});
    await section(0);
    const result = await page.evaluate(() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth,
      formWidth: document.querySelector("#questionnaire-form").getBoundingClientRect().width}));
    assert.ok(result.documentWidth <= width + 1, JSON.stringify(result));
    evidence.geometries.push({state: "问卷填写", ...result});
  }
  await navigate("profile");
  await page.emulateMediaFeatures([{name: "prefers-reduced-motion", value: "reduce"}]);
  assert.equal(await page.$eval(".profile-radar-visual", node => getComputedStyle(node).animationName), "none");
  record("独立问卷在四种宽度下没有横向溢出，减少动态效果设置通过");
  assert.deepEqual(errors, []);
  assert.ok(evidence.requests.some(request => request.path.endsWith("/preview") && request.status === 200));
  assert.ok(evidence.requests.some(request => request.path.endsWith("/confirm") && request.status === 200));
  await writeFile(path.join(output, "verification.json"), JSON.stringify(evidence, null, 2));
  console.log("个人中心浏览器检查通过。");
} catch (error) {
  for (const page of await browser.pages()) {
    console.log(JSON.stringify(await page.evaluate(() => ({url: location.href, body: document.body.className,
      overviewHidden: document.querySelector("#profile-overview-view")?.hidden,
      questionnaireHidden: document.querySelector("#profile-questionnaire-view")?.hidden,
      entry: document.querySelector("#profile-questionnaire-open")?.outerHTML,
      focused: document.activeElement?.id, dialog: [...document.querySelectorAll("dialog[open]")].map(node => node.id),
      scrollY, height: innerHeight,
      navigation: [...document.querySelectorAll("#questionnaire-section-tabs button")].map(node => ({text: node.textContent, rectangle: node.getBoundingClientRect().toJSON()})),
      form: document.querySelector("#questionnaire-form")?.getBoundingClientRect().toJSON(),
      sidebar: document.querySelector(".questionnaire-sidebar")?.getBoundingClientRect().toJSON()})), null, 2));
  }
  throw error;
} finally {
  await browser.close();
}
