from __future__ import annotations

from pathlib import Path


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

    # L1 Copilot task center elements
    for element_id in (
        "copilot",
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
        "task-card-health",
        "task-card-research",
        "task-card-rebalance",
        "copilot-btn-health-check",
        "copilot-stock-input",
        "copilot-btn-stock-research",
        "copilot-btn-rebalance",
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
        "function handleParsePortfolioSubmit(",
        "function openPortfolioModal(",
        "function closePortfolioModal(",
        "function openLLMConfigModal(",
        "function closeLLMConfigModal(",
        "function handleSaveLLMConfig(",
        "function buildCopilotDrilldownRow(",
        "function buildCopilotMetricBox(",
        "function buildCopilotLoadingCard(",
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
        ".copilot-hero-card",
        ".copilot-stats-grid",
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
    ):
        assert selector in styles

    assert ".copilot-stats-grid, .copilot-tasks-grid, .decision-metrics-row" in styles
