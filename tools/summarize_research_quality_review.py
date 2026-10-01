"""Deterministic human-review counts; no answer generation or financial calculation."""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = "research-quality-review.v1"
SCENARIOS = {"NORMAL", "MISSING", "STALE", "CONFLICT", "ISOLATION", "INJECTION"}
LABELS = {"support": {"SUPPORTED", "UNSUPPORTED", "UNCERTAIN"},
          "citation_support": {"SUPPORTED", "UNSUPPORTED", "UNCERTAIN"},
          "numeric_consistency": {"CONSISTENT", "INCONSISTENT", "UNVERIFIED"},
          "numeric_source_verified": {"YES", "NO", "UNCERTAIN"},
          "answerability": {"SUFFICIENT", "INSUFFICIENT", "UNCERTAIN"},
          "refusal": {"NOT_REFUSED", "REASONABLE", "WRONG"},
          "isolation_time": {"PASS", "FAIL", "UNCERTAIN"}}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _aware(value):
    if not _text(value):
        return False
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.tzinfo is not None and date.utcoffset() is not None
    except ValueError:
        return False


def _ids(value):
    return isinstance(value, list) and all(_text(item) for item in value) and len(set(value)) == len(value)


def validate(pack):
    if not isinstance(pack, dict) or pack.get("schema_version") != SCHEMA:
        raise ValueError("unsupported review schema")
    if pack.get("corpus_kind") not in {"REAL_CORPUS", "SYNTHETIC_FROZEN"} or not _text(pack.get("dataset_id")):
        raise ValueError("dataset id and explicit corpus kind are required")
    items = pack.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("review requires at least one question")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or not _text(item.get("id")) or item["id"] in seen:
            raise ValueError("question ids must be unique")
        seen.add(item["id"])
        if item.get("scenario") is not None and (not isinstance(item["scenario"], str) or item["scenario"] not in SCENARIOS):
            raise ValueError("scenario must be NORMAL/MISSING/STALE/CONFLICT/ISOLATION/INJECTION or null")
        if any(not isinstance(item.get(key), str) for key in ("question", "answer")):
            raise ValueError("question and recorded answer must be strings")
        if not _ids(item.get("retrieved_evidence_ids")) or not (item.get("relevant_evidence_ids") is None or _ids(item["relevant_evidence_ids"])):
            raise ValueError("evidence ids must be unique strings or unlabelled relevance null")
        if item.get("relevant_evidence_ids") is not None and len(item["relevant_evidence_ids"]) > 10:
            raise ValueError("frozen relevance has at most ten evidence ids per question")
        documents = item.get("source_documents")
        if not isinstance(documents, list):
            raise ValueError("source_documents must be an array")
        doc_ids = set()
        for doc in documents:
            if not isinstance(doc, dict) or not _text(doc.get("id")) or doc["id"] in doc_ids or any(not isinstance(doc.get(key), str) for key in ("title", "text")):
                raise ValueError("document ids and original text structure are invalid")
            doc_ids.add(doc["id"])
            if any(doc.get(key) is not None and not isinstance(doc[key], str) for key in ("source_url", "published_at")):
                raise ValueError("document source and publication time must be strings or null")
        claims = item.get("atomic_claims")
        if not isinstance(claims, list):
            raise ValueError("atomic_claims must be an array")
        claim_ids = set()
        for claim in claims:
            if not isinstance(claim, dict) or not _text(claim.get("id")) or claim["id"] in claim_ids or not isinstance(claim.get("text"), str) or type(claim.get("critical_financial_numeric")) is not bool or not _ids(claim.get("citation_ids")):
                raise ValueError("atomic claim ids, financial flags or citation structure are invalid")
            claim_ids.add(claim["id"])
        for annotation in [item.get("annotation", {}), *(claim.get("assessment", {}) for claim in claims)]:
            if not isinstance(annotation, dict):
                raise ValueError("annotation must be an object")
            for key, values in LABELS.items():
                if annotation.get(key) is not None and (not isinstance(annotation[key], str) or annotation[key] not in values):
                    raise ValueError(f"invalid manual label: {key}")
            for key in ("basis", "notes", "numeric_reference"):
                if annotation.get(key) is not None and not isinstance(annotation[key], str):
                    raise ValueError(f"annotation text is invalid: {key}")
    return pack


def _ratio(numerator, denominator, missing=0):
    return {"numerator": numerator, "denominator": denominator,
            "missing_annotations": missing,
            "value": numerator / denominator if denominator and not missing else None,
            "status": "N/A" if not denominator else "NOT_EVALUATED" if missing else "CALCULATED"}


def summarize(pack):
    validate(pack)
    claims = [(item, claim) for item in pack["items"] for claim in item["atomic_claims"]]
    cited = [(item, claim) for item, claim in claims if claim["citation_ids"]]
    numeric = [(item, claim) for item, claim in claims if claim["critical_financial_numeric"]]
    pending, completeness, citation_bad_ids = [], [], []
    for item in pack["items"]:
        docs = {doc["id"]: doc for doc in item["source_documents"]}
        if not _text(item["question"]) or not _text(item["answer"]): completeness.append(f"{item['id']}: question/recorded answer missing")
        for doc in docs.values():
            if not _text(doc["text"]) or not _text(doc["title"]): completeness.append(f"{item['id']}/{doc['id']}: original text missing")
        for claim in item["atomic_claims"]:
            if not _text(claim["text"]): completeness.append(f"{item['id']}/{claim['id']}: claim text missing")
            annotation = claim.get("assessment", {})
            if annotation.get("support") not in {"SUPPORTED", "UNSUPPORTED"} or not _text(annotation.get("basis")):
                pending.append(f"{item['id']}/{claim['id']}: support/basis")
            if annotation.get("support") == "SUPPORTED" and not any(_text(doc["text"]) for doc in docs.values()): completeness.append(f"{item['id']}/{claim['id']}: supported label without original")
            invalid_ids = set(claim["citation_ids"]) - docs.keys()
            if invalid_ids: citation_bad_ids.append(f"{item['id']}/{claim['id']}: unknown citation ids")
            if claim["citation_ids"] and annotation.get("citation_support") not in {"SUPPORTED", "UNSUPPORTED"}: pending.append(f"{item['id']}/{claim['id']}: citation support")
            if claim["critical_financial_numeric"] and (annotation.get("numeric_consistency") not in {"CONSISTENT", "INCONSISTENT"} or annotation.get("numeric_source_verified") != "YES" or not _text(annotation.get("numeric_reference"))): pending.append(f"{item['id']}/{claim['id']}: independently verified numeric reference")
        annotation = item.get("annotation", {})
        for key in ("answerability", "refusal", "isolation_time"):
            if annotation.get(key) is None or annotation.get(key) == "UNCERTAIN": pending.append(f"{item['id']}: {key}")
        if not _text(annotation.get("notes")): pending.append(f"{item['id']}: annotation basis")
        if item["relevant_evidence_ids"] is None: pending.append(f"{item['id']}: relevance not labelled")
        elif set(item["relevant_evidence_ids"]) - docs.keys(): completeness.append(f"{item['id']}: relevant evidence absent from originals")
    def annotation(claim): return claim.get("assessment", {})
    missing_support = sum(annotation(claim).get("support") not in {"SUPPORTED", "UNSUPPORTED"} or not _text(annotation(claim).get("basis")) for _, claim in claims)
    missing_citation = sum(annotation(claim).get("citation_support") not in {"SUPPORTED", "UNSUPPORTED"} or not _text(annotation(claim).get("basis")) or bool(set(claim["citation_ids"]) - {doc["id"] for doc in item["source_documents"]}) for item, claim in cited)
    missing_numeric = sum(annotation(claim).get("numeric_consistency") not in {"CONSISTENT", "INCONSISTENT"} or annotation(claim).get("numeric_source_verified") != "YES" or not _text(annotation(claim).get("numeric_reference")) for _, claim in numeric)
    unsupported = _ratio(sum(annotation(claim).get("support") == "UNSUPPORTED" for _, claim in claims), len(claims), missing_support)
    citations = _ratio(sum(annotation(claim).get("citation_support") == "SUPPORTED" for _, claim in cited), len(cited), missing_citation)
    numbers = _ratio(sum(annotation(claim).get("numeric_consistency") == "CONSISTENT" for _, claim in numeric), len(numeric), missing_numeric)
    sufficient = [item for item in pack["items"] if item.get("annotation", {}).get("answerability") == "SUFFICIENT"]
    uncertain_answerability = sum(item.get("annotation", {}).get("answerability") not in {"SUFFICIENT", "INSUFFICIENT"} for item in pack["items"])
    refusal_missing = uncertain_answerability + sum(item.get("annotation", {}).get("refusal") not in LABELS["refusal"] for item in sufficient)
    wrong_refusal = _ratio(sum(item.get("annotation", {}).get("refusal") == "WRONG" for item in sufficient), len(sufficient), refusal_missing)
    recall_items = [item for item in pack["items"] if item["relevant_evidence_ids"]]
    recall_missing = sum(item["relevant_evidence_ids"] is None for item in pack["items"])
    recall = {"denominator": len(recall_items), "missing_annotations": recall_missing, "value": None, "status": "N/A" if not recall_items else "NOT_EVALUATED" if recall_missing else "CALCULATED"}
    if recall["status"] == "CALCULATED": recall["value"] = sum(len(set(item["retrieved_evidence_ids"][:10]) & set(item["relevant_evidence_ids"])) / len(item["relevant_evidence_ids"]) for item in recall_items) / len(recall_items)
    isolation = {"events": sum(item.get("annotation", {}).get("isolation_time") == "FAIL" for item in pack["items"]), "question_count": len(pack["items"]), "missing_annotations": sum(item.get("annotation", {}).get("isolation_time") not in {"PASS", "FAIL"} for item in pack["items"])}
    if not _text(pack.get("reviewer")): pending.append("reviewer missing")
    if not _aware(pack.get("frozen_at")): completeness.append("aware frozen_at missing")
    if pack["corpus_kind"] == "REAL_CORPUS":
        for item in pack["items"]:
            for doc in item["source_documents"]:
                parsed = urlparse(doc.get("source_url") or "")
                if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password or not _aware(doc.get("published_at")):
                    completeness.append(f"{item['id']}/{doc['id']}: real provenance/publication time missing")
    metrics = {"unsupported_atomic_fact_rate": unsupported, "citation_support_rate": citations, "critical_numeric_consistency": numbers, "recall_at_10": recall, "wrong_refusal_rate": wrong_refusal, "isolation_time_errors": isolation}
    observed_scenarios = sorted({item["scenario"] for item in pack["items"] if item.get("scenario")})
    missing_scenarios = sorted(SCENARIOS - set(observed_scenarios))
    unassigned_scenarios = sum(item.get("scenario") is None for item in pack["items"])
    sample_blockers = []
    if len(pack["items"]) < 100: sample_blockers.append("MINIMUM_100_QUESTIONS_NOT_MET")
    if missing_scenarios: sample_blockers.append("REQUIRED_SCENARIOS_MISSING: " + ", ".join(missing_scenarios))
    if unassigned_scenarios: sample_blockers.append(f"SCENARIO_UNASSIGNED: {unassigned_scenarios}")
    sample_coverage = {"minimum_questions": 100, "question_count": len(pack["items"]), "required_scenarios": sorted(SCENARIOS), "observed_scenarios": observed_scenarios, "missing_scenarios": missing_scenarios, "unassigned_question_count": unassigned_scenarios, "blockers": sample_blockers}
    eligible = not sample_blockers and not pending and not completeness and not citation_bad_ids and all(metric["status"] == "CALCULATED" for metric in (unsupported, citations, numbers, recall, wrong_refusal))
    passed = eligible and unsupported["numerator"] * 100 <= unsupported["denominator"] and citations["numerator"] * 100 >= citations["denominator"] * 95 and numbers["numerator"] == numbers["denominator"] and recall["value"] >= .9 and wrong_refusal["numerator"] * 100 <= wrong_refusal["denominator"] * 5 and isolation["events"] == 0
    gate = "NOT_APPLICABLE_SYNTHETIC" if pack["corpus_kind"] != "REAL_CORPUS" else "UNVERIFIED" if not eligible else "PASS_HUMAN_LABELS_ONLY" if passed else "FAIL"
    return {"schema_version": "research-quality-summary.v1", "dataset_id": pack["dataset_id"], "corpus_kind": pack["corpus_kind"], "input_hash": sha256(json.dumps(pack, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "reviewer": pack.get("reviewer"), "question_count": len(pack["items"]), "atomic_claim_count": len(claims), "sample_coverage": sample_coverage, "metrics": metrics, "pending_annotations": pending, "input_completeness_errors": completeness + citation_bad_ids, "financial_gate": gate, "thresholds": {"minimum_questions": 100, "critical_numeric_consistency": 1, "unsupported_atomic_fact_rate_max": .01, "citation_support_rate_min": .95, "recall_at_10_min": .9, "wrong_refusal_rate_max": .05, "isolation_time_errors_max": 0}, "limitations": "人工标签统计，不自动证明来源真实、声明分解完整或冻结样本代表性；至少100题且覆盖正常/缺失/过期/冲突/隔离/注入，缺少场景标识阻断门槛。门槛为计划拟议值，PASS_HUMAN_LABELS_ONLY不构成上线审批。合成操作样例不能通过真实金融门槛。"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        pack = json.loads(args.input.read_text(encoding="utf-8-sig"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON literal")))
        result = summarize(pack)
    except (ValueError, OSError, TypeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"financial_gate={result['financial_gate']}; questions={result['question_count']}; pending={len(result['pending_annotations'])}")


if __name__ == "__main__":
    main()
