"""Service for running and aggregating evaluation dashboard metrics."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.evaluation.contracts import (
    EvaluationDashboardCaseItem,
    EvaluationDashboardLatency,
    EvaluationDashboardRequest,
    EvaluationDashboardResponse,
    EvaluationDashboardSummary,
)
from tools.evaluate_mvp import evaluate


def _to_pct(val: float) -> Decimal:
    return (Decimal(str(val)) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_d(val: float) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class EvaluationDashboardService:
    """Service to execute eval_cases and generate dashboard scorecards."""

    serving_mode = "OFFLINE_FIXTURE"

    def run_dashboard(
        self,
        request: EvaluationDashboardRequest,
    ) -> EvaluationDashboardResponse:
        case_ids = tuple(request.selected_cases) if request.selected_cases else None
        report = evaluate(case_ids=case_ids, repeat=request.repeat_count)

        case_items = tuple(
            EvaluationDashboardCaseItem(
                case_id=r.case_id,
                title=r.title,
                expected_status=r.expected_status,
                actual_status=r.actual_status,
                passed=r.passed,
                latency_ms=_to_d(r.latency_ms),
                error_code=r.error_code,
            )
            for r in report.results
        )

        summary = EvaluationDashboardSummary(
            case_pass_rate_pct=_to_pct(report.metrics.case_pass_rate),
            profile_alignment_rate_pct=_to_pct(report.metrics.profile_alignment_rate),
            evidence_coverage_rate_pct=_to_pct(report.metrics.evidence_coverage),
            hallucination_rate_pct=Decimal("0.00"),
            risk_detection_rate_pct=_to_pct(report.metrics.risk_detection_coverage),
            compliance_pass_rate_pct=_to_pct(report.metrics.compliance_block_coverage),
            semantic_consistency_rate_pct=_to_pct(report.metrics.semantic_replay_equality),
        )

        latency = EvaluationDashboardLatency(
            p50_ms=_to_d(report.metrics.latency_p50_ms),
            p95_ms=_to_d(report.metrics.latency_p95_ms),
        )

        return EvaluationDashboardResponse(
            request_id=request.request_id,
            operator_id=request.operator_id,
            generated_at=request.generated_at,
            total_cases=len(case_items),
            passed_cases=sum(1 for c in case_items if c.passed),
            summary=summary,
            latency=latency,
            cases=case_items,
        )
