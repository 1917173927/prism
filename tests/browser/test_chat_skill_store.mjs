import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.PRISM_TEST_BASE_URL;
const owner = process.env.PRISM_TEST_OWNER_ID;
const executablePath = process.env.PRISM_TEST_BROWSER;
assert.ok(baseUrl && owner && executablePath, "请指定验证服务、实际账户与 Chromium 路径。");
assert.equal(process.env.PRISM_TEST_ISOLATED, "1", "保存操作需要独立数据库副本。");
const modelCatalog = JSON.parse(await fs.readFile(process.env.PRISM_TEST_MODEL_FILE, "utf8"));
const directory = path.resolve("output/chat-skill-store-integration");
const temporary = path.join(directory, "temporary");
await fs.mkdir(temporary, {recursive: true});
const browser = await puppeteer.launch({executablePath, headless: true,
  userDataDir: await fs.mkdtemp(path.join(directory, "profile-")),
  env: {...process.env, TEMP: temporary, TMP: temporary, TMPDIR: temporary}});
const evidence = {checks: [], geometry: [], requests: [], chats: [], pageErrors: []};
const record = message => { evidence.checks.push(message); console.log(message); };

try {
  const page = await browser.newPage();
  page.setDefaultTimeout(45000);
  page.on("pageerror", error => evidence.pageErrors.push(error.message));
  page.on("response", response => {
    const pathname = new URL(response.url()).pathname;
    if (/^\/api\/v1\/(skills|user\/model-settings|copilot\/chat)/.test(pathname)) {
      evidence.requests.push({path: pathname, method: response.request().method(), status: response.status()});
    }
  });
  page.on("request", request => {
    if (new URL(request.url()).pathname !== "/api/v1/copilot/chat") return;
    const body = JSON.parse(request.postData());
    evidence.chats.push({context: Boolean(body.session_truth_id), truthRevision: body.session_truth_revision,
      portfolioSnapshot: body.portfolio_snapshot_id, modelMode: body.model_mode, conversation: Boolean(body.conversation_id)});
  });
  await page.evaluateOnNewDocument(owner => {
    localStorage.setItem("prism_custom_user_profile_v2", JSON.stringify({ownerId: owner}));
    document.addEventListener("DOMContentLoaded", () => { document.getElementById("owner-id").value = owner; }, {once: true});
  }, owner);
  async function api(pathname) {
    return page.evaluate(async ({pathname, owner}) => {
      const response = await fetch(pathname, {headers: {"X-Owner-ID": owner}});
      if (!response.ok) throw new Error(`${pathname}: ${response.status}`);
      return response.json();
    }, {pathname, owner});
  }
  async function click(selector) {
    await page.$eval(selector, node => node.scrollIntoView({block: "center", behavior: "instant"}));
    await page.waitForFunction(selector => {
      const node = document.querySelector(selector), rect = node.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return node === hit || node.contains(hit);
    }, {}, selector);
    await page.click(selector);
  }
  async function route(hash, selector) {
    await page.evaluate(hash => { location.hash = hash; }, hash);
    await page.waitForSelector(selector, {visible: true});
  }
  async function setValue(selector, value) {
    await page.$eval(selector, (node, value) => { node.value = value; node.dispatchEvent(new Event("input", {bubbles: true})); }, value);
  }
  async function waitSkills() {
    await page.waitForFunction(() => document.querySelectorAll(".research-skill-card").length > 0
      && document.getElementById("skill-store-message").hidden);
  }
  async function submitChat(message) {
    await setValue("#copilot-natural-input", message);
    const response = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/copilot/chat");
    await click("#copilot-submit-query");
    assert.equal((await response).status(), 200);
    await page.waitForFunction(() => !document.getElementById("copilot-submit-query").disabled, {timeout: 60000});
    const result = await page.$eval(".chat-msg.assistant:last-child .chat-content-box", node => node.textContent.trim());
    assert.ok(result.length > 0 && !result.startsWith("请求未完成：") && !result.startsWith("分析已停止"), result);
    assert.ok(await page.$eval("#chat-send-progress", node => node.textContent.includes("分析已完成")));
    return result.length;
  }
  async function saveModel(model) {
    await click("#home-model-trigger");
    await page.waitForFunction(() => !document.getElementById("btn-save-llm-config").disabled);
    await page.select("#llm-provider-select", "deepseek");
    await setValue("#llm-model-input", model);
    const saved = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/user/model-settings" && response.request().method() === "PUT");
    const tested = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/user/model-settings/test");
    await click("#btn-save-llm-config");
    assert.equal((await saved).status(), 200);
    assert.equal((await tested).status(), 200);
    await page.waitForFunction(() => !document.getElementById("btn-save-llm-config").disabled);
    assert.ok(await page.$eval("#llm-config-status", node => node.textContent.includes("连接测试通过")));
    await click("#close-llm-config-modal-btn");
    assert.equal((await api("/api/v1/user/model-settings")).model, model);
  }

  await page.setViewport({width: 1440, height: 1000});
  await page.goto(baseUrl + "/?dev=0#copilot", {waitUntil: "networkidle0"});
  await page.waitForSelector("body:not(.questionnaire-pending)");
  assert.equal(await page.$eval("#owner-id", node => node.value), owner);
  assert.equal((await api("/api/health")).data_mode, "LIVE");
  const portfolio = (await api("/api/v1/advisor/portfolio/current")).data;
  assert.ok(portfolio?.portfolio?.position_snapshot?.snapshot_id);
  const originalModel = await api("/api/v1/user/model-settings");
  assert.ok(originalModel.is_configured);
  await click("#new-chat-session");
  const initialGeometry = await page.evaluate(() => ({
    storeTop: document.getElementById("nav-store").getBoundingClientRect().top,
    newTop: document.getElementById("new-chat-session").getBoundingClientRect().top,
    sendWidth: document.getElementById("copilot-submit-query").getBoundingClientRect().width,
    sendHeight: document.getElementById("copilot-submit-query").getBoundingClientRect().height,
  }));
  assert.ok(initialGeometry.storeTop < initialGeometry.newTop);
  assert.equal(initialGeometry.sendWidth, 34); assert.equal(initialGeometry.sendHeight, 34);
  assert.equal(await page.$eval("#copilot-submit-query use", node => node.getAttribute("href")), "#icon-arrow-up");
  assert.equal(await page.$eval("#chat-session-search", node => node.value), "");
  await click("#agent-feature-trigger"); await click('[data-feature-id="industry"]');
  await page.keyboard.press("Escape");
  await setValue("#copilot-natural-input", "保存我的对话草稿");
  await setValue("#chat-session-search", "手动输入");
  await click("#nav-store"); await waitSkills();
  assert.equal(await page.$eval("#home-history-sidebar", node => node.inert), false);
  assert.equal(await page.$eval("#nav-store", node => node.classList.contains("active")), true);
  assert.equal(await page.$$eval("dialog[open]", nodes => nodes.length), 0);
  const skills = (await api("/api/v1/skills")).items;
  const listed = await page.$$eval(".research-skill-card", nodes => nodes.map(node => ({id: node.dataset.skillId, version: node.dataset.skillVersion})));
  assert.deepEqual(listed, skills.map(item => ({id: item.skill_id, version: item.version})));
  record("侧栏入口、发送箭头、Tools 与真实技能目录检查通过");

  const chosen = skills[0];
  const chosenSelector = `[data-skill-id="${chosen.skill_id}"][data-skill-version="${chosen.version}"] .research-skill-name button`;
  await click(chosenSelector);
  assert.equal(await page.$eval("#skill-technical-details", node => node.open), false);
  assert.equal(await page.$eval("#skill-management-details", node => node.open), false);
  await click("#skill-technical-details summary");
  const metadata = await page.$$eval("#skill-technical-details dd", nodes => nodes.map(node => node.textContent));
  assert.ok(metadata.includes(chosen.skill_id) && metadata.includes(chosen.version) && metadata.includes(chosen.endpoint));
  for (let index = 0; index < 18; index++) {
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement === document.body
      || document.getElementById("skill-store-detail").contains(document.activeElement)), true);
  }
  await click("#skill-detail-close"); await click(chosenSelector);
  assert.equal(await page.evaluate(() => {
    const before = document.activeElement; document.getElementById("nav-copilot").focus();
    return before === document.activeElement;
  }), true);
  await click("#skill-technical-details summary");
  await click("#skill-management-details summary");
  const originalGlobal = chosen.enabled;
  for (const enabled of [!originalGlobal, originalGlobal]) {
    const label = enabled ? "全局启用" : "全局停用";
    const controls = await page.$$("#skill-management-details button");
    const control = controls[await page.$$eval("#skill-management-details button", (nodes, label) => nodes.findIndex(node => node.textContent === label), label)];
    assert.ok(control);
    const response = page.waitForResponse(response => new URL(response.url()).pathname.endsWith(`/${chosen.skill_id}/${chosen.version}`) && response.request().method() === "PATCH");
    await control.click(); assert.equal((await response).status(), 200);
    await page.waitForFunction(enabled => [...document.querySelectorAll("#skill-management-details button")].some(node => node.textContent === (enabled ? "全局停用" : "全局启用") && !node.disabled), {}, enabled);
    assert.equal((await api("/api/v1/skills")).items.find(item => item.skill_id === chosen.skill_id && item.version === chosen.version).enabled, enabled);
  }
  assert.equal(await page.$eval("#skill-management-details", node => node.open), true);
  await click("#skill-management-details summary");
  await click("#skill-personal-toggle");
  await page.waitForFunction(enabled => document.getElementById("skill-personal-toggle").getAttribute("aria-pressed") === String(!enabled)
    && !document.getElementById("skill-personal-toggle").disabled, {}, chosen.personal_enabled);
  const changed = (await api("/api/v1/skills")).items.find(item => item.skill_id === chosen.skill_id && item.version === chosen.version);
  assert.equal(changed.personal_enabled, !chosen.personal_enabled); assert.ok(changed.selection_revision > chosen.selection_revision);
  assert.equal(await page.$eval("#skill-technical-details", node => node.open), true);
  await click("#skill-personal-toggle");
  await page.waitForFunction(enabled => document.getElementById("skill-personal-toggle").getAttribute("aria-pressed") === String(enabled)
    && !document.getElementById("skill-personal-toggle").disabled, {}, chosen.personal_enabled);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.getElementById("skill-store-detail").open);
  assert.equal(await page.evaluate(() => document.activeElement.closest(".research-skill-card")?.dataset.skillId), chosen.skill_id);
  await click("#skill-store-personal"); await page.keyboard.press("ArrowLeft");
  assert.equal(await page.$eval("#skill-store-public", node => node.getAttribute("aria-selected")), "true");
  await setValue("#skill-store-search", chosen.skill_id);
  assert.equal(await page.$$eval(".research-skill-card", nodes => nodes.length), skills.filter(item => item.skill_id.includes(chosen.skill_id)).length);
  await click("#skill-store-filters summary"); await click("#skill-store-versions");
  assert.ok(await page.$eval(".research-skill-name small", (node, version) => node.textContent.includes(version), chosen.version));
  await click("#skill-store-filters summary");
  await click(chosenSelector);
  await page.mouse.click(8, 8);
  await page.waitForFunction(() => !document.getElementById("skill-store-detail").open);
  await click(chosenSelector);
  await page.evaluate(() => history.back());
  await page.waitForSelector("#copilot", {visible: true});
  assert.equal(await page.$eval("#skill-store-detail", node => node.open), false);
  assert.equal(await page.$eval("#copilot-natural-input", node => node.value), "保存我的对话草稿");
  assert.equal(await page.$eval("#home-selected-tool", node => node.hidden), false);
  assert.equal(await page.$eval("#chat-session-search", node => node.value), "手动输入");
  await page.evaluate(() => history.forward()); await page.waitForSelector("#skill-store", {visible: true}); await waitSkills();
  assert.equal(await page.$eval("#skill-store-detail", node => node.open), false);
  await click(".research-store-return"); await page.waitForSelector("#copilot", {visible: true});
  assert.equal(await page.$eval("#copilot-natural-input", node => node.value), "保存我的对话草稿");
  await page.reload({waitUntil: "networkidle0"});
  assert.equal(await page.$eval("#chat-session-search", node => node.value), "");
  record("技能选择实际保存、详情展开、键盘焦点、返回草稿与搜索刷新检查通过");

  await route("skill-store", "#skill-store"); await waitSkills();
  await page.reload({waitUntil: "networkidle0"}); await waitSkills();
  assert.equal(await page.$$eval(".research-skill-card", nodes => nodes.length), skills.length);
  assert.equal(await page.$eval("#chat-session-search", node => node.value), "");
  const wasDark = await page.evaluate(() => document.body.classList.contains("prism-theme-dark"));
  const originalColors = await page.$eval("#skill-store-detail", node => ({background: getComputedStyle(node).backgroundColor, color: getComputedStyle(node).color}));
  await click(".topbar-more-menu > summary"); await click("#theme-toggle");
  await page.waitForFunction(wasDark => document.body.classList.contains("prism-theme-dark") !== wasDark, {}, wasDark);
  const colors = await page.$eval("#skill-store-detail", node => ({background: getComputedStyle(node).backgroundColor, color: getComputedStyle(node).color}));
  assert.notEqual(colors.background, colors.color);
  assert.notEqual(colors.background, originalColors.background);
  await click(".topbar-more-menu > summary"); await click("#theme-toggle");
  await page.waitForFunction(wasDark => document.body.classList.contains("prism-theme-dark") === wasDark, {}, wasDark);
  const routes = await page.evaluate(() => {
    const primary = [...document.querySelectorAll("#home-primary-navigation a")].map(node => [node.hash.slice(1), node.hash]);
    const portfolio = [...document.querySelectorAll("[data-portfolio-route]")].map(node => [node.dataset.portfolioRoute, `#${node.getAttribute("aria-controls")}`]);
    const research = [...document.querySelectorAll("[data-research-route]")].map(node => [node.dataset.researchRoute, `#${node.dataset.researchRoute}`]);
    return [...new Map([...primary, ["skill-store", "#skill-store"], ...portfolio, ...research,
      ["market-risk", "#market"], ["market-sectors", "#market"], ["profile-preferences", "#profile"]]).entries()];
  });
  for (const width of [1440, 1024, 768, 390, 320]) {
    await page.setViewport({width, height: 1000});
    let reference;
    for (const [hash, selector] of routes) {
      await route(hash, selector);
      const geometry = await page.evaluate(() => {
        const header = document.getElementById("home-navigation"), brand = header.querySelector(".brand"), nav = document.getElementById("home-primary-navigation");
        const bounds = node => { const rect = node.getBoundingClientRect(); return [rect.left, rect.top, rect.width, rect.height]; };
        return {header: bounds(header), brand: bounds(brand), navigation: bounds(nav), fontSize: getComputedStyle(brand.querySelector("strong")).fontSize,
          border: getComputedStyle(brand).borderBottomWidth, documentWidth: document.documentElement.scrollWidth, width: innerWidth};
      });
      assert.equal(geometry.fontSize, "20px"); assert.equal(geometry.border, "0px");
      assert.ok(geometry.documentWidth <= width + 1, JSON.stringify({hash, ...geometry}));
      const navigation = {header: geometry.header, brand: geometry.brand, navigation: geometry.navigation};
      if (!reference) reference = navigation;
      assert.deepEqual(navigation, reference, `${width}px ${hash}`);
      evidence.geometry.push({hash, ...geometry});
    }
    await route("skill-store", "#skill-store"); await waitSkills();
    if (width <= 760) {
      const history = await page.evaluate(() => ({
        titleTop: document.getElementById("skill-store-title").getBoundingClientRect().top,
        showBottom: document.getElementById("home-history-show").getBoundingClientRect().bottom,
      }));
      assert.ok(history.titleTop >= history.showBottom + 8);
      await click("#home-history-show");
      assert.equal(await page.$eval("#home-history-sidebar", node => node.inert), false);
      await page.waitForFunction(() => Math.abs(document.getElementById("home-history-sidebar").getBoundingClientRect().left) < 1);
      await click("#home-history-hide");
      assert.equal(await page.$eval("#home-history-sidebar", node => node.inert), true);
      await page.waitForFunction(() => getComputedStyle(document.getElementById("home-history-sidebar")).visibility === "hidden");
    }
    await click(".research-skill-name button");
    const dialog = await page.$eval("#skill-store-detail", node => { const rect = node.getBoundingClientRect(); return {left: rect.left, right: rect.right, height: rect.height}; });
    assert.ok(dialog.left >= 0 && dialog.right <= width && dialog.height <= 1000);
    await page.keyboard.press("Escape");
  }
  record(`五种窗口宽度、${evidence.geometry.length} 次页面导航、深色主题与弹窗尺寸检查通过`);

  await page.setViewport({width: 1440, height: 1000});
  await route("copilot", "#copilot"); await click("#new-chat-session");
  const ordinaryTruth = await api("/api/v1/advisor/session-truth");
  const ordinaryLength = await submitChat("请用两句话解释什么是资产分散配置。");
  const ordinary = evidence.chats.at(-1);
  assert.equal(ordinary.context, ordinaryTruth.status === "LOCKED"); assert.equal(ordinary.conversation, true);
  record(`普通对话实际返回 ${ordinaryLength} 个字符，使用独立会话`);
  await click("#persona-switcher-bar > summary"); await click("#home-context-trigger");
  await click(".agent-rail-details.account-details > summary");
  await click("#confirm-session-truth"); await page.waitForSelector("#truth-confirm-dialog", {visible: true});
  await click("#commit-session-truth");
  await page.waitForFunction(() => !document.getElementById("truth-confirm-dialog").open);
  const truth = await api("/api/v1/advisor/session-truth"); assert.equal(truth.status, "LOCKED");
  assert.equal(await page.$eval("#copilot", node => node.classList.contains("context-open")), false);
  const contextLength = await submitChat("请基于已确认的持仓和风险设置，说明组合的主要风险以及需要关注的事项。");
  const personalized = evidence.chats.at(-1);
  assert.equal(personalized.context, true); assert.equal(personalized.truthRevision, truth.revision);
  assert.equal(personalized.portfolioSnapshot, portfolio.portfolio.position_snapshot.snapshot_id);
  record(`指定持仓上下文实际返回 ${contextLength} 个字符，快照与资料版本一致`);

  await click("#home-model-trigger");
  await page.waitForFunction(() => !document.getElementById("btn-save-llm-config").disabled);
  for (const provider of ["qwen", "openai", "deepseek"]) {
    await page.select("#llm-provider-select", provider);
    assert.ok(await page.$eval("#llm-base-url-input", node => node.value.startsWith("https://")));
    assert.ok(await page.$eval("#llm-model-input", node => node.value.length > 0));
  }
  assert.equal(await page.$eval("#llm-api-key-input", node => node.value), "");
  await click("#close-llm-config-modal-btn");
  const alternative = modelCatalog.models.findLast(model => model !== originalModel.model);
  assert.ok(alternative);
  await saveModel(alternative);
  const switchedLength = await submitChat("请用一句话解释长期持有与短期交易的区别。");
  assert.ok(switchedLength > 0);
  await saveModel(originalModel.model);
  assert.deepEqual(evidence.pageErrors, []);
  record("服务商预设、高级字段、实际模型切换、保存与连接测试通过");
  console.log(JSON.stringify({checks: evidence.checks.length, geometryStates: evidence.geometry.length, chats: evidence.chats.length, pageErrors: evidence.pageErrors.length}));
} finally {
  await fs.writeFile(path.join(directory, "verification.json"), JSON.stringify(evidence, null, 2));
  await browser.close();
}
