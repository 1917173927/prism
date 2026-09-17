from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "app" / "api" / "static"


def test_product_brand_is_consistent_across_entry_pages() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    login = (STATIC / "login.html").read_text(encoding="utf-8")
    logo = (STATIC / "wencai-zhitou-logo.svg").read_text(encoding="utf-8")

    assert "<title>问财智投 · 决策工作台</title>" in markup
    assert '<div class="brand" aria-label="问财智投">' in markup
    assert '<strong>问财智投</strong>' in markup
    assert 'href="/static/wencai-zhitou-logo.svg"' in markup
    assert "<title>问财智投 · 账户登录</title>" in login
    assert "进入问财智投" in login
    assert "对话气泡和上升走势" in logo


def test_primary_navigation_is_chinese_and_has_initial_selection() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")

    expected_links = {
        "#overview": "总览",
        "#advisor": "投顾查询",
        "#portfolio": "持仓",
        "#context-memory": "上下文记忆",
        "#portfolio-optimization": "组合优化",
        "#research-tracks": "研究轨道",
        "#stock-research": "个股研究",
        "#fund-research": "ETF / 基金研究",
        "#convertible-bond-research": "可转债研究",
        "#evidence": "证据链",
        "#profile": "风险画像",
    }
    for href, label in expected_links.items():
        assert f'href="{href}"' in markup
        assert label in markup
    assert '<nav class="nav-list" aria-label="工作区分区">' in markup
    assert 'href="#copilot" id="nav-copilot" aria-current="location"' in markup

    forbidden_core_labels = (
        "Decision workspace",
        "Evidence chain explorer",
        "Context Memory",
        "Research Tracks",
        "Risk Profile 确认失败",
        "AUDIT FIRST",
        "INVESTMENT RESEARCH WORKSPACE",
    )
    for label in forbidden_core_labels:
        assert label not in markup


def test_navigation_renderer_syncs_hash_selection_and_safe_localization() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    for token in (
        "function syncNavigation(",
        'item.classList.toggle("active", selected)',
        'item.setAttribute("aria-current", "location")',
        'window.addEventListener("hashchange"',
        'item.addEventListener("click", () => syncNavigation(item.hash.slice(1)))',
        "function displayScenarioLabel(",
        "function displayDescription(",
        "function displayMethodology(",
        "操作未完成，请检查输入或稍后重试。",
        '"synthetic fixture omitted a required field": "合成样例缺少必需字段"',
        '"exposure or concentration input is not complete": "暴露或集中度输入不完整"',
        '"Review technology exposure through Macro, Industry, Stock and ETF/Fund tracks.":',
        'DISPLAY_VALUE_LABELS[rendered.toUpperCase()]',
        'option.value = scenario.scenario_id || ""',
        'select.value = known ? previous : options[0].scenario_id',
    ):
        assert token in script

    for label in (
        "Evidence chain explorer",
        "Decision workspace",
        "Current owner",
        "Risk Profile 确认失败",
        "Profile 提案验证失败",
        "Portfolio 校验失败",
        "需复核的安全问题（issue）",
    ):
        assert label not in script


def test_authenticated_ui_removes_mock_chat_and_marks_unready_tools() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    login = (STATIC / "login.html").read_text(encoding="utf-8")

    assert 'accountAccessEnabled = context.enabled === true' in script
    assert 'querySelector(\'option[value="MOCK"]\')' in script
    assert 'formalUnavailable ? "工具数据 · 未就绪"' in script
    assert "正式账户不允许切换至 Mock 数据" in script
    assert 'connectionStatus: "NONE"' in script
    assert 'llmConfig.connectionStatus = settings.connection_verified ? "CONNECTED" : settings.is_configured ? "SAVED" : "NONE"' in script
    assert 'llmConfig.connectionStatus = "CONNECTED"' in script
    assert 'llmConfig.connectionStatus = "FAILED"' in script
    assert "已保存" in script
    assert "连接测试通过" in script
    assert "连接失败" in script
    assert 'document.querySelector(\'#username\')' in login
    assert 'document.querySelector(\'#password\')' in login
    assert 'document.querySelector(\'#confirmation\')' in login
