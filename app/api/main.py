"""Owner-scoped HTTP API and static explainable workbench."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

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
)
from app.evaluation import (
    EvaluationDashboardRequest,
    EvaluationDashboardResponse,
)
from app.explainability import (
    AdvancedExplainabilityRequest,
    AdvancedExplainabilityResponse,
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
from app.providers.live_market import A_SHARE_DATABASE, ETF_LOOKTHROUGH_DATABASE
from app.runtime.mode import (
    DataMode,
    LiveProviderUnavailableError,
    ModeRevisionConflictError,
    get_runtime_mode_controller,
)
from typing import Any
import json


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
    persona_id: str | None = "persona-zhang-r3"
    persona_info: dict[str, Any] | None = None
    portfolio_context: dict[str, Any] | None = None
    history: list[dict[str, Any]] | None = None
    stream: bool = True
    llm_config: dict[str, Any] | None = None


class CopilotParsePortfolioApiRequest(BaseModel):
    text: str


class CopilotParsePortfolioOcrApiRequest(BaseModel):
    image_base64: str = Field(description="Base64-encoded image string or data URI")


class CopilotValidatePortfolioOcrApiRequest(BaseModel):
    owner_id: str = Field(min_length=1)
    positions: list[dict[str, Any]]
    cash_cny: Decimal = Field(ge=0)


class CopilotConfigApiRequest(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"


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
) -> FastAPI:
    """Create an API instance with an explicitly injectable store and clock.

    The default store is process-local memory, so a caller must inject a path-backed
    ``SQLiteDecisionEventStore`` when local persistence across restarts is desired.
    """

    owned_store = store is None
    active_store = store or SQLiteDecisionEventStore(":memory:")
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
    active_market_quotes = market_provider or CompositeMarketProvider()
    active_wencai_provider = wencai_provider or WencaiSkillHubProvider()

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
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")

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

    @api.get("/api/v1/runtime/data-mode")
    def get_runtime_data_mode():
        controller = get_runtime_mode_controller()
        return JSONResponse(content={"status": "SUCCESS", "data": controller.get_status()})

    @api.put("/api/v1/runtime/data-mode")
    async def update_runtime_data_mode(req: RuntimeDataModeSwitchRequest):
        controller = get_runtime_mode_controller()
        try:
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
        return active_stock.template(owner_id)

    @api.post(
        "/api/v1/advisor/stock-research-runs",
        response_model=StockResearchResponse,
    )
    async def create_stock_research_run(
        request: StockResearchRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> StockResearchResponse:
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
        return active_fund.template(owner_id)

    @api.post(
        "/api/v1/advisor/fund-research-runs",
        response_model=FundResearchResponse,
    )
    async def create_fund_research_run(
        request: FundResearchRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> FundResearchResponse:
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
        return active_convertible_bond.template(owner_id)

    @api.post(
        "/api/v1/advisor/convertible-bond-research-runs",
        response_model=ConvertibleBondResearchResponse,
    )
    async def create_convertible_bond_research_run(
        request: ConvertibleBondResearchRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> ConvertibleBondResearchResponse:
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
        return active_portfolio_optimization.template(owner_id)

    @api.post(
        "/api/v1/advisor/portfolio-optimization-runs",
        response_model=PortfolioOptimizationResponse,
    )
    async def create_portfolio_optimization_run(
        request: PortfolioOptimizationRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> PortfolioOptimizationResponse:
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
                expected_profile = confirm_questionnaire(request.questionnaire)
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
        return active_scenario_simulation.template(owner_id)

    @api.post(
        "/api/v1/advisor/scenario-simulation-runs",
        response_model=ScenarioSimulationResponse,
    )
    def create_scenario_simulation_run(
        request: ScenarioSimulationRequest,
        owner_id: str = Depends(owner_dependency),
    ) -> ScenarioSimulationResponse:
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
    copilot_agent = CopilotAgent()

    @api.post("/api/v1/copilot/chat")
    async def copilot_chat_endpoint(req: CopilotChatApiRequest):
        """Streaming SSE endpoint for live conversational investment copilot."""
        async def sse_generator():
            history_objs = [CopilotMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in (req.history or [])]
            async for chunk in copilot_agent.stream_chat(
                user_message=req.message,
                history=history_objs,
                persona_info=req.persona_info,
                portfolio_context=req.portfolio_context,
                llm_config=req.llm_config,
            ):
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
        try:
            return JSONResponse(content=recalculate_portfolio_values(req.positions, req.cash_cny, req.owner_id))
        except (ArithmeticError, TypeError, ValueError) as exc:
            return JSONResponse(
                status_code=422,
                content={"status": "FAILED", "error_code": "OCR_VALUE_VALIDATION_FAILED",
                         "message": str(exc)},
            )

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

    @api.post("/api/v1/copilot/config")
    def copilot_update_config_endpoint(req: CopilotConfigApiRequest):
        """Update active LLM client configuration in memory."""
        from app.llm.client import LLMConfig
        copilot_agent.client.config = LLMConfig(
            api_key=req.api_key.strip(),
            base_url=req.base_url.strip(),
            model=req.model.strip(),
        )
        return JSONResponse(
            content={
                "status": "SUCCESS",
                "is_configured": copilot_agent.client.is_configured,
                "model": copilot_agent.client.config.model,
                "base_url": copilot_agent.client.config.base_url,
            }
        )

    @api.get("/api/v1/copilot/config")
    def copilot_get_config_endpoint():
        """Get active LLM client configuration state."""
        cfg = copilot_agent.client.config
        masked_key = (cfg.api_key[:3] + "..." + cfg.api_key[-4:]) if len(cfg.api_key) > 7 else ("***" if cfg.api_key else "")
        return JSONResponse(
            content={
                "is_configured": copilot_agent.client.is_configured,
                "masked_api_key": masked_key,
                "base_url": cfg.base_url,
                "model": cfg.model,
            }
        )

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
        clean_code = symbol.split(".")[0].strip()
        if not clean_code.isdigit() or len(clean_code) != 6:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_SECURITY_CODE",
                    "message": f"证券代码格式无效：[{symbol}] 不符合 6 位数字代码规范。",
                },
            )
        if not any(clean_code.startswith(p) for p in VALID_A_SHARE_PREFIXES):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_SECURITY_CODE",
                    "message": f"证券代码格式无效：标的代码 [{clean_code}] 非沪深北交易所合规证券前缀（合规前缀如 60/688/00/300/8/51/159/11/12）。",
                },
            )
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
        return calculate_custom_stress(request)

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
            if not controller.is_live_ready:
                return JSONResponse(
                    status_code=409,
                    content={
                        "status": "BLOCKED",
                        "error_code": "LIVE_PROVIDER_UNAVAILABLE",
                        "message": "LIVE 数据源未通过凭据与接口契约校验。",
                        "missing_fields": list(controller.live_readiness_issues),
                    },
                )
            return await refresh_portfolio_live(request, active_wencai_provider)
        return refresh_portfolio_mock(request)

    @api.post("/api/v1/runtime/provider-query")
    async def execute_live_provider_query(
        request: LiveProviderQueryRequest,
    ) -> JSONResponse:
        """Expose the verified provider contract for read-only research tools."""
        controller = get_runtime_mode_controller()
        if controller.mode != DataMode.LIVE or not controller.is_live_ready:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "BLOCKED",
                    "error_code": "LIVE_PROVIDER_UNAVAILABLE",
                    "message": "当前不是可用的 LIVE 官方数据模式。",
                    "missing_fields": list(controller.live_readiness_issues),
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
        status_code = 200 if result.status in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL, ProviderStatus.EMPTY} else 502
        return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))

    @api.get("/api/v1/copilot/live-quote")
    async def copilot_live_quote_endpoint(
        symbol: str = "300750",
        auto_complete_dependency: bool = False,
    ):
        """Query real-time stock quote and valuation data."""
        controller = get_runtime_mode_controller()
        if controller.mode == DataMode.LIVE:
            if not controller.is_live_ready:
                return JSONResponse(
                    status_code=409,
                    content={
                        "status": "BLOCKED",
                        "error_code": "LIVE_PROVIDER_UNAVAILABLE",
                        "message": "LIVE 数据源未通过凭据与接口契约校验，未回退到 MOCK。",
                        "execution_context": {
                            "data_mode": "LIVE",
                            "provider": "wencai_skillhub_provider",
                            "provider_serving_mode": "UNAVAILABLE",
                            "is_synthetic": False,
                            "missing_fields": list(controller.live_readiness_issues),
                        },
                    },
                )
            result = await active_wencai_provider.execute(
                ProviderRequest(
                    request_id=f"live-quote-{datetime.now(UTC).timestamp()}",
                    operation=ProviderOperation.MARKET_DATA,
                    subject=symbol,
                    required_fields=("price_cny", "observed_at", "sector"),
                )
            )
            if result.status not in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL} or not result.records:
                return JSONResponse(
                    status_code=502,
                    content={
                        "status": result.status.value,
                        "error_code": "LIVE_PROVIDER_FAILED",
                        "message": "官方 LIVE 行情未返回可核验记录，未回退到 MOCK。",
                        "execution_context": {
                            "data_mode": "LIVE",
                            "provider": result.provider,
                            "provider_serving_mode": result.serving_mode.value,
                            "is_synthetic": False,
                            "retrieved_at": result.retrieved_at.isoformat(),
                            "missing_fields": list(result.missing_fields),
                            "issues": [issue.safe_message for issue in result.issues],
                        },
                    },
                )
            data = dict(result.records[0].fields)
            data.setdefault("source", result.records[0].source)
            data["provider_tier"] = "LIVE_PRIMARY"
            data["is_synthetic"] = False
            data["retrieved_at"] = result.retrieved_at.isoformat()
            return JSONResponse(
                status_code=200,
                content={
                    "status": result.status.value,
                    "data": data,
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": result.provider,
                        "provider_serving_mode": result.serving_mode.value,
                        "is_synthetic": False,
                        "observed_at": data.get("observed_at"),
                        "retrieved_at": result.retrieved_at.isoformat(),
                        "missing_fields": list(result.missing_fields),
                    },
                },
            )

        clean_code = symbol.split(".")[0].strip()
        if not clean_code.isdigit() or len(clean_code) != 6:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_SECURITY_CODE",
                    "message": f"证券代码格式无效：[{symbol}] 不符合 6 位数字代码规范。",
                },
            )
        if not any(clean_code.startswith(p) for p in VALID_A_SHARE_PREFIXES):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_SECURITY_CODE",
                    "message": f"证券代码格式无效：标的代码 [{clean_code}] 非沪深北交易所合规证券前缀（合规前缀如 60/688/00/300/8/51/159/11/12）。",
                },
            )
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
        """Query real-time fund/ETF look-through holdings."""
        controller = get_runtime_mode_controller()
        if controller.mode == DataMode.LIVE:
            if not controller.is_live_ready:
                return JSONResponse(
                    status_code=409,
                    content={
                        "status": "BLOCKED",
                        "error_code": "LIVE_PROVIDER_UNAVAILABLE",
                        "message": "LIVE 基金数据源未通过凭据与接口契约校验，未回退到 MOCK。",
                        "execution_context": {
                            "data_mode": "LIVE",
                            "provider": "wencai_skillhub_provider",
                            "provider_serving_mode": "UNAVAILABLE",
                            "is_synthetic": False,
                            "missing_fields": list(controller.live_readiness_issues),
                        },
                    },
                )
            result = await active_wencai_provider.execute(
                ProviderRequest(
                    request_id=f"live-fund-{datetime.now(UTC).timestamp()}",
                    operation=ProviderOperation.FUND_DATA,
                    subject=fund_code,
                    required_fields=("price_cny", "observed_at", "sector", "top_holdings"),
                )
            )
            if result.status not in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL} or not result.records:
                return JSONResponse(
                    status_code=502,
                    content={
                        "status": result.status.value,
                        "error_code": "LIVE_PROVIDER_FAILED",
                        "message": "官方 LIVE 基金穿透未返回可核验记录，未回退到 MOCK。",
                        "execution_context": {
                            "data_mode": "LIVE",
                            "provider": result.provider,
                            "provider_serving_mode": result.serving_mode.value,
                            "is_synthetic": False,
                            "retrieved_at": result.retrieved_at.isoformat(),
                            "missing_fields": list(result.missing_fields),
                            "issues": [issue.safe_message for issue in result.issues],
                        },
                    },
                )
            data = dict(result.records[0].fields)
            data.setdefault("source", result.records[0].source)
            data["is_synthetic"] = False
            data["retrieved_at"] = result.retrieved_at.isoformat()
            return JSONResponse(
                status_code=200,
                content={
                    "status": result.status.value,
                    "data": data,
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": result.provider,
                        "provider_serving_mode": result.serving_mode.value,
                        "is_synthetic": False,
                        "observed_at": data.get("observed_at"),
                        "retrieved_at": result.retrieved_at.isoformat(),
                        "missing_fields": list(result.missing_fields),
                    },
                },
            )

        clean_code = fund_code.split(".")[0].strip()
        if not clean_code.isdigit() or len(clean_code) != 6:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "REJECTED",
                    "error_code": "INVALID_FUND_CODE",
                    "message": f"基金代码格式无效：[{fund_code}] 不符合 6 位数字代码规范。",
                },
            )
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


app = create_app()


__all__ = ["app", "create_app"]
