"""Owner-scoped HTTP API and static explainable workbench."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import os
import re

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from app.api.access import LocalAccessMiddleware, load_accounts
from app.service.natural_profile import NaturalProfileRequest, NaturalProfileError, extract_natural_profile
from app.service.session_truth import TruthConfirmation, TruthInputRequired, current_facts, truth_status, fingerprint, SessionAssertionsRequest, check_session_assertions
from app.service.workflow import WorkflowDefinition, WorkflowSaveRequest, WorkflowRunRequest, default_workflow, bind_workflow
from app.service.semantic_memory import search_context_memories
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.contracts import (
    AdvisorPortfolioContextRequest,
    AdvisorPortfolioContextResponse,
    AdvisorProfileContextRequest,
    AdvisorProfileContextResponse,
    AdvisorProfileConfirmationRequest,
    AdvisorProfileConfirmationResponse,
    AdvisorProfileProposalRequest,
    AdvisorProfileProposalResponse,
    AdvisorQueryResponse,
    AdvisorQueryTemplateResponse,
    BehaviorEventsWriteRequest,
    BehaviorEventsWriteResponse,
    BehaviorProfileRecomputeRequest,
    BehaviorProfileResponse,
    BehaviorProfileLookupResponse,
    DisplayPolicyResponse,
    DisplayPolicyUpdateRequest,
    MarketAssessmentResponse,
    MarketAnalysisResponse,
    MarketCatalogItem,
    MarketQuoteCard,
    ProfileSummaryResponse,
    QuestionnaireConfirmationRequest,
    QuestionnaireConfirmationResponse,
    QuestionnairePreviewRequest,
    QuestionnairePreviewResponse,
    UserPreferenceResponse,
    UserPreferenceUpdateRequest,
    DecisionEventListResponse,
    DecisionEventWriteResponse,
    ErrorResponse,
    ResearchMatrixIssueResponse,
    ResearchMatrixNodeResponse,
    ResearchMatrixResponse,
    ResearchMatrixTemplateResponse,
    ResearchScenarioResponse,
)
from app.recommendation import RecommendationCompositionResult
from app.market_analysis import (
    INDEX_REGISTRY,
    aggregate_monthly,
    correlated_returns,
    find_index,
    technical_indicators,
    volume_summary,
)
from app.providers.ifind_quant import IFindQuantError, IFindQuantProvider
from app.providers.etnet import EtNetError, EtNetProvider
from app.providers.yahoo_finance import YahooFinanceError, YahooFinanceProvider
from app.research import ResearchSpecialistMatrixRequest
from app.stock import (
    StockResearchRequest,
    StockResearchResponse,
    StockResearchTemplateResponse,
)
from app.fund import (
    FundResearchRequest,
    FundResearchResponse,
    FundResearchTemplateResponse,
)
from app.convertible_bond import (
    ConvertibleBondResearchRequest,
    ConvertibleBondResearchResponse,
    ConvertibleBondResearchTemplateResponse,
)
from app.optimization import (
    PortfolioOptimizationRequest,
    PortfolioOptimizationResponse,
    PortfolioOptimizationTemplateResponse,
)
from app.simulation import (
    ScenarioSimulationRequest,
    ScenarioSimulationResponse,
    ScenarioSimulationTemplateResponse,
)
from app.scenarios import CustomStressScenarioRequest, CustomStressScenarioResponse, calculate_custom_stress
from app.history import (
    RecommendationComparisonRequest,
    RecommendationComparisonResponse,
    RecommendationHistoryResponse,
)
from app.rebalancing import (
    PortfolioRebalancingRequest,
    PortfolioRebalancingResponse,
)
from app.providers.live_market import (
    CompositeMarketProvider,
    FallbackStaticProvider,
    MarketDataProvider,
    market_prefix,
)
from app.providers.fuyao import (
    CAPABILITY_FAILURE_CODES,
    FuyaoFinanceProvider,
    FuyaoProviderError,
)
from app.evaluation import (
    EvaluationDashboardRequest,
    EvaluationDashboardResponse,
)
from app.explainability import (
    AdvancedExplainabilityRequest,
    AdvancedExplainabilityResponse,
)
from app.profile import (
    DisplayPolicySource,
    QUESTIONNAIRE_TEMPLATE,
    QuestionnaireTemplate,
    BehaviorEventType,
    behavior_event_from_portfolio,
    build_display_policy,
    build_questionnaire_snapshot,
    calculate_behavior_profile,
    effective_risk_profile,
)
from app.portfolio import PortfolioOcrConfirmation
from app.dev_assist import (
    DevAssistError,
    DevAssistRequest,
    DevAssistResponse,
    extract_document_text,
    run_dev_assist,
)
from app.service import (
    AdvisorIntentRequest,
    AdvisorPlanResponse,
    AdvisorQueryError,
    AdvisorQueryRequest,
    FixtureAdvisorQueryService,
    FixtureResearchSpecialistMatrixService,
    SpecialistMatrixError,
    SpecialistMatrixOutput,
    ProfileConfirmationError,
    confirm_questionnaire,
    IntentPlanningError,
    build_intent_plan,
    ProfileProposalError,
    build_profile_proposal,
    confirm_profile_proposal,
    FixtureStockResearchService,
    StockResearchError,
    FixtureFundResearchService,
    FundResearchError,
    FixtureConvertibleBondResearchService,
    ConvertibleBondResearchError,
    FixturePortfolioOptimizationService,
    PortfolioOptimizationError,
    FixtureScenarioSimulationService,
    ScenarioSimulationError,
    RecommendationHistoryService,
    PortfolioRebalancingService,
    EvaluationDashboardService,
    AdvancedExplainabilityService,
)
from app.portfolio import (
    PortfolioImportBundle,
    PortfolioRefreshRequest,
    PortfolioRefreshResponse,
    refresh_portfolio_live,
    refresh_portfolio_mock,
)
from app.portfolio.health import (
    PortfolioHealthRequest,
    PortfolioHealthResponse,
    calculate_portfolio_health,
)
from app.profile import RiskQuestionnaire
from app.providers import (
    ProviderOperation,
    ProviderRequest,
    ProviderServingMode,
    ProviderStatus,
    WencaiSkillHubProvider,
)
from app.store import (
    ContextMemoryListResponse,
    ContextMemoryWriteRequest,
    ContextMemoryWriteResponse,
    ContextMemoryCorruptError,
    DecisionEvent,
    DecisionEventStore,
    StoreConflictError,
    StoreCorruptError,
    StoreError,
    StoreOwnerError,
    SQLiteDecisionEventStore,
    build_context_memory_record,
)
from app.store.contracts import build_decision_event
from app.llm import CopilotAgent, CopilotMessage
from app.llm.client import AsyncLLMClient, LLMConfig
from app.security import ProtectedSecretStore, SecretProtectionError
from app.providers.live_market import A_SHARE_DATABASE, ETF_LOOKTHROUGH_DATABASE
from app.runtime.mode import (
    DataMode,
    LiveProviderUnavailableError,
    ModeRevisionConflictError,
    get_runtime_mode_controller,
)
from typing import Any, Literal
import json
from hashlib import sha256


class RuntimeDataModeSwitchRequest(BaseModel):
    target_mode: str = Field(..., description="Target runtime data mode: MOCK or LIVE")
    expected_revision: int = Field(..., description="Expected controller revision for optimistic locking")


class LiveProviderQueryRequest(BaseModel):
    request_id: str = Field(min_length=1)
    operation: ProviderOperation
    subject: str = Field(min_length=1)
    as_of: datetime | None = None
    required_fields: tuple[str, ...] = ()
    parameters: dict[str, Any] = Field(default_factory=dict)


class CopilotChatApiRequest(BaseModel):
    message: str
    model_mode: Literal["AUTO", "LIVE", "MOCK"] = "AUTO"
    owner_id: str | None = None
    profile_version: int | None = None
    behavior_profile_version: int | None = None
    portfolio_snapshot_id: str | None = None
    persona_id: str | None = "persona-zhang-r3"
    persona_info: dict[str, Any] | None = None
    portfolio_context: dict[str, Any] | None = None
    history: list[dict[str, Any]] | None = None
    stream: bool = True
    llm_config: dict[str, Any] | None = None
    session_truth_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    session_truth_revision: int | None = Field(default=None, ge=1)


class CopilotParsePortfolioApiRequest(BaseModel):
    text: str


class CopilotParsePortfolioOcrApiRequest(BaseModel):
    image_base64: str = Field(description="Base64-encoded image string or data URI")


class CopilotValidatePortfolioOcrApiRequest(BaseModel):
    owner_id: str = Field(min_length=1)
    positions: list[dict[str, Any]]
    cash_cny: Decimal = Field(ge=0)


class ConfirmedOcrPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    name: str | None = None
    asset_class: str | None = None
    sector: str | None = None
    quantity: Decimal = Field(gt=0)
    cost_price: Decimal | None = Field(default=None, gt=0)
    previous_close: Decimal | None = Field(default=None, gt=0)
    observed_at: str | None = None
    price_source: str | None = None
    price: Decimal = Field(gt=0)
    market_value_cny: Decimal | None = Field(default=None, ge=0)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    confidence_pct: Decimal | None = Field(default=None, ge=0, le=100)
    needs_review: bool = False
    original_code: str | None = None
    review_reasons: list[str] = Field(default_factory=list)
    weight: Decimal | None = Field(default=None, ge=0, le=1)
    calculated_market_value_cny: Decimal | None = Field(default=None, ge=0)
    confidence_level: str | None = None


class CopilotConfirmPortfolioOcrApiRequest(CopilotValidatePortfolioOcrApiRequest):
    model_config = ConfigDict(extra="forbid")

    positions: list[ConfirmedOcrPosition]
    image_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ReplacePortfolioApiRequest(CopilotValidatePortfolioOcrApiRequest):
    data_mode: Literal["MOCK", "LIVE"] | None = None


class CopilotConfigApiRequest(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=20)


_STATIC_DIR = Path(__file__).parent / "static"


def _error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(error_code=error_code, message=message).model_dump(
        mode="json"
    )
    return JSONResponse(status_code=status_code, content=payload)


def _owner_id_from_header(x_owner_id: str | None) -> str:
    if x_owner_id is None or not isinstance(x_owner_id, str) or not x_owner_id.strip():
        raise StoreOwnerError("owner scope is required")
    return x_owner_id.strip()


def _research_matrix_response(output: SpecialistMatrixOutput) -> ResearchMatrixResponse:
    matrix_by_id = {node.node_id: node for node in output.matrix.nodes}
    response_nodes: list[ResearchMatrixNodeResponse] = []
    for node in output.execution.state.nodes:
        matrix_node = matrix_by_id[node.node_id]
        issues = [
            ResearchMatrixIssueResponse(
                code=issue.code.value,
                safe_message=issue.safe_message,
            )
            for issue in node.issues
        ]
        if node.result is not None:
            issues.extend(
                ResearchMatrixIssueResponse(
                    code=issue.code.value,
                    safe_message=issue.safe_message,
                )
                for issue in node.result.issues
            )
        response_nodes.append(
            ResearchMatrixNodeResponse(
                node_id=node.node_id,
                role=matrix_node.role,
                node_kind=node.node_kind,
                subject=matrix_node.subject,
                required=node.required,
                status=node.status,
                started_at=node.started_at,
                finished_at=node.finished_at,
                issues=tuple(issues),
                provider=node.result.provider if node.result is not None else None,
                provider_serving_mode=(
                    node.result.provider_serving_mode
                    if node.result is not None
                    else ProviderServingMode.DIRECT
                ),
                provider_cache_age_ms=(
                    node.result.provider_cache_age_ms
                    if node.result is not None
                    else None
                ),
            )
        )
    return ResearchMatrixResponse(
        matrix_id=output.matrix.matrix_id,
        scenario=ResearchScenarioResponse.model_validate(
            {
                "scenario_id": output.scenario.scenario_id,
                "label": output.scenario.label,
                "description": output.scenario.description,
            }
        ),
        request_id=output.request_id,
        owner_id=output.owner_id,
        run_id=output.execution.state.run_id,
        run_status=output.execution.state.status,
        pipeline_status=output.pipeline.status,
        nodes=tuple(sorted(response_nodes, key=lambda item: item.node_id)),
        validations=output.pipeline.validations,
        issues=output.pipeline.issues,
        trace=output.pipeline.trace,
    )


def create_app(
    store: DecisionEventStore | None = None,
    *,
    database_path: str | Path = ":memory:",
    database_url: str | None = None,
    auth_accounts_path: str | Path | None = None,
    clock: Callable[[], datetime] | None = None,
    advisor_service: FixtureAdvisorQueryService | None = None,
    specialist_service: FixtureResearchSpecialistMatrixService | None = None,
    stock_service: FixtureStockResearchService | None = None,
    fund_service: FixtureFundResearchService | None = None,
    convertible_bond_service: FixtureConvertibleBondResearchService | None = None,
    portfolio_optimization_service: FixturePortfolioOptimizationService | None = None,
    scenario_simulation_service: FixtureScenarioSimulationService | None = None,
    recommendation_history_service: RecommendationHistoryService | None = None,
    portfolio_rebalancing_service: PortfolioRebalancingService | None = None,
    evaluation_dashboard_service: EvaluationDashboardService | None = None,
    advanced_explainability_service: AdvancedExplainabilityService | None = None,
    market_provider: MarketDataProvider | None = None,
    wencai_provider: WencaiSkillHubProvider | None = None,
    live_finance_provider: FuyaoFinanceProvider | None = None,
    yahoo_finance_provider: YahooFinanceProvider | None = None,
    etnet_provider: EtNetProvider | None = None,
    # Backward-compatible injection point for existing iFinD provider tests.
    ifind_quant_provider: IFindQuantProvider | None = None,
    secret_store: ProtectedSecretStore | None = None,
) -> FastAPI:
    """Create an API instance with an explicitly injectable store and clock.

    Factory callers default to isolated memory. The desktop module entrypoint
    supplies a local database path so confirmed user data survives restarts.
    """

    accounts = load_accounts(auth_accounts_path) if auth_accounts_path else {}
    active_secret_store = secret_store
    owned_store = store is None
    if store is not None and database_url is not None:
        raise ValueError("select either an injected store or database_url")
    if store is None and database_url is None and str(database_path) != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    if store is not None:
        active_store = store
    elif database_url is not None:
        from app.store.postgres import PostgresDecisionEventStore
        active_store = PostgresDecisionEventStore(database_url)
    else:
        active_store = SQLiteDecisionEventStore(database_path)
    active_clock = clock or (lambda: datetime.now(UTC))
    active_advisor = advisor_service or FixtureAdvisorQueryService()
    active_specialist = specialist_service or FixtureResearchSpecialistMatrixService()
    active_stock = stock_service or FixtureStockResearchService()
    active_fund = fund_service or FixtureFundResearchService()
    active_convertible_bond = convertible_bond_service or FixtureConvertibleBondResearchService()
    active_portfolio_optimization = (
        portfolio_optimization_service or FixturePortfolioOptimizationService()
    )
    active_scenario_simulation = (
        scenario_simulation_service
        or FixtureScenarioSimulationService(
            optimization_service=active_portfolio_optimization
        )
    )
    active_recommendation_history = (
        recommendation_history_service or RecommendationHistoryService(active_store)
    )
    active_portfolio_rebalancing = (
        portfolio_rebalancing_service or PortfolioRebalancingService()
    )
    active_evaluation_dashboard = (
        evaluation_dashboard_service or EvaluationDashboardService()
    )
    active_advanced_explainability = (
        advanced_explainability_service or AdvancedExplainabilityService()
    )

    fixture_types = (
            FixtureAdvisorQueryService,
            FixtureResearchSpecialistMatrixService,
            FixtureStockResearchService,
            FixtureFundResearchService,
            FixtureConvertibleBondResearchService,
            FixturePortfolioOptimizationService,
            FixtureScenarioSimulationService,
    )

    def service_uses_fixture(service: object) -> bool:
        if isinstance(service, fixture_types):
            return True
        declared_mode = getattr(service, "serving_mode", None)
        if declared_mode is not None:
            normalized_mode = str(declared_mode).upper()
            return normalized_mode not in {"LIVE", "DIRECT", "REAL"}
        return False

    def reject_fixture_execution_in_live(
        service: object, capability: str
    ) -> JSONResponse | None:
        if (
            get_runtime_mode_controller().mode == DataMode.LIVE
            and service_uses_fixture(service)
        ):
            return _error_response(
                409,
                "LIVE_RESEARCH_NOT_AVAILABLE",
                f"{capability}尚未接入真实研究服务；LIVE 模式拒绝返回演示数据",
            )
        return None

    user_model_settings: dict[str, CopilotConfigApiRequest] = {}

    def model_setting_scope(owner_id: str) -> str:
        # Without account authentication this is a single-user loopback
        # workbench.  Use one installation-scoped DPAPI slot instead of
        # pretending the caller-controlled owner label is an identity boundary.
        if active_secret_store is not None and not accounts:
            return "local:workbench"
        return owner_id

    def persisted_model_setting(owner_id: str) -> CopilotConfigApiRequest | None:
        scope = model_setting_scope(owner_id)
        cached = user_model_settings.get(scope)
        if active_secret_store is None:
            return cached
        try:
            encoded = active_secret_store.get(f"llm:{scope}")
            if encoded is None:
                user_model_settings.pop(scope, None)
                return None
            setting = CopilotConfigApiRequest.model_validate_json(encoded)
        except (SecretProtectionError, ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="模型密钥安全存储暂时不可用",
            ) from exc
        if not setting.api_key.strip():
            return None
        user_model_settings[scope] = setting
        return setting
    active_market_quotes = market_provider or CompositeMarketProvider()
    active_wencai_provider = wencai_provider or WencaiSkillHubProvider()
    active_live_finance = live_finance_provider or FuyaoFinanceProvider()
    active_yahoo_finance = yahoo_finance_provider or ifind_quant_provider or YahooFinanceProvider()
    active_etnet = etnet_provider or EtNetProvider()
    live_probe_lock = asyncio.Lock()

    async def fetch_overseas_quote(symbol: str) -> dict | None:
        providers = []
        if active_yahoo_finance.is_configured:
            providers.append(active_yahoo_finance)
        if active_etnet.is_configured and active_etnet.supports_symbol(symbol):
            providers.append(active_etnet)
        for provider in providers:
            try:
                quote = await provider.get_index_quote(symbol)
            except (IFindQuantError, YahooFinanceError, EtNetError, TimeoutError, ValueError, ArithmeticError):
                continue
            if quote is not None and quote.get("symbol") == symbol:
                return quote
        return None

    async def fetch_overseas_data(
        symbol: str,
        start: date,
        end: date,
    ) -> tuple[dict | None, list[dict]]:
        providers = []
        if active_yahoo_finance.is_configured:
            providers.append(active_yahoo_finance)
        if active_etnet.is_configured and active_etnet.supports_symbol(symbol):
            providers.append(active_etnet)
        best: tuple[dict | None, list[dict]] = (None, [])
        for provider in providers:
            try:
                quote, bars = await asyncio.gather(
                    provider.get_index_quote(symbol),
                    provider.get_index_history(symbol, start, end),
                )
            except (IFindQuantError, YahooFinanceError, EtNetError, TimeoutError, ValueError, ArithmeticError):
                continue
            if quote is None or quote.get("symbol") != symbol or not bars:
                continue
            if len(bars) >= 20 or not best[1]:
                best = (quote, bars)
            if len(bars) >= 20:
                return best
        return best

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if owned_store:
                active_store.close()

    api = FastAPI(
        title="Prism Decision API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    if accounts:
        api.add_middleware(LocalAccessMiddleware, accounts=accounts, audit=active_store.record_access)
    api.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @api.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _: Request, __: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            422,
            "INVALID_INPUT",
            "request failed contract validation",
        )

    @api.exception_handler(StoreOwnerError)
    async def owner_error_handler(_: Request, __: StoreOwnerError) -> JSONResponse:
        return _error_response(403, "OWNER_SCOPE", "owner scope is not allowed")

    @api.exception_handler(StoreConflictError)
    async def conflict_error_handler(
        _: Request, __: StoreConflictError
    ) -> JSONResponse:
        return _error_response(
            409,
            "CONFLICT",
            "decision event already exists with different content",
        )

    @api.exception_handler(StoreCorruptError)
    async def corrupt_error_handler(_: Request, __: StoreCorruptError) -> JSONResponse:
        return _error_response(
            500,
            "CORRUPT_RECORD",
            "stored decision event failed integrity validation",
        )

    @api.exception_handler(ContextMemoryCorruptError)
    async def context_memory_corrupt_error_handler(
        _: Request, __: ContextMemoryCorruptError
    ) -> JSONResponse:
        return _error_response(
            500,
            "STORE_CORRUPT",
            "stored context memory failed integrity validation",
        )

    @api.exception_handler(StoreError)
    async def store_error_handler(_: Request, __: StoreError) -> JSONResponse:
        return _error_response(400, "STORE_ERROR", "decision event request was refused")

    @api.exception_handler(AdvisorQueryError)
    async def advisor_query_error_handler(
        _: Request, __: AdvisorQueryError
    ) -> JSONResponse:
        return _error_response(400, "ADVISOR_QUERY_ERROR", "advisor query was refused")

    @api.exception_handler(SpecialistMatrixError)
    async def specialist_matrix_error_handler(
        _: Request, __: SpecialistMatrixError
    ) -> JSONResponse:
        return _error_response(400, "RESEARCH_MATRIX_ERROR", "research matrix was refused")

    @api.exception_handler(StockResearchError)
    async def stock_research_error_handler(
        _: Request, __: StockResearchError
    ) -> JSONResponse:
        return _error_response(400, "STOCK_RESEARCH_ERROR", "stock research was refused")

    @api.exception_handler(FundResearchError)
    async def fund_research_error_handler(
        _: Request, __: FundResearchError
    ) -> JSONResponse:
        return _error_response(400, "FUND_RESEARCH_ERROR", "fund research was refused")

    @api.exception_handler(ConvertibleBondResearchError)
    async def convertible_bond_research_error_handler(
        _: Request, __: ConvertibleBondResearchError
    ) -> JSONResponse:
        return _error_response(
            400,
            "CONVERTIBLE_BOND_RESEARCH_ERROR",
            "convertible-bond research was refused",
        )

    @api.exception_handler(PortfolioOptimizationError)
    async def portfolio_optimization_error_handler(
        _: Request, __: PortfolioOptimizationError
    ) -> JSONResponse:
        return _error_response(
            400,
            "PORTFOLIO_OPTIMIZATION_ERROR",
            "portfolio optimization was refused",
        )

    @api.exception_handler(ScenarioSimulationError)
    async def scenario_simulation_error_handler(
        _: Request, __: ScenarioSimulationError
    ) -> JSONResponse:
        return _error_response(
            400,
            "SCENARIO_SIMULATION_ERROR",
            "scenario simulation was refused",
        )

    @api.exception_handler(ProfileConfirmationError)
    async def profile_confirmation_error_handler(
        _: Request, __: ProfileConfirmationError
    ) -> JSONResponse:
        return _error_response(
            400,
            "PROFILE_CONTEXT_ERROR",
            "risk profile confirmation was refused",
        )

    @api.exception_handler(IntentPlanningError)
    async def intent_planning_error_handler(
        _: Request, __: IntentPlanningError
    ) -> JSONResponse:
        return _error_response(
            400,
            "INTENT_PLAN_ERROR",
            "advisor intent plan was refused",
        )

    @api.exception_handler(ProfileProposalError)
    async def profile_proposal_error_handler(
        _: Request, __: ProfileProposalError
    ) -> JSONResponse:
        return _error_response(
            400,
            "PROFILE_PROPOSAL_ERROR",
            "profile proposal was refused",
        )

    @api.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error_response(404, "NOT_FOUND", "decision event was not found")
        return _error_response(exc.status_code, "HTTP_ERROR", "request was refused")

    def owner_dependency(
        x_owner_id: str | None = Header(default=None, alias="X-Owner-ID"),
    ) -> str:
        return _owner_id_from_header(x_owner_id)

    @api.get("/", include_in_schema=False)
    def workbench() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})

    @api.get("/login", include_in_schema=False)
    def local_login_page() -> FileResponse:
        return FileResponse(_STATIC_DIR / "login.html", media_type="text/html")

    @api.get("/api/v1/auth/context")
    def auth_context(request: Request):
        account = getattr(request.state, "account", None)
        return {"enabled": bool(accounts), "owner_id": account.owner_id if account else None,
                "admin": account.admin if account else False}

    @api.post("/api/v1/auth/login")
    def create_local_login(request: Request):
        account = getattr(request.state, "account", None)
        if account is None:
            raise HTTPException(status_code=401, detail="local account authentication required")
        # FastAPI keeps the constructed middleware stack separately; retrieve
        # the live instance from the request path instead of trusting client data.
        layer = request.app.middleware_stack
        while layer is not None and not isinstance(layer, LocalAccessMiddleware):
            layer = getattr(layer, "app", None)
        if layer is None:
            raise HTTPException(status_code=409, detail="local session mode is disabled")
        response = JSONResponse({"owner_id": account.owner_id, "local_demo": True})
        response.set_cookie("prism_local_session", layer.issue_session(account), httponly=True, samesite="lax")
        return response

    @api.post("/api/v1/auth/logout")
    def local_logout(request: Request):
        layer = request.app.middleware_stack
        while layer is not None and not isinstance(layer, LocalAccessMiddleware):
            layer = getattr(layer, "app", None)
        if layer is not None:
            layer.revoke_session(request.cookies.get("prism_local_session"))
        response = JSONResponse({"logged_out": True})
        response.delete_cookie("prism_local_session")
        return response

    @api.get("/api/v1/access-audit")
    def access_audit(owner_id: str = Depends(owner_dependency), limit: int = Query(100, ge=1, le=500)):
        return {"items": active_store.list_access(owner_id, limit)}

    @api.get("/api/health")
    def health() -> dict[str, Any]:
        controller = get_runtime_mode_controller()
        return {
            "status": "ok",
            "schema_version": "decision-event.v1",
            "data_mode": controller.mode.value,
            "revision": controller.revision,
            "live_ready": controller.is_live_ready,
            "capabilities": controller.capabilities,
        }

    @api.post(
        "/api/v1/advisor/behavior/events",
        response_model=BehaviorEventsWriteResponse,
    )
    def write_behavior_events(
        request: BehaviorEventsWriteRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> BehaviorEventsWriteResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("behavior request owner does not match owner scope")
        stored, created_count = active_store.save_behavior_events(owner_id, request.events)
        return BehaviorEventsWriteResponse(
            owner_id=owner_id,
            accepted_count=len(stored),
            created_count=created_count,
            event_ids=tuple(item.event_id for item in stored),
        )

    @api.get(
        "/api/v1/advisor/behavior/profile",
        response_model=BehaviorProfileLookupResponse,
    )
    def get_behavior_profile(
        owner_id: str = Depends(owner_dependency),
    ) -> BehaviorProfileLookupResponse:
        profile = active_store.get_latest_behavior_profile(owner_id)
        if profile is None:
            return BehaviorProfileLookupResponse(status="INSUFFICIENT_DATA")
        return BehaviorProfileLookupResponse(status="CALCULATED", profile=profile)

    @api.post(
        "/api/v1/advisor/behavior/recompute",
        response_model=BehaviorProfileResponse,
    )
    def recompute_behavior_profile(
        request: BehaviorProfileRecomputeRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> BehaviorProfileResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("behavior profile owner does not match owner scope")
        events = active_store.list_behavior_events(owner_id)
        current = active_store.get_latest_behavior_profile(owner_id)
        version = 1 if current is None else current.profile_version + 1
        policy = active_store.get_display_policy(owner_id)
        profile = calculate_behavior_profile(
            request.questionnaire_profile,
            events,
            calculated_at=request.calculated_at,
            display_policy=policy,
            profile_version=version,
        )
        active_store.save_behavior_profile(profile)
        effective = effective_risk_profile(request.questionnaire_profile, profile)
        return BehaviorProfileResponse(profile=profile, effective_profile=effective)

    @api.patch(
        "/api/v1/advisor/display-policy",
        response_model=DisplayPolicyResponse,
    )
    def update_display_policy(
        request: DisplayPolicyUpdateRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> DisplayPolicyResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("display policy owner does not match owner scope")
        policy = build_display_policy(
            owner_id,
            request.trust_score,
            updated_at=request.updated_at,
            source=DisplayPolicySource.EXPLICIT,
        )
        return DisplayPolicyResponse(policy=active_store.save_display_policy(policy))

    def _preferences(owner_id: str) -> UserPreferenceResponse:
        stored = active_store.get_user_preferences(owner_id)
        if stored is None:
            return UserPreferenceResponse(
                owner_id=owner_id, theme="LIGHT", holdings_data_enabled=False,
                market_data_enabled=True, updated_at=active_clock(),
            )
        return UserPreferenceResponse.model_validate({
            **stored,
            "holdings_data_enabled": False,
            "market_data_enabled": True,
        })

    @api.get("/api/v1/user/preferences", response_model=UserPreferenceResponse)
    def get_user_preferences(owner_id: str = Depends(owner_dependency)) -> UserPreferenceResponse:
        return _preferences(owner_id)

    @api.put("/api/v1/user/preferences", response_model=UserPreferenceResponse)
    def update_user_preferences(
        request: UserPreferenceUpdateRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> UserPreferenceResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("user preferences owner does not match owner scope")
        response = UserPreferenceResponse(
            owner_id=owner_id,
            theme=request.theme,
            holdings_data_enabled=False,
            market_data_enabled=True,
            updated_at=active_clock(),
        )
        active_store.save_user_preferences(owner_id, response.model_dump(mode="json"))
        # Authenticated deployments audit responses in LocalAccessMiddleware;
        # development mode has no middleware, so retain a single explicit row.
        if not accounts:
            active_store.record_access(owner_id, "PUT", "/api/v1/user/preferences", 200)
        return response

    industry_cache: dict[str, Any] = {}
    industry_lock = asyncio.Lock()

    @api.get("/api/v1/market/industries")
    async def get_market_industries(owner_id: str = Depends(owner_dependency)):
        from time import monotonic
        if not active_live_finance.is_configured:
            return {"status": "REVIEW_REQUIRED", "rows": [], "message": "未配置同花顺行业数据服务"}
        async with industry_lock:
            if monotonic() < industry_cache.get("expires", 0):
                return industry_cache["result"]
            try:
                rows = await active_live_finance.get_industry_observations()
            except FuyaoProviderError as exc:
                return {"status": "REVIEW_REQUIRED", "rows": [], "message": exc.safe_message}
            result = {"status": "CALCULATED" if rows and all(r["status"] == "CALCULATED" for r in rows) else "REVIEW_REQUIRED",
                      "rows": rows, "source": "同花顺金融数据 · 行业指数日线", "message": "固定观察行业的 1、5、20 个交易日涨跌幅；不代表全市场排名。"}
            industry_cache.update(result=result, expires=monotonic() + 60)
            return result

    @api.get("/api/v1/market/catalog", response_model=list[MarketCatalogItem])
    def get_market_catalog(owner_id: str = Depends(owner_dependency)) -> list[MarketCatalogItem]:
        del owner_id
        return [MarketCatalogItem(
            market=item.market, index_id=item.index_id, name=item.name, symbol=item.symbol,
            currency=item.currency, timezone=item.timezone, precision=item.precision,
            status="AVAILABLE" if item.market == "CN" or (
                item.symbol and (
                    active_yahoo_finance.is_configured
                    or (item.market == "HK" and active_etnet.is_configured and active_etnet.supports_symbol(item.symbol))
                )
            ) else "UNAVAILABLE",
        ) for item in INDEX_REGISTRY]

    @api.get("/api/v1/market/quotes/{market}", response_model=list[MarketQuoteCard])
    async def get_market_quotes(
        market: str,
        owner_id: str = Depends(owner_dependency),
    ) -> list[MarketQuoteCard]:
        del owner_id
        normalized_market = market.strip().upper()
        selected_items = [item for item in INDEX_REGISTRY if item.market == normalized_market]
        if not selected_items:
            raise HTTPException(status_code=404, detail="market is not registered")

        async def read_quote(item) -> MarketQuoteCard:
            unavailable = MarketQuoteCard(
                market=item.market, index_id=item.index_id, name=item.name,
                symbol=item.symbol, currency=item.currency, precision=item.precision,
                status="UNAVAILABLE", source="公开行情代码、权限或上游数据不可用",
            )
            if item.symbol is None:
                return unavailable
            provider = active_live_finance if item.market == "CN" and active_live_finance.is_configured else active_market_quotes
            try:
                quote = await (provider.get_index_quote(item.symbol) if item.market == "CN"
                               else fetch_overseas_quote(item.symbol))
            except (FuyaoProviderError, IFindQuantError, YahooFinanceError, EtNetError, TimeoutError, ValueError, ArithmeticError):
                return unavailable
            if quote is None or quote.get("symbol") != item.symbol:
                return unavailable
            try:
                observed_at = datetime.fromisoformat(str(quote["observed_at"]))
                return MarketQuoteCard(
                    market=item.market, index_id=item.index_id, name=item.name,
                    symbol=item.symbol, currency=item.currency, precision=item.precision,
                    status="LIVE", source=str(quote.get("source", "Yahoo Finance行情")),
                    observed_at=observed_at, price=Decimal(str(quote["price_cny"])),
                    change_pct=Decimal(str(quote["change_pct"])),
                )
            except (KeyError, TypeError, ValueError, ArithmeticError):
                return unavailable

        return list(await asyncio.gather(*(read_quote(item) for item in selected_items)))

    @api.get("/api/v1/market/analysis/{market}/{index_id}", response_model=MarketAnalysisResponse)
    async def get_market_analysis(
        market: str,
        index_id: str,
        interval: str = Query(default="1d", pattern=r"^(1d|1M)$"),
        owner_id: str = Depends(owner_dependency),
    ) -> MarketAnalysisResponse:
        del owner_id
        selected = find_index(market.strip().upper(), index_id.strip())
        if selected is None:
            raise HTTPException(status_code=404, detail="market index is not registered")
        end_time = active_clock().astimezone(UTC)
        start_time = end_time - timedelta(days=3653 if interval == "1M" else 731)
        if selected.symbol is None:
            return MarketAnalysisResponse(
                market=selected.market, index_id=selected.index_id, name=selected.name,
                currency=selected.currency, timezone=selected.timezone, precision=selected.precision,
                interval=interval, status="REVIEW_REQUIRED", source="公开行情代码、权限或上游数据不可用",
            )

        quote = None
        daily_bars: list[dict] = []
        provider = active_live_finance if selected.market == "CN" and active_live_finance.is_configured else active_market_quotes
        try:
            if selected.market == "CN":
                quote = await provider.get_index_quote(selected.symbol)
                daily_bars = await provider.get_index_history(selected.symbol, start=start_time, end=end_time)
            else:
                quote, daily_bars = await fetch_overseas_data(selected.symbol, start_time.date(), end_time.date())
        except (FuyaoProviderError, IFindQuantError, YahooFinanceError, EtNetError, TimeoutError, ValueError, ArithmeticError):
            quote, daily_bars = None, []
        if quote is None or quote.get("symbol") != selected.symbol or not daily_bars:
            return MarketAnalysisResponse(
                market=selected.market, index_id=selected.index_id, name=selected.name,
                symbol=selected.symbol, currency=selected.currency, timezone=selected.timezone,
                precision=selected.precision, interval=interval, status="REVIEW_REQUIRED",
                source="公开行情未返回可验证的指数行情（权限、非正式接口或代码不可用）",
            )

        bars = aggregate_monthly(daily_bars) if interval == "1M" else daily_bars
        # A fallback provider can return a valid shorter history. Preserve it,
        # but expose that the requested ten-year monthly window is incomplete.
        history_status = "LIVE" if interval == "1d" or len(bars) >= 120 else "REVIEW_REQUIRED"
        if str(quote.get("source", "")).startswith(("Yahoo Finance", "ET Net")) and len(bars) < 20:
            history_status = "REVIEW_REQUIRED"
        latest = Decimal(str(bars[-1]["close"]))
        previous = Decimal(str(bars[-2]["close"])) if len(bars) > 1 else Decimal(str(bars[-1]["open"]))
        change = latest - previous
        change_pct = change / previous * Decimal(100) if previous else Decimal(0)
        factor_definitions = (
            ("us10y", "美国10年期国债收益率", "%", True),
            ("brent", "Brent原油近月", "USD/桶", False),
            ("comex-gold", "COMEX黄金近月", "USD/盎司", False),
        )

        async def analyze_factor(factor_id: str, name: str, unit: str, is_yield: bool) -> dict:
            unavailable = {"factor_id": factor_id, "name": name, "unit": unit, "status": "UNAVAILABLE",
                           "source": "Yahoo Finance宏观因子不可用", "sample_size": 0}
            if not active_yahoo_finance.is_configured:
                return unavailable
            try:
                points = await active_yahoo_finance.get_factor_history(factor_id, start_time.date(), end_time.date())
            except (IFindQuantError, YahooFinanceError, TimeoutError, ValueError, ArithmeticError):
                return unavailable
            if not points:
                return unavailable
            correlation = correlated_returns(
                bars, points, yield_factor=is_yield, monthly=interval == "1M", market=selected.market,
            )
            cutoff = str(bars[-1]["time"])[:7] if interval == "1M" else str(bars[-1]["time"])[:10]
            def point_key(point: dict) -> str:
                return str(point["time"])[:7] if interval == "1M" else str(point["time"])[:10]
            strict_factor_cutoff = selected.market in {"CN", "HK"}
            eligible_points = []
            for point in points:
                observed_key = point_key(point)
                if observed_key < cutoff or (not strict_factor_cutoff and observed_key == cutoff):
                    eligible_points.append(point)
            if not eligible_points:
                return unavailable
            latest_point = eligible_points[-1]
            latest_value = Decimal(str(latest_point["value"]))
            previous_value = Decimal(str(eligible_points[-2]["value"])) if len(eligible_points) > 1 else latest_value
            factor_observed_at = datetime.fromisoformat(str(latest_point["time"])[:10]).replace(tzinfo=UTC)
            return {"factor_id": factor_id, "name": name, "unit": unit, "status": "LIVE",
                    "source": "Yahoo Finance非正式接口", "observed_at": factor_observed_at, "latest_value": latest_value,
                    "change": latest_value - previous_value, **correlation}

        factors = await asyncio.gather(*(analyze_factor(*definition) for definition in factor_definitions))
        return MarketAnalysisResponse(
            market=selected.market, index_id=selected.index_id, name=selected.name,
            symbol=selected.symbol, currency=selected.currency, timezone=selected.timezone,
            precision=selected.precision, interval=interval, status="CALCULATED",
            source=str(quote.get("source", "Yahoo Finance行情")), history_status=history_status,
            observed_at=datetime.fromisoformat(quote["observed_at"]),
            price=latest, change=change, change_pct=change_pct, bars=bars,
            volume=volume_summary(bars), indicators=technical_indicators(bars), factors=factors,
        )

    @api.get("/api/v1/market-assessments/{index_name}", response_model=MarketAssessmentResponse)
    async def get_market_assessment(
        index_name: str,
        owner_id: str = Depends(owner_dependency),
    ) -> MarketAssessmentResponse:
        """Return an observed quote when available; unknown inputs remain review-only."""
        clean = index_name.strip()
        if not clean:
            raise HTTPException(status_code=422, detail="index name is required")
        # Codes are limited to the provider's supported local index aliases.  A
        # non-matching name is intentionally not converted into a fabricated quote.
        known = {"上证指数": "000001.SH", "深证成指": "399001.SZ", "创业板指": "399006.SZ", "沪深300": "000300.SH"}
        code = known.get(clean)
        if code is None:
            return MarketAssessmentResponse(
                index_name=clean, status="REVIEW_REQUIRED", source="未配置对应指数行情源",
                freshness="UNAVAILABLE", summary="未识别该指数或未接入可验证行情源；请核对名称后重试。",
                compliance_status="REVIEW_REQUIRED",
            )
        index_provider = market_provider or (active_live_finance if active_live_finance.is_configured else active_market_quotes)
        bars = []
        history_status = "UNAVAILABLE"
        try:
            quote = await index_provider.get_index_quote(code)
        except FuyaoProviderError:
            quote = None
        if quote is not None and hasattr(index_provider, "get_index_history"):
            try:
                bars = await index_provider.get_index_history(code)
                history_status = "LIVE" if bars else "UNAVAILABLE"
            except FuyaoProviderError:
                history_status = "UNAVAILABLE"
        if quote is None or quote.get("symbol") != code:
            return MarketAssessmentResponse(
                index_name=clean, index_code=code, status="REVIEW_REQUIRED", source="行情 Provider 未返回可验证数据",
                freshness="UNAVAILABLE", summary="行情源暂不可用，系统未以演示价格替代实时行情。",
                compliance_status="REVIEW_REQUIRED",
            )
        observed_at = datetime.fromisoformat(quote["observed_at"])
        is_synthetic = bool(quote.get("is_synthetic"))
        return MarketAssessmentResponse(
            index_name=clean, index_code=code, status="CALCULATED", source=str(quote.get("source", "行情 Provider")),
            observed_at=observed_at, freshness="MOCK" if is_synthetic else "LIVE",
            price=Decimal(str(quote["price_cny"])), change_pct=Decimal(str(quote["change_pct"])),
            bars=bars, history_status=history_status,
            summary="已返回可追溯行情快照；走势研判需结合数据新鲜度与风险画像审阅。",
            compliance_status="REVIEW_REQUIRED",
        )

    @api.get(
        "/api/v1/advisor/profile/questionnaire-template",
        response_model=QuestionnaireTemplate,
    )
    def get_questionnaire_template(
        owner_id: str = Depends(owner_dependency),
    ):
        del owner_id
        return QUESTIONNAIRE_TEMPLATE

    @api.post(
        "/api/v1/advisor/profile/questionnaire/preview",
        response_model=QuestionnairePreviewResponse,
    )
    def preview_questionnaire(
        request: QuestionnairePreviewRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> QuestionnairePreviewResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("questionnaire preview owner does not match owner scope")
        current = active_store.get_latest_questionnaire_snapshot(owner_id)
        snapshot = build_questionnaire_snapshot(
            owner_id,
            request.answers,
            confirmed_at=request.evaluated_at,
            snapshot_version=1 if current is None else current.snapshot_version + 1,
        )
        return QuestionnairePreviewResponse(snapshot=snapshot)

    @api.post(
        "/api/v1/advisor/profile/questionnaire/confirm",
        response_model=QuestionnaireConfirmationResponse,
    )
    def confirm_full_questionnaire(
        request: QuestionnaireConfirmationRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> QuestionnaireConfirmationResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("questionnaire confirmation owner does not match owner scope")
        current = active_store.get_latest_questionnaire_snapshot(owner_id)
        snapshot = build_questionnaire_snapshot(
            owner_id,
            request.answers,
            confirmed_at=request.confirmed_at,
            snapshot_version=1 if current is None else current.snapshot_version + 1,
        )
        stored, created = active_store.save_questionnaire_snapshot(snapshot)
        return QuestionnaireConfirmationResponse(snapshot=stored, created=created)

    @api.get(
        "/api/v1/advisor/profile/summary",
        response_model=ProfileSummaryResponse,
    )
    def get_profile_summary(
        owner_id: str = Depends(owner_dependency),
    ) -> ProfileSummaryResponse:
        snapshot = active_store.get_latest_questionnaire_snapshot(owner_id)
        behavior = active_store.get_latest_behavior_profile(owner_id)
        policy = active_store.get_display_policy(owner_id) or build_display_policy(
            owner_id,
            50,
            updated_at=active_clock(),
            source=DisplayPolicySource.DEFAULT,
        )
        events = active_store.list_behavior_events(owner_id)
        trade_count = sum(item.event_type == BehaviorEventType.TRADE for item in events)
        snapshot_count = sum(item.event_type == BehaviorEventType.POSITION_SNAPSHOT for item in events)
        gaps: list[str] = []
        actions: list[str] = []
        effective = snapshot.profile if snapshot is not None else None
        if snapshot is None:
            gaps.append("尚未完成 19 题风险问卷")
            actions.append("完成风险测评")
        if trade_count < 3:
            gaps.append(f"90 日交易记录不足：当前 {trade_count} 条，至少需要 3 条")
            actions.append("导入交易记录")
        if snapshot_count < 2:
            gaps.append(f"持仓快照不足：当前 {snapshot_count} 次，至少需要 2 次")
            actions.append("确认持仓快照")
        if snapshot is not None and behavior is not None:
            if behavior.questionnaire_profile_id == snapshot.profile.profile_id:
                effective = effective_risk_profile(snapshot.profile, behavior)
            else:
                gaps.append("行为画像基于旧问卷，需要重新计算")
                actions.append("重新计算行为画像")
        if behavior is not None and behavior.evidence_status.value == "INSUFFICIENT_DATA":
            gaps.append("行为证据尚未达到计算条件")
        return ProfileSummaryResponse(
            owner_id=owner_id,
            questionnaire_snapshot=snapshot,
            behavior_profile=behavior,
            effective_profile=effective,
            display_policy=policy,
            data_gaps=tuple(dict.fromkeys(gaps)),
            next_actions=tuple(dict.fromkeys(actions)),
        )

    @api.post(
        "/api/v1/dev-assist/runs",
        response_model=DevAssistResponse,
    )
    def create_dev_assist_run(
        request: DevAssistRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> DevAssistResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("development assistance owner does not match owner scope")
        return run_dev_assist(request, generated_at=active_clock())

    @api.post(
        "/api/v1/dev-assist/runs/upload",
        response_model=DevAssistResponse,
    )
    async def create_dev_assist_upload_run(
        prd_file: UploadFile = File(...),
        technical_file: UploadFile = File(...),
        target_stack: str = Form("Python 3.11, FastAPI, Pydantic, vanilla JavaScript"),
        owner_id: str = Depends(owner_dependency),
    ) -> DevAssistResponse:
        try:
            prd_content = await prd_file.read()
            technical_content = await technical_file.read()
            prd_text = extract_document_text(prd_file.filename or "prd.txt", prd_content)
            technical_text = extract_document_text(
                technical_file.filename or "technical.txt", technical_content
            )
        except DevAssistError as exc:
            return JSONResponse(
                status_code=422,
                content={
                    "schema_version": "api-error.v1",
                    "error_code": "DEV_ASSIST_DOCUMENT_INVALID",
                    "message": str(exc),
                },
            )
        digest = sha256(prd_content + b"\x00" + technical_content).hexdigest()[:24]
        request = DevAssistRequest(
            run_id=f"dev-assist:{digest}",
            owner_id=owner_id,
            requested_at=active_clock(),
            prd_text=prd_text,
            technical_text=technical_text,
            target_stack=target_stack,
        )
        return run_dev_assist(request, generated_at=active_clock())

    @api.get("/api/v1/runtime/data-mode")
    async def get_runtime_data_mode():
        controller = get_runtime_mode_controller()
        if controller.needs_initial_probe and active_live_finance.is_configured:
            async with live_probe_lock:
                if controller.needs_initial_probe:
                    capabilities = await active_live_finance.probe_capabilities()
                    await controller.apply_fuyao_probe(capabilities, auto_activate=True,
                                                       errors=getattr(active_live_finance, "last_probe_errors", None))
        return JSONResponse(content={"status": "SUCCESS", "data": controller.get_status()})

    @api.put("/api/v1/runtime/data-mode")
    async def update_runtime_data_mode(req: RuntimeDataModeSwitchRequest):
        controller = get_runtime_mode_controller()
        try:
            target_mode = str(req.target_mode).upper()
            if (
                target_mode == "LIVE"
                and active_live_finance.is_configured
                and not controller.is_fuyao_ready
            ):
                async with live_probe_lock:
                    if not controller.is_fuyao_ready:
                        capabilities = await active_live_finance.probe_capabilities()
                        await controller.apply_fuyao_probe(capabilities,
                                                           errors=getattr(active_live_finance, "last_probe_errors", None))
            new_status = await controller.switch_mode(req.target_mode, req.expected_revision)
            return JSONResponse(content={"status": "SUCCESS", "data": new_status})
        except ModeRevisionConflictError as exc:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "CONFLICT",
                    "error_code": "MODE_REVISION_CONFLICT",
                    "message": str(exc),
                    "current_status": controller.get_status(),
                },
            )
        except LiveProviderUnavailableError as exc:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "CONFLICT",
                    "error_code": "LIVE_PROVIDER_UNAVAILABLE",
                    "message": str(exc),
                    "current_status": controller.get_status(),
                },
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_DATA_MODE",
                    "message": str(exc),
                },
            )

    @api.post(
        "/api/v1/decision-events",
        response_model=DecisionEventWriteResponse,
    )
    def create_decision_event(
        result: RecommendationCompositionResult,
        owner_id: str = Depends(owner_dependency),
    ) -> DecisionEventWriteResponse:
        if result.owner_id != owner_id:
            raise StoreOwnerError("result owner does not match owner scope")
        try:
            event = build_decision_event(result, recorded_at=active_clock())
            stored, created = active_store.save(event)
        except (ValidationError, ValueError) as exc:
            raise StoreError("decision event failed contract validation") from exc
        return DecisionEventWriteResponse(event=stored, created=created)

    @api.post(
        "/api/v1/advisor/queries",
        response_model=AdvisorQueryResponse,
    )
    async def create_advisor_query(
        query: AdvisorQueryRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> AdvisorQueryResponse:
        if blocked := reject_fixture_execution_in_live(active_advisor, "投顾查询"):
            return blocked
        if (
            query.questionnaire.owner_id != owner_id
            or query.portfolio.owner_id != owner_id
        ):
            raise StoreOwnerError("query owner does not match owner scope")
        try:
            output = await active_advisor.run(query)
        except AdvisorQueryError:
            raise
        except Exception as exc:
            raise AdvisorQueryError("advisor query was refused") from exc
        try:
            event = build_decision_event(
                output.result,
                recorded_at=active_clock(),
            )
            stored, created = active_store.save(event)
        except (ValidationError, ValueError) as exc:
            raise StoreError("advisor result failed event validation") from exc
        return AdvisorQueryResponse(
            query_id=output.query_id,
            owner_id=output.owner_id,
            profile_id=output.profile_id,
            research_run_id=output.research_run_id,
            status=output.status.value,
            created=created,
            event=stored,
        )

    @api.get(
        "/api/v1/advisor/query-template",
        response_model=AdvisorQueryTemplateResponse,
    )
    def get_advisor_query_template(
        owner_id: str = Depends(owner_dependency),
    ) -> AdvisorQueryTemplateResponse:
        if blocked := reject_fixture_execution_in_live(active_advisor, "投顾查询模板"):
            return blocked
        template = active_advisor.query_template(owner_id)
        return AdvisorQueryTemplateResponse(
            fixture_id=template.fixture_id,
            generated_at=template.generated_at,
            questionnaire=template.questionnaire,
            portfolio=template.portfolio,
        )

    @api.post(
        "/api/v1/advisor/context/portfolio",
        response_model=AdvisorPortfolioContextResponse,
    )
    def confirm_portfolio_context(
        request: AdvisorPortfolioContextRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> AdvisorPortfolioContextResponse:
        if request.portfolio.owner_id != owner_id:
            raise StoreOwnerError("portfolio context owner does not match owner scope")
        try:
            portfolio = PortfolioImportBundle.model_validate(
                request.portfolio.model_dump(mode="python")
            )
            return AdvisorPortfolioContextResponse(
                portfolio=portfolio,
                position_count=len(portfolio.position_snapshot.positions),
                fund_snapshot_count=len(portfolio.fund_holdings),
                holding_count=sum(
                    len(snapshot.holdings) for snapshot in portfolio.fund_holdings
                ),
            )
        except (ValidationError, ValueError) as exc:
            raise AdvisorQueryError("portfolio context was refused") from exc

    @api.post(
        "/api/v1/advisor/context/profile",
        response_model=AdvisorProfileContextResponse,
    )
    def confirm_profile_context(
        request: AdvisorProfileContextRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> AdvisorProfileContextResponse:
        if request.questionnaire.owner_id != owner_id:
            raise StoreOwnerError("profile context owner does not match owner scope")
        try:
            questionnaire = RiskQuestionnaire.model_validate(
                request.questionnaire.model_dump(mode="python")
            )
        except (ValidationError, ValueError) as exc:
            raise ProfileConfirmationError("risk profile confirmation was refused") from exc
        profile = confirm_questionnaire(questionnaire)
        return AdvisorProfileContextResponse(
            questionnaire=questionnaire,
            profile=profile,
        )

    @api.post(
        "/api/v1/advisor/context-memory",
        response_model=ContextMemoryWriteResponse,
    )
    def save_context_memory(
        context: ContextMemoryWriteRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> ContextMemoryWriteResponse:
        if context.owner_id != owner_id:
            raise StoreOwnerError("context memory owner does not match owner scope")
        try:
            record = build_context_memory_record(
                context,
                saved_at=active_clock(),
            )
            stored, created = active_store.save_context_memory(record)
        except StoreError:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise StoreError("context memory request was refused") from exc
        return ContextMemoryWriteResponse(record=stored, created=created)

    @api.get(
        "/api/v1/advisor/context-memory",
        response_model=ContextMemoryListResponse,
    )
    def list_context_memory(
        limit: int = Query(default=20, ge=1, le=100),
        owner_id: str = Depends(owner_dependency),
    ) -> ContextMemoryListResponse:
        try:
            records = active_store.list_context_memory(owner_id, limit=limit)
        except StoreError:
            raise
        except (TypeError, ValueError) as exc:
            raise StoreError("context memory list was refused") from exc
        return ContextMemoryListResponse(owner_id=owner_id, records=records)

    @api.post(
        "/api/v1/advisor/profile-proposals",
        response_model=AdvisorProfileProposalResponse,
    )
    def create_profile_proposal(
        request: AdvisorProfileProposalRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> AdvisorProfileProposalResponse:
        if (
            request.questionnaire.owner_id != owner_id
            or request.extraction.owner_id != owner_id
        ):
            raise StoreOwnerError("profile proposal owner does not match owner scope")
        draft = build_profile_proposal(request.questionnaire, request.extraction)
        return AdvisorProfileProposalResponse(draft=draft)

    @api.post(
        "/api/v1/advisor/profile-proposals/confirm",
        response_model=AdvisorProfileConfirmationResponse,
    )
    def confirm_profile_proposal_endpoint(
        request: AdvisorProfileConfirmationRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> AdvisorProfileConfirmationResponse:
        if (
            request.questionnaire.owner_id != owner_id
            or request.extraction.owner_id != owner_id
        ):
            raise StoreOwnerError("profile confirmation owner does not match owner scope")
        profile = confirm_profile_proposal(
            request.questionnaire,
            request.extraction,
            request.resolutions,
        )
        return AdvisorProfileConfirmationResponse(profile=profile)

    @api.post(
        "/api/v1/advisor/plans",
        response_model=AdvisorPlanResponse,
    )
    def create_advisor_plan(
        request: AdvisorIntentRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> AdvisorPlanResponse:
        if blocked := reject_fixture_execution_in_live(active_specialist, "投顾研究计划"):
            return blocked
        if request.owner_id != owner_id:
            raise StoreOwnerError("intent owner does not match owner scope")
        try:
            matrix = active_specialist.matrix_template(owner_id)
            return build_intent_plan(request, matrix)
        except IntentPlanningError:
            raise
        except Exception as exc:
            raise IntentPlanningError("advisor intent plan was refused") from exc

    @api.get(
        "/api/v1/advisor/research-matrix-template",
        response_model=ResearchMatrixTemplateResponse,
    )
    def get_research_matrix_template(
        owner_id: str = Depends(owner_dependency),
    ) -> ResearchMatrixTemplateResponse:
        if blocked := reject_fixture_execution_in_live(active_specialist, "专家研究矩阵模板"):
            return blocked
        template = active_specialist.matrix_template(owner_id)
        return ResearchMatrixTemplateResponse(
            matrix_id=template.matrix_id,
            owner_id=template.owner_id,
            generated_at=template.generated_at,
            scope_description=template.scope_description,
            roles=tuple(sorted({node.role for node in template.nodes}, key=lambda item: item.value)),
            node_count=len(template.nodes),
            scenarios=tuple(
                ResearchScenarioResponse.model_validate(
                    {
                        "scenario_id": scenario.scenario_id,
                        "label": scenario.label,
                        "description": scenario.description,
                    }
                )
                for scenario in active_specialist.scenarios
            ),
        )

    @api.post(
        "/api/v1/advisor/research-runs",
        response_model=ResearchMatrixResponse,
    )
    async def create_research_matrix_run(
        request: ResearchSpecialistMatrixRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> ResearchMatrixResponse:
        if blocked := reject_fixture_execution_in_live(active_specialist, "专家研究矩阵"):
            return blocked
        if request.owner_id != owner_id:
            raise StoreOwnerError("research request owner does not match owner scope")
        try:
            output = await active_specialist.run(request)
        except SpecialistMatrixError:
            raise
        except Exception as exc:
            raise SpecialistMatrixError("specialist matrix execution was refused") from exc
        try:
            if output.owner_id != owner_id:
                raise SpecialistMatrixError("specialist matrix output owner drifted")
            return _research_matrix_response(output)
        except SpecialistMatrixError:
            raise
        except (AttributeError, KeyError, TypeError, ValidationError, ValueError) as exc:
            raise SpecialistMatrixError("specialist matrix output was refused") from exc

    @api.get(
        "/api/v1/advisor/stock-research-template",
        response_model=StockResearchTemplateResponse,
    )
    def get_stock_research_template(
        owner_id: str = Depends(owner_dependency),
    ) -> StockResearchTemplateResponse:
        if blocked := reject_fixture_execution_in_live(active_stock, "股票研究模板"):
            return blocked
        return active_stock.template(owner_id)

    @api.post(
        "/api/v1/advisor/stock-research-runs",
        response_model=StockResearchResponse,
    )
    async def create_stock_research_run(
        request: StockResearchRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> StockResearchResponse:
        if blocked := reject_fixture_execution_in_live(active_stock, "股票完整研究"):
            return blocked
        if request.owner_id != owner_id:
            raise StoreOwnerError("stock research request owner does not match owner scope")
        try:
            output = await active_stock.run(request)
            if not isinstance(output, StockResearchResponse) or output.owner_id != owner_id:
                raise StockResearchError("stock research output owner drifted")
        except StockResearchError:
            raise
        except Exception as exc:
            raise StockResearchError("stock research execution was refused") from exc
        return output

    @api.get(
        "/api/v1/advisor/fund-research-template",
        response_model=FundResearchTemplateResponse,
    )
    def get_fund_research_template(
        owner_id: str = Depends(owner_dependency),
    ) -> FundResearchTemplateResponse:
        if blocked := reject_fixture_execution_in_live(active_fund, "基金研究模板"):
            return blocked
        return active_fund.template(owner_id)

    @api.post(
        "/api/v1/advisor/fund-research-runs",
        response_model=FundResearchResponse,
    )
    async def create_fund_research_run(
        request: FundResearchRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> FundResearchResponse:
        if blocked := reject_fixture_execution_in_live(active_fund, "基金完整研究"):
            return blocked
        if request.owner_id != owner_id:
            raise StoreOwnerError("fund research request owner does not match owner scope")
        try:
            raw_output = await active_fund.run(request)
            if not isinstance(raw_output, FundResearchResponse):
                raise FundResearchError("fund research output type was invalid")
            # Revalidate at the injection boundary.  A custom service or a
            # model_copy(..., update=...) must not bypass the response contract.
            output = FundResearchResponse.model_validate(
                raw_output.model_dump(mode="python")
            )
            if output.owner_id != owner_id:
                raise FundResearchError("fund research output owner drifted")
            if (
                output.request_id != request.request_id
                or output.subject != request.subject
                or output.period != request.period
                or output.scenario.scenario_id != request.scenario_id
            ):
                raise FundResearchError("fund research output scope drifted")
        except FundResearchError:
            raise
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise FundResearchError("fund research execution was refused") from exc
        return output

    @api.get(
        "/api/v1/advisor/convertible-bond-research-template",
        response_model=ConvertibleBondResearchTemplateResponse,
    )
    def get_convertible_bond_research_template(
        owner_id: str = Depends(owner_dependency),
    ) -> ConvertibleBondResearchTemplateResponse:
        if blocked := reject_fixture_execution_in_live(active_convertible_bond, "可转债研究模板"):
            return blocked
        return active_convertible_bond.template(owner_id)

    @api.post(
        "/api/v1/advisor/convertible-bond-research-runs",
        response_model=ConvertibleBondResearchResponse,
    )
    async def create_convertible_bond_research_run(
        request: ConvertibleBondResearchRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> ConvertibleBondResearchResponse:
        if blocked := reject_fixture_execution_in_live(active_convertible_bond, "可转债完整研究"):
            return blocked
        if request.owner_id != owner_id:
            raise StoreOwnerError(
                "convertible-bond research request owner does not match owner scope"
            )
        try:
            raw_output = await active_convertible_bond.run(request)
            if not isinstance(raw_output, ConvertibleBondResearchResponse):
                raise ConvertibleBondResearchError(
                    "convertible-bond research output type was invalid"
                )
            output = ConvertibleBondResearchResponse.model_validate(
                raw_output.model_dump(mode="python")
            )
            if output.owner_id != owner_id:
                raise ConvertibleBondResearchError(
                    "convertible-bond research output owner drifted"
                )
            expected_manifest_id = getattr(active_convertible_bond, "manifest_id", None)
            expected_node_ids = getattr(active_convertible_bond, "node_ids", None)
            if (
                not isinstance(expected_manifest_id, str)
                or output.manifest_id != expected_manifest_id
                or not isinstance(expected_node_ids, tuple)
                or tuple(node.node_id for node in output.nodes) != expected_node_ids
            ):
                raise ConvertibleBondResearchError(
                    "convertible-bond research output manifest drifted"
                )
            if (
                output.request_id != request.request_id
                or output.subject != request.subject
                or output.period != request.period
                or output.scenario.scenario_id != request.scenario_id
            ):
                raise ConvertibleBondResearchError(
                    "convertible-bond research output scope drifted"
                )
        except ConvertibleBondResearchError:
            raise
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise ConvertibleBondResearchError(
                "convertible-bond research execution was refused"
            ) from exc
        return output

    @api.get(
        "/api/v1/advisor/portfolio-optimization-template",
        response_model=PortfolioOptimizationTemplateResponse,
    )
    def get_portfolio_optimization_template(
        owner_id: str = Depends(owner_dependency),
    ) -> PortfolioOptimizationTemplateResponse:
        if blocked := reject_fixture_execution_in_live(active_portfolio_optimization, "组合优化模板"):
            return blocked
        return active_portfolio_optimization.template(owner_id)

    @api.post(
        "/api/v1/advisor/portfolio-optimization-runs",
        response_model=PortfolioOptimizationResponse,
    )
    async def create_portfolio_optimization_run(
        request: PortfolioOptimizationRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> PortfolioOptimizationResponse:
        if blocked := reject_fixture_execution_in_live(active_portfolio_optimization, "组合优化研究"):
            return blocked
        if request.owner_id != owner_id:
            raise StoreOwnerError(
                "portfolio optimization request owner does not match owner scope"
            )
        try:
            raw_output = await active_portfolio_optimization.run(request)
            if not isinstance(raw_output, PortfolioOptimizationResponse):
                raise PortfolioOptimizationError(
                    "portfolio optimization output type was invalid"
                )
            output = PortfolioOptimizationResponse.model_validate(
                raw_output.model_dump(mode="python")
            )
            if output.owner_id != owner_id:
                raise PortfolioOptimizationError(
                    "portfolio optimization output owner drifted"
                )
            try:
                expected_profile = request.confirmed_profile or confirm_questionnaire(request.questionnaire)
            except ProfileConfirmationError as exc:
                raise PortfolioOptimizationError(
                    "portfolio optimization profile could not be confirmed"
                ) from exc
            if (
                output.request_id != request.request_id
                or output.generated_at != request.generated_at
                or output.profile_id != expected_profile.profile_id
                or output.profile_version != expected_profile.profile_version
                or output.risk_level != expected_profile.risk_level
                or output.portfolio_bundle_id != request.portfolio.bundle_id
                or output.position_snapshot_id
                != request.portfolio.position_snapshot.snapshot_id
            ):
                raise PortfolioOptimizationError(
                    "portfolio optimization output identity drifted"
                )
            if output.scenario.scenario_id != request.scenario_id:
                raise PortfolioOptimizationError(
                    "portfolio optimization output scenario drifted"
                )
        except PortfolioOptimizationError:
            raise
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise PortfolioOptimizationError(
                "portfolio optimization execution was refused"
            ) from exc
        return output

    @api.get(
        "/api/v1/advisor/scenario-simulation-template",
        response_model=ScenarioSimulationTemplateResponse,
    )
    def get_scenario_simulation_template(
        owner_id: str = Depends(owner_dependency),
    ) -> ScenarioSimulationTemplateResponse:
        if blocked := reject_fixture_execution_in_live(active_scenario_simulation, "情景模拟模板"):
            return blocked
        return active_scenario_simulation.template(owner_id)

    @api.post(
        "/api/v1/advisor/scenario-simulation-runs",
        response_model=ScenarioSimulationResponse,
    )
    def create_scenario_simulation_run(
        request: ScenarioSimulationRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> ScenarioSimulationResponse:
        if blocked := reject_fixture_execution_in_live(active_scenario_simulation, "情景模拟研究"):
            return blocked
        if request.owner_id != owner_id:
            raise StoreOwnerError(
                "scenario simulation request owner does not match owner scope"
            )
        try:
            raw_output = active_scenario_simulation.execute(request)
            if not isinstance(raw_output, ScenarioSimulationResponse):
                raise ScenarioSimulationError(
                    "scenario simulation output type was invalid"
                )
            output = ScenarioSimulationResponse.model_validate(
                raw_output.model_dump(mode="python")
            )
            if output.owner_id != owner_id:
                raise ScenarioSimulationError(
                    "scenario simulation output owner drifted"
                )
            try:
                expected_profile = confirm_questionnaire(request.questionnaire)
            except ProfileConfirmationError as exc:
                raise ScenarioSimulationError(
                    "scenario simulation profile could not be confirmed"
                ) from exc
            if (
                output.request_id != request.request_id
                or output.generated_at != request.generated_at
                or output.profile_id != expected_profile.profile_id
                or output.profile_version != expected_profile.profile_version
                or output.baseline.portfolio_bundle_id != request.portfolio.bundle_id
                or output.baseline.position_snapshot_id
                != request.portfolio.position_snapshot.snapshot_id
            ):
                raise ScenarioSimulationError(
                    "scenario simulation output identity drifted"
                )
            if output.scenario.scenario_id != request.scenario_id:
                raise ScenarioSimulationError(
                    "scenario simulation output scenario drifted"
                )
        except ScenarioSimulationError:
            raise
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise ScenarioSimulationError(
                "scenario simulation execution was refused"
            ) from exc
        return output

    @api.get(
        "/api/v1/decision-events",
        response_model=DecisionEventListResponse,
    )
    def list_decision_events(
        owner_id: str = Depends(owner_dependency),
    ) -> DecisionEventListResponse:
        return DecisionEventListResponse(items=active_store.list(owner_id))

    @api.get(
        "/api/v1/decision-events/{event_id}",
        response_model=DecisionEvent,
    )
    def get_decision_event(
        event_id: str,
        owner_id: str = Depends(owner_dependency),
    ) -> DecisionEvent:
        event = active_store.get(owner_id, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="not found")
        return event

    @api.get(
        "/api/v1/advisor/recommendation-history",
        response_model=RecommendationHistoryResponse,
    )
    def get_recommendation_history(
        limit: int = Query(default=20, ge=1, le=100),
        action_filter: str | None = Query(default=None),
        owner_id: str = Depends(owner_dependency),
    ) -> RecommendationHistoryResponse:
        return active_recommendation_history.get_history(
            owner_id=owner_id,
            limit=limit,
            action_filter=action_filter,
        )

    @api.post(
        "/api/v1/advisor/recommendation-history/compare",
        response_model=RecommendationComparisonResponse,
    )
    def compare_recommendation_history(
        request: RecommendationComparisonRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> RecommendationComparisonResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("comparison request owner does not match owner scope")
        try:
            return active_recommendation_history.compare_receipts(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @api.get(
        "/api/v1/advisor/rebalancing-template",
    )
    def get_rebalancing_template(
        owner_id: str = Depends(owner_dependency),
    ) -> dict[str, object]:
        if blocked := reject_fixture_execution_in_live(active_advisor, "再平衡模板"):
            return blocked
        template = active_advisor.query_template(owner_id)
        positions = template.portfolio.position_snapshot.positions
        total_val = sum((p.market_value for p in positions), start=Decimal("0"))
        target_weights = {
            p.asset_id: str((p.market_value / total_val * Decimal("100")).quantize(Decimal("0.01")))
            for p in positions
        }
        return {
            "schema_version": "rebalancing-template.v1",
            "owner_id": owner_id,
            "bundle": template.portfolio.model_dump(mode="json"),
            "target_weights": target_weights,
            "deadband_pct": "0.50",
            "max_turnover_pct": "50.00",
        }

    @api.post(
        "/api/v1/advisor/rebalancing-runs",
        response_model=PortfolioRebalancingResponse,
    )
    def create_rebalancing_run(
        request: PortfolioRebalancingRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> PortfolioRebalancingResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("rebalancing request owner does not match owner scope")
        return active_portfolio_rebalancing.plan_rebalancing(request)

    @api.get(
        "/api/v1/advisor/evaluation-dashboard-summary",
        response_model=EvaluationDashboardResponse,
    )
    def get_evaluation_dashboard_summary(
        owner_id: str = Depends(owner_dependency),
    ) -> EvaluationDashboardResponse:
        if blocked := reject_fixture_execution_in_live(active_evaluation_dashboard, "离线评测看板"):
            return blocked
        req = EvaluationDashboardRequest(
            request_id=f"eval-dash-{int(active_clock().timestamp())}",
            operator_id=owner_id,
            generated_at=active_clock(),
            repeat_count=1,
        )
        return active_evaluation_dashboard.run_dashboard(req)

    @api.post(
        "/api/v1/advisor/evaluation-dashboard-runs",
        response_model=EvaluationDashboardResponse,
    )
    def create_evaluation_dashboard_run(
        request: EvaluationDashboardRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> EvaluationDashboardResponse:
        if blocked := reject_fixture_execution_in_live(active_evaluation_dashboard, "离线评测看板"):
            return blocked
        if request.operator_id != owner_id:
            raise StoreOwnerError("dashboard request operator does not match owner scope")
        return active_evaluation_dashboard.run_dashboard(request)

    @api.get(
        "/api/v1/advisor/explainability-template",
    )
    def get_explainability_template(
        owner_id: str = Depends(owner_dependency),
    ) -> dict[str, object]:
        return {
            "schema_version": "explainability-template.v1",
            "owner_id": owner_id,
            "data_mode": "TEMPLATE_ONLY",
            "calculation_status": "NOT_CALCULATED",
            "requires_portfolio_health": True,
            "risk_score": None,
            "risk_level": None,
            "action_type": None,
            "asset": None,
            "tech_exposure_pct": None,
            "tech_cap_pct": None,
            "top_asset_weight_pct": None,
            "finding_count": 0,
        }

    @api.post(
        "/api/v1/advisor/explainability-runs",
        response_model=AdvancedExplainabilityResponse,
    )
    def create_explainability_run(
        request: AdvancedExplainabilityRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> AdvancedExplainabilityResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("explainability request owner does not match owner scope")
        return active_advanced_explainability.explain_decision(request)

    # -------------------------------------------------------------------------
    # Copilot Direction 2: Live LLM Chat, Tool Calling & Portfolio Parser Routes
    # -------------------------------------------------------------------------
    copilot_agent = CopilotAgent(
        live_finance_provider=active_live_finance,
        skillhub_provider=active_wencai_provider,
    )

    def owner_llm_config(owner_id: str | None) -> LLMConfig:
        setting = persisted_model_setting(owner_id) if owner_id else None
        return LLMConfig(**setting.model_dump()) if setting else copilot_agent.client.config

    def owner_llm_client(owner_id: str | None) -> AsyncLLMClient:
        return AsyncLLMClient(owner_llm_config(owner_id))

    @api.post("/api/v1/advisor/profile-extractions")
    async def natural_profile_extraction(req: NaturalProfileRequest, owner_id: str = Depends(owner_dependency)):
        if req.owner_id != owner_id:
            raise StoreOwnerError("profile extraction owner mismatch")
        try:
            return await extract_natural_profile(req, owner_llm_client(owner_id), active_clock())
        except NaturalProfileError as exc:
            return _error_response(422, "PROFILE_EXTRACTION_REFUSED", str(exc))

    @api.post("/api/v1/advisor/context-memory/search")
    async def search_memory(req: MemorySearchRequest, owner_id: str = Depends(owner_dependency)):
        try:
            return await search_context_memories(active_store, owner_id, req.query, owner_llm_client(owner_id), limit=req.limit)
        except ValueError:
            return _error_response(422, "MEMORY_SEARCH_REFUSED", "检索内容无效或包含敏感信息")

    @api.get("/api/v1/advisor/session-truth")
    def read_session_truth(owner_id: str = Depends(owner_dependency),
                           session_id: str = Query("workbench", pattern=r"^[A-Za-z0-9_.-]{1,100}$")):
        record = active_store.get_session_truth(owner_id, session_id)
        try:
            facts = current_facts(active_store, owner_id, get_runtime_mode_controller().mode.value)
        except TruthInputRequired:
            return {"status":"INPUT_REQUIRED", "revision":record["revision"] if record else 0,
                    "changed_fields":["required_context"], "record":record}
        return truth_status(record, facts)

    @api.get("/api/v1/advisor/workflow")
    def get_workflow(owner_id: str = Depends(owner_dependency)):
        if blocked := reject_fixture_execution_in_live(active_specialist, "研究工作流"):
            return blocked
        matrix = active_specialist.matrix_template(owner_id)
        saved = active_store.get_workflow(owner_id)
        synthetic = service_uses_fixture(active_specialist)
        return {**(saved or {"revision":0, "definition":default_workflow(matrix).model_dump(mode="json")}),
                "catalog":[{"node_id":n.node_id, "role":n.role, "subject":n.subject} for n in matrix.nodes],
                "data_mode":"MOCK" if synthetic else "LIVE",
                "is_synthetic":synthetic,
                "boundary":("固定研究节点与合成数据的编排演练，不执行交易" if synthetic
                            else "真实研究节点编排；只生成研究结果，不执行交易")}

    @api.post("/api/v1/advisor/workflow")
    def save_workflow(req: WorkflowSaveRequest, owner_id: str = Depends(owner_dependency)):
        if blocked := reject_fixture_execution_in_live(active_specialist, "研究工作流"):
            return blocked
        if req.definition.owner_id != owner_id:
            raise StoreOwnerError("workflow owner mismatch")
        try:
            bind_workflow(req.definition, active_specialist.matrix_template(owner_id))
        except ValueError:
            return _error_response(422, "WORKFLOW_INVALID", "节点必须来自当前目录；依赖不能重复、成环或指向未知节点，预算须覆盖节点超时")
        return active_store.save_workflow(owner_id, req.definition.model_dump(mode="json"), req.expected_revision, active_clock().isoformat())

    @api.post("/api/v1/advisor/workflow-runs")
    async def run_workflow(req: WorkflowRunRequest, owner_id: str = Depends(owner_dependency)):
        if blocked := reject_fixture_execution_in_live(active_specialist, "研究工作流"):
            return blocked
        saved = active_store.get_workflow(owner_id)
        if not saved or saved["revision"] != req.expected_revision:
            return _error_response(409, "WORKFLOW_REVISION_CONFLICT", "请重新读取并保存工作流，再执行指定版本")
        definition = WorkflowDefinition.model_validate(saved["definition"])
        matrix = bind_workflow(definition, active_specialist.matrix_template(owner_id))
        request = ResearchSpecialistMatrixRequest(matrix_id=matrix.matrix_id, owner_id=owner_id,
            request_id="workflow-run:" + uuid4().hex, generated_at=active_clock())
        try:
            async with asyncio.timeout(definition.budget_ms / 1000):
                output = await active_specialist.run(request, matrix_override=matrix)
        except TimeoutError:
            return _error_response(408, "WORKFLOW_DEADLINE", "工作流执行超过总预算，已取消")
        synthetic = service_uses_fixture(active_specialist)
        return {"definition_revision":saved["revision"],
                "data_mode":"MOCK" if synthetic else "LIVE", "is_synthetic":synthetic,
                "result":output.model_dump(mode="json")}

    @api.post("/api/v1/advisor/session-truth")
    def confirm_session_truth(req: TruthConfirmation, owner_id: str = Depends(owner_dependency),
                              session_id: str = Query("workbench", pattern=r"^[A-Za-z0-9_.-]{1,100}$")):
        try:
            facts = current_facts(active_store, owner_id, get_runtime_mode_controller().mode.value)
        except TruthInputRequired:
            return _error_response(422, "TRUTH_INPUT_REQUIRED", "请先确认风险问卷与持仓")
        if req.expected_fingerprint is not None and req.expected_fingerprint != fingerprint(facts):
            return _error_response(409, "PREMISE_DRIFT", "预览后的分析前提已变化，请重新核对再确认")
        record = active_store.save_session_truth(owner_id, session_id, facts, req.expected_revision, active_clock().isoformat())
        return truth_status(record, facts)

    @api.post("/api/v1/advisor/session-truth/check")
    def check_truth(req: SessionAssertionsRequest, owner_id: str = Depends(owner_dependency),
                    session_id: str = Query("workbench", pattern=r"^[A-Za-z0-9_.-]{1,100}$")):
        record = active_store.get_session_truth(owner_id, session_id)
        if record is None or record["revision"] != req.expected_revision:
            return _error_response(409, "TRUTH_REVISION_CONFLICT", "请先锁定或重新读取当前前提版本")
        try:
            facts = current_facts(active_store, owner_id, get_runtime_mode_controller().mode.value)
        except TruthInputRequired:
            return _error_response(422, "TRUTH_INPUT_REQUIRED", "请先确认风险问卷与持仓")
        if truth_status(record, facts)["status"] != "LOCKED":
            return _error_response(409, "PREMISE_DRIFT", "当前前提已变化，不能用旧版本继续核验")
        return check_session_assertions(record, facts, req, owner_id=owner_id)

    @api.post("/api/v1/copilot/chat")
    async def copilot_chat_endpoint(
        req: CopilotChatApiRequest,
        request: Request,
        x_owner_id: str | None = Header(default=None, alias="X-Owner-ID"),
    ):
        """Streaming SSE endpoint for live conversational investment copilot."""
        account = getattr(request.state, "account", None)
        if account and not account.admin and req.llm_config:
            return _error_response(403, "ADMIN_REQUIRED", "custom model configuration requires an administrator")
        scoped_owner = x_owner_id.strip() if x_owner_id and x_owner_id.strip() else req.owner_id
        if scoped_owner is not None and req.owner_id is not None and scoped_owner != req.owner_id:
            raise StoreOwnerError("chat owner does not match owner scope")
        if not req.session_truth_id:
            # An unlocked turn is general chat only.  Do not trust profile or
            # portfolio claims supplied without a server-verified truth lock,
            # including stale assistant history from an earlier snapshot.
            req.profile_version = None
            req.behavior_profile_version = None
            req.portfolio_snapshot_id = None
            req.persona_info = None
            req.portfolio_context = None
            req.history = []
        if req.session_truth_id:
            if not scoped_owner:
                raise StoreOwnerError("session truth requires an owner")
            record = active_store.get_session_truth(scoped_owner, req.session_truth_id)
            if not record or record["revision"] != req.session_truth_revision:
                return _error_response(409, "TRUTH_REVISION_CONFLICT", "分析前提版本已变化，请重新读取并确认")
            try:
                facts = current_facts(active_store, scoped_owner, get_runtime_mode_controller().mode.value)
            except TruthInputRequired:
                return _error_response(409, "TRUTH_CONTEXT_CHANGED", "当前缺少已锁定的分析前提，请重新确认")
            if truth_status(record, facts)["status"] != "LOCKED":
                return _error_response(409, "TRUTH_CONTEXT_CHANGED", "画像、持仓或数据模式已变化，请确认新的分析前提")
            profile = facts["profile"]
            bundle = facts["portfolio"]
            if ((req.portfolio_snapshot_id and req.portfolio_snapshot_id != bundle["position_snapshot"]["snapshot_id"])
                    or (req.profile_version is not None and req.profile_version != profile["profile_version"])):
                return _error_response(409, "TRUTH_CLAIM_CONFLICT", "请求引用的画像或持仓版本与锁定前提不一致")
            req.persona_info = {"name":"当前账户", "tag":profile["risk_level"],
                                "max_drawdown":profile["max_drawdown_tolerance_pct"], "budget_cap":"以确定性风险闸门为准"}
            req.portfolio_context = {"session_truth":{"session_id":req.session_truth_id, "revision":record["revision"]},
                                     "data_mode":facts["data_mode"], "portfolio":bundle}
        stored_profile = active_store.get_latest_behavior_profile(scoped_owner) if scoped_owner else None
        stored_policy = active_store.get_display_policy(scoped_owner) if scoped_owner else None
        if stored_policy is None:
            stored_policy = build_display_policy(
                scoped_owner or "anonymous",
                50,
                updated_at=active_clock(),
                source=DisplayPolicySource.DEFAULT,
            )

        persisted_setting = persisted_model_setting(scoped_owner) if scoped_owner else None
        if not req.llm_config and persisted_setting is not None:
            req.llm_config = persisted_setting.model_dump()
        controller = get_runtime_mode_controller()
        configured = bool((req.llm_config or {}).get("api_key")) or copilot_agent.client.is_configured
        if req.model_mode != "MOCK" and not configured:
            return _error_response(409, "MODEL_NOT_CONFIGURED", "请在更多 → 模型设置中配置 API Key")
        if req.model_mode != "MOCK" and controller.mode != DataMode.LIVE:
            return _error_response(409, "DATA_MODE_NOT_LIVE", "真实模型调用要求工具数据同时处于 LIVE")

        async def sse_generator():
            context_event = {
                "type": "analysis_context",
                "display_policy": stored_policy.model_dump(mode="json"),
                "profile_version": req.profile_version,
                "behavior_profile_id": stored_profile.behavior_profile_id if stored_profile else None,
                "behavior_profile_version": stored_profile.profile_version if stored_profile else None,
                "requested_behavior_profile_version": req.behavior_profile_version,
                "portfolio_snapshot_id": req.portfolio_snapshot_id,
                "analysis_steps": [
                    "解析问题意图与结构化槽位",
                    "读取已确认画像和持仓快照",
                    "调用确定性金融工具并核对阈值",
                    "生成带来源和边界的结论",
                ],
                "facts": [
                    f"有效风险等级：{stored_profile.suitability_level.value}"
                    if stored_profile else "尚无行为画像快照"
                ],
                "thresholds": ["AI 信任度 <35 展开审计链", "AI 信任度 >=65 结论优先"],
                "evidence": [item.evidence_id for item in stored_profile.evidence] if stored_profile else [],
                "warnings": [
                    message
                    for message in (
                        "本轮未绑定已锁定的画像与持仓前提；仅可按一般问题回答，不得生成个性化配置结论"
                        if not req.session_truth_id
                        else None,
                        "行为数据不足；不得据此提高风险等级"
                        if stored_profile is None
                        or stored_profile.evidence_status.value == "INSUFFICIENT_DATA"
                        else None,
                        "请求引用的行为画像版本不是当前版本"
                        if stored_profile is not None
                        and req.behavior_profile_version is not None
                        and req.behavior_profile_version != stored_profile.profile_version
                        else None,
                    )
                    if message is not None
                ],
            }
            yield f"data: {json.dumps(context_event, ensure_ascii=False)}\n\n"
            if req.model_mode == "MOCK":
                payload = {"type": "token", "delta": "## 演示回复\n\n当前为 **AI 模拟模式**。\n\n- 可测试对话、持仓导入与页面联动。\n- 正式分析请切换真实接口并配置模型。\n\n|项目|状态|\n|---|---|\n|模型调用|模拟数据|\n|投资结论|未生成|\n\n仅供演示参考，不构成投资建议。"}
                yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                yield "data: [DONE]\n\n"
                return
            history_objs = [CopilotMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in (req.history or [])]
            async with aclosing(copilot_agent.stream_chat(
                user_message=req.message,
                history=history_objs,
                persona_info=req.persona_info,
                portfolio_context=req.portfolio_context,
                llm_config=req.llm_config,
            )) as stream:
                async for chunk in stream:
                    if req.session_truth_id:
                        try:
                            latest = active_store.get_session_truth(scoped_owner, req.session_truth_id)
                            fresh = current_facts(active_store, scoped_owner, get_runtime_mode_controller().mode.value)
                            stable = latest and latest["revision"] == req.session_truth_revision and truth_status(latest, fresh)["status"] == "LOCKED"
                        except (StoreError, TruthInputRequired):
                            stable = False
                        if not stable:
                            yield 'data: {"type":"error","message":"分析前提已变化，本次生成已停止，请重新确认"}\n\n'
                            yield "data: [DONE]\n\n"
                            return
                    payload_str = json.dumps(chunk, ensure_ascii=False)
                    yield f"data: {payload_str}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @api.post("/api/v1/copilot/parse-portfolio")
    async def copilot_parse_portfolio_endpoint(req: CopilotParsePortfolioApiRequest):
        """Natural language to structured portfolio entity extraction."""
        result = await copilot_agent.parse_portfolio_from_text(req.text)
        return JSONResponse(content=result)

    @api.post("/api/v1/copilot/parse-portfolio-ocr")
    async def copilot_parse_portfolio_ocr_endpoint(req: CopilotParsePortfolioOcrApiRequest):
        """Extract structured holdings and cash from screenshot using lightweight RapidOCR."""
        from app.llm.ocr_portfolio_parser import OCRPortfolioParser
        parser = OCRPortfolioParser.get_instance()
        try:
            result = parser.parse_base64_image(req.image_base64)
            return JSONResponse(content=result)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "FAILED",
                    "error": str(exc),
                    "positions": [],
                    "parsed_count": 0,
                },
            )

    @api.post("/api/v1/copilot/validate-portfolio-ocr")
    def copilot_validate_portfolio_ocr_endpoint(
        req: CopilotValidatePortfolioOcrApiRequest,
        owner_id: str = Depends(owner_dependency),
    ):
        """Recalculate edited OCR quantities and all dependent values in Python."""
        from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
        if req.owner_id != owner_id:
            raise StoreOwnerError("OCR portfolio owner does not match owner scope")
        mode = get_runtime_mode_controller().mode
        if mode == DataMode.LIVE and any(
            "MISSING_OBSERVED_FIELDS" in (item.get("review_reasons") or [])
            for item in req.positions
        ):
            return _error_response(
                422,
                "LIVE_OCR_PRICE_REQUIRED",
                "LIVE 持仓存在未核验价格；请提供真实价格后再保存",
            )
        try:
            calculated = recalculate_portfolio_values(
                req.positions, req.cash_cny, req.owner_id,
                allow_synthetic_lookthrough=mode == DataMode.MOCK,
            )
            active_store.save_current_portfolio(owner_id, mode.value, calculated)
            return JSONResponse(content=calculated)
        except (ArithmeticError, TypeError, ValueError) as exc:
            return JSONResponse(
                status_code=422,
                content={"status": "FAILED", "error_code": "OCR_VALUE_VALIDATION_FAILED",
                         "message": str(exc)},
            )

    @api.put("/api/v1/advisor/portfolio/current")
    def replace_current_portfolio(req: ReplacePortfolioApiRequest, owner_id: str = Depends(owner_dependency)):
        if req.owner_id != owner_id:
            raise StoreOwnerError("portfolio owner does not match owner scope")
        if req.data_mode and req.data_mode != get_runtime_mode_controller().mode.value:
            return _error_response(409, "DATA_MODE_CHANGED", "数据模式已变化，请刷新页面后重新保存")
        if not req.positions and req.cash_cny == 0:
            data = {"status": "SUCCESS", "positions": [], "cash_cny": 0, "total_value_cny": 0, "portfolio": None}
            active_store.clear_current_portfolio(owner_id, get_runtime_mode_controller().mode.value)
            return data
        return copilot_validate_portfolio_ocr_endpoint(req, owner_id)

    @api.get("/api/v1/advisor/portfolio/summary")
    def get_portfolio_summary(owner_id: str = Depends(owner_dependency)):
        from app.portfolio.summary import portfolio_summary
        mode = get_runtime_mode_controller().mode.value
        result = portfolio_summary(active_store.get_current_portfolio(owner_id, mode))
        return {**result, "data_mode": mode, "owner_id": owner_id}

    @api.get("/api/v1/advisor/portfolio/current")
    def get_current_portfolio(owner_id: str = Depends(owner_dependency)):
        mode = get_runtime_mode_controller().mode.value
        return {"data_mode": mode, "data": active_store.get_current_portfolio(owner_id, mode)}

    @api.post("/api/v1/copilot/upload-portfolio-ocr")
    async def copilot_upload_portfolio_ocr_endpoint(file: UploadFile = File(...)):
        """Upload image file directly for RapidOCR processing."""
        from app.llm.ocr_portfolio_parser import OCRPortfolioParser
        parser = OCRPortfolioParser.get_instance()
        try:
            content = await file.read()
            result = parser.parse_image_bytes(content)
            return JSONResponse(content=result)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "FAILED",
                    "error": str(exc),
                    "positions": [],
                    "parsed_count": 0,
                },
            )

    @api.post("/api/v1/advisor/portfolio/ocr")
    async def advisor_portfolio_ocr_endpoint(
        file: UploadFile = File(...),
        owner_id: str = Depends(owner_dependency),
    ):
        """Parse a bounded screenshot without persisting the original image."""
        allowed_types = {"image/png", "image/jpeg", "image/webp"}
        if file.content_type not in allowed_types:
            return _error_response(415, "OCR_MEDIA_TYPE", "only PNG, JPEG and WebP images are supported")
        content = await file.read(5 * 1024 * 1024 + 1)
        if not content or len(content) > 5 * 1024 * 1024:
            return _error_response(413, "OCR_FILE_SIZE", "image must be between 1 byte and 5 MiB")
        image_digest = sha256(content).hexdigest()
        from app.llm.ocr_portfolio_parser import OCRPortfolioParser

        try:
            result = OCRPortfolioParser.get_instance().parse_image_bytes(content)
        except Exception:
            return _error_response(400, "OCR_PARSE_FAILED", "portfolio screenshot could not be parsed")
        if get_runtime_mode_controller().mode == DataMode.LIVE:
            try:
                for position in result.get("positions", []):
                    if position.get("asset_class") != "FUND_ETF":
                        position["sector"] = "Unclassified"
                    reasons = list(position.get("review_reasons") or [])
                    if "MISSING_OBSERVED_FIELDS" not in reasons:
                        continue
                    symbol = str(position.get("asset_id") or "")
                    clean_symbol = _validated_exchange_code(
                        symbol, FuyaoFinanceProvider.A_SHARE_PREFIXES
                    )
                    if clean_symbol is None:
                        return _error_response(
                            422,
                            "LIVE_OCR_PRICE_REQUIRED",
                            "截图缺少可核验价格，且当前真实报价服务不支持该标的；不能保存到 LIVE 持仓",
                        )
                    quote = await active_live_finance.get_quote(clean_symbol)
                    if quote is None or quote.get("is_synthetic") is not False:
                        return _error_response(502, "LIVE_OCR_QUOTE_UNAVAILABLE", "真实报价未返回，不能确认 LIVE 持仓")
                    position.update({
                        "asset_id": quote["symbol"],
                        "name": quote.get("name") or position.get("name"),
                        "price": quote["price_cny"],
                        "market_value_cny": round(float(position.get("quantity", 0)) * float(quote["price_cny"]), 2),
                        "cost_price": None,
                        "previous_close": quote.get("previous_close_cny"),
                        "observed_at": quote["observed_at"],
                        "price_source": quote.get("source") or "Fuyao structured financial data API",
                        "sector": "Unclassified",
                        "review_reasons": [reason for reason in reasons if reason != "MISSING_OBSERVED_FIELDS"],
                    })
                    position["needs_review"] = bool(position["review_reasons"])
                result["has_low_confidence_items"] = any(
                    bool(position.get("needs_review"))
                    for position in result.get("positions", [])
                )
            except FuyaoProviderError as exc:
                if exc.code in CAPABILITY_FAILURE_CODES:
                    await get_runtime_mode_controller().record_fuyao_capability_failure("stock_quote", exc.code)
                return _error_response(502, exc.code, exc.safe_message)
        result.update({
            "owner_id": owner_id,
            "image_digest": image_digest,
            "confirmation_status": "REVIEW_REQUIRED" if result.get("has_low_confidence_items") else "CALCULATED",
            "original_image_persisted": False,
        })
        return JSONResponse(content=result)

    @api.post("/api/v1/advisor/portfolio/ocr/confirm")
    def advisor_portfolio_ocr_confirm_endpoint(
        req: CopilotConfirmPortfolioOcrApiRequest,
        owner_id: str = Depends(owner_dependency),
    ):
        """Confirm edited OCR rows, recalculate them, and persist only structured data."""
        if req.owner_id != owner_id:
            raise StoreOwnerError("OCR confirmation owner does not match owner scope")
        from app.llm.ocr_portfolio_parser import recalculate_portfolio_values

        mode = get_runtime_mode_controller().mode
        if mode == DataMode.LIVE and any(
            "MISSING_OBSERVED_FIELDS" in item.review_reasons for item in req.positions
        ):
            return _error_response(
                422,
                "LIVE_OCR_PRICE_REQUIRED",
                "LIVE 持仓存在未核验价格；请重新识别并取得真实报价后再确认",
            )
        try:
            confirmed_positions = [
                item.model_dump(mode="json") for item in req.positions
            ]
            calculated = recalculate_portfolio_values(
                confirmed_positions, req.cash_cny, owner_id,
                allow_synthetic_lookthrough=mode == DataMode.MOCK,
            )
            portfolio = PortfolioImportBundle.model_validate(calculated["portfolio"])
            confirmed_at = active_clock()
            confirmed_payload = json.dumps(
                {"positions": calculated["positions"], "cash_cny": calculated["cash_cny"]},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
            record = PortfolioOcrConfirmation(
                confirmation_id="ocr-confirmation:" + sha256(
                    f"{owner_id}:{req.image_digest}".encode("utf-8")
                ).hexdigest()[:32],
                owner_id=owner_id,
                image_digest=req.image_digest,
                confirmed_payload_hash=sha256(confirmed_payload).hexdigest(),
                confirmed_at=confirmed_at,
                portfolio=portfolio,
            )
            stored, created = active_store.save_portfolio_ocr_confirmation(record)
            if not created:
                calculated["portfolio"] = stored.portfolio.model_dump(mode="json")
            behavior_event = behavior_event_from_portfolio(
                stored.portfolio,
                source="user-confirmed OCR portfolio",
            )
            active_store.save_behavior_events(owner_id, (behavior_event,))
        except StoreConflictError:
            raise
        except (ArithmeticError, TypeError, ValueError, ValidationError):
            return _error_response(422, "OCR_VALUE_VALIDATION_FAILED", "confirmed OCR rows failed deterministic validation")
        calculated.update({
            "confirmation": stored.model_dump(mode="json"),
            "created": created,
            "confirmation_status": "CALCULATED",
            "original_image_persisted": False,
        })
        active_store.save_current_portfolio(owner_id, mode.value, calculated)
        return JSONResponse(content=calculated)

    @api.get("/api/v1/user/model-settings")
    def get_user_model_settings(owner_id: str = Depends(owner_dependency)):
        setting = persisted_model_setting(owner_id)
        cfg = setting or copilot_agent.client.config
        setting_scope = (
            "LOCAL_MACHINE"
            if active_secret_store is not None and not accounts
            else "USER"
        )
        return {"is_configured": bool(cfg.api_key), "scope": setting_scope if setting else "SERVER",
                "model": cfg.model, "base_url": cfg.base_url,
                "persistence": "OS_PROTECTED" if active_secret_store is not None else "PROCESS_ONLY"}

    @api.put("/api/v1/user/model-settings")
    def save_user_model_settings(req: CopilotConfigApiRequest, owner_id: str = Depends(owner_dependency)):
        from urllib.parse import urlsplit
        try:
            url = urlsplit(req.base_url.strip())
            port = url.port
        except ValueError:
            raise HTTPException(status_code=422, detail="模型服务地址格式无效") from None
        if url.scheme != "https" or url.hostname not in {"api.deepseek.com", "api.openai.com", "dashscope.aliyuncs.com"} or port not in (None, 443) or url.username or url.password or url.query or url.fragment:
            raise HTTPException(status_code=422, detail="请选择支持的 HTTPS 模型服务地址")
        if not req.model.strip() or len(req.model) > 100 or len(req.api_key) > 4096:
            raise HTTPException(status_code=422, detail="模型名称或密钥格式无效")
        if req.api_key.strip():
            setting = req.model_copy(update={"api_key": req.api_key.strip(), "base_url": req.base_url.strip().rstrip("/")})
            scope = model_setting_scope(owner_id)
            if active_secret_store is not None:
                try:
                    active_secret_store.set(f"llm:{scope}", setting.model_dump_json())
                except (SecretProtectionError, ValueError) as exc:
                    raise HTTPException(status_code=503, detail="模型密钥安全保存失败") from exc
            user_model_settings[scope] = setting
        else:
            scope = model_setting_scope(owner_id)
            if active_secret_store is not None:
                try:
                    active_secret_store.delete(f"llm:{scope}")
                except (SecretProtectionError, ValueError) as exc:
                    raise HTTPException(status_code=503, detail="模型密钥安全删除失败") from exc
            user_model_settings.pop(scope, None)
        return get_user_model_settings(owner_id)

    @api.post("/api/v1/user/model-settings/test")
    async def test_user_model_settings(owner_id: str = Depends(owner_dependency)):
        config = owner_llm_config(owner_id)
        if not config.api_key:
            return _error_response(409, "MODEL_NOT_CONFIGURED", "请先保存 API Key")
        client = AsyncLLMClient(config.model_copy(update={"timeout_seconds": 8}))
        async def probe():
            async with aclosing(client.stream_chat([{"role": "user", "content": "Reply OK."}])) as stream:
                async for event in stream:
                    if event.get("type") == "error":
                        return False
                    if event.get("type") == "content" and event.get("delta"):
                        return True
            return False
        try:
            ok = await asyncio.wait_for(probe(), timeout=10)
        except (TimeoutError, ValueError):
            ok = False
        if not ok:
            return _error_response(502, "MODEL_TEST_FAILED", "模型未返回有效内容，请检查配置或稍后重试")
        return {"status": "PASS"}

    @api.post("/api/v1/copilot/config")
    def copilot_update_config_endpoint(
        req: CopilotConfigApiRequest,
        owner_id: str = Depends(owner_dependency),
    ):
        """Compatibility endpoint; apply the same owner scope and allowlist as model settings."""
        return save_user_model_settings(req, owner_id)

    @api.get("/api/v1/copilot/config")
    def copilot_get_config_endpoint(owner_id: str = Depends(owner_dependency)):
        """Compatibility endpoint; never disclose or partially echo credentials."""
        return get_user_model_settings(owner_id)

    VALID_A_SHARE_PREFIXES = (
        "600", "601", "603", "605",  # SSE Main
        "688", "689",                # SSE STAR
        "000", "001", "002", "003",  # SZSE Main / SME
        "300", "301",                # SZSE ChiNext
        "82", "83", "87", "88", "92", # BSE
        "510", "512", "513", "515", "588", # SSE ETF
        "159",                       # SZSE ETF
        "110", "113", "123", "127", "128", # Convertible Bonds
    )
    VALID_EXCHANGE_FUND_PREFIXES = ("510", "512", "513", "515", "588", "159")

    def _validated_exchange_code(
        value: str, allowed_prefixes: tuple[str, ...]
    ) -> str | None:
        match = re.fullmatch(r"(?P<code>\d{6})(?:\.(?P<suffix>SH|SZ|BJ))?", value.strip().upper())
        if match is None:
            return None
        clean_code = match.group("code")
        if not clean_code.startswith(allowed_prefixes):
            return None
        suffix = match.group("suffix")
        if suffix is not None and suffix != market_prefix(clean_code).upper():
            return None
        return clean_code

    async def _auto_complete_security_baseline(clean_code: str) -> dict[str, Any] | None:
        """Fetch the resilient quote chain; never manufacture missing observations."""
        if clean_code in A_SHARE_DATABASE:
            baseline = A_SHARE_DATABASE[clean_code]
        else:
            baseline = {}
        quote = await active_market_quotes.get_quote(clean_code)
        if quote is None:
            return None
        record_data = {**baseline, **quote, "auto_indexed": True,
                       "audit_note": "行情经主备快照链获取；缺失的财务字段保持显式缺失。"}
        A_SHARE_DATABASE[clean_code] = record_data
        return record_data

    @api.post("/api/v1/copilot/auto-index-security")
    async def copilot_auto_index_security(symbol: str = Query(...)):
        """Automatically complete the missing baseline dependency for a valid security."""
        clean_code = _validated_exchange_code(symbol, VALID_A_SHARE_PREFIXES)
        if clean_code is None:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_SECURITY_CODE",
                    "message": f"证券代码格式无效：[{symbol}] 不符合 6 位数字代码规范。",
                },
            )
        controller = get_runtime_mode_controller()
        if controller.mode == DataMode.LIVE:
            try:
                data = await active_live_finance.get_quote(symbol)
            except FuyaoProviderError as exc:
                if exc.code in CAPABILITY_FAILURE_CODES:
                    await controller.record_fuyao_capability_failure("stock_quote", exc.code)
                return JSONResponse(status_code=503, content={
                    "status": "FAILED", "error_code": exc.code,
                    "message": exc.safe_message,
                })
            if data is None:
                return JSONResponse(status_code=404, content={
                    "status": "NOT_FOUND", "error_code": "SECURITY_NOT_FOUND",
                    "message": f"扶摇数据接口未返回标的 [{clean_code}] 的行情。",
                })
            return JSONResponse(content={
                "status": "SUCCESS",
                "message": f"已从扶摇接口取得标的 [{clean_code} {data.get('name', '')}] 行情；未写入模拟底稿。",
                "data": data,
                "auto_completed": False,
            })
        data = await _auto_complete_security_baseline(clean_code)
        if data is None:
            return JSONResponse(status_code=503, content={
                "status": "FAILED", "error_code": "MARKET_DATA_UNAVAILABLE",
                "message": f"标的 [{clean_code}] 的主源、备用源与静态底稿均不可用。",
            })
        return JSONResponse(
            content={
                "status": "SUCCESS",
                "message": f"已自动完成行情前置依赖：标的 [{clean_code} {data.get('name', '')}] 快照已建档；缺失财务字段保持显式标注。",
                "data": data,
                "auto_completed": True,
            }
        )

    @api.post(
        "/api/v1/advisor/custom-stress-scenarios",
        response_model=CustomStressScenarioResponse,
    )
    def create_custom_stress_scenario(
        request: CustomStressScenarioRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> CustomStressScenarioResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("custom stress request owner does not match owner scope")
        try:
            return calculate_custom_stress(request)
        except ValueError:
            return _error_response(422, "STRESS_INPUT_INCOMPLETE", "持仓含缺失或未分类的行业暴露，无法执行五行业压力测试；请先补齐穿透数据。")

    @api.post(
        "/api/v1/advisor/portfolio-health",
        response_model=PortfolioHealthResponse,
    )
    def create_portfolio_health(
        request: PortfolioHealthRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> PortfolioHealthResponse:
        if request.owner_id != owner_id:
            raise StoreOwnerError("portfolio health request owner does not match owner scope")
        return calculate_portfolio_health(request)

    @api.post(
        "/api/v1/advisor/portfolio/refresh",
        response_model=PortfolioRefreshResponse,
    )
    async def refresh_advisor_portfolio(
        request: PortfolioRefreshRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> PortfolioRefreshResponse:
        """Refresh portfolio market observations without falling back to MOCK."""
        if request.owner_id != owner_id:
            raise StoreOwnerError("portfolio refresh request owner does not match owner scope")
        controller = get_runtime_mode_controller()
        if controller.mode == DataMode.LIVE:
            if not controller.is_wencai_ready:
                return JSONResponse(
                    status_code=409,
                    content={
                        "status": "BLOCKED",
                        "error_code": "LIVE_PROVIDER_UNAVAILABLE",
                        "message": "问财组合刷新能力未通过凭据与接口契约校验。",
                        "missing_fields": ["WENCAI_RESEARCH_AND_REFRESH"],
                    },
                )
            response = await refresh_portfolio_live(request, active_wencai_provider)
            if any(row.provider_status == ProviderStatus.FAILED.value for row in response.positions):
                await controller.record_wencai_failure("PORTFOLIO_REFRESH_FAILED")
            return response
        return refresh_portfolio_mock(request)

    @api.post("/api/v1/runtime/provider-query")
    async def execute_live_provider_query(
        request: LiveProviderQueryRequest,
    ) -> JSONResponse:
        """Expose the verified provider contract for read-only research tools."""
        controller = get_runtime_mode_controller()
        if controller.mode != DataMode.LIVE or not controller.is_wencai_ready:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "BLOCKED",
                    "error_code": "LIVE_PROVIDER_UNAVAILABLE",
                    "message": "当前不是可用的问财 LIVE 研究模式。",
                    "missing_fields": ["WENCAI_RESEARCH_AND_REFRESH"],
                },
            )
        provider_request = ProviderRequest(
            request_id=request.request_id,
            operation=request.operation,
            subject=request.subject,
            as_of=request.as_of,
            required_fields=request.required_fields,
            parameters=request.parameters,
        )
        result = await active_wencai_provider.execute(provider_request)
        if result.status == ProviderStatus.FAILED:
            error_code = result.issues[0].code.value if result.issues else "PROVIDER_FAILED"
            await controller.record_wencai_failure(error_code)
        status_code = 200 if result.status in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL, ProviderStatus.EMPTY} else 502
        return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))

    @api.get("/api/v1/copilot/live-quote")
    async def copilot_live_quote_endpoint(
        symbol: str = "300750",
        auto_complete_dependency: bool = False,
    ):
        """Query real-time stock quote and valuation data."""
        clean_code = _validated_exchange_code(symbol, VALID_A_SHARE_PREFIXES)
        if clean_code is None:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_SECURITY_CODE",
                    "message": f"证券代码格式无效：[{symbol}] 不符合 6 位数字代码规范。",
                },
            )
        controller = get_runtime_mode_controller()
        if controller.mode == DataMode.LIVE:
            try:
                data = await active_live_finance.get_quote(symbol)
            except FuyaoProviderError as exc:
                if exc.code in CAPABILITY_FAILURE_CODES:
                    await controller.record_fuyao_capability_failure("stock_quote", exc.code)
                return JSONResponse(status_code=503, content={
                    "status": "FAILED",
                    "error_code": exc.code,
                    "message": exc.safe_message,
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "fuyao_finance_api",
                        "provider_serving_mode": "UNAVAILABLE",
                        "is_synthetic": False,
                    },
                })
            if data is None:
                return JSONResponse(status_code=404, content={
                    "status": "NOT_FOUND",
                    "error_code": "SECURITY_NOT_FOUND",
                    "message": f"扶摇数据接口未返回标的 [{symbol}] 的行情。",
                })
            return JSONResponse(content={
                "status": "SUCCESS",
                "data": data,
                "execution_context": {
                    "data_mode": "LIVE",
                    "provider": "fuyao_finance_api",
                    "provider_serving_mode": data["provider_tier"],
                    "is_synthetic": False,
                    "observed_at": data.get("observed_at"),
                    "retrieved_at": data["retrieved_at"],
                    "quote_latency_ms": data["quote_latency_ms"],
                    "staleness_seconds": data["staleness_seconds"],
                    "missing_fields": data["missing_fields"],
                },
            })

        data = await FallbackStaticProvider().get_quote(clean_code)
        if not data and auto_complete_dependency:
            data = await _auto_complete_security_baseline(clean_code)

        if not data:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "NOT_FOUND",
                    "error_code": "SECURITY_NOT_FOUND",
                    "message": f"未收录标的底稿：当前量化底稿库尚未收录标的 [{clean_code}] 的行情快照或审计财报底稿，拒绝生成未经核验的虚假研判。",
                },
            )
        return JSONResponse(
            content={
                "status": "SUCCESS",
                "data": data,
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": data["provider_tier"],
                    "provider_serving_mode": data["provider_tier"],
                    "is_synthetic": data["is_synthetic"],
                    "observed_at": data.get("observed_at"),
                    "retrieved_at": data["retrieved_at"],
                    "quote_latency_ms": data["quote_latency_ms"],
                    "staleness_seconds": data["staleness_seconds"],
                    "missing_fields": data["missing_fields"],
                },
            }
        )

    @api.get("/api/v1/copilot/live-fund")
    async def copilot_live_fund_endpoint(fund_code: str = "588000"):
        """Query the latest disclosed fund/ETF look-through holdings."""
        clean_code = _validated_exchange_code(fund_code, VALID_EXCHANGE_FUND_PREFIXES)
        if clean_code is None:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_FUND_CODE",
                    "message": f"基金代码格式无效：[{fund_code}] 不符合 6 位数字代码规范。",
                },
            )
        controller = get_runtime_mode_controller()
        if controller.mode == DataMode.LIVE:
            try:
                data = await active_live_finance.get_fund_lookthrough(fund_code)
            except FuyaoProviderError as exc:
                if exc.code in CAPABILITY_FAILURE_CODES:
                    await controller.record_fuyao_capability_failure("fund_lookthrough", exc.code)
                return JSONResponse(status_code=503, content={
                    "status": "FAILED",
                    "error_code": exc.code,
                    "message": exc.safe_message,
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "fuyao_finance_api",
                        "provider_serving_mode": "UNAVAILABLE",
                        "is_synthetic": False,
                    },
                })
            if data is None:
                return JSONResponse(status_code=404, content={
                    "status": "NOT_FOUND",
                    "error_code": "FUND_NOT_FOUND",
                    "message": f"扶摇数据接口未返回基金 [{fund_code}] 的披露持仓。",
                })
            return JSONResponse(content={
                "status": "SUCCESS",
                "data": data,
                "execution_context": {
                    "data_mode": "LIVE",
                    "provider": "fuyao_finance_api",
                    "provider_serving_mode": data["provider_tier"],
                    "is_synthetic": False,
                    "observed_at": data["observed_at"],
                    "retrieved_at": data["retrieved_at"],
                    "staleness_seconds": data["staleness_seconds"],
                    "missing_fields": data["missing_fields"],
                    "data_freshness_label": data["data_freshness_label"],
                },
            })

        data = ETF_LOOKTHROUGH_DATABASE.get(clean_code)
        if not data:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "NOT_FOUND",
                    "error_code": "FUND_NOT_FOUND",
                    "message": f"未收录基金底稿：当前量化底稿库尚未收录基金 [{clean_code}] 的穿透持仓底稿。",
                },
            )
        return JSONResponse(
            content={
                "status": "SUCCESS",
                "data": data,
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "static_market_provider",
                    "provider_serving_mode": "SYNTHETIC_FIXTURE",
                    "is_synthetic": True,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "missing_fields": [],
                },
            }
        )

    return api


_DEFAULT_SECRET_STORE = (
    ProtectedSecretStore(
        os.getenv("PRISM_SECRET_STORE_PATH")
        or str(Path(__file__).resolve().parents[2] / "data/private/prism-secrets.json")
    )
    if os.name == "nt"
    else None
)

app = create_app(
    database_url=os.getenv("PRISM_DATABASE_URL") or None,
    database_path=os.getenv("PRISM_DB_PATH") or str(Path(__file__).resolve().parents[2] / "data/private/prism.sqlite3"),
    auth_accounts_path=os.getenv("PRISM_AUTH_ACCOUNTS_FILE") or None,
    secret_store=_DEFAULT_SECRET_STORE,
)


__all__ = ["app", "create_app"]
