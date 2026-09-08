"""Public API response contracts with no raw exception payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from app.contracts.evidence import (
    ContractModel,
    DecisionTrace,
    NonEmptyStr,
)
from app.gates import GateStatus
from app.orchestration import ResearchNodeRunStatus, ResearchRunStatus
from app.research import (
    ResearchNodeKind,
    CrossValidationResult,
    ResearchPipelineIssue,
    ResearchPipelineStatus,
    ResearchScenarioId,
    ResearchSpecialistMatrixRequest,
    ResearchSpecialistRole,
)
from app.store import DecisionEvent, DecisionEventSummary
from app.portfolio import PortfolioImportBundle
from app.providers import FrozenDict, ProviderServingMode
from app.stock import (
    StockResearchRequest,
    StockResearchResponse,
    StockResearchNodeResponse,
    StockResearchTemplateResponse,
)
from app.fund import (
    FundResearchRequest,
    FundResearchResponse,
    FundResearchNodeResponse,
    FundResearchTemplateResponse,
)
from app.convertible_bond import (
    ConvertibleBondResearchRequest,
    ConvertibleBondResearchResponse,
    ConvertibleBondResearchNodeResponse,
    ConvertibleBondResearchTemplateResponse,
)
from app.profile import (
    BehaviorEvent,
    BehaviorProfile,
    ConflictResolution,
    ProfileDraft,
    ProfileExtractionProposal,
    RiskProfile,
    RiskQuestionnaire,
    DisplayPolicy,
    QuestionnaireAnswer,
    QuestionnaireSnapshot,
)
from app.service import (
    AdvisorIntentRequest,
    AdvisorPlanResponse,
    AdvisorQueryRequest,
    InvestmentIntentType,
)
from pydantic import Field
from pydantic import model_validator


class DecisionEventWriteResponse(ContractModel):
    schema_version: Literal["decision-event-write.v1"] = "decision-event-write.v1"
    event: DecisionEvent
    created: bool


class DecisionEventListResponse(ContractModel):
    schema_version: Literal["decision-event-list.v1"] = "decision-event-list.v1"
    items: tuple[DecisionEventSummary, ...]


class ErrorResponse(ContractModel):
    schema_version: Literal["api-error.v1"] = "api-error.v1"
    error_code: str
    message: str


class AdvisorQueryResponse(ContractModel):
    schema_version: Literal["advisor-query-response.v1"] = (
        "advisor-query-response.v1"
    )
    query_id: NonEmptyStr
    owner_id: NonEmptyStr
    profile_id: NonEmptyStr
    research_run_id: NonEmptyStr
    status: GateStatus
    created: bool
    event: DecisionEvent

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if self.owner_id != self.event.owner_id:
            raise ValueError("advisor response owner does not match event")
        if self.status != self.event.status:
            raise ValueError("advisor response status does not match event")
        if self.event.result.decision_gate is not None and (
            self.profile_id != self.event.result.decision_gate.profile_id
        ):
            raise ValueError("advisor response profile does not match event")
        if self.event.result.receipt is not None and (
            self.profile_id != self.event.result.receipt.profile_id
            or self.research_run_id != self.event.result.receipt.research_run_id
        ):
            raise ValueError("advisor response receipt does not match event")
        return self


class AdvisorQueryTemplateResponse(ContractModel):
    schema_version: Literal["advisor-query-template.v1"] = (
        "advisor-query-template.v1"
    )
    fixture_id: NonEmptyStr
    generated_at: datetime
    questionnaire: RiskQuestionnaire
    portfolio: PortfolioImportBundle

    @model_validator(mode="after")
    def validate_template_response(self) -> Self:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if self.questionnaire.owner_id != self.portfolio.owner_id:
            raise ValueError("template response owners must match")
        return self


_CONTEXT_SENSITIVE_SUBSTRINGS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "private_key",
    "secret",
    "token",
    "credential",
    "cookie",
)


def _validate_context_payload_safety(serialized: str, label: str) -> None:
    normalized = serialized.casefold().replace("-", "_")
    if any(item in normalized for item in _CONTEXT_SENSITIVE_SUBSTRINGS):
        raise ValueError(f"{label} must not contain sensitive fields")


class AdvisorPortfolioContextRequest(ContractModel):
    """Strict, owner-scoped Portfolio confirmation input."""

    schema_version: Literal["portfolio-context-request.v1"] = (
        "portfolio-context-request.v1"
    )
    portfolio: PortfolioImportBundle

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        _validate_context_payload_safety(
            self.model_dump_json(), "portfolio context request"
        )
        return self


class AdvisorPortfolioContextResponse(ContractModel):
    """Validated Portfolio context with structural, non-financial metadata."""

    schema_version: Literal["portfolio-context-response.v1"] = (
        "portfolio-context-response.v1"
    )
    portfolio: PortfolioImportBundle
    position_count: int = Field(ge=1)
    fund_snapshot_count: int = Field(ge=0)
    holding_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        expected_positions = len(self.portfolio.position_snapshot.positions)
        expected_funds = len(self.portfolio.fund_holdings)
        expected_holdings = sum(
            len(snapshot.holdings) for snapshot in self.portfolio.fund_holdings
        )
        if self.position_count != expected_positions:
            raise ValueError("portfolio context position_count is not authoritative")
        if self.fund_snapshot_count != expected_funds:
            raise ValueError("portfolio context fund_snapshot_count is not authoritative")
        if self.holding_count != expected_holdings:
            raise ValueError("portfolio context holding_count is not authoritative")
        _validate_context_payload_safety(
            self.model_dump_json(), "portfolio context response"
        )
        return self


class AdvisorProfileContextRequest(ContractModel):
    """Strict, owner-scoped Risk Questionnaire confirmation input."""

    schema_version: Literal["profile-context-request.v1"] = (
        "profile-context-request.v1"
    )
    questionnaire: RiskQuestionnaire

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        _validate_context_payload_safety(
            self.model_dump_json(), "profile context request"
        )
        return self


class AdvisorProfileContextResponse(ContractModel):
    """Deterministic profile confirmation result without persistence."""

    schema_version: Literal["profile-context-response.v1"] = (
        "profile-context-response.v1"
    )
    questionnaire: RiskQuestionnaire
    profile: RiskProfile

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if self.questionnaire.owner_id != self.profile.owner_id:
            raise ValueError("profile context owners must match")
        if self.questionnaire.questionnaire_id != self.profile.questionnaire_id:
            raise ValueError("profile context questionnaire does not match profile")
        if self.questionnaire.answered_at != self.profile.created_at:
            raise ValueError("profile context timestamps must match")
        _validate_context_payload_safety(
            self.model_dump_json(), "profile context response"
        )
        return self


class AdvisorProfileProposalRequest(ContractModel):
    """Strict typed profile extraction proposal; no raw natural-language field."""

    schema_version: Literal["advisor-profile-proposal-request.v1"] = (
        "advisor-profile-proposal-request.v1"
    )
    questionnaire: RiskQuestionnaire
    extraction: ProfileExtractionProposal

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.questionnaire.owner_id != self.extraction.owner_id:
            raise ValueError("profile proposal owners must match")
        _validate_context_payload_safety(
            self.model_dump_json(), "profile proposal request"
        )
        return self


class AdvisorProfileProposalResponse(ContractModel):
    """Rebuilt draft with explicit conflicts and no generated decision."""

    schema_version: Literal["advisor-profile-proposal-response.v1"] = (
        "advisor-profile-proposal-response.v1"
    )
    draft: ProfileDraft

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        _validate_context_payload_safety(
            self.model_dump_json(), "profile proposal response"
        )
        return self


class AdvisorProfileConfirmationRequest(ContractModel):
    """Typed proposal plus explicit choices; clients cannot submit a draft."""

    schema_version: Literal["advisor-profile-confirmation-request.v1"] = (
        "advisor-profile-confirmation-request.v1"
    )
    questionnaire: RiskQuestionnaire
    extraction: ProfileExtractionProposal
    resolutions: dict[str, ConflictResolution] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.questionnaire.owner_id != self.extraction.owner_id:
            raise ValueError("profile confirmation owners must match")
        normalized_resolutions: dict[str, ConflictResolution] = {}
        for key, value in self.resolutions.items():
            if not isinstance(key, str) or not key.strip() or key != key.strip():
                raise ValueError("profile confirmation conflict IDs must be non-empty")
            normalized_resolutions[key] = ConflictResolution(value)
        object.__setattr__(self, "resolutions", FrozenDict(normalized_resolutions))
        _validate_context_payload_safety(
            self.model_dump_json(), "profile confirmation request"
        )
        return self


class AdvisorProfileConfirmationResponse(ContractModel):
    """A deterministic, resolved RiskProfile with conflict choices retained."""

    schema_version: Literal["advisor-profile-confirmation-response.v1"] = (
        "advisor-profile-confirmation-response.v1"
    )
    profile: RiskProfile

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        _validate_context_payload_safety(
            self.model_dump_json(), "profile confirmation response"
        )
        return self


class BehaviorEventsWriteRequest(ContractModel):
    schema_version: Literal["behavior-events-write-request.v1"] = "behavior-events-write-request.v1"
    owner_id: NonEmptyStr
    events: tuple[BehaviorEvent, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if any(item.owner_id != self.owner_id for item in self.events):
            raise ValueError("behavior events must share request owner")
        if len({item.event_id for item in self.events}) != len(self.events):
            raise ValueError("behavior event IDs must be unique")
        return self


class BehaviorEventsWriteResponse(ContractModel):
    schema_version: Literal["behavior-events-write-response.v1"] = "behavior-events-write-response.v1"
    owner_id: NonEmptyStr
    accepted_count: int = Field(ge=1)
    created_count: int = Field(ge=0)
    event_ids: tuple[NonEmptyStr, ...]


class BehaviorProfileRecomputeRequest(ContractModel):
    schema_version: Literal["behavior-profile-recompute-request.v1"] = "behavior-profile-recompute-request.v1"
    owner_id: NonEmptyStr
    calculated_at: datetime
    questionnaire_profile: RiskProfile

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.calculated_at.tzinfo is None or self.calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware")
        if self.questionnaire_profile.owner_id != self.owner_id:
            raise ValueError("questionnaire profile owner does not match request owner")
        return self


class BehaviorProfileResponse(ContractModel):
    schema_version: Literal["behavior-profile-response.v1"] = "behavior-profile-response.v1"
    profile: BehaviorProfile
    effective_profile: RiskProfile

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.profile.owner_id != self.effective_profile.owner_id:
            raise ValueError("behavior and effective profile owners must match")
        if self.profile.effective_risk_score != self.effective_profile.risk_score:
            raise ValueError("effective profile score must match behavior profile")
        return self


class BehaviorProfileLookupResponse(ContractModel):
    schema_version: Literal["behavior-profile-lookup-response.v1"] = "behavior-profile-lookup-response.v1"
    status: Literal["CALCULATED", "INSUFFICIENT_DATA"]
    profile: BehaviorProfile | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.status == "CALCULATED" and self.profile is None:
            raise ValueError("CALCULATED lookup requires a profile")
        if self.status == "INSUFFICIENT_DATA" and self.profile is not None:
            raise ValueError("INSUFFICIENT_DATA lookup must not contain a profile")
        return self


class DisplayPolicyUpdateRequest(ContractModel):
    schema_version: Literal["display-policy-update-request.v1"] = "display-policy-update-request.v1"
    owner_id: NonEmptyStr
    trust_score: int = Field(ge=0, le=100)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return self


class DisplayPolicyResponse(ContractModel):
    schema_version: Literal["display-policy-response.v1"] = "display-policy-response.v1"
    policy: DisplayPolicy


class QuestionnairePreviewRequest(ContractModel):
    schema_version: Literal["questionnaire-preview-request.v1"] = "questionnaire-preview-request.v1"
    owner_id: NonEmptyStr
    evaluated_at: datetime
    answers: tuple[QuestionnaireAnswer, ...] = Field(min_length=19, max_length=19)

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return self


class QuestionnaireConfirmationRequest(ContractModel):
    schema_version: Literal["questionnaire-confirmation-request.v1"] = "questionnaire-confirmation-request.v1"
    owner_id: NonEmptyStr
    confirmed_at: datetime
    answers: tuple[QuestionnaireAnswer, ...] = Field(min_length=19, max_length=19)

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return self


class QuestionnairePreviewResponse(ContractModel):
    schema_version: Literal["questionnaire-preview-response.v1"] = "questionnaire-preview-response.v1"
    snapshot: QuestionnaireSnapshot
    persisted: Literal[False] = False


class QuestionnaireConfirmationResponse(ContractModel):
    schema_version: Literal["questionnaire-confirmation-response.v1"] = "questionnaire-confirmation-response.v1"
    snapshot: QuestionnaireSnapshot
    created: bool


class ProfileSummaryResponse(ContractModel):
    schema_version: Literal["profile-summary-response.v1"] = "profile-summary-response.v1"
    owner_id: NonEmptyStr
    questionnaire_snapshot: QuestionnaireSnapshot | None = None
    behavior_profile: BehaviorProfile | None = None
    effective_profile: RiskProfile | None = None
    display_policy: DisplayPolicy
    data_gaps: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    next_actions: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class ResearchScenarioResponse(ContractModel):
    """Safe catalog metadata for one deterministic research replay."""

    schema_version: Literal["research-scenario-response.v1"] = (
        "research-scenario-response.v1"
    )
    scenario_id: ResearchScenarioId
    label: NonEmptyStr
    description: NonEmptyStr

    @model_validator(mode="after")
    def validate_safety(self) -> Self:
        _validate_context_payload_safety(self.model_dump_json(), "research scenario response")
        return self


class ResearchMatrixTemplateResponse(ContractModel):
    schema_version: Literal["research-matrix-template.v1"] = (
        "research-matrix-template.v1"
    )
    matrix_id: NonEmptyStr
    owner_id: NonEmptyStr
    generated_at: datetime
    scope_description: NonEmptyStr
    roles: tuple[ResearchSpecialistRole, ...] = Field(min_length=4)
    node_count: int = Field(ge=4)
    scenarios: tuple[ResearchScenarioResponse, ...] = Field(min_length=5)

    @model_validator(mode="after")
    def validate_template_response(self) -> Self:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("research template generated_at must be timezone-aware")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("research template roles must not contain duplicates")
        if set(self.roles) != set(ResearchSpecialistRole):
            raise ValueError("research template must cover all specialist roles")
        if self.node_count < len(self.roles):
            raise ValueError("research template node_count is too small")
        scenario_ids = [item.scenario_id for item in self.scenarios]
        if scenario_ids != sorted(scenario_ids, key=lambda item: item.value):
            raise ValueError("research template scenarios must be sorted")
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("research template scenarios must be unique")
        if ResearchScenarioId.BASELINE_READY not in scenario_ids:
            raise ValueError("research template must include the baseline scenario")
        return self


class ResearchMatrixIssueResponse(ContractModel):
    code: NonEmptyStr
    safe_message: NonEmptyStr


class ResearchMatrixNodeResponse(ContractModel):
    node_id: NonEmptyStr
    role: ResearchSpecialistRole
    node_kind: ResearchNodeKind
    subject: NonEmptyStr
    required: bool
    status: ResearchNodeRunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    issues: tuple[ResearchMatrixIssueResponse, ...] = Field(default_factory=tuple)
    provider: NonEmptyStr | None = None
    provider_serving_mode: ProviderServingMode = ProviderServingMode.DIRECT
    provider_cache_age_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        for name, value in (
            ("started_at", self.started_at),
            ("finished_at", self.finished_at),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"research node {name} must be timezone-aware")
        if self.started_at is None and self.finished_at is not None:
            raise ValueError("research node finished_at requires started_at")
        if self.started_at is not None and self.finished_at is not None:
            if self.finished_at < self.started_at:
                raise ValueError("research node finished_at must not precede started_at")
        cache_mode = self.provider_serving_mode in {
            ProviderServingMode.CACHE_FRESH,
            ProviderServingMode.CACHE_STALE_FALLBACK,
        }
        if cache_mode and self.provider_cache_age_ms is None:
            raise ValueError("cached research node requires provider_cache_age_ms")
        if not cache_mode and self.provider_cache_age_ms is not None:
            raise ValueError("direct/fallback research node must not contain cache age")
        if self.provider_serving_mode != ProviderServingMode.DIRECT and self.provider is None:
            raise ValueError("non-direct research node requires provider identity")
        return self


class ResearchMatrixResponse(ContractModel):
    schema_version: Literal["research-matrix-response.v1"] = (
        "research-matrix-response.v1"
    )
    matrix_id: NonEmptyStr
    scenario: ResearchScenarioResponse
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    run_id: NonEmptyStr
    run_status: ResearchRunStatus
    pipeline_status: ResearchPipelineStatus
    nodes: tuple[ResearchMatrixNodeResponse, ...] = Field(min_length=4)
    validations: tuple[CrossValidationResult, ...] = Field(default_factory=tuple)
    issues: tuple[ResearchPipelineIssue, ...] = Field(default_factory=tuple)
    trace: DecisionTrace

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        node_ids = [node.node_id for node in self.nodes]
        if node_ids != sorted(node_ids) or len(node_ids) != len(set(node_ids)):
            raise ValueError("research response nodes must be unique and sorted")
        if {node.role for node in self.nodes} != set(ResearchSpecialistRole):
            raise ValueError("research response must cover all specialist roles")
        claim_ids = [item.claim_id for item in self.validations]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("research response validations must be unique")
        if any(item.owner_id != self.owner_id for item in self.validations):
            raise ValueError("research response validation owner does not match")
        if self.trace.recommendations:
            raise ValueError("research response must not contain recommendations")
        if self.pipeline_status.value == "READY":
            if self.run_status != ResearchRunStatus.COMPLETED:
                raise ValueError("READY research response requires completed run")
            if not self.validations or not self.trace.facts or not self.trace.findings:
                raise ValueError("READY research response requires validation trace")
        elif self.trace.facts or self.trace.findings:
            raise ValueError("non-ready research response must not expose facts/findings")
        serialized = self.model_dump_json().casefold()
        for forbidden in (
            "api_key",
            "authorization",
            "password",
            "private_key",
            "secret",
            "token",
            "credential",
            "cookie",
        ):
            if forbidden in serialized:
                raise ValueError("research response must not contain sensitive fields")
        return self


__all__ = [
    "AdvisorIntentRequest",
    "AdvisorPlanResponse",
    "AdvisorProfileConfirmationRequest",
    "AdvisorProfileConfirmationResponse",
    "DecisionEventListResponse",
    "DecisionEventWriteResponse",
    "AdvisorQueryResponse",
    "AdvisorQueryTemplateResponse",
    "AdvisorPortfolioContextRequest",
    "AdvisorPortfolioContextResponse",
    "AdvisorProfileContextRequest",
    "AdvisorProfileContextResponse",
    "AdvisorProfileProposalRequest",
    "AdvisorProfileProposalResponse",
    "QuestionnairePreviewRequest",
    "QuestionnairePreviewResponse",
    "QuestionnaireConfirmationRequest",
    "QuestionnaireConfirmationResponse",
    "ProfileSummaryResponse",
    "ResearchScenarioResponse",
    "ResearchMatrixTemplateResponse",
    "ResearchMatrixIssueResponse",
    "ResearchMatrixNodeResponse",
    "ResearchMatrixResponse",
    "ErrorResponse",
    "AdvisorQueryRequest",
    "InvestmentIntentType",
    "ResearchSpecialistMatrixRequest",
    "StockResearchRequest",
    "StockResearchResponse",
    "StockResearchNodeResponse",
    "StockResearchTemplateResponse",
    "FundResearchRequest",
    "FundResearchResponse",
    "FundResearchNodeResponse",
    "FundResearchTemplateResponse",
    "ConvertibleBondResearchRequest",
    "ConvertibleBondResearchResponse",
    "ConvertibleBondResearchNodeResponse",
    "ConvertibleBondResearchTemplateResponse",
]
