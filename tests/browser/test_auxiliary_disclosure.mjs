import assert from "node:assert/strict";

async function openPage(tab, origin, pageId) {
  const url = `${origin}/#${pageId}`;
  if (await tab.url() !== url) await tab.goto(url);
  await tab.getAXState({emit:false});
}

// 在 CUA 会话中传入已正常登录的 tab；全部界面操作使用 CUA。
export async function auditAuxiliaryPages(tab) {
  const origin = new URL(await tab.url()).origin;
  const pages = [
    ["portfolio-optimization", 1], ["portfolio-rebalancing", 1], ["scenario-simulation", 1],
    ["stock-research", 1], ["fund-research", 1], ["convertible-bond-research", 1],
    ["portfolio", 0], ["recommendation-history", 0], ["advanced-explainability", 1],
  ];
  const observations = [];
  for (const [pageId, expectedActions] of pages) {
    await openPage(tab, origin, pageId);
    const observation = await tab.playwright.evaluate(pageId => {
      const page = document.getElementById(pageId);
      const visible = node => node && node.getClientRects().length > 0
        && !node.closest("[hidden], details:not([open]) > :not(summary)");
      return {
        pageId, width:innerWidth, pageVisible:visible(page),
        headerVisible:visible(document.getElementById("home-navigation")),
        headerCount:document.querySelectorAll("#home-navigation").length,
        activeNavigation:document.querySelectorAll("#home-navigation [aria-current]").length,
        legacyNavigation:document.querySelectorAll(".topbar, .nav-list, .topbar-actions").length,
        breadcrumbCount:page.querySelectorAll(".breadcrumb").length,
        tabsHidden:document.getElementById("workspace-page-tabs").hidden,
        primaryActions:[...page.querySelectorAll("button.primary")].filter(visible).length,
        openDetails:page.querySelectorAll(".auxiliary-disclosure[open]").length,
        disclosureCount:page.querySelectorAll(".auxiliary-disclosure").length,
        backTarget:page.querySelector(".auxiliary-back-link")?.getAttribute("href"),
        overflow:document.documentElement.scrollWidth > innerWidth,
      };
    }, pageId);
    assert.equal(observation.pageVisible, true);
    assert.equal(observation.headerVisible, true);
    assert.equal(observation.headerCount, 1);
    assert.equal(observation.activeNavigation, 1);
    assert.equal(observation.legacyNavigation, 0);
    assert.equal(observation.breadcrumbCount, 0);
    assert.equal(observation.tabsHidden, true);
    assert.equal(observation.primaryActions, expectedActions, JSON.stringify(observation));
    assert.equal(observation.openDetails, 0, JSON.stringify(observation));
    assert.equal(observation.backTarget, "#overview");
    assert.equal(observation.overflow, false, JSON.stringify(observation));
    if (observation.disclosureCount && !["recommendation-history", "portfolio"].includes(pageId)) {
      const disclosure = tab.playwright.locator(`#${pageId} .auxiliary-disclosure:not(.dev-only) > summary`).first();
      await disclosure.press("Enter");
      await tab.getAXState({emit:false});
      assert.equal(await tab.playwright.evaluate(pageId =>
        document.getElementById(pageId).querySelectorAll(".auxiliary-disclosure[open]").length, pageId), 1);
      await disclosure.press("Enter");
      await tab.getAXState({emit:false});
    }
    observations.push(observation);
  }
  return observations;
}

export async function auditProfileDialog(tab) {
  const origin = new URL(await tab.url()).origin;
  const observations = [];
  for (const page of ["copilot", "overview", "market", "trading-style", "profile"]) {
    await openPage(tab, origin, page);
    await tab.playwright.locator("#persona-switcher-bar > summary").click();
    await tab.getAXState({emit:false});
    await tab.playwright.locator("#open-profile-modal-btn").click();
    await tab.getAXState({emit:false});
    const observation = await tab.playwright.evaluate(() => {
      const modal = document.getElementById("profile-edit-modal");
      return {page:location.hash, tag:modal.tagName, parent:modal.parentElement.tagName,
        open:modal.open, modal:modal.matches(":modal"), hiddenAncestor:!!modal.closest("[hidden]"),
        visible:modal.getClientRects().length > 0, focusInside:modal.contains(document.activeElement)};
    });
    assert.equal(observation.tag, "DIALOG");
    assert.equal(observation.parent, "BODY");
    assert.equal(observation.open, true);
    assert.equal(observation.modal, true);
    assert.equal(observation.hiddenAncestor, false);
    assert.equal(observation.visible, true);
    assert.equal(observation.focusInside, true);
    await tab.playwright.locator("#profile-name-input").press("Escape");
    await tab.getAXState({emit:false});
    const closed = await tab.playwright.evaluate(() => ({
      open:document.getElementById("profile-edit-modal").open, focus:document.activeElement.id,
    }));
    assert.equal(closed.open, false);
    assert.equal(closed.focus, "open-profile-modal-btn");
    await tab.playwright.locator("#persona-switcher-bar > summary").click();
    await tab.getAXState({emit:false});
    observations.push(observation);
  }
  return observations;
}

export async function auditStressParameters(tab) {
  const origin = new URL(await tab.url()).origin;
  await openPage(tab, origin, "scenario-simulation");
  await tab.playwright.locator("#stress-sector-select").selectOption("CONSUMER_HEALTHCARE");
  await tab.getAXState({emit:false});
  const hiddenParameter = await tab.playwright.evaluate(() => ({
    current:document.getElementById("stress-single-change").value,
    technology:document.getElementById("stress-technology").value,
    noteVisible:!document.getElementById("stress-active-shocks").hidden,
    note:document.getElementById("stress-active-shocks").textContent,
  }));
  assert.equal(hiddenParameter.current, "0");
  assert.equal(hiddenParameter.technology, "-20");
  assert.equal(hiddenParameter.noteVisible, true);
  assert.match(hiddenParameter.note, /科技/);
  await tab.playwright.locator("#stress-sector-select").selectOption("TECHNOLOGY");
  await tab.playwright.locator("#stress-single-change").press("Home");
  await tab.playwright.locator("#stress-single-change").press("ArrowRight");
  await tab.getAXState({emit:false});
  assert.equal(await tab.playwright.evaluate(() => document.getElementById("stress-technology").value), "-29.5");
  await tab.playwright.locator("#stress-multiple-sectors > summary").click();
  await tab.getAXState({emit:false});
  assert.equal(await tab.playwright.evaluate(() => document.getElementById("stress-single-fields").hidden), true);
  await tab.playwright.locator("#stress-consumer").press("End");
  await tab.getAXState({emit:false});
  await tab.playwright.locator("#stress-multiple-sectors > summary").click();
  await tab.getAXState({emit:false});
  await tab.playwright.locator("#stress-sector-select").selectOption("CONSUMER_HEALTHCARE");
  await tab.getAXState({emit:false});
  const observation = await tab.playwright.evaluate(() => ({
    single:document.getElementById("stress-single-change").value,
    technology:document.getElementById("stress-technology").value,
    consumer:document.getElementById("stress-consumer").value,
    note:document.getElementById("stress-active-shocks").textContent,
    noteVisible:!document.getElementById("stress-active-shocks").hidden,
    singleVisible:!document.getElementById("stress-single-fields").hidden,
    resultEmpty:document.getElementById("custom-stress-result").children.length === 0,
    status:document.getElementById("custom-stress-status").textContent,
  }));
  assert.equal(observation.single, "30");
  assert.equal(observation.consumer, "30");
  assert.equal(observation.technology, "-29.5");
  assert.equal(observation.noteVisible, true);
  assert.equal(observation.singleVisible, true);
  assert.equal(observation.resultEmpty, true);
  assert.equal(observation.status, "待计算");
  return observation;
}

export async function auditUnavailableResearch(tab) {
  const origin = new URL(await tab.url()).origin;
  const observations = [];
  for (const page of ["stock-research", "fund-research", "convertible-bond-research"]) {
    await openPage(tab, origin, page);
    await tab.playwright.locator(`#run-${page}`).click();
    await tab.getAXState({emit:false});
    await tab.playwright.locator(`#${page}-error`).waitFor({state:"visible", timeoutMs:15000});
    const message = await tab.playwright.locator(`#${page}-error`).innerText();
    const status = await tab.playwright.locator(`#${page}-status`).innerText();
    assert.equal(await tab.playwright.locator(`#run-${page}`).isEnabled(), true);
    assert.equal(status, "未运行");
    assert.match(message, /[\u3400-\u9fff]/);
    assert.ok(message.length > 0);
    observations.push({page, status, message});
  }
  return observations;
}

// 页面已读取正常账户的画像与持仓；在独立测试服务中断期间执行。
export async function auditAnalysisFailures(tab) {
  const origin = new URL(await tab.url()).origin;
  const observations = [];
  for (const [page, action, statusId, expectedStatus] of [
    ["portfolio-optimization", "run-portfolio-optimization", "portfolio-optimization-status", "未运行"],
    ["advanced-explainability", "run-explainability", "explainability-status-chip", "计算失败"],
    ["portfolio-rebalancing", "run-rebalancing", "rebalancing-status-chip", "未生成"],
  ]) {
    await openPage(tab, origin, page);
    await tab.playwright.locator(`#${action}`).click();
    await tab.getAXState({emit:false});
    await tab.playwright.locator(`#${page}-error`).waitFor({state:"visible", timeoutMs:15000});
    const message = await tab.playwright.locator(`#${page}-error`).innerText();
    const status = await tab.playwright.locator(`#${statusId}`).innerText();
    assert.equal(status, expectedStatus);
    assert.equal(await tab.playwright.locator(`#${action}`).isEnabled(), true);
    assert.match(message, /[\u3400-\u9fff]/);
    observations.push({page, status, message});
  }
  return observations;
}

const contextActions = {
  "portfolio-optimization": ["run-portfolio-optimization", "portfolio-optimization-status"],
  "advanced-explainability": ["run-explainability", "explainability-status-chip"],
  "portfolio-rebalancing": ["run-rebalancing", "rebalancing-status-chip"],
};

// 独立服务暂停期间启动真实请求，再通过账户设置变更页面上下文。
export async function changeContextDuringAnalysis(tab, page) {
  const origin = new URL(await tab.url()).origin;
  await openPage(tab, origin, page);
  const [action, statusId] = contextActions[page];
  await tab.playwright.locator(`#${action}`).click();
  await tab.getAXState({emit:false});
  assert.equal(await tab.playwright.locator(`#${action}`).isEnabled(), false);
  await tab.playwright.locator("#persona-switcher-bar > summary").click();
  await tab.getAXState({emit:false});
  await tab.playwright.locator("#open-profile-modal-btn").click();
  await tab.getAXState({emit:false});
  await tab.playwright.locator("#btn-save-profile").click();
  await tab.getAXState({emit:false});
  assert.equal(await tab.playwright.locator(`#${statusId}`).innerText(), "待运行");
  await tab.playwright.locator("#profile-edit-modal").waitFor({state:"hidden", timeoutMs:15000});
  await tab.playwright.locator("#persona-switcher-bar > summary").click();
  await tab.getAXState({emit:false});
}

// 恢复真实服务后确认旧请求已经退出，当前页面继续等待新的分析。
export async function auditCancelledAnalysis(tab, page) {
  const [action, statusId] = contextActions[page];
  await tab.playwright.locator(`#${action}:not([disabled])`).waitFor({state:"visible", timeoutMs:15000});
  await tab.getAXState({emit:false});
  const status = await tab.playwright.locator(`#${statusId}`).innerText();
  const errorVisible = await tab.playwright.locator(`#${page}-error`).isVisible();
  assert.equal(status, "待运行");
  assert.equal(errorVisible, false);
  return {page, status, errorVisible};
}
