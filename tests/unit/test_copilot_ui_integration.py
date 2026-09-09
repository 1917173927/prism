from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "app" / "api" / "static"


def test_copilot_markup_structure() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")

    # Navigation structure
    assert 'id="nav-copilot"' in markup
    assert 'id="nav-expert-section"' in markup
    assert 'id="nav-expert-toggle"' in markup
    assert 'id="nav-expert-items"' in markup

    # Persona switcher
    assert 'id="persona-switcher-bar"' in markup
    assert 'data-persona="persona-zhang-r3"' in markup
    assert 'data-persona="persona-li-r2"' in markup
    assert 'data-persona="persona-wang-r4"' in markup

    # L1 Agent-first home elements
    for element_id in (
        "copilot",
        "agent-home-grid",
        "agent-conversation",
        "agent-profile-rail",
        "start-conversation-profile-update",
        "copilot-hero-avatar",
        "copilot-hero-name",
        "copilot-hero-tag",
        "copilot-hero-portfolio-tag",
        "copilot-hero-desc",
        "copilot-stat-aum",
        "copilot-stat-tech",
        "copilot-stat-budget",
        "copilot-stat-evidence",
        "copilot-natural-input",
        "copilot-submit-query",
        "copilot-quick-tags",
        "copilot-decision-output",
        "copilot-chat-panel",
        "copilot-chat-messages",
        "portfolio-modal",
        "btn-parse-portfolio",
        "open-llm-config-btn",
        "llm-config-modal",
        "btn-save-llm-config",
        "btn-clear-llm-config",
        "btn-custom-profile-chip",
        "open-profile-modal-btn",
        "profile-edit-modal",
        "btn-save-profile",
        "btn-reset-profile",
        "behavior-profile-card",
        "behavior-profile-status",
        "ai-trust-score",
        "save-display-policy",
        "recompute-behavior-profile",
        "dev-assist",
        "run-dev-assist",
        "dev-assist-output",
    ):
        assert f'id="{element_id}"' in markup

    # Preserved L3 expert workspace grid
    assert 'id="expert-workspace-grid"' in markup
    assert 'id="overview"' in markup
    assert 'id="advisor"' in markup


def test_copilot_script_personas_and_workflows() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    # Personas definition and switching
    for token in (
        "custom-user",
        "persona-zhang-r3",
        "persona-li-r2",
        "persona-wang-r4",
        "function switchPersona(",
        "function loadUserProfile()",
        "function saveUserProfile(",
        "function openProfileModal()",
        "function closeProfileModal()",
        "function handleSaveProfile()",
        "function handleResetProfile()",
        "function loadCopilotChatHistory()",
        "function saveCopilotChatHistory()",
        "function buildPipelineStepItem(",
        "function setPipelineStepState(",
        "function handleCopilotIntent(",
        "function runCopilotHealthCheck()",
        "function runCopilotStockResearch()",
        "function runCopilotRebalance()",
        "function runCopilotScenarioShock()",
        "function handleNaturalQuerySubmit()",
        "function handleStreamingChat(",
        "function applyQuestionnaireGate(",
        "function startConversationProfileUpdate(",
        "function renderConversationProfileQuestion(",
        "function confirmConversationProfileUpdate(",
        "function handleParsePortfolioSubmit(",
        "function openPortfolioModal(",
        "function closePortfolioModal(",
        "function openLLMConfigModal(",
        "function closeLLMConfigModal(",
        "function handleSaveLLMConfig(",
        "function buildCopilotDrilldownRow(",
        "function buildCopilotMetricBox(",
        "function buildCopilotLoadingCard(",
        "function renderBehaviorProfile(",
        "function loadBehaviorProfile(",
        "function saveDisplayPolicy(",
        "function recomputeBehaviorProfile(",
        "function renderDevAssistResult(",
        "function runDevAssist(",
    ):
        assert token in script

    # Verify drilldown links
    for drilldown_hash in (
        "#research-tracks",
        "#advanced-explainability",
        "#evidence",
        "#overview",
        "#portfolio-rebalancing",
        "#portfolio-optimization",
        "#scenario-simulation",
        "#stock-research",
    ):
        assert drilldown_hash in script

    # XSS safety
    assert "innerHTML" not in script
    assert "outerHTML" not in script


def test_copilot_styles_and_responsive_rules() -> None:
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")

    for selector in (
        ".nav-section-primary",
        ".nav-item-copilot",
        ".nav-item-copilot.active",
        ".nav-section-expert",
        ".persona-switcher-bar",
        ".persona-chip.active",
        ".copilot-section",
        ".agent-home-grid",
        ".agent-conversation",
        ".agent-profile-rail",
        ".agent-profile-summary",
        ".conversation-profile-card",
        ".copilot-query-box",
        ".copilot-natural-input",
        ".copilot-submit-btn",
        ".copilot-quick-tags",
        ".copilot-tasks-grid",
        ".copilot-task-card",
        ".copilot-decision-card",
        ".decision-banner",
        ".decision-metrics-row",
        ".decision-drilldown-row",
        ".drilldown-btn",
        ".copilot-chat-stream-panel",
        ".copilot-modal",
        ".portfolio-textarea",
        ".llm-config-trigger-btn",
        ".chat-pipeline-box",
        ".pipeline-step",
        ".pipeline-step.active",
        ".edit-profile-chip",
        ".evidence-answer-card",
        ".evidence-bar-track",
        ".evidence-process-flow",
        ".evidence-professional-details",
        ".behavior-profile-card",
        ".display-policy-control",
        ".dev-assist-grid",
        ".chat-audit-details",
    ):
        assert selector in styles

    assert ".copilot-stats-grid, .copilot-tasks-grid, .decision-metrics-row" in styles


def test_display_policy_is_a_three_level_user_control_with_legacy_api_mapping() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'id="ai-trust-score" type="range"' not in markup
    assert re.findall(
        r'<input type="radio" name="display-policy-level" value="(\d+)"',
        markup,
    ) == ["80", "50", "20"]
    for label in ("简洁", "标准", "详细"):
        assert f">{label}<" in markup

    # The visible control is discrete, while the historical API/database
    # contract continues to receive one of the established numeric values.
    assert "const DISPLAY_DETAIL_LEVELS" in script
    assert "function setDisplayPolicyControl(" in script
    assert "trust_score: trust" in script
    assert 'input[name="display-policy-level"]' in script


def test_portfolio_panel_declares_demo_data_and_hides_snapshot_identifiers() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'id="portfolio-source-note"' in markup
    assert "示例持仓数据，仅用于界面演示，不代表真实账户" in markup
    assert "function setPortfolioSourcePresentation(" in script
    assert "示例持仓明细" in script
    assert "parentPosition" in script
    assert "快照 ${text(fund.snapshot_id)}" not in script


def test_user_facing_asset_research_localizes_statuses_and_machine_identifiers() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    research_start = script.index("function renderResearchMatrix")
    research_end = script.index("function renderPortfolioOptimization(result)")
    research_renderers = script[research_start:research_end]

    for helper in (
        "researchSubjectLabel",
        "researchMetricLabel",
        "researchSourceLabel",
        "researchEvidenceLabel",
        "researchFindingLabel",
        "researchNarrative",
        "researchStatusLabel",
        "researchSeverityLabel",
    ):
        assert helper in research_renderers

    for raw_render in (
        "text(node.node_id)",
        "text(evidence.evidence_id)",
        "text(evidence.lineage_id)",
        "text(finding.finding_id)",
        "text(finding.kind)",
        "text(validation.metric)",
        "text(validation.status)",
        "text(evidence.quality_status)",
        "text(fact.status)",
        "text(finding.severity)",
    ):
        assert raw_render not in research_renderers

    assert "displayScenarioLabel" in research_renderers
    assert "发现 → 事实 → 证据" in research_renderers
