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
        "data-source-status",
        "theme-toggle",
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


def test_prism_ui_v2_design_tokens_are_semantic_and_legacy_compatible() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")

    assert 'class="questionnaire-pending prism-ui-v2"' in markup
    for token in (
        "--text-primary: #202124",
        "--page: #f7f7f8",
        "--brand: #e86f00",
        "--market-up: #c83b32",
        "--market-down: #16805a",
        "--success: #16805a",
        "--danger: #c83b32",
        "--warning: #a66b00",
        "--info: #356fa8",
        "--clay: var(--brand)",
    ):
        assert token in styles


def test_prism_ui_v2_default_copy_is_user_centered() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    for copy in (
        "分析你的投资组合",
        "投资研究会话",
        "结合你的持仓、投资偏好与可用市场数据回答。",
        "投资偏好",
        "分析资料",
        "组合概览",
        "行业分布与设置范围",
    ):
        assert copy in markup

    for internal_copy in (
        "从你的问题开始",
        "事实基线",
        "组合全景分析与多维体检",
        "PASS 合规正常",
        "不会自动执行交易",
        "不会自动下单",
    ):
        assert internal_copy not in markup

    for dynamic_copy in (
        'LOCKED:"分析资料已更新"',
        'DETAILED: Object.freeze({ score: 20, mode: "AUDIT_EXPANDED", label: "详细", hint: "展开结论、依据和数据说明" })',
        'title.textContent = "从一个具体问题开始"',
        'document.createTextNode(" 暂无明显问题")',
        'vBadge.textContent = v.isOver ? "需要关注" : "范围内"',
    ):
        assert dynamic_copy in script


def test_prism_ui_v2_reorganizes_shell_without_replacing_business_nodes() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'class="persona-switcher-bar profile-actions-menu" id="persona-switcher-bar"' in markup
    assert 'class="topbar-actions topbar-more-menu"' in markup
    assert 'id="profile-menu-current-label"' in markup
    for node_id in (
        "btn-custom-profile-chip",
        "open-profile-modal-btn",
        "open-portfolio-modal-btn",
        "global-data-mode-toggle",
        "portfolio-import-entry",
        "view-mode-toggle",
        "health-status",
        "copilot-chat-messages",
        "copilot-natural-input",
        "copilot-submit-query",
        "copilot-decision-output",
    ):
        assert markup.count(f'id="{node_id}"') == 1

    assert "/* Prism UI v2 integration: shell, topbar, and Agent home */" in styles
    for selector in (
        ".prism-ui-v2 .app-shell",
        ".prism-ui-v2 .profile-actions-menu",
        ".prism-ui-v2 .topbar-more-menu",
        ".prism-ui-v2 .agent-home-grid",
        ".prism-ui-v2 .agent-conversation",
        ".prism-ui-v2 .agent-profile-rail",
    ):
        assert selector in styles
    assert 'byId("profile-menu-current-label")' in script


def test_prism_ui_v2_scopes_overview_surface_and_table_styles() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")

    for node_id in (
        "overview-industry-table-body",
        "overview-metrics-body",
        "copilot-hero-donut-chart",
        "copilot-donut-legend",
        "donut-sector-detail",
    ):
        assert markup.count(f'id="{node_id}"') == 1

    assert "/* Prism UI v2 integration: overview */" in styles
    for selector in (
        ".prism-ui-v2 #overview .overview-card",
        ".prism-ui-v2 #overview .cf-status-widget",
        ".prism-ui-v2 #overview .health-check-matrix-table",
        ".prism-ui-v2 #overview .overview-health-metric-box",
        ".prism-ui-v2 #overview .donut-cause-callout",
        ".prism-ui-v2 #overview .donut-legend-chip",
    ):
        assert selector in styles


def test_agent_home_uses_demo_composition_without_changing_dom_identity() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    v2_styles = (STATIC / "prism-v2.css").read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="/static/styles.css?v=20260916-' in markup
    assert '<link rel="stylesheet" href="/static/prism-v2.css?v=20260918-' in markup
    assert '<script src="/static/app.js?v=20260918-' in markup
    assert '<script src="/static/lightweight-charts.js?v=5.2.1" defer></script>' in markup
    agent_start = markup.index('<section class="copilot-section" id="copilot"')
    agent_end = markup.index('id="portfolio-modal"', agent_start)
    agent_markup = markup[agent_start:agent_end]

    assert agent_markup.index('id="copilot-chat-messages"') < agent_markup.index('class="copilot-query-box"')
    assert agent_markup.index('class="copilot-query-box"') < agent_markup.index('id="copilot-quick-tags"')
    assert agent_markup.index('id="copilot-quick-tags"') < agent_markup.index('id="copilot-decision-output"')
    assert 'class="agent-empty-state" data-chat-empty-state' in agent_markup
    assert "agent-welcome-message" not in agent_markup
    assert '<div class="chat-avatar" aria-hidden="true">P</div>' not in agent_markup

    for node_id in (
        "copilot",
        "agent-home-grid",
        "agent-conversation",
        "copilot-chat-panel",
        "copilot-chat-messages",
        "copilot-natural-input",
        "copilot-submit-query",
        "copilot-quick-tags",
        "copilot-decision-output",
        "agent-profile-rail",
        "behavior-profile-card",
        "behavior-profile-content",
        "portfolio-refresh-status",
        "session-truth-status",
    ):
        assert markup.count(f'id="{node_id}"') == 1

    assert "function clearChatEmptyState(" in script
    assert 'messages?.querySelector("[data-chat-empty-state]")?.remove()' in script
    assert 'content.className = "agent-empty-state"' in script
    assert 'progressTrack.className = "chat-progress-track"' in script
    assert 'progressBar.className = "chat-progress-bar"' in script
    assert 'progressBar.style.width = "60%"' in script
    assert 'byId("chat-send-progress").replaceChildren(pipelineBox)' in script
    assert 'pipelineBox.append(pipeHead, stepsGrid)' in script
    assert 'aiBubble.append(contentBox)' in script
    for stage_label in ("理解问题", "查询真实数据（按需）", "核验事实与约束", "组织回答"):
        assert stage_label in script
    assert 'setPipelineStepState(s2, "skipped")' in script
    assert 'event.type === "grounding_start"' in script
    assert 'event.type === "research_skipped"' in script
    assert 'event.type === "done" && !streamError' in script
    assert '["FAILED", "BLOCKED", "REJECTED"].includes(toolStatus)' in script
    assert 'setPipelineStepState(s2, "failed")' in script
    assert 'setPipelineStepState(s3, "skipped")' in script
    assert 'stepEl.classList.remove("pending", "active", "completed", "skipped", "failed")' in script
    assert 'id="btn-clear-chat" class="clear-chat-btn" type="button" title="保留当前记录并开始新对话">新对话</button>' in markup
    assert "function clearConversationContext()" in script
    assert "if (activeChatController) activeChatController.abort();" in script
    assert 'workspaceStorage.removeItem(ownerStorageKey(CHAT_LEGACY_STORAGE_KEY))' in script
    assert 'clearChatBtn.addEventListener("click", clearConversationContext)' in script
    assert "const CHAT_PRECHECK_TIMEOUT_MS = 8000;" in script
    assert "const CHAT_STREAM_IDLE_TIMEOUT_MS = 15000;" in script
    assert "async function readChatStreamChunk(reader)" in script
    assert "refreshSessionTruth(truthRequest.signal)" in script
    market_start = script.index('if (id === "market")')
    market_end = script.index('if (id === "industry")', market_start)
    market_block = script[market_start:market_end]
    assert "buildMarketFeatureResultCard" in market_block
    assert 'window.location.hash = "market";' not in market_block


    assert "Agent home is defined here as a complete composition" in v2_styles
    for selector in (
        ".prism-ui-v2 .agent-home-grid",
        ".prism-ui-v2 .agent-conversation",
        ".prism-ui-v2 .agent-conversation .chat-panel-header",
        ".prism-ui-v2 .agent-conversation .copilot-chat-messages",
        ".prism-ui-v2 .agent-conversation .chat-msg",
        ".prism-ui-v2 .agent-conversation .chat-bubble",
        ".prism-ui-v2 .agent-conversation .copilot-query-box",
        ".prism-ui-v2 .agent-conversation .copilot-natural-input",
        ".prism-ui-v2 .agent-conversation .copilot-submit-btn",
        ".prism-ui-v2 .agent-conversation .copilot-quick-tags",
        ".prism-ui-v2 .agent-conversation .quick-tag-chip",
        ".prism-ui-v2 .agent-profile-rail",
        ".prism-ui-v2 .agent-profile-summary",
        ".prism-ui-v2 .agent-profile-rail .behavior-profile-card",
        ".prism-ui-v2 .agent-profile-rail .display-policy-option",
    ):
        assert selector in v2_styles

    for geometry in (
        "grid-template-columns: 220px minmax(0, 1fr)",
        "grid-template-columns: minmax(0, 1fr) 310px",
        "min-height: 260px",
        "border-radius: var(--radius-lg)",
        "box-shadow: none",
    ):
        assert geometry in v2_styles

    for legacy_teal in (
        "rgba(23, 108, 120",
        "#6d9298",
        "#eef6f5",
        "#3d7a86",
        "#1d6976",
        "#15535e",
    ):
        assert legacy_teal not in v2_styles.lower()


def test_visible_multi_session_history_and_scoped_follow_up_context() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    styles = (STATIC / "prism-v2.css").read_text(encoding="utf-8")

    for node_id in ("chat-history-title", "new-chat-session", "chat-session-list", "active-chat-title"):
        assert f'id="{node_id}"' in markup
    assert "暂无历史对话" in markup
    assert "同一会话、同一资料版本" in markup
    for token in (
        'const CHAT_SESSIONS_STORAGE_KEY = "prism_copilot_chat_sessions_v1"',
        "function renderChatSessionList()",
        "function formatChatSessionTime(value)",
        "function activateChatSession(sessionId)",
        "function deleteChatSession(sessionId)",
        "function renameChatSession(sessionId)",
        "function createPersistedChatSession(title",
        'fetch("/api/v1/copilot/conversations"',
        "conversation_id: activeChatSessionId",
        "function completedHistoryForScope(contextScope)",
        "history: completedHistoryForScope(contextScope)",
        '`truth:workbench:${chatTruth.revision}`',
        '!accountAccessEnabled && state.dataMode === "MOCK"',
    ):
        assert token in script
    for selector in (".chat-history-panel", ".chat-session-item.is-active", ".chat-session-delete"):
        assert selector in styles


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
    assert "导入持仓后即可查看持仓明细与基金底层股票。" in markup
    assert "function setPortfolioSourcePresentation(" in script
    assert "示例持仓明细" in script
    assert "parentPosition" in script
    assert "快照 ${text(fund.snapshot_id)}" not in script


def test_ocr_editor_is_wide_scroll_free_and_all_business_fields_are_editable() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    renderer = script.split("function renderPortfolioOcrResult(data)", 1)[1].split(
        "function initPortfolioModalTabs()", 1
    )[0]

    assert 'class="copilot-modal-content portfolio-entry-modal"' in markup
    assert "width: min(1240px, calc(100vw - 24px))" in styles
    assert "max-width: 1240px" in styles
    wrapper_styles = styles.split(".ocr-table-wrapper {", 1)[1].split("}", 1)[0]
    assert "overflow-x: visible" in wrapper_styles
    assert "overflow-x: auto" not in wrapper_styles
    assert '["代码", "名称", "持股", "可用", "成本价", "当前市价", "持仓市值", "报价时间"]' in renderer
    for field in (
        "asset_id", "name", "quantity", "available_quantity", "cost_price",
        "price", "market_value_cny", "observed_at",
    ):
        assert f'field: "{field}"' in renderer
    assert '"置信度", "审核裁决"' not in renderer
    assert "置信度仅用于定位可能有误的字段，不限制编辑或确认" in renderer
    assert "const defaultObservedAt = toLocalDateTimeInputValue()" in renderer
    assert 'MISSING_OBSERVED_AT: []' in renderer
    assert 'value: pos.observed_at ? toLocalDateTimeInputValue(pos.observed_at) : defaultObservedAt' in renderer
    assert 'fieldSources.observed_at = "system default: browser local current time"' in renderer
    assert 'return { asset_id: assetId, name,' in renderer
    assert 'return { ...pos' not in renderer
    submitted_position = renderer.split("仅提交 ConfirmedOcrPosition 契约允许的字段", 1)[1].split(
        "const validated = await validateAndActivatePortfolio", 1
    )[0]
    for derived_field in ("previous_close", "day_pnl_cny", "confidence_pct", "identity_candidates", "weight"):
        assert derived_field not in submitted_position
    assert 'confirmStatus.className = "ocr-confirm-status"' in renderer
    assert 'actions.append(errorNote)' not in renderer
    assert 'const validated = await validateAndActivatePortfolio' in renderer
    assert 'runPortfolioAnalysis();' not in renderer


def test_industry_shortcut_uses_confirmed_portfolio_template() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'data-chat-prefix="行业配置"' in markup
    assert "检查行业暴露及画像上限" in markup
    assert "请基于我已确认的持仓和风险画像" in script
    assert "不要推荐无关股票" in script
    assert "requiresPortfolio: true, requiresProfile: true" in script


def test_stock_shortcut_requires_a_subject_and_routes_codes_to_real_research() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'position => position.asset_type === "STOCK"' in script
    assert 'if (id === "stock" && spec.name === "target") control.value = currentFeatureStock()' in script
    assert 'setError("请输入需要分析的 6 位证券代码或证券名称")' in script
    assert 'runCopilotStockResearch(directStock[1])' in script
    assert "/api/v1/copilot/stock-analysis?symbol=" in script


def test_six_analysis_shortcuts_use_explicit_live_or_deterministic_chains() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    feature_block = script.split("const AGENT_FEATURES", 1)[1].split(
        'byId("welcome-start")', 1
    )[0]

    assert 'await runConfiguredAgentFeature(featureId, values)' in feature_block
    assert 'await handleNaturalQuerySubmit()' not in feature_block
    assert '"FUND_DATA",' in feature_block
    assert '基金代码 基金简称 单位净值 管理费率 托管费率' in feature_block
    assert '披露持仓 行业分布' not in feature_block
    assert 'function normalizeFeatureRows(title, rows)' in feature_block
    assert '筛选表已按基金代码合并' in feature_block
    assert 'runLiveProviderFeature("CONVERTIBLE_BOND_DATA"' in feature_block
    assert 'placeholder: "例如 113056 或 价格低于 130 元"' in feature_block
    assert 'INVALID_CONVERTIBLE_BOND_CODE' not in feature_block
    assert 'fallbackSubject.trim()' in feature_block
    assert '不是有效的沪深可转债代码' in feature_block
    assert '这不是连接失败' in feature_block
    assert 'await runCopilotStockResearch(values.target, Number(values.lookback || 5))' in feature_block
    assert 'const health = await refreshPortfolioHealth()' in feature_block
    assert 'const result = await runPortfolioOptimization()' in feature_block
    assert 'await assessMarket()' in feature_block
    assert 'alternateCapabilities: ["stock_quote"]' in feature_block
    assert 'alternateCapabilities: ["fund_lookthrough"]' in feature_block
    assert 'candidates.some(capability => capabilities[capability] === true)' in feature_block
    assert 'state.wencaiConfigured === true && state.wencaiLastErrorCode !== "AUTH_FAILED"' in feature_block
    assert '|| configuredProviderReady' in feature_block
    assert 'await fetchRuntimeDataMode();' in feature_block


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

def test_formal_report_uses_accessible_solid_asset_pie_from_report_contract() -> None:
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    renderer = script.split('function renderPortfolioAssetStructure', 1)[1].split('function appendRiskBoundaryRow', 1)[0]
    assert 'assetStructure || []' in renderer
    assert 'Number(group.market_value_cny) > 0' in renderer
    assert 'groups.length === 1' in renderer
    assert 'portfolio-asset-pie-sector' in renderer
    assert 'svg.setAttribute("role", "img")' in renderer
    assert 'sector.setAttribute("aria-label", sectorLabel)' in renderer
    for key, color in (("stock", "#d97706"), ("cash", "#2f855a"), ("etf", "#2563eb"),
                       ("convertible", "#7c3aed"), ("bond", "#0891b2"), ("other", "#6b7280")):
        assert f'{key}: "{color}"' in script


def test_market_choices_and_visible_source_controls_are_distinct() -> None:
    markup = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert set(re.findall(r'data-market-region="([^"]+)"', markup)) == {'CN', 'HK', 'US'}
    assert set(re.findall(r'data-market-interval="([^"]+)"', markup)) == {'1d', '1M'}
    assert set(re.findall(r'data-market-indicator="([^"]+)"', markup)) == {'boll', 'macd', 'kdj'}
    assert 'id="market-index-options"' in markup
    assert markup.count('id="chat-runtime-mode"') == 0
    assert 'id="visible-ai-mode"' in markup and 'id="visible-data-mode"' in markup
    more_menu = markup.split('<div class="topbar-more-panel">', 1)[1].split('</details>', 1)[0]
    assert 'id="data-source-status"' in more_menu
    assert 'id="theme-toggle"' in more_menu
    for removed_id in ('profile-preferences-title', 'preference-holdings', 'preference-market',
                       'profile-natural-text', 'profile-proposal-title'):
        assert f'id="{removed_id}"' not in markup
    assert 'id="visual-companion-drawer"' not in markup
    assert 'id="companion-allocation-card"' not in markup
    assert 'id="companion-risk-card"' not in markup
    assert 'id="floating-companion-btn"' not in markup
    assert 'class="portfolio-holdings-layout"' not in markup


def test_portfolio_report_navigation_status_and_boundaries_are_restructured() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    styles = (STATIC / "prism-v2.css").read_text(encoding="utf-8")

    heading = markup.index('class="overview-header-bar page-heading overview-heading"')
    tabs = markup.index('id="workspace-page-tabs"')
    metrics = markup.index('class="metric-strip"', heading)
    assert heading < tabs < metrics
    assert 'insertAdjacentElement("afterend", pageTabs)' in script
    assert 'id="portfolio-analysis-status"' in markup
    assert 'id="portfolio-analysis-retry"' in markup
    assert 'id="portfolio-extended-analysis"' in markup
    assert 'class="portfolio-report-subcard portfolio-report-asset-card"' in markup
    assert 'class="portfolio-report-subcard portfolio-report-risk-card"' in markup
    assert '.portfolio-report-asset-card,' in styles
    assert '.portfolio-report-risk-card { grid-column: 1 / -1; }' in styles
    risk_renderer = script.split('function renderPortfolioRiskBoundaries', 1)[1].split('function renderPortfolioReport', 1)[0]
    for label in ("单一标的集中度", "权益类占比", "行业及未分类资产", "现金比例", "计算口径"):
        assert label in risk_renderer
    assert '"REVIEW_REQUIRED"' in risk_renderer
    assert "最大回撤容忍度仅作为投资者画像边界" in risk_renderer
    assert 'renderPortfolioAnalysisStatus(error.message' in script
    assert 'setError(`持仓已保存' not in script


def test_feature_tools_yield_space_after_chat_starts_and_remain_reopenable() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    styles = (STATIC / "prism-v2.css").read_text(encoding="utf-8")

    assert 'id="agent-feature-toggle"' in markup
    assert 'aria-controls="agent-feature-popover"' in markup
    assert 'id="agent-feature-popover"' in markup
    assert 'function setAgentFeatureToolsCompact(compact, options = {})' in script
    assert 'setAgentFeatureToolsCompact(true);\n    const chatOwner' in script
    assert 'setAgentFeatureToolsCompact(false);' in script
    assert 'event.key !== "Escape"' in script
    assert '.agent-feature-tools.is-compact.is-open .agent-feature-popover' in styles
    assert 'position: absolute;' in styles
    assert 'max-height: min(72vh, 680px);' in styles


def test_feature_tools_share_the_conversation_column_beside_the_profile_rail() -> None:
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    styles = (STATIC / "prism-v2.css").read_text(encoding="utf-8")

    grid = markup.index('class="agent-home-grid" id="agent-home-grid"')
    workbench = markup.index('class="agent-workbench-column"', grid)
    feature_tools = markup.index('id="agent-feature-tools"', workbench)
    conversation = markup.index('id="agent-conversation"', feature_tools)
    profile_rail = markup.index('id="agent-profile-rail"', conversation)
    assert grid < workbench < feature_tools < conversation < profile_rail
    assert '</section>\n            </div>\n\n            <aside class="agent-profile-rail"' in markup
    assert 'grid-template-columns: minmax(0, 1fr) 310px;' in styles
    assert '.agent-workbench-column > .agent-feature-tools { width: 100%; margin-bottom: 0; }' in styles
    assert '.agent-workbench-column:has(> .agent-feature-tools.is-compact) > .agent-conversation' in styles
    assert 'min-height: 260px;' in styles
    assert 'max-height: 520px;' in styles
    assert 'overscroll-behavior: contain;' in styles
    assert '.agent-workbench-column:has(> .agent-feature-tools.is-compact) .copilot-chat-messages' in styles


def test_live_provider_results_use_compact_emphasized_card_layout() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    styles = (STATIC / "prism-v2.css").read_text(encoding="utf-8")

    assert 'provider-feature-card' in script
    assert 'provider-feature-metrics' in script
    assert 'provider-feature-table-wrap' in script
    assert 'provider-status-chip' in script
    assert 'function providerColumns(title, rows)' in script
    assert 'maximumFractionDigits: 6' in script
    assert 'max-height: 360px;' in styles
    assert 'position: sticky;' in styles
    assert 'text-overflow: ellipsis;' in styles
    assert 'max-height: 520px;' in styles
    assert 'scrollbar-gutter: stable;' in styles
    assert '.agent-conversation .copilot-output-container { display: block; max-height: 520px;' in styles
