"""Fixture-first execution of the four structured research specialist tracks."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from urllib.parse import quote
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.orchestration import (
    ResearchClaimSpec,
    ResearchNodeRequest,
    ResearchNodeSpec,
    ResearchRunExecutionResult,
    build_research_evidence_pipeline,
    build_research_plan,
    create_research_run,
    execute_research_run,
)
from app.providers import (
    FixtureFinancialProvider,
    ProviderIssue,
    ProviderIssueCode,
    ProviderRecord,
    ProviderRequest,
    ProviderResult,
    ProviderExecutionPolicy,
    ProviderStatus,
)
from app.research import (
    ResearchSpecialistMatrix,
    ResearchSpecialistMatrixRequest,
    ResearchScenarioDefinition,
    ResearchScenarioId,
    ValidationClaim,
)
from app.research.pipeline import ResearchEvidencePipelineResult


_DEFAULT_MATRIX_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "research"
_DEFAULT_MANIFEST = _DEFAULT_MATRIX_ROOT / "specialist_matrix.json"
_DEFAULT_PROVIDER_DIR = _DEFAULT_MATRIX_ROOT / "providers"


_SCENARIO_DEFINITIONS = (
    ResearchScenarioDefinition(
        scenario_id=ResearchScenarioId.BASELINE_READY,
        label="基线：来源一致",
        description="两条独立来源对四条研究 claim 给出一致数值，形成 READY 证据闭包。",
    ),
    ResearchScenarioDefinition(
        scenario_id=ResearchScenarioId.SOURCE_DISAGREEMENT,
        label="分歧：来源冲突",
        description="宏观来源对同一政策利率给出不同数值，保留双方 Evidence 并要求复核。",
    ),
    ResearchScenarioDefinition(
        scenario_id=ResearchScenarioId.SOURCE_EMPTY,
        label="异常：范围无结果",
        description="行业来源在声明范围内没有记录，系统不把无结果当作零值。",
    ),
    ResearchScenarioDefinition(
        scenario_id=ResearchScenarioId.SOURCE_FAILED,
        label="异常：来源失败",
        description="个股来源安全失败，run 关闭未完成节点并阻止下游事实升级。",
    ),
    ResearchScenarioDefinition(
        scenario_id=ResearchScenarioId.SOURCE_PARTIAL,
        label="异常：字段缺失",
        description="基金来源返回部分记录但缺少必需字段，保留可见范围并要求复核。",
    ),
)
_SCENARIO_BY_ID = {item.scenario_id: item for item in _SCENARIO_DEFINITIONS}
_UNSET = object()


def _validated_result(
    result: ProviderResult,
    *,
    status: ProviderStatus | None = None,
    records: tuple[ProviderRecord, ...] | None = None,
    missing_fields: tuple[str, ...] | None = None,
    issues: tuple[ProviderIssue, ...] | None = None,
    scope_description: str | None | object = _UNSET,
) -> ProviderResult:
    """Rebuild an overlay result through the Provider contract validators."""

    payload = result.model_dump(mode="python")
    if status is not None:
        payload["status"] = status
    if records is not None:
        payload["records"] = records
    if missing_fields is not None:
        payload["missing_fields"] = missing_fields
    if issues is not None:
        payload["issues"] = issues
    if scope_description is not _UNSET:
        payload["scope_description"] = scope_description
    return ProviderResult.model_validate(payload)


class _ScenarioFixtureProvider:
    """Apply one explicit offline scenario to the existing fixture provider."""

    def __init__(self, base: FixtureFinancialProvider, scenario_id: ResearchScenarioId) -> None:
        self._base = base
        self._scenario_id = scenario_id

    @property
    def name(self) -> str:
        return self._base.name

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        result = await self._base.execute(request)
        scenario = self._scenario_id

        if scenario == ResearchScenarioId.BASELINE_READY:
            return result

        if scenario == ResearchScenarioId.SOURCE_DISAGREEMENT:
            if request.request_id != "matrix-macro-request-b":
                return result
            records: list[ProviderRecord] = []
            for record in result.records:
                fields = dict(record.fields)
                fields["policy_rate_pct"] = "3.25"
                records.append(
                    ProviderRecord.model_validate(
                        {
                            **record.model_dump(mode="python"),
                            "fields": fields,
                        }
                    )
                )
            return _validated_result(result, records=tuple(records))

        if scenario == ResearchScenarioId.SOURCE_PARTIAL:
            if request.request_id != "matrix-fund-request-b":
                return result
            records = []
            for record in result.records:
                fields = {
                    key: value
                    for key, value in record.fields.items()
                    if key != "technology_weight_pct"
                }
                units = {
                    key: value
                    for key, value in record.units.items()
                    if key != "technology_weight_pct"
                }
                if not fields:
                    fields = {"coverage_pct": "50.00"}
                    units = {"coverage_pct": "pct"}
                records.append(
                    ProviderRecord.model_validate(
                        {
                            **record.model_dump(mode="python"),
                            "fields": fields,
                            "units": units,
                        }
                    )
                )
            issue = ProviderIssue(
                code=ProviderIssueCode.INVALID_RESPONSE,
                stage="scenario",
                safe_message="synthetic fixture omitted a required field",
                retriable=False,
                diagnostics={"scenario_id": scenario.value},
            )
            return _validated_result(
                result,
                status=ProviderStatus.PARTIAL,
                records=tuple(records),
                missing_fields=("technology_weight_pct",),
                issues=(issue,),
            )

        if scenario == ResearchScenarioId.SOURCE_EMPTY:
            if request.request_id != "matrix-industry-request-b":
                return result
            return _validated_result(
                result,
                status=ProviderStatus.EMPTY,
                records=(),
                missing_fields=(),
                issues=(),
                scope_description="synthetic fixture returned no records for the requested scope",
            )

        if scenario == ResearchScenarioId.SOURCE_FAILED:
            if request.request_id != "matrix-stock-request-b":
                return result
            issue = ProviderIssue(
                code=ProviderIssueCode.TRANSPORT_ERROR,
                stage="scenario",
                safe_message="synthetic fixture source was unavailable",
                retriable=False,
                diagnostics={"scenario_id": scenario.value},
            )
            return _validated_result(
                result,
                status=ProviderStatus.FAILED,
                records=(),
                missing_fields=(),
                issues=(issue,),
                scope_description=None,
            )

        raise ValueError("unknown research scenario")


class SpecialistMatrixError(RuntimeError):
    """Safe refusal for an invalid or unavailable specialist matrix."""


class SpecialistMatrixOutput(ContractModel):
    """Closed run and evidence-pipeline output without recommendation semantics."""

    schema_version: Literal["research-specialist-matrix-output.v1"] = (
        "research-specialist-matrix-output.v1"
    )
    matrix: ResearchSpecialistMatrix
    scenario: ResearchScenarioDefinition
    request_id: NonEmptyStr
    owner_id: NonEmptyStr
    execution: ResearchRunExecutionResult
    pipeline: ResearchEvidencePipelineResult

    @model_validator(mode="after")
    def validate_output(self) -> Self:
        if self.matrix.owner_id != self.owner_id:
            raise ValueError("matrix owner does not match output owner")
        if self.scenario.scenario_id not in _SCENARIO_BY_ID:
            raise ValueError("output scenario is not in the scenario catalog")
        if self.execution.state.owner_id != self.owner_id:
            raise ValueError("execution owner does not match output owner")
        if self.execution.state.request_id != self.request_id:
            raise ValueError("execution request does not match output request")
        if self.pipeline.owner_id != self.owner_id:
            raise ValueError("pipeline owner does not match output owner")
        if self.pipeline.run_id != self.execution.state.run_id:
            raise ValueError("pipeline run does not match execution run")
        if self.pipeline.request_id != self.request_id:
            raise ValueError("pipeline request does not match output request")
        if self.pipeline.trace.recommendations:
            raise ValueError("specialist matrix must not produce recommendations")
        matrix_nodes = {node.node_id: node for node in self.matrix.nodes}
        plan_nodes = {node.node_id: node for node in self.execution.state.plan.nodes}
        if set(matrix_nodes) != set(plan_nodes):
            raise ValueError("execution plan nodes do not match specialist matrix")
        for node_id, matrix_node in matrix_nodes.items():
            plan_node = plan_nodes[node_id]
            if (
                plan_node.owner_id != self.owner_id
                or plan_node.node_kind != matrix_node.node_kind
                or plan_node.required != matrix_node.required
                or plan_node.dependencies != matrix_node.dependencies
            ):
                raise ValueError("execution plan node does not match specialist matrix")
        expected_claim_ids = {node.claim_id for node in self.matrix.claims()}
        actual_claim_ids = {item.claim_id for item in self.pipeline.validations}
        if actual_claim_ids != expected_claim_ids:
            raise ValueError("pipeline claims do not match specialist matrix")
        return self


def _safe_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or value is None or isinstance(value, (Mapping, list, tuple)):
        raise ValueError("evidence value is not a scalar")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("evidence value is not a Decimal") from exc
    if not parsed.is_finite():
        raise ValueError("evidence value must be finite")
    return parsed


class FixtureResearchSpecialistMatrixService:
    """Run a packaged four-track matrix through the existing research pipeline."""

    def __init__(
        self,
        *,
        manifest_path: str | Path = _DEFAULT_MANIFEST,
        provider_dir: str | Path = _DEFAULT_PROVIDER_DIR,
        provider_policy: ProviderExecutionPolicy | None = None,
    ) -> None:
        self._manifest_path = Path(manifest_path)
        self._provider_dir = Path(provider_dir)
        self._provider_policy = provider_policy
        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            self._template = ResearchSpecialistMatrix.model_validate(payload)
        except Exception as exc:
            raise SpecialistMatrixError("specialist matrix could not be loaded") from exc
        if not self._provider_dir.exists() or not self._provider_dir.is_dir():
            raise SpecialistMatrixError("specialist provider fixtures are unavailable")

    @property
    def matrix_id(self) -> str:
        return self._template.matrix_id

    @property
    def scenarios(self) -> tuple[ResearchScenarioDefinition, ...]:
        """Return the stable, safe scenario catalog for the workbench."""

        return tuple(sorted(_SCENARIO_DEFINITIONS, key=lambda item: item.scenario_id.value))

    def matrix_template(self, owner_id: str) -> ResearchSpecialistMatrix:
        """Return the manifest rebound and revalidated for one owner."""

        try:
            request = ResearchSpecialistMatrixRequest.model_validate(
                {
                    "matrix_id": self._template.matrix_id,
                    "request_id": "template",
                    "owner_id": owner_id,
                    "generated_at": self._template.generated_at,
                }
            )
            nodes = tuple(
                node.model_copy(update={"owner_id": request.owner_id})
                for node in self._template.nodes
            )
            return ResearchSpecialistMatrix.model_validate(
                {
                    **self._template.model_dump(mode="python"),
                    "owner_id": request.owner_id,
                    "nodes": nodes,
                }
            )
        except Exception as exc:
            raise SpecialistMatrixError("specialist matrix template was refused") from exc

    @staticmethod
    def _plan(
        matrix: ResearchSpecialistMatrix,
        scenario_id: ResearchScenarioId = ResearchScenarioId.BASELINE_READY,
    ):
        nodes = tuple(
            ResearchNodeSpec(
                node_id=node.node_id,
                owner_id=matrix.owner_id,
                node_kind=node.node_kind,
                required=node.required,
                dependencies=node.dependencies,
                timeout_ms=min(node.timeout_ms, matrix.budget_ms),
            )
            for node in matrix.nodes
        )
        scope_description = matrix.scope_description
        if scenario_id != ResearchScenarioId.BASELINE_READY:
            scope_description = f"{scope_description} · replay {scenario_id.value}"
        return build_research_plan(matrix.owner_id, scope_description, nodes)

    @staticmethod
    def _requests(matrix: ResearchSpecialistMatrix) -> dict[str, ResearchNodeRequest]:
        return {
            node.node_id: ResearchNodeRequest(
                node_id=node.node_id,
                request=ProviderRequest(
                    request_id=node.request_id,
                    operation=node.operation,
                    subject=node.subject,
                    required_fields=node.required_fields,
                    parameters=node.parameters,
                    timeout_ms=min(node.timeout_ms, matrix.budget_ms),
                ),
            )
            for node in matrix.nodes
        }

    @staticmethod
    def _claim_specs(
        matrix: ResearchSpecialistMatrix,
        execution: ResearchRunExecutionResult,
    ) -> tuple[ResearchClaimSpec, ...]:
        specs: list[ResearchClaimSpec] = []
        for representative in matrix.claims():
            source_lineages = {
                (node.source, node.lineage_id)
                for node in matrix.nodes
                if node.claim_id == representative.claim_id
            }
            observation_ids = tuple(
                sorted(
                    observation.observation_id
                    for observation in execution.observations
                    if (
                        (observation.source, observation.lineage_id) in source_lineages
                        and observation.subject == representative.subject
                        and observation.metric == representative.metric
                        and observation.unit == representative.unit
                        and observation.period == representative.period
                    )
                )
            )
            claim = ValidationClaim(
                claim_id=representative.claim_id,
                owner_id=matrix.owner_id,
                subject=representative.subject,
                metric=representative.metric,
                unit=representative.unit,
                period=representative.period,
                expected_value=representative.expected_value,
            )
            specs.append(
                ResearchClaimSpec(
                    claim=claim,
                    finding_kind=representative.finding_kind,
                    finding_severity=representative.finding_severity,
                    statement=representative.finding_statement,
                    observation_ids=observation_ids,
                )
            )
        return tuple(specs)

    @staticmethod
    def _check_evidence_integrity(
        matrix: ResearchSpecialistMatrix,
        execution: ResearchRunExecutionResult,
    ) -> None:
        """Ensure a complete run contains exactly the declared source fields."""

        expected = {
            (
                node.source,
                node.record_id,
                node.lineage_id,
                node.metric,
                node.unit,
                node.period,
            )
            for node in matrix.nodes
        }
        actual: set[tuple[str, str, str, str, str, str]] = set()
        for evidence in execution.evidence:
            try:
                _safe_decimal(evidence.value)
            except ValueError as exc:
                raise SpecialistMatrixError("specialist evidence is not a scalar") from exc
            matching = [
                node
                for node in matrix.nodes
                if node.source == evidence.source
                and node.lineage_id == evidence.lineage_id
                and node.metric == evidence.field
                and node.unit == evidence.unit
                and node.period == evidence.period
            ]
            if len(matching) != 1:
                raise SpecialistMatrixError("specialist evidence source identity drifted")
            node = matching[0]
            if quote(node.record_id, safe="") not in evidence.evidence_id:
                raise SpecialistMatrixError("specialist evidence record identity drifted")
            actual.add(
                (
                    node.source,
                    node.record_id,
                    node.lineage_id,
                    evidence.field,
                    evidence.unit or "",
                    evidence.period or "",
                )
            )
        if actual != expected:
            raise SpecialistMatrixError("specialist evidence set drifted from matrix")

    async def run(
        self,
        request: ResearchSpecialistMatrixRequest,
        *,
        matrix_override: ResearchSpecialistMatrix | None = None,
    ) -> SpecialistMatrixOutput:
        """Execute one owner-scoped, deterministic matrix without side effects."""

        try:
            request = ResearchSpecialistMatrixRequest.model_validate(
                request.model_dump(mode="python")
                if isinstance(request, ResearchSpecialistMatrixRequest)
                else request
            )
        except Exception as exc:
            raise SpecialistMatrixError("specialist matrix request was refused") from exc
        if request.matrix_id != self._template.matrix_id:
            raise SpecialistMatrixError("requested specialist matrix is unavailable")
        scenario = _SCENARIO_BY_ID.get(request.scenario_id)
        if scenario is None:
            raise SpecialistMatrixError("requested research scenario is unavailable")

        try:
            matrix = matrix_override or self.matrix_template(request.owner_id)
            if matrix.owner_id != request.owner_id or matrix.matrix_id != request.matrix_id:
                raise SpecialistMatrixError("workflow matrix scope does not match request")
            plan = self._plan(matrix, request.scenario_id)
            state = create_research_run(
                plan,
                request.request_id,
                matrix.budget_ms,
                request.generated_at,
            )
            clock = lambda: request.generated_at
            execution = await execute_research_run(
                state,
                _ScenarioFixtureProvider(
                    FixtureFinancialProvider(fixture_dir=self._provider_dir, clock=clock),
                    request.scenario_id,
                ),
                self._requests(matrix),
                started_at=request.generated_at,
                clock=clock,
                policy=self._provider_policy,
            )
            if execution.state.status.value == "COMPLETED":
                self._check_evidence_integrity(matrix, execution)
            pipeline = build_research_evidence_pipeline(
                execution,
                self._claim_specs(matrix, execution),
            )
            return SpecialistMatrixOutput(
                matrix=matrix,
                scenario=scenario,
                request_id=request.request_id,
                owner_id=request.owner_id,
                execution=execution,
                pipeline=pipeline,
            )
        except SpecialistMatrixError:
            raise
        except Exception as exc:
            raise SpecialistMatrixError("specialist matrix execution was refused") from exc


__all__ = [
    "FixtureResearchSpecialistMatrixService",
    "SpecialistMatrixError",
    "SpecialistMatrixOutput",
]
