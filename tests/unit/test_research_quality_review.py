import copy
import json
from pathlib import Path

import pytest

from tools.summarize_research_quality_review import summarize, validate


STATIC = Path(__file__).resolve().parents[2] / "app/api/static"


def package(name="research-quality-review-demo.json"):
    return json.loads((STATIC / name).read_text(encoding="utf-8"))


def labelled():
    value = package()
    value["reviewer"] = "unit-test-reviewer"
    value["items"] = value["items"][:1]
    item = value["items"][0]
    item["annotation"] = {"answerability": "SUFFICIENT", "refusal": "NOT_REFUSED", "isolation_time": "PASS", "notes": "Fixture only"}
    item["relevant_evidence_ids"] = ["notice-1"]
    for claim in item["atomic_claims"]:
        claim["assessment"] = {"support": "SUPPORTED", "citation_support": "SUPPORTED", "basis": "Fixture label for arithmetic tests, not a factual annotation"}
    return value


def test_unlabelled_keeps_complete_denominators_and_never_passes():
    result = summarize(package())
    facts = result["metrics"]["unsupported_atomic_fact_rate"]
    assert facts["denominator"] == 3
    assert facts["missing_annotations"] == 3
    assert facts["value"] is None
    assert facts["status"] == "NOT_EVALUATED"
    assert result["metrics"]["critical_numeric_consistency"]["status"] == "N/A"
    assert result["financial_gate"] == "NOT_APPLICABLE_SYNTHETIC"
    real = summarize(package("research-quality-review-real-template.json"))
    assert real["financial_gate"] == "UNVERIFIED"
    assert real["pending_annotations"] and real["input_completeness_errors"]


def test_rates_use_full_population_and_citation_ids_not_quote_existence():
    value = labelled()
    value["items"][0]["atomic_claims"][1]["assessment"].update(support="UNSUPPORTED", citation_support="UNSUPPORTED")
    result = summarize(value)
    assert result["metrics"]["unsupported_atomic_fact_rate"]["value"] == .5
    assert result["metrics"]["citation_support_rate"]["value"] == .5
    value["items"][0]["atomic_claims"][0]["citation_ids"] = ["unknown"]
    result = summarize(value)
    assert result["metrics"]["citation_support_rate"]["value"] is None
    assert result["input_completeness_errors"]


def test_real_labels_and_zero_financial_denominator_cannot_pass():
    value = labelled()
    value["corpus_kind"] = "REAL_CORPUS"
    value["items"][0]["source_documents"][0]["source_url"] = "https://example.com/frozen-test"
    result = summarize(value)
    assert result["financial_gate"] == "UNVERIFIED"
    assert result["metrics"]["critical_numeric_consistency"]["denominator"] == 0
    # Artificial flags below exercise gate arithmetic only, never a real acceptance.
    claim = value["items"][0]["atomic_claims"][0]
    claim["critical_financial_numeric"] = True
    claim["assessment"].update(numeric_consistency="CONSISTENT", numeric_source_verified="NO", numeric_reference="unit-test reference")
    assert summarize(value)["financial_gate"] == "UNVERIFIED"
    claim["assessment"]["numeric_source_verified"] = "YES"
    result = summarize(value)
    assert result["financial_gate"] == "UNVERIFIED"
    assert "MINIMUM_100_QUESTIONS_NOT_MET" in result["sample_coverage"]["blockers"]
    value["items"][0]["annotation"]["isolation_time"] = "FAIL"
    assert summarize(value)["financial_gate"] == "UNVERIFIED"


def controlled_hundred_labels():
    """Declared-real fixture exercises gate logic only; never real financial acceptance."""
    value = labelled()
    value["dataset_id"] = "controlled-gate-unit-test-not-real-evidence"
    value["corpus_kind"] = "REAL_CORPUS"
    item = value["items"][0]
    item["source_documents"][0]["source_url"] = "https://example.test/controlled-unit-test"
    claim = item["atomic_claims"][0]
    claim["critical_financial_numeric"] = True
    claim["assessment"].update(numeric_consistency="CONSISTENT", numeric_source_verified="YES", numeric_reference="Artificial counting label, not a verified financial value")
    value["items"] = []
    for index in range(100):
        clone = copy.deepcopy(item)
        clone["id"] = f"controlled-{index}"
        clone["scenario"] = ["NORMAL", "MISSING", "STALE", "CONFLICT", "ISOLATION", "INJECTION"][index % 6]
        value["items"].append(clone)
    return value


def test_hundred_controlled_labels_only_exercise_sample_and_scenario_gate():
    value = controlled_hundred_labels()
    result = summarize(value)
    assert result["financial_gate"] == "PASS_HUMAN_LABELS_ONLY"
    assert result["sample_coverage"]["blockers"] == []
    value["items"] = value["items"][:99]
    assert summarize(value)["financial_gate"] == "UNVERIFIED"
    value = controlled_hundred_labels()
    for item in value["items"]: item["scenario"] = "NORMAL"
    result = summarize(value)
    assert result["financial_gate"] == "UNVERIFIED"
    assert len(result["sample_coverage"]["missing_scenarios"]) == 5


def test_absent_scenario_blocks_even_when_other_questions_cover_six():
    value = controlled_hundred_labels()
    value["items"][0].pop("scenario")
    result = summarize(value)
    assert result["financial_gate"] == "UNVERIFIED"
    assert result["sample_coverage"]["missing_scenarios"] == []
    assert result["sample_coverage"]["unassigned_question_count"] == 1
    assert "SCENARIO_UNASSIGNED: 1" in result["sample_coverage"]["blockers"]
    value = controlled_hundred_labels()
    for item in value["items"]:
        for claim in item["atomic_claims"]: claim["critical_financial_numeric"] = False
    assert summarize(value)["financial_gate"] == "UNVERIFIED"


@pytest.mark.parametrize("scenario", ["OTHER", 7, ["NORMAL"]])
def test_invalid_scenario_rejected(scenario):
    value = labelled(); value["items"][0]["scenario"] = scenario
    with pytest.raises(ValueError, match="scenario"): validate(value)


def test_recall_missing_labels_not_dropped_and_only_top_ten_count():
    value = labelled()
    other = copy.deepcopy(value["items"][0]); other["id"] = "other"; other["relevant_evidence_ids"] = None; value["items"].append(other)
    result = summarize(value)
    assert result["metrics"]["recall_at_10"]["status"] == "NOT_EVALUATED"
    assert result["metrics"]["recall_at_10"]["missing_annotations"] == 1
    other["relevant_evidence_ids"] = []
    value["items"][0]["retrieved_evidence_ids"] = [f"irrelevant-{index}" for index in range(10)] + ["notice-1"]
    assert summarize(value)["metrics"]["recall_at_10"]["value"] == 0


@pytest.mark.parametrize("change", [
    lambda value: value["items"][0]["atomic_claims"][0].update(critical_financial_numeric=1),
    lambda value: value["items"][0]["atomic_claims"][0]["assessment"].update(support="PASS"),
    lambda value: value["items"][0].update(relevant_evidence_ids=["notice-1"] * 2),
    lambda value: value["items"].append(copy.deepcopy(value["items"][0])),
])
def test_rejects_malformed_annotations_and_duplicate_ids(change):
    value = labelled(); change(value)
    with pytest.raises(ValueError): validate(value)
