import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import time

import pytest

from app.contracts import EvidenceQualityStatus
from app.orchestration import (
    ResearchNodeRequest,
    ResearchRunExecutionResult,
    ResearchNodeSpec,
    ResearchNodeRunStatus,
    ResearchRunStatus,
    build_research_plan,
    create_research_run,
    execute_research_run,
)
from app.providers import (
    ProviderRecord,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
    compute_request_fingerprint,
)
from app.research import ResearchNodeKind, ResearchNodeStatus


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
OWNER = "executor-owner-001"


def _plan(*nodes: ResearchNodeSpec):
    return build_research_plan(OWNER, "synthetic executor run", nodes)


def _state(
    nodes: tuple[ResearchNodeSpec, ...],
    budget_ms: int = 2000,
    *,
    created_at: datetime = NOW,
):
    return create_research_run(
        _plan(*nodes), "executor-request-001", budget_ms, created_at
    )


def _request(
    node_id: str,
    operation,
    subject: str,
    *,
    timeout_ms: int = 1000,
) -> ResearchNodeRequest:
    return ResearchNodeRequest(
        node_id=node_id,
        request=ProviderRequest(
            request_id=f"provider-request-{node_id}",
            operation=operation,
            subject=subject,
            required_fields=("value",),
            parameters={"period": "2026-Q2"},
            timeout_ms=timeout_ms,
        ),
    )


class DelayedSuccessProvider:
    def __init__(self, delays: dict[str, float] | None = None) -> None:
        self.delays = delays or {}
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "synthetic-executor-provider"

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.calls.append(request.subject)
        await asyncio.sleep(self.delays.get(request.subject, 0.0))
        fingerprint = compute_request_fingerprint(request)
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=fingerprint,
            provider=self.name,
            status=ProviderStatus.SUCCESS,
            retrieved_at=NOW,
            records=(
                ProviderRecord(
                    source=f"synthetic-source-{request.subject}",
                    record_id=f"record-{request.subject}",
                    fields={"value": 10.0},
                    units={"value": "CNY"},
                    period="2026-Q2",
                    observed_at=NOW,
                    lineage_id=f"lineage-{request.subject}",
                ),
            ),
            latency_ms=5,
        )


class ExplodingProvider:
    @property
    def name(self) -> str:
        return "synthetic-exploding-provider"

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        raise RuntimeError("upstream crashed with api_key=must-not-escape")


class WrongIdentityProvider(DelayedSuccessProvider):
    @property
    def name(self) -> str:
        return "synthetic-identity-provider"

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        result = await super().execute(request)
        return result.model_copy(update={"provider": "unexpected-provider"})


class SecretValueProvider(DelayedSuccessProvider):
    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.calls.append(request.subject)
        return ProviderResult(
            request_id=request.request_id,
            request_fingerprint=compute_request_fingerprint(request),
            provider=self.name,
            status=ProviderStatus.SUCCESS,
            retrieved_at=NOW,
            records=(
                ProviderRecord(
                    source="safe-source",
                    record_id="safe-record",
                    fields={"value": "api_key=must-not-be-stored"},
                    units={"value": "CNY"},
                    period="2026-Q2",
                    observed_at=NOW,
                    lineage_id="safe-lineage",
                ),
            ),
        )


class SlowProvider(DelayedSuccessProvider):
    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.calls.append(request.subject)
        await asyncio.sleep(0.1)
        return await super().execute(request)


def _run(state, provider, requests, **kwargs):
    return asyncio.run(execute_research_run(state, provider, requests, **kwargs))


def test_two_ready_roots_execute_in_parallel_and_complete() -> None:
    nodes = (
        ResearchNodeSpec(
            node_id="macro-root",
            owner_id=OWNER,
            node_kind=ResearchNodeKind.MACRO,
            required=True,
            timeout_ms=1000,
        ),
        ResearchNodeSpec(
            node_id="industry-root",
            owner_id=OWNER,
            node_kind=ResearchNodeKind.INDUSTRY,
            required=True,
            timeout_ms=1000,
        ),
    )
    state = _state(nodes)
    requests = {
        "macro-root": _request("macro-root", "MACRO_DATA", "MACRO_A"),
        "industry-root": _request("industry-root", "INDUSTRY_DATA", "INDUSTRY_A"),
    }
    class BarrierProvider(DelayedSuccessProvider):
        def __init__(self):
            super().__init__({})
            self.entered = set()
            self.both_entered = asyncio.Event()

        async def execute(self, request):
            self.entered.add(request.subject)
            if len(self.entered) == 2:
                self.both_entered.set()
            # A sequential executor cannot release the first root. This proves
            # overlap without treating workstation scheduling as a latency SLA.
            await asyncio.wait_for(self.both_entered.wait(), timeout=0.8)
            return await super().execute(request)

    provider = BarrierProvider()
    result = _run(state, provider, requests, started_at=NOW, clock=lambda: NOW)

    assert result.state.status == ResearchRunStatus.COMPLETED
    assert all(node.status == ResearchNodeRunStatus.COMPLETE for node in result.state.nodes)
    assert provider.entered == {"INDUSTRY_A", "MACRO_A"}
    assert sorted(provider.calls) == ["INDUSTRY_A", "MACRO_A"]
    assert len(result.evidence) == 2
    assert len(result.observations) == 2
    assert all(item.quality_status == EvidenceQualityStatus.VERIFIED for item in result.observations)


def test_dependency_node_waits_for_completed_parent() -> None:
    nodes = (
        ResearchNodeSpec(
            node_id="fund-child",
            owner_id=OWNER,
            node_kind=ResearchNodeKind.FUND,
            dependencies=("macro-root",),
            required=True,
            timeout_ms=1000,
        ),
        ResearchNodeSpec(
            node_id="macro-root",
            owner_id=OWNER,
            node_kind=ResearchNodeKind.MACRO,
            required=True,
            timeout_ms=1000,
        ),
    )
    state = _state(nodes)
    requests = {
        "macro-root": _request("macro-root", "MACRO_DATA", "MACRO_A"),
        "fund-child": _request("fund-child", "FUND_DATA", "FUND_A"),
    }
    provider = DelayedSuccessProvider()

    result = _run(state, provider, requests, started_at=NOW, clock=lambda: NOW)

    assert result.state.status == ResearchRunStatus.COMPLETED
    assert provider.calls == ["MACRO_A", "FUND_A"]
    assert [node.node_id for node in result.state.nodes] == ["macro-root", "fund-child"]


def test_optional_empty_fixture_state_is_partial_and_keeps_no_zero_observation() -> None:
    nodes = (
        ResearchNodeSpec(
            node_id="optional-empty",
            owner_id=OWNER,
            node_kind=ResearchNodeKind.FUND,
            required=False,
            timeout_ms=1000,
        ),
        ResearchNodeSpec(
            node_id="required-success",
            owner_id=OWNER,
            node_kind=ResearchNodeKind.FUND,
            required=True,
            timeout_ms=1000,
        ),
    )
    # The custom provider can express an empty response without fabricating a row.
    class EmptyAwareProvider(DelayedSuccessProvider):
        async def execute(self, request: ProviderRequest) -> ProviderResult:
            self.calls.append(request.subject)
            if request.subject == "EMPTY":
                return ProviderResult(
                    request_id=request.request_id,
                    request_fingerprint=compute_request_fingerprint(request),
                    provider=self.name,
                    status=ProviderStatus.EMPTY,
                    retrieved_at=NOW,
                    scope_description="synthetic empty scope",
                )
            return await super().execute(request)

    state = _state(nodes)
    requests = {
        "optional-empty": _request("optional-empty", "FUND_DATA", "EMPTY"),
        "required-success": _request("required-success", "FUND_DATA", "FUND_A"),
    }
    result = _run(state, EmptyAwareProvider(), requests, started_at=NOW, clock=lambda: NOW)

    assert result.state.status == ResearchRunStatus.PARTIAL
    assert any(node.result and node.result.status == ResearchNodeStatus.EMPTY for node in result.state.nodes)
    assert all(observation.value != Decimal("0") for observation in result.observations)


def test_required_partial_result_fails_run_but_preserves_partial_evidence() -> None:
    node = ResearchNodeSpec(
        node_id="required-partial",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=1000,
    )

    class PartialProvider(DelayedSuccessProvider):
        async def execute(self, request: ProviderRequest) -> ProviderResult:
            self.calls.append(request.subject)
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=compute_request_fingerprint(request),
                provider=self.name,
                status=ProviderStatus.PARTIAL,
                retrieved_at=NOW,
                records=(
                    ProviderRecord(
                        source="partial-source",
                        record_id="partial-record",
                        fields={"value": 10.0},
                        units={"value": "CNY"},
                        period="2026-Q2",
                        observed_at=NOW,
                        lineage_id="partial-lineage",
                    ),
                ),
                missing_fields=("other_value",),
            )

    partial_request = _request("required-partial", "FUND_DATA", "PARTIAL")
    partial_request = ResearchNodeRequest(
        node_id=partial_request.node_id,
        request=partial_request.request.model_copy(
            update={"required_fields": ("value", "other_value")}
        ),
    )
    result = _run(
        _state((node,)),
        PartialProvider(),
        {"required-partial": partial_request},
        started_at=NOW,
        clock=lambda: NOW,
    )

    assert result.state.status == ResearchRunStatus.FAILED
    assert result.state.issues
    assert result.state.issues[0].code.value == "REQUIRED_NODE_INCOMPLETE"
    assert result.state.nodes[0].status == ResearchNodeRunStatus.PARTIAL
    assert len(result.observations) == 1
    assert result.observations[0].quality_status == EvidenceQualityStatus.PARTIAL


def test_numeric_evidence_without_lineage_remains_observable_but_not_independent() -> None:
    node = ResearchNodeSpec(
        node_id="unlinked",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=1000,
    )

    class UnlinkedProvider(DelayedSuccessProvider):
        async def execute(self, request: ProviderRequest) -> ProviderResult:
            self.calls.append(request.subject)
            return ProviderResult(
                request_id=request.request_id,
                request_fingerprint=compute_request_fingerprint(request),
                provider=self.name,
                status=ProviderStatus.SUCCESS,
                retrieved_at=NOW,
                records=(
                    ProviderRecord(
                        source="unlinked-source",
                        record_id="unlinked-record",
                        fields={"value": 10.0},
                        units={"value": "CNY"},
                        period="2026-Q2",
                        observed_at=NOW,
                        lineage_id=None,
                    ),
                ),
            )

    result = _run(
        _state((node,)),
        UnlinkedProvider(),
        {"unlinked": _request("unlinked", "FUND_DATA", "UNLINKED")},
        started_at=NOW,
        clock=lambda: NOW,
    )

    assert result.state.status == ResearchRunStatus.COMPLETED
    assert result.observations[0].lineage_id is None
    assert result.evidence[0].lineage_id is None


def test_provider_exception_maps_to_safe_failed_node_without_secret() -> None:
    node = ResearchNodeSpec(
        node_id="exploding",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=1000,
    )
    result = _run(
        _state((node,)),
        ExplodingProvider(),
        {"exploding": _request("exploding", "FUND_DATA", "FAILURE")},
        started_at=NOW,
        clock=lambda: NOW,
    )

    assert result.state.status == ResearchRunStatus.FAILED
    node_result = result.state.nodes[0].result
    assert node_result is not None and node_result.status == ResearchNodeStatus.FAILED
    serialized = result.model_dump_json().lower()
    assert "api_key" not in serialized
    assert "must-not-escape" not in serialized


def test_provider_identity_and_sensitive_values_are_rejected_safely() -> None:
    node = ResearchNodeSpec(
        node_id="identity",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=1000,
    )
    result = _run(
        _state((node,)),
        WrongIdentityProvider(),
        {"identity": _request("identity", "FUND_DATA", "IDENTITY")},
        started_at=NOW,
        clock=lambda: NOW,
    )
    assert result.state.status == ResearchRunStatus.FAILED
    assert result.evidence == ()

    node = node.model_copy(update={"node_id": "value-filter"})
    result = _run(
        _state((node,)),
        SecretValueProvider(),
        {"value-filter": _request("value-filter", "FUND_DATA", "SENSITIVE_VALUE")},
        started_at=NOW,
        clock=lambda: NOW,
    )
    assert result.state.status == ResearchRunStatus.FAILED
    assert result.evidence == ()
    assert "api_key" not in result.model_dump_json().lower()


def test_timeout_maps_to_failed_required_run() -> None:
    node = ResearchNodeSpec(
        node_id="slow",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=30,
    )
    request = _request("slow", "FUND_DATA", "SLOW", timeout_ms=30)
    result = _run(
        _state((node,), budget_ms=500, created_at=datetime.now(UTC)),
        SlowProvider(),
        {"slow": request},
        started_at=datetime.now(UTC),
    )

    assert result.state.status == ResearchRunStatus.FAILED
    assert result.state.nodes[0].result is not None
    assert result.state.nodes[0].result.status == ResearchNodeStatus.FAILED
    assert result.evidence == ()


def test_request_set_is_exact_and_operation_is_bound_to_node_kind() -> None:
    node = ResearchNodeSpec(
        node_id="fund-node",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=1000,
    )
    state = _state((node,))
    with pytest.raises(ValueError, match="match every plan node"):
        _run(state, DelayedSuccessProvider(), {})
    with pytest.raises(ValueError, match="operation does not match"):
        _run(
            state,
            DelayedSuccessProvider(),
            {"fund-node": _request("fund-node", "MACRO_DATA", "FUND_A")},
        )


def test_sensitive_subject_is_rejected_before_provider_execution() -> None:
    node = ResearchNodeSpec(
        node_id="fund-node",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=1000,
    )
    request = _request("fund-node", "FUND_DATA", "api_key=secret")
    with pytest.raises(ValueError, match="disallowed"):
        _run(
            _state((node,)),
            DelayedSuccessProvider(),
            {"fund-node": request},
        )


def test_execution_result_contract_rejects_dangling_or_mismatched_observation() -> None:
    node = ResearchNodeSpec(
        node_id="fund-node",
        owner_id=OWNER,
        node_kind=ResearchNodeKind.FUND,
        required=True,
        timeout_ms=1000,
    )
    state = _state((node,))
    with pytest.raises(ValueError, match="unknown evidence"):
        from app.research import ResearchObservation

        ResearchRunExecutionResult(
            state=state,
            observations=(
                ResearchObservation(
                    observation_id="orphan-observation",
                    owner_id=OWNER,
                    evidence_id="unknown-evidence",
                    subject="FUND_A",
                    metric="value",
                    value=10,
                    unit="CNY",
                    period="2026-Q2",
                    provider="provider",
                    source="source",
                    lineage_id="lineage",
                    quality_status=EvidenceQualityStatus.VERIFIED,
                    retrieved_at=NOW,
                ),
            ),
        )
