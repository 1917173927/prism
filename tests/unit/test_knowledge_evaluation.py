import json

from tools.evaluate_research_knowledge import CASE_PATH, compare_reports, evaluate


def test_frozen_hundred_questions_report_retrieval_without_invented_human_metrics():
    dataset = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    assert len(dataset["questions"]) == 100
    assert len({case["id"] for case in dataset["questions"]}) == 100
    result = evaluate()
    assert result["question_count"] == 100
    assert result["isolation_and_time_error_events"] == 0
    assert result["hybrid_question_count"] == 0
    # This baseline intentionally includes cross-language semantic questions;
    # no acceptance threshold is fabricated from keyword retrieval performance.
    assert 0 <= result["recall_at_10"]["value"] <= 1
    assert result["recall_at_10"]["denominator"] == 70
    for metric in ("human_fact_correctness", "human_citation_support", "unsupported_atomic_fact_rate"):
        assert result[metric]["status"] == "NOT_EVALUATED"
        assert result[metric]["value"] is None
    assert result["critical_numeric_consistency"]["status"] == "N/A"
    assert result["truncated_question_count"] == 0
    assert compare_reports(result, result)["retrieval_gate"] == "UNVERIFIED"
