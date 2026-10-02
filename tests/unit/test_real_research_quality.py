import asyncio
from copy import deepcopy
from hashlib import sha256

import pytest

from tools.run_real_research_quality import execute, validate_frozen


def cases():
    documents = []
    for key, owner, visibility, published in (
        ("available", "publisher", "PUBLIC", "2024-01-02T12:00:00+08:00"),
        ("future", "publisher", "PUBLIC", "2025-01-02T12:00:00+08:00"),
        ("private", "bob", "PRIVATE", "2024-01-02T12:00:00+08:00"),
    ):
        text = {"available": "公开原文：字段金额100亿元。", "future": "未来原文：字段金额200亿元。", "private": "私有原文：字段金额300亿元。"}[key]
        documents.append({"id": key, "owner_id": owner,
            "extract_sha256": sha256(text.encode()).hexdigest(), "provenance": {"raw_sha256": "a" * 64},
            "document": {"title": key, "text": text, "source": "test-only-controlled-source",
                "source_url": f"https://example.com/{key}", "published_at": published,
                "visibility": visibility, "subject": "test", "period": "2024"},
            "numeric_fields": [{"token": text.split("金额")[1].split("亿元")[0], "statement": text, "reference": "separate-test-reference"}]})
    return {"schema_version": "research-real-cases.v1", "dataset_id": "unit-test-only-not-real-evidence",
            "frozen_at": "2026-01-01T00:00:00+00:00", "documents": documents,
            "questions": [{"id": "q1", "question": "原文金额是什么？", "query": "原文 字段金额",
                "owner_id": "alice", "subject": "test", "period": "2024", "as_of": "2024-06-01T00:00:00+08:00",
                "scenario": "ISOLATION", "relevant_documents": ["available"], "forbidden_documents": ["private", "future"],
                "review_documents": ["private", "future"]}]}


def test_answers_use_actual_originals_not_gold_or_reference_statements():
    frozen = cases()
    frozen["documents"][0]["numeric_fields"][0]["statement"] = "INDEPENDENT_REFERENCE_NOT_AN_ANSWER"
    pack, report = asyncio.run(execute(frozen))
    item = pack["items"][0]
    assert "字段金额100亿元" in item["answer"]
    assert "INDEPENDENT_REFERENCE_NOT_AN_ANSWER" not in item["answer"]
    assert "字段金额200亿元" not in item["answer"]
    assert "字段金额300亿元" not in item["answer"]
    assert item["retrieved_evidence_ids"] == item["relevant_evidence_ids"]
    assert report["isolation_time_forbidden_events"] == 0
    assert report["records"][0]["citation_checks"][0]["status"] == "PASS"
    assert pack["review_method"] == "UNREVIEWED"
    assert pack["reviewer"] == ""
    assert all(not claim["assessment"] for claim in item["atomic_claims"])
    assert report["production_hybrid_enabled"] is False


def test_real_empty_execution_abstains_without_invented_values():
    frozen = cases()
    frozen["questions"][0].update(as_of="2023-01-01T00:00:00+08:00", relevant_documents=[])
    pack, report = asyncio.run(execute(frozen))
    item = pack["items"][0]
    assert not item["retrieved_evidence_ids"]
    assert "未取得当前仍有效的可见原文" in item["answer"]
    assert item["atomic_claims"][0]["claim_type"] == "EXECUTION_ABSTENTION"
    assert report["recall_at_10"] is None


@pytest.mark.parametrize("mutation", ["hash", "answers", "unknown_document", "duplicate", "naive_time"])
def test_frozen_integrity_or_gold_boundary_failures_are_blocked(mutation):
    frozen = deepcopy(cases())
    if mutation == "hash":
        frozen["documents"][0]["document"]["text"] += "changed"
    elif mutation == "answers":
        frozen["questions"][0]["answer"] = "precomputed answer"
    elif mutation == "unknown_document":
        frozen["questions"][0]["relevant_documents"] = ["not-in-corpus"]
    elif mutation == "duplicate":
        frozen["questions"].append(frozen["questions"][0])
    else:
        frozen["frozen_at"] = "2026-01-01T00:00:00"
    with pytest.raises(ValueError):
        validate_frozen(frozen)
