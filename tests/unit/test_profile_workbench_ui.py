from pathlib import Path


ROOT = Path(__file__).parents[2]
INDEX = (ROOT / "app/api/static/index.html").read_text(encoding="utf-8")
APP = (ROOT / "app/api/static/app.js").read_text(encoding="utf-8")


def test_regular_workbench_has_five_primary_pages_and_profile_questionnaire() -> None:
    for href in ("#copilot", "#overview", "#stock-research", "#recommendation-history", "#profile"):
        assert href in INDEX
    assert 'id="questionnaire-form"' in INDEX
    assert 'id="questionnaire-summary-content"' not in INDEX
    assert 'id="profile-risk-select"' not in INDEX
    assert 'AI 信任度与解释偏好' in INDEX


def test_first_visit_is_guarded_by_the_formal_questionnaire() -> None:
    assert '<body class="questionnaire-pending prism-ui-v2">' in INDEX
    assert 'id="questionnaire-entry-loading"' in INDEX
    assert "function applyQuestionnaireGate(" in APP
    assert 'questionnaireGate: "PENDING"' in APP


def test_profile_summary_precedes_questionnaire_in_dom_order() -> None:
    assert INDEX.index('class="profile-summary-section"') < INDEX.index('id="questionnaire-form"')


def test_home_is_agent_first_and_keeps_secondary_profile_context_quiet() -> None:
    copilot_start = INDEX.index('<section class="copilot-section" id="copilot"')
    copilot_end = INDEX.index('id="portfolio-modal"', copilot_start)
    copilot_markup = INDEX[copilot_start:copilot_end]

    assert 'id="agent-home-grid"' in copilot_markup
    assert 'id="agent-conversation"' in copilot_markup
    assert 'id="agent-profile-rail"' in copilot_markup
    assert 'id="start-conversation-profile-update"' in copilot_markup
    assert 'id="copilot-chat-panel"' in copilot_markup
    assert 'id="copilot-natural-input"' in copilot_markup
    assert 'id="task-card-health"' not in copilot_markup
    assert '问卷完成度' not in copilot_markup


def test_conversation_can_collect_and_confirm_profile_context() -> None:
    for token in (
        "function startConversationProfileUpdate(",
        "function renderConversationProfileQuestion(",
        "function confirmConversationProfileUpdate(",
        'prism_conversation_profile_v1',
    ):
        assert token in APP

    confirm_start = APP.index("function confirmConversationProfileUpdate(")
    confirm_end = APP.index("function loadCopilotChatHistory(", confirm_start)
    confirm_body = APP[confirm_start:confirm_end]
    assert "renderBehaviorProfile(state.behaviorProfile);" in confirm_body


def test_system_governance_is_developer_only_and_evaluation_starts_unrun() -> None:
    assert 'class="nav-section-expert collapsed dev-only"' in INDEX
    assert 'id="evaluation-pass-chip">尚未运行' in INDEX
    assert '100.00% 通过' not in INDEX


def test_navigation_keeps_old_hashes_and_profile_is_owner_scoped() -> None:
    assert 'href="#portfolio"' in INDEX
    assert 'portfolio-optimization' in INDEX
    assert 'questionnaire-template' in APP
    assert 'profile/summary' in APP
    assert 'X-Owner-ID' in APP


def test_profile_result_renders_radar_strategy_and_allocation_without_trade_gate() -> None:
    result_start = APP.index("function renderProfileSummary(")
    result_end = APP.index("async function loadQuestionnaireTemplate(", result_start)
    result = APP[result_start:result_end]
    assert "renderProfileRadar(presentation)" in result
    assert "presentation.tags" in result
    assert "presentation.service_strategy" in result
    assert "presentation.asset_allocation" in result
    assert "交易记录参考" not in result
    assert "还缺哪些数据" not in result


def test_holdings_page_has_kpis_diagnosis_and_formal_report_export() -> None:
    assert 'id="overview-position-count"' in INDEX
    assert 'id="portfolio-report-card"' in INDEX
    assert 'id="portfolio-diagnosis-drawer"' in INDEX
    assert 'id="portfolio-report-concentration-summary"' in INDEX
    assert 'id="portfolio-report-protection-summary"' in INDEX
    for token in (
        "当日盈亏",
        "累计盈亏",
        "持仓数量",
        "/api/v1/advisor/portfolio/report",
        "openPortfolioDiagnosis",
        "buildPortfolioReportHtml",
        "Prism-持仓正式报告.html",
        "查看诊断",
        "集中度与浮亏",
        "底仓保护与配置参考",
    ):
        assert token in APP or token in INDEX
