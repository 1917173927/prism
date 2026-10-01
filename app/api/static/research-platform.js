/* Research results render server-calculated values; this module performs no financial calculations. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const METRIC_LABELS = Object.freeze({daily_return: "日收益率", momentum_20: "20 日动量", realized_volatility_20: "20 日实现波动", current_drawdown: "当前回撤", maximum_drawdown: "窗口最大回撤"});
  let metricData = null;
  let selectedMetric = "realized_volatility_20";
  let metricChart = null;
  let metricResize = null;
  let darkTheme = document.body.classList.contains("prism-theme-dark");

  function node(tag, text, className = "") {
    const result = document.createElement(tag);
    if (text != null) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  }
  function destroyMetricChart() {
    metricResize?.disconnect();
    metricResize = null;
    metricChart?.remove();
    metricChart = null;
  }
  function metricAvailable(metric) {
    return metric?.status === "CALCULATED" && metric.value != null && Number.isFinite(Number(metric.value));
  }
  function renderMetricChart() {
    const container = byId("research-metric-chart");
    const metadata = byId("research-metric-chart-meta");
    if (!container || !metadata) return;
    destroyMetricChart();
    container.replaceChildren();
    container.style.height = "auto";
    const metric = metricData?.research_metrics?.[selectedMetric];
    const points = metric?.series || [];
    metadata.textContent = metric ? `${METRIC_LABELS[selectedMetric]} · ${metric.unit || "单位未提供"} · ${metric.input_start || "起点缺失"} 至 ${metric.input_end || "终点缺失"} · ${metric.source || "来源未提供"} · ${metric.method_version || "方法版本未提供"}` : "";
    if (!metricAvailable(metric) || !points.length) {
      container.append(node("p", metric?.missing_reason || "尚无可展示的时间序列。", "empty-state"));
      return;
    }
    if (!window.LightweightCharts) { container.append(node("p", "行情图组件未能加载。")); return; }
    // Invalid series must remain unavailable instead of being repaired into invented observations.
    if (points.some((point, index) => point.value == null || !Number.isFinite(Number(point.value)) || !/^\d{4}-\d{2}-\d{2}$/.test(point.time) || (index > 0 && points[index - 1].time >= point.time))) {
      container.append(node("p", "时间序列未通过日期及数值校验。", "empty-state"));
      return;
    }
    const css = getComputedStyle(document.body);
    const color = name => css.getPropertyValue(name).trim();
    container.style.height = "280px";
    metricChart = window.LightweightCharts.createChart(container, {
      width: container.clientWidth, height: 280,
      layout: {background: {type: "solid", color: color("--surface")}, textColor: color("--text-secondary")},
      grid: {vertLines: {color: color("--border-subtle")}, horzLines: {color: color("--border-subtle")}},
      timeScale: {timeVisible: false, borderColor: color("--border")},
      rightPriceScale: {borderColor: color("--border")},
    });
    const chart = metricChart;
    const series = chart.addSeries(window.LightweightCharts.LineSeries, {color: color("--brand"), lineWidth: 2, priceFormat: {type: "price", precision: 4, minMove: .0001}});
    series.setData(points.map(point => ({time: point.time, value: Number(point.value)})));
    chart.timeScale().fitContent();
    metricResize = new ResizeObserver(entries => {
      const width = Math.floor(entries[0]?.contentRect.width || 0);
      if (width > 0 && metricChart === chart) { chart.applyOptions({width}); chart.timeScale().fitContent(); }
    });
    metricResize.observe(container);
  }
  function renderMetrics(detail = {}) {
    const cards = byId("research-metric-cards");
    const status = byId("research-metrics-status");
    if (!cards || !status) return;
    metricData = detail.data || null;
    cards.replaceChildren();
    if (!metricData) {
      status.textContent = detail.status === "LOADING" ? "正在读取" : "UNAVAILABLE";
      cards.append(node("p", detail.status === "LOADING" ? "正在读取新的指标输入；上一结果已失效。" : detail.message || "尚未取得研究指标。", "empty-state"));
      renderMetricChart();
      return;
    }
    const metrics = metricData.research_metrics || {};
    status.textContent = Object.values(metrics).some(metricAvailable) ? "CALCULATED" : "UNAVAILABLE";
    for (const [key, label] of Object.entries(METRIC_LABELS)) {
      const metric = metrics[key];
      const available = metricAvailable(metric);
      const card = node("article", null, "research-metric-card");
      const button = node("button");
      button.type = "button";
      button.dataset.researchMetric = key;
      button.setAttribute("aria-pressed", String(selectedMetric === key));
      button.append(node("span", label), node("strong", available ? `${Number(metric.value).toFixed(4)}${metric.unit || ""}` : "—"));
      button.addEventListener("click", () => {
        selectedMetric = key;
        cards.querySelectorAll("[data-research-metric]").forEach(item => item.setAttribute("aria-pressed", String(item.dataset.researchMetric === key)));
        renderMetricChart();
      });
      card.append(button, node("small", available ? `CALCULATED · 样本 ${metric.sample_count} · 日频` : `UNAVAILABLE · ${metric?.missing_reason || "后端未提供该指标"}`));
      const details = node("details");
      details.append(node("summary", "数据与方法"));
      const definition = node("dl");
      const fields = {
        "计算窗口": metric ? `${metric.input_start || "未提供"} 至 ${metric.input_end || "未提供"}` : "未提供",
        "来源": metric?.source || "未提供", "方法版本": metric?.method_version || "未提供",
        "参数": metric?.parameters ? JSON.stringify(metric.parameters) : "未提供",
        "输入快照": metric?.snapshot_id || metricData.input_snapshot_id || "未提供",
      };
      for (const [name, value] of Object.entries(fields)) definition.append(node("dt", name), node("dd", value));
      details.append(definition);
      card.append(details);
      cards.append(card);
    }
    renderMetricChart();
  }
  document.addEventListener("prism:market-analysis", event => renderMetrics(event.detail));
  const themeObserver = new MutationObserver(() => {
    const nextDark = document.body.classList.contains("prism-theme-dark");
    if (nextDark !== darkTheme) { darkTheme = nextDark; renderMetricChart(); }
  });
  themeObserver.observe(document.body, {attributes: true, attributeFilter: ["class"]});
  window.addEventListener("pagehide", () => { destroyMetricChart(); themeObserver.disconnect(); });
})();
