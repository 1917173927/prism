/* Standalone presentation: immutable local snapshots, no provider or model calls. */
(() => {
  "use strict";
  const data = window.PRISM_DEMO_DATA;
  if (!data) {
    document.body.textContent = "演示资料未加载，请刷新页面或重新启动演示。";
    return;
  }
  function freezeSnapshot(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
      Object.values(value).forEach(freezeSnapshot);
      Object.freeze(value);
    }
    return value;
  }
  freezeSnapshot(data);
  const pages = [...document.querySelectorAll("[data-page]")];
  const pageIds = new Set(pages.map(page => page.dataset.page));
  const one = selector => document.querySelector(selector);
  const all = selector => [...document.querySelectorAll(selector)];
  const statusLabels = Object.freeze({
    PASS: "符合参考范围", CALCULATED: "已计算", VERIFIED: "样例可用", OVERBOUND: "超过参考上限",
    UNAVAILABLE: "暂无法分析", BLOCKED: "已阻止", FAILED: "未完成", PENDING_REVIEW: "待核对",
    DEMO: "演示资料", WAITING: "待开始", CANCELED: "已取消", RUNNING: "进行中", COMPLETED: "已完成",
  });
  function statusLabel(value) {
    return statusLabels[value] || (/^[A-Z][A-Z0-9_ -]+$/.test(String(value)) ? "状态待确认" : String(value));
  }
  function reasonLabel(value) {
    const labels = {
      INSUFFICIENT_RETURNS: "历史收益数据不足，暂无法判断波动状态。",
      DEGENERATE_TRAINING_RETURNS: "历史收益没有足够变化，暂无法区分波动状态。",
      RESEARCH_DEPENDENCY_UNAVAILABLE: "计算服务暂不可用，请稍后重试。",
      MODEL_NOT_CONVERGED: "当前样本未形成稳定结果，暂不判断波动状态。",
      DEGENERATE_FITTED_STATES: "当前样本无法区分两种波动状态。",
      NUMERICAL_FILTER_FAILURE: "当前数据未形成有效的状态概率。",
      INSUFFICIENT_ASSETS: "至少需要两个资产的历史收益资料。",
      INSUFFICIENT_ALIGNED_RETURNS: "资产共同交易日的收益资料不足。",
      ZERO_VARIANCE_ASSET: "部分资产收益没有变化，暂无法分析联动。",
      NON_PSD_ESTIMATE: "资产联动结果未通过数值检查，暂不展示。",
    };
    return labels[value] || (/^[A-Z][A-Z0-9_]+$/.test(String(value)) ? "资料或计算条件未满足，请检查输入资料。" : String(value));
  }
  const state = {
    page: null, scroll: new Map(), instrument: "shanghai", period: "daily",
    profileTab: "summary", skillCategory: "*", selectedSkills: new Set(),
    liveStatus: "READY", liveStep: -1, timer: null, capture: false,
  };
  const chartResources = [];
  let chartFrame = null;
  let citationTrigger = null;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function status(text, tone = "neutral") {
    return element("span", `status ${tone}`, statusLabel(text));
  }
  function button(text, attributes = {}, className = "button secondary") {
    const node = element("button", className, text);
    node.type = "button";
    Object.entries(attributes).forEach(([key, value]) => { node.dataset[key] = value; });
    return node;
  }
  function fillList(name, items, render) {
    const container = one(`[data-list="${name}"]`);
    if (container) container.replaceChildren(...items.map(render));
  }
  function valueAt(path) {
    if (path.startsWith("market.active.")) {
      return data.market.instruments[state.instrument]?.[path.slice("market.active.".length)];
    }
    return path.split(".").reduce((value, part) => value?.[part], data);
  }
  function bindValues() {
    all("[data-value]").forEach(node => {
      const value = valueAt(node.dataset.value);
      node.textContent = value === null || value === undefined ? "未提供" : node.classList.contains("status") ? statusLabel(value) : String(value);
      if (node.classList.contains("status") && /(?:\.status|_status)$/.test(node.dataset.value)) {
        const pass = ["PASS", "CALCULATED", "VERIFIED"].includes(value);
        const warning = ["UNAVAILABLE", "BLOCKED", "OVERBOUND", "FAILED", "PENDING_REVIEW"].includes(value);
        node.classList.toggle("pass", pass);
        node.classList.toggle("warning", warning);
        node.classList.toggle("neutral", !pass && !warning);
      }
    });
  }
  function renderTable(name, rows, fields) {
    const container = one(`[data-table="${name}"]`);
    if (!container) return;
    container.replaceChildren(...rows.map(row => {
      const tr = element("tr");
      fields.forEach(field => {
        const td = element("td", field === "name" ? "title" : "number", row[field] ?? "未提供");
        if (["return_pct", "pnl"].includes(field) && row.tone) td.classList.add(row.tone);
        tr.append(td);
      });
      return tr;
    }));
  }
  function metricCard(item, className = "metric-item") {
    const card = element("div", className);
    card.append(element("span", "label", item.label), element("strong", "value number", item.value));
    if (item.unit) card.append(element("span", "unit", item.unit));
    if (item.note) card.append(element("p", "muted", item.note));
    return card;
  }
  function renderStatic() {
    bindValues();
    renderTable("holdings", data.holdings || [], ["name", "code", "quantity", "price_cny", "market_value_cny", "weight_pct", "return_pct"]);
    renderTable("trades", data.trading.records || [], ["date", "name", "side", "quantity", "price", "pnl"]);
    fillList("allocation", data.allocation || [], item => {
      const row = element("div", "allocation-row");
      const track = element("div", "allocation-track");
      const bar = element("span", "allocation-bar");
      // This is a frozen display percentage, not a calculated portfolio weight.
      bar.style.width = `${item.value}%`;
      bar.style.backgroundColor = item.color;
      track.append(bar);
      row.append(element("span", "label", item.name), track, element("strong", "number", item.label));
      return row;
    });
    fillList("market-sectors", data.market.sectors || [], item => {
      const row = element("div", "sector-row");
      row.append(element("span", "title", item.name), element("strong", `number ${item.tone || ""}`, item.return_pct), element("span", "muted", item.coverage));
      return row;
    });
    fillList("trading-metrics", data.trading.metrics || [], item => metricCard(item, "kpi-card"));
    fillList("trading-style", data.trading.style || [], item => metricCard(item, "timeline-item"));
    fillList("profile-dimensions", data.profile.dimensions || [], item => {
      const row = element("div", "dimension-row");
      const track = element("div", "allocation-track");
      const bar = element("span", "allocation-bar");
      bar.style.width = `${item.value}%`;
      track.append(bar);
      row.append(element("span", "label", item.label), track, element("strong", "number", item.value));
      return row;
    });
    fillList("factor-missing", data.algorithms.factors.missing || [], item => element("li", "gap-item", item));
    all("[data-algorithm-reason]").forEach(node => {
      const reason = data.algorithms[node.dataset.algorithmReason]?.reason;
      node.hidden = !reason;
      node.textContent = reason ? reasonLabel(reason) : "";
    });
    const covariance = data.algorithms.covariance;
    const matrix = one('[data-table="covariance"]');
    if (matrix) matrix.replaceChildren(...(covariance.matrix_display || covariance.matrix).map((values, index) => {
      const tr = element("tr");
      const label = element("th", "label", covariance.labels[index]);
      label.scope = "row";
      tr.append(label, ...values.map(value => element("td", "number", value)));
      return tr;
    }));
    fillList("copilot-presets", data.copilot.presets || [], preset => button(preset.query, {copilotPreset: preset.id}, "prompt-chip"));
    renderMarket();
    renderSkills();
    renderDocuments();
    renderLive();
    renderProfile();
    renderAnswer(data.copilot.presets?.[0]);
  }

  function renderMarket() {
    fillList("market-quotes", data.market.quotes || [], quote => {
      const card = button("", {marketInstrument: quote.id}, `quote-card ${state.instrument === quote.id ? "active" : ""}`);
      card.setAttribute("aria-pressed", String(state.instrument === quote.id));
      card.append(element("span", "label", quote.name), element("strong", "value number", quote.value), element("span", `number ${quote.tone || ""}`, quote.change_pct));
      return card;
    });
    all("[data-market-instrument]").forEach(node => {
      const active = node.dataset.marketInstrument === state.instrument;
      node.classList.toggle("active", active);
      node.setAttribute("aria-pressed", String(active));
    });
    all("[data-market-period]").forEach(node => {
      const active = node.dataset.marketPeriod === state.period;
      node.classList.toggle("active", active);
      node.setAttribute("aria-pressed", String(active));
    });
    const title = one("#market-chart-title");
    if (title) title.textContent = data.market.instruments[state.instrument].name;
    fillList("market-metrics", data.market.instruments[state.instrument].metrics || [], item => metricCard(item));
    bindValues();
  }
  function renderSkills() {
    const query = one('[data-search="skills"]')?.value.trim().toLowerCase() || "";
    const skills = (data.skills || []).filter(skill =>
      (state.skillCategory === "*" || skill.category === state.skillCategory) &&
      `${skill.name} ${skill.description} ${skill.category}`.toLowerCase().includes(query));
    fillList("skills", skills, skill => {
      const card = element("article", "skill-card");
      const heading = element("div", "card-heading");
      heading.append(element("h3", "title", skill.name), status(skill.status, "pass"));
      card.append(heading, element("p", "muted", skill.description));
      const meta = element("div", "skill-meta");
      meta.append(element("span", "muted", skill.category), element("span", "muted", skill.source));
      const selected = state.selectedSkills.has(skill.id);
      const toggle = button(selected ? "已选用" : "选用工具", {skillToggle: skill.id}, selected ? "button selected" : "button secondary");
      toggle.setAttribute("aria-pressed", String(selected));
      card.append(meta, toggle);
      return card;
    });
    all("[data-skill-category]").forEach(node => {
      const active = node.dataset.skillCategory === state.skillCategory;
      node.classList.toggle("active", active);
      node.setAttribute("aria-pressed", String(active));
    });
    const counter = one("[data-skill-count]");
    if (counter) counter.textContent = `${skills.length} 项演示工具 · 已选 ${state.selectedSkills.size} 项`;
    if (!skills.length) fillList("skills", ["演示工具中没有匹配项目。"], text => element("p", "empty-state", text));
    const selected = data.skills.filter(skill => state.selectedSkills.has(skill.id));
    fillList("tools", selected, skill => {
      const row = element("div", "tool-row");
      row.append(element("span", "title", skill.name), status("DEMO"));
      return row;
    });
    if (!selected.length) fillList("tools", ["尚未选用研究工具"], text => element("p", "muted", text));
  }
  function renderDocuments() {
    const query = one('[data-search="knowledge"]')?.value.trim().toLowerCase() || "";
    const terms = query.split(/\s+/).filter(Boolean);
    const documents = (data.documents || []).filter(doc => {
      const haystack = [doc.title, doc.subject, doc.period, ...(doc.keywords || [])].join(" ").toLowerCase();
      return terms.every(term => haystack.includes(term));
    });
    fillList("documents", documents, doc => {
      const row = element("article", "document-row");
      const content = element("div", "document-content");
      const heading = element("div", "card-heading");
      heading.append(element("h3", "title", doc.title), status(doc.availability));
      content.append(heading, element("p", "muted", `${doc.type} · ${doc.subject} · ${doc.period}`), element("p", "excerpt", doc.excerpt));
      const footer = element("div", "document-meta");
      footer.append(element("span", "muted", `${doc.source} · ${doc.published_at}`), button("查看引用", {citation: doc.id}, "button text-button"));
      content.append(footer);
      row.append(content);
      return row;
    });
    if (!documents.length) fillList("documents", ["固定演示资料中未找到匹配内容。此操作不会访问网站或模型。"], text => element("p", "empty-state", text));
    const counter = one("[data-knowledge-count]");
    if (counter) counter.textContent = `${documents.length} 篇演示资料`;
  }
  function renderAnswer(preset, question) {
    fillList("copilot", [preset || null], item => {
      const answer = element("article", "answer-block");
      const heading = element("div", "card-heading");
      heading.append(element("h3", "title", item?.title || "演示样例未覆盖此问题"), status("DEMO"));
      answer.append(heading);
      if (question) answer.append(element("p", "user-question", question));
      answer.append(element("p", "answer-text", item?.text || "此页面只展示固定样例，未调用模型、行情服务或检索接口。请使用上方示例问题查看演示结果。"));
      if (item?.claims?.length) {
        const claims = element("ul", "claim-list");
        item.claims.forEach(claim => claims.append(element("li", "claim-item", typeof claim === "string" ? claim : claim.text)));
        answer.append(claims);
      }
      if (item?.document_ids?.length) {
        const citations = element("div", "citation-links");
        item.document_ids.forEach(id => {
          const doc = data.documents.find(document => document.id === id);
          if (doc) citations.append(button(doc.title, {citation: id}, "citation-link"));
        });
        answer.append(citations);
      }
      return answer;
    });
  }
  function closeCitation({restoreFocus = true} = {}) {
    const drawer = one("#citation-drawer");
    if (drawer) drawer.hidden = true;
    document.body.classList.remove("drawer-open");
    if (restoreFocus && citationTrigger?.isConnected) citationTrigger.focus({preventScroll: true});
    citationTrigger = null;
  }
  function openCitation(id, trigger) {
    const doc = data.documents.find(item => item.id === id);
    const drawer = one("#citation-drawer");
    if (!doc || !drawer) return;
    citationTrigger = trigger;
    const values = {title: doc.title, excerpt: doc.excerpt, source: doc.source, meta: `${doc.subject} · ${doc.period} · ${doc.published_at} · 演示资料`};
    Object.entries(values).forEach(([key, value]) => {
      const node = one(`[data-citation="${key}"]`);
      if (node) node.textContent = value;
    });
    drawer.hidden = false;
    document.body.classList.add("drawer-open");
    one('[data-action="citation-close"]')?.focus({preventScroll: true});
  }
  function renderProfile() {
    all("[data-profile-tab]").forEach(node => {
      const active = node.dataset.profileTab === state.profileTab;
      node.classList.toggle("active", active);
      node.setAttribute("aria-selected", String(active));
      node.tabIndex = active ? 0 : -1;
    });
    all("[data-profile-panel]").forEach(node => { node.hidden = node.dataset.profilePanel !== state.profileTab; });
  }

  function renderLive() {
    const labels = {READY: "待开始", RUNNING: "演示进行中", COMPLETED: "演示已完成", CANCELED: "已取消"};
    const label = one("[data-live-status]");
    if (label) label.textContent = labels[state.liveStatus];
    const timing = one("[data-live-timing]");
    const timingLabels = {READY: "待启动", RUNNING: "本地步骤播放", COMPLETED: "固定演示时间线", CANCELED: "已取消"};
    if (timing) timing.textContent = timingLabels[state.liveStatus];
    fillList("live-steps", data.live.steps || [], (step, index) => {
      const row = element("li", "run-step");
      const complete = state.liveStatus === "COMPLETED" || index < state.liveStep;
      const active = state.liveStatus === "RUNNING" && index === state.liveStep;
      const tone = complete ? "pass" : active ? "warning" : "neutral";
      row.classList.toggle("active", active);
      row.append(element("span", "step-number", String(index + 1).padStart(2, "0")), element("div", "step-content"));
      row.lastElementChild.append(element("strong", "title", step.title), element("p", "muted", step.detail));
      row.append(status(complete ? "COMPLETED" : active ? "RUNNING" : state.liveStatus === "CANCELED" ? "CANCELED" : "WAITING", tone));
      return row;
    });
    fillList("live-result", state.liveStatus === "COMPLETED" ? data.live.result : [], item => metricCard(item, "result-card"));
    const start = one('[data-action="live-start"]');
    const cancel = one('[data-action="live-cancel"]');
    if (start) start.disabled = state.liveStatus === "RUNNING";
    if (cancel) cancel.disabled = state.liveStatus !== "RUNNING";
  }
  function cancelLive() {
    if (state.timer !== null) window.clearTimeout(state.timer);
    state.timer = null;
    if (state.liveStatus === "RUNNING") state.liveStatus = "CANCELED";
    renderLive();
  }
  function advanceLive() {
    state.timer = null;
    if (state.page !== "live-research" || state.liveStatus !== "RUNNING") return;
    state.liveStep += 1;
    if (state.liveStep >= data.live.steps.length) {
      state.liveStatus = "COMPLETED";
      renderLive();
      return;
    }
    renderLive();
    state.timer = window.setTimeout(advanceLive, data.live.steps[state.liveStep].duration_ms);
  }
  function startLive() {
    if (state.page !== "live-research" || state.liveStatus === "RUNNING") return;
    state.liveStatus = "RUNNING";
    state.liveStep = -1;
    advanceLive();
  }

  function destroyCharts() {
    if (chartFrame !== null) window.cancelAnimationFrame(chartFrame);
    chartFrame = null;
    chartResources.splice(0).forEach(resource => {
      const {chart, observer} = resource;
      resource.disposed = true;
      observer?.disconnect();
      chart.remove();
    });
  }
  function drawCharts() {
    destroyCharts();
    const section = pages.find(page => page.dataset.page === state.page);
    if (!section) return;
    section.querySelectorAll("[data-chart]").forEach(container => {
      const type = container.dataset.chart;
      if (!["market", "portfolio", "regime"].includes(type)) return;
      const library = window.LightweightCharts;
      container.replaceChildren();
      if (!library || container.clientWidth <= 0) {
        container.append(element("p", "empty-state", "图表暂无法显示，请刷新页面后重试。"));
        return;
      }
      if (type === "regime" && data.algorithms.regime.status !== "CALCULATED") {
        container.append(element("p", "empty-state", "当前资料未满足波动分析条件。"));
        return;
      }
      const css = window.getComputedStyle?.(document.body);
      const color = (name, fallback) => css?.getPropertyValue(name).trim() || fallback;
      const brand = color("--brand", "#e86f00");
      const marketUp = color("--market-up", "#d95a5a");
      const marketDown = color("--market-down", "#14836e");
      const chart = library.createChart(container, {
        width: container.clientWidth, height: container.clientHeight || 240,
        layout: {background: {type: "solid", color: "#ffffff"}, textColor: "#758098", fontFamily: "Inter, system-ui, sans-serif", fontSize: 11},
        grid: {vertLines: {visible: false}, horzLines: {color: "#edf0f6"}},
        rightPriceScale: {borderVisible: false, ...(type === "regime" ? {scaleMargins: {top: .08, bottom: .06}} : {})}, timeScale: {borderVisible: false, rightOffset: 2},
        handleScroll: false, handleScale: false,
      });
      if (type === "market") {
        const instrument = data.market.instruments[state.instrument];
        const candles = chart.addSeries(library.CandlestickSeries, {upColor: marketUp, downColor: marketDown, borderVisible: false, wickUpColor: marketUp, wickDownColor: marketDown});
        candles.setData(state.period === "monthly" ? instrument.monthly : instrument.candles);
        if (state.period === "daily" && instrument.volume?.length) {
          const volume = chart.addSeries(library.HistogramSeries, {priceFormat: {type: "volume"}, priceScaleId: "volume"}, 1);
          volume.setData(instrument.volume);
          chart.panes()[0]?.setHeight(240);
          chart.panes()[1]?.setHeight(66);
        }
      } else {
        const series = chart.addSeries(library.AreaSeries, {lineColor: brand, topColor: color("--chart-area-top", "#e86f0030"), bottomColor: color("--chart-area-bottom", "#e86f0003"), lineWidth: 2, priceLineVisible: false, lastValueVisible: false, ...(type === "regime" ? {priceFormat: {type: "percent", precision: 1, minMove: .1}, autoscaleInfoProvider: () => ({priceRange: {minValue: 0, maxValue: 100}})} : {})});
        series.setData(type === "portfolio" ? data.trend : data.algorithms.regime.display_series);
      }
      chart.timeScale().fitContent();
      const resource = {chart, observer: null, disposed: false};
      if (typeof window.ResizeObserver === "function") {
        resource.observer = new window.ResizeObserver(entries => {
          const {width, height} = entries[0]?.contentRect || {};
          if (!resource.disposed && width > 0) chart.applyOptions(height > 0 ? {width, height} : {width});
        });
        resource.observer.observe(container);
      }
      chartResources.push(resource);
    });
  }
  function scheduleCharts() {
    destroyCharts();
    chartFrame = window.requestAnimationFrame(() => {
      chartFrame = null;
      drawCharts();
    });
  }
  function navigate() {
    const requested = window.location.hash.slice(1);
    const next = pageIds.has(requested) ? requested : "copilot";
    if (next !== requested) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${next}`);
    if (state.page === next) return;
    if (state.page) state.scroll.set(state.page, window.scrollY);
    cancelLive();
    closeCitation({restoreFocus: false});
    state.page = next;
    pages.forEach(page => { page.hidden = page.dataset.page !== next; });
    all("[data-nav]").forEach(link => {
      const active = link.dataset.nav === next;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    document.body.classList.remove("nav-open");
    one('[data-action="menu-toggle"]')?.setAttribute("aria-expanded", "false");
    const heading = one(`[data-page-title="${next}"]`) || pages.find(page => page.dataset.page === next)?.querySelector("h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({preventScroll: true});
      document.title = `${heading.textContent} · 问财智投产品演示`;
      all("[data-page-name]").forEach(node => { node.textContent = heading.textContent; });
    }
    all("[data-page-menu]").forEach(node => { node.value = next; });
    window.scrollTo({top: state.scroll.get(next) || 0, behavior: "instant"});
    scheduleCharts();
  }
  function setCapture(active) {
    state.capture = active;
    document.body.classList.toggle("capture-mode", active);
    all('[data-action="capture-toggle"]').forEach(toggle => {
      toggle.setAttribute("aria-pressed", String(active));
      const label = active ? "退出截图模式" : "截图模式";
      toggle.setAttribute("aria-label", label);
      toggle.title = label;
      if (!toggle.classList.contains("icon-button")) toggle.textContent = label;
    });
    const url = new URL(window.location.href);
    if (active) url.searchParams.set("capture", "1");
    else url.searchParams.delete("capture");
    window.history.replaceState(null, "", url);
    scheduleCharts();
  }
  function reset() {
    cancelLive();
    closeCitation();
    state.selectedSkills = new Set(data.skills.filter(skill => skill.selected).map(skill => skill.id));
    state.skillCategory = "*";
    state.instrument = "shanghai";
    state.period = "daily";
    state.profileTab = "summary";
    state.liveStatus = "READY";
    state.liveStep = -1;
    state.scroll.clear();
    all("[data-search], [data-input]").forEach(input => { input.value = ""; });
    all("[data-preference]").forEach(input => { input.value = input.dataset.default || "standard"; });
    const output = one("[data-preference-output]");
    if (output) output.textContent = "标准解释 · 仅改变本次演示显示";
    renderStatic();
    window.scrollTo({top: 0, behavior: "instant"});
    if (window.location.hash !== "#copilot") window.location.hash = "copilot";
    else scheduleCharts();
  }
  document.addEventListener("click", event => {
    const target = event.target.closest("button, [data-action], [data-nav], a[href]");
    if (!target) return;
    if (target.dataset.nav || (target.tagName === "A" && target.getAttribute("href")?.startsWith("#"))) {
      document.body.classList.remove("nav-open");
      one('[data-action="menu-toggle"]')?.setAttribute("aria-expanded", "false");
    }
    if (target.dataset.copilotPreset) {
      const preset = data.copilot.presets.find(item => item.id === target.dataset.copilotPreset);
      if (preset) {
        const input = one('[data-input="copilot"]');
        if (input) input.value = preset.query;
        renderAnswer(preset, preset.query);
      }
    }
    if (target.dataset.skillToggle) {
      const id = target.dataset.skillToggle;
      if (data.skills.some(skill => skill.id === id)) {
        if (state.selectedSkills.has(id)) state.selectedSkills.delete(id);
        else state.selectedSkills.add(id);
        renderSkills();
        one(`[data-skill-toggle="${id}"]`)?.focus({preventScroll: true});
      }
    }
    if (target.dataset.skillCategory !== undefined) {
      state.skillCategory = target.dataset.skillCategory;
      renderSkills();
    }
    if (target.dataset.profileTab) {
      state.profileTab = target.dataset.profileTab;
      renderProfile();
    }
    if (target.dataset.marketInstrument && data.market.instruments[target.dataset.marketInstrument]) {
      state.instrument = target.dataset.marketInstrument;
      renderMarket();
      scheduleCharts();
    }
    if (["daily", "monthly"].includes(target.dataset.marketPeriod)) {
      state.period = target.dataset.marketPeriod;
      renderMarket();
      scheduleCharts();
    }
    if (target.dataset.citation) openCitation(target.dataset.citation, target);
    const actions = {
      "menu-toggle": () => {
        const open = document.body.classList.toggle("nav-open");
        target.setAttribute("aria-expanded", String(open));
      },
      "capture-toggle": () => setCapture(!state.capture),
      reset, "citation-close": () => closeCitation(), "live-start": startLive, "live-cancel": cancelLive,
    };
    actions[target.dataset.action]?.();
  });
  document.addEventListener("submit", event => {
    const form = event.target.closest("[data-form]");
    if (!form) return;
    event.preventDefault();
    if (form.dataset.form === "knowledge") renderDocuments();
    if (form.dataset.form === "copilot") {
      const input = one('[data-input="copilot"]');
      const query = input?.value.trim() || "";
      if (!query) return input?.focus();
      const preset = data.copilot.presets.find(item => item.query === query);
      renderAnswer(preset, query);
    }
  });
  document.addEventListener("input", event => {
    if (event.target.dataset.search === "skills") renderSkills();
    if (event.target.dataset.search === "knowledge") renderDocuments();
  });
  document.addEventListener("change", event => {
    if (event.target.dataset.pageMenu !== undefined && pageIds.has(event.target.value)) {
      window.location.hash = event.target.value;
    }
    if (event.target.dataset.preference === "detail") {
      const labels = {brief: "简洁解释", concise: "简洁解释", standard: "标准解释", detailed: "详细解释"};
      const output = one("[data-preference-output]");
      if (output) output.textContent = `${labels[event.target.value] || "标准解释"} · 仅改变本次演示显示`;
    }
  });
  document.addEventListener("keydown", event => {
    const drawer = one("#citation-drawer");
    if (event.target.matches("[data-profile-tab]") && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      const tabs = all("[data-profile-tab]");
      const index = tabs.indexOf(event.target);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      if (tabs[next]) {
        event.preventDefault();
        state.profileTab = tabs[next].dataset.profileTab;
        renderProfile();
        tabs[next].focus({preventScroll: true});
      }
    }
    if (event.key === "Escape") {
      if (drawer && !drawer.hidden) closeCitation();
      else if (state.capture) setCapture(false);
      document.body.classList.remove("nav-open");
      one('[data-action="menu-toggle"]')?.setAttribute("aria-expanded", "false");
    }
    if (event.key === "Tab" && drawer && !drawer.hidden) {
      const focusable = [...drawer.querySelectorAll('button, a[href], [tabindex="0"]')].filter(node => !node.disabled && !node.hidden);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  });
  window.addEventListener("hashchange", navigate);
  if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  window.addEventListener("pagehide", () => { cancelLive(); destroyCharts(); closeCitation({restoreFocus: false}); });
  window.addEventListener("pageshow", () => { if (state.page) scheduleCharts(); });
  state.selectedSkills = new Set(data.skills.filter(skill => skill.selected).map(skill => skill.id));
  renderStatic();
  navigate();
  setCapture(new URLSearchParams(window.location.search).get("capture") === "1");
})();
