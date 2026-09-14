"""Application use cases that compose existing deterministic domain modules."""

from app.service.advisor_query import (
    AdvisorQueryError,
    FixtureAdvisorQueryService,
)
from app.service.contracts import (
    AdvisorQueryOutput,
    AdvisorQueryRequest,
    AdvisorQueryTemplate,
)
from app.service.specialist_matrix import (
    FixtureResearchSpecialistMatrixService,
    SpecialistMatrixError,
    SpecialistMatrixOutput,
)
from app.service.profile_confirmation import (
    ProfileConfirmationError,
    confirm_questionnaire,
)
from app.service.intent_planning import (
    AdvisorIntentRequest,
    AdvisorPlanResponse,
    IntentPlanningError,
    InvestmentIntentType,
    build_intent_plan,
)
from app.service.profile_proposal import (
    ProfileProposalError,
    build_profile_proposal,
    confirm_profile_proposal,
)
from app.service.stock_research import (
    FixtureStockResearchService,
    StockResearchError,
)
from app.service.fund_research import (
    FixtureFundResearchService,
    FundResearchError,
)
from app.service.convertible_bond_research import (
    FixtureConvertibleBondResearchService,
    ConvertibleBondResearchError,
)
from app.service.portfolio_optimization import (
    DeterministicPortfolioOptimizationService,
    FixturePortfolioOptimizationService,
    PortfolioOptimizationError,
)
from app.service.scenario_simulation import (
    FixtureScenarioSimulationService,
    ScenarioSimulationError,
)
from app.service.recommendation_history import RecommendationHistoryService
from app.service.portfolio_rebalancing import PortfolioRebalancingService
from app.service.evaluation_dashboard import EvaluationDashboardService
from app.service.advanced_explainability import AdvancedExplainabilityService

__all__ = [
    "AdvisorQueryError",
    "AdvisorQueryOutput",
    "AdvisorQueryRequest",
    "AdvisorQueryTemplate",
    "FixtureAdvisorQueryService",
    "FixtureResearchSpecialistMatrixService",
    "SpecialistMatrixError",
    "SpecialistMatrixOutput",
    "ProfileConfirmationError",
    "confirm_questionnaire",
    "AdvisorIntentRequest",
    "AdvisorPlanResponse",
    "IntentPlanningError",
    "InvestmentIntentType",
    "build_intent_plan",
    "ProfileProposalError",
    "build_profile_proposal",
    "confirm_profile_proposal",
    "FixtureStockResearchService",
    "StockResearchError",
    "FixtureFundResearchService",
    "FundResearchError",
    "FixtureConvertibleBondResearchService",
    "ConvertibleBondResearchError",
    "FixturePortfolioOptimizationService",
    "DeterministicPortfolioOptimizationService",
    "PortfolioOptimizationError",
    "FixtureScenarioSimulationService",
    "ScenarioSimulationError",
    "RecommendationHistoryService",
    "PortfolioRebalancingService",
    "EvaluationDashboardService",
    "AdvancedExplainabilityService",
]
