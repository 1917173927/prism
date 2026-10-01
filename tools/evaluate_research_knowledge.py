"""Frozen synthetic retrieval evaluation; never fabricates human correctness labels."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import time

from app.service.knowledge import KnowledgeDocumentInput, KnowledgeService
from app.service.knowledge_embedding import MODEL_ID, MODEL_REVISION
from app.store.sqlite import SQLiteDecisionEventStore

CASE_PATH = Path(__file__).resolve().parents[1] / "eval_cases" / "research" / "knowledge_100.json"


class KeywordOnlyEmbedder:
    model_id, revision = "disabled-baseline", "disabled"
    def encode(self, *args, **kwargs):
        raise RuntimeError("keyword baseline")


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None,
            "status": "CALCULATED" if denominator else "N/A"}


def evaluate(*, hybrid=False, case_path=CASE_PATH):
    content = Path(case_path).read_bytes()
    frozen = json.loads(content)
    store = SQLiteDecisionEventStore()
    service = KnowledgeService(store, clock=lambda: datetime(2026, 10, 1, tzinfo=UTC),
                               embedder=None if hybrid else KeywordOnlyEmbedder(), hybrid_enabled=hybrid)
    ids = {}
    started = time.perf_counter()
    try:
        for item in frozen["documents"]:
            record = service.ingest(item["owner_id"], KnowledgeDocumentInput.model_validate(item["document"]), admin=item["document"]["visibility"] == "PUBLIC")
            ids[item["id"]] = record["document_id"]
        details, recalls, latency, isolation_events, refused_available, quote_passed, quote_total = [], [], [], 0, 0, 0, 0
        for case in frozen["questions"]:
            deleted = case.get("deleted_document")
            if deleted:
                service.delete("fixture-owner", ids[deleted], admin=True)
            result = service.search(case["owner_id"], case["query"], subject=case.get("subject"),
                                    period=case.get("period"), as_of=case.get("as_of"))
            returned = {item["document_id"] for item in result["matches"]}
            expected = {ids[key] for key in case["expected_documents"]}
            forbidden = {ids[key] for key in case.get("forbidden_documents", [])}
            isolation_events += len(returned & forbidden)
            recall = len(returned & expected) / len(expected) if expected else None
            if recall is not None:
                recalls.append(recall)
                refused_available += int(not returned)
            latency.append(result["elapsed_ms"])
            for match in result["matches"]:
                checked = service.verify_citations(case["owner_id"], [{**match, "quote": match["text"]}], as_of=case.get("as_of"))
                quote_total += 1
                quote_passed += int(checked["status"] == "PASS")
            details.append({"question_id": case["id"], "scenario": case["scenario"], "expected_count": len(expected),
                            "returned_count": len(returned), "recall_at_10": recall,
                            "forbidden_count": len(returned & forbidden), "mode": result["mode"],
                            "candidate_truncated": result["candidate_truncated"], "elapsed_ms": result["elapsed_ms"]})
        latency.sort()
        real_hybrid = sum(item["mode"] == "HYBRID_RRF" for item in details)
        return {"schema_version": "research-knowledge-evaluation.v1", "dataset_hash": sha256(content).hexdigest(),
                "dataset_kind": frozen["dataset_kind"], "labeling": frozen["labeling"], "question_count": len(details),
                "recall_unit": "DOCUMENT_RELEVANCE_PROGRAMMATIC_LABELS_NOT_HUMAN_FRAGMENT_SUPPORT",
                "requested_mode": "HYBRID" if hybrid else "KEYWORD", "hybrid_question_count": real_hybrid,
                "embedding_model": MODEL_ID if hybrid else None, "embedding_revision": MODEL_REVISION if hybrid else None,
                "recall_at_10": {"value": sum(recalls) / len(recalls) if recalls else None, "denominator": len(recalls)},
                "exact_quote_location_integrity": _ratio(quote_passed, quote_total),
                "false_empty_rate": _ratio(refused_available, len(recalls)), "isolation_and_time_error_events": isolation_events,
                "truncated_question_count": sum(item["candidate_truncated"] for item in details),
                "human_fact_correctness": {"status": "NOT_EVALUATED", "value": None},
                "human_citation_support": {"status": "NOT_EVALUATED", "value": None},
                "unsupported_atomic_fact_rate": {"status": "NOT_EVALUATED", "value": None},
                "critical_numeric_consistency": {"status": "N/A", "value": None, "denominator": 0},
                "latency_ms": {"p50": latency[int((len(latency)-1)*0.5)] if latency else None,
                               "p95": latency[int((len(latency)-1)*0.95)] if latency else None},
                "total_seconds": round(time.perf_counter() - started, 3), "questions": details,
                "limitations": "程序构造的受控资料与检索标签；未作逐声明人工事实及引用支持标注。精确引文定位完整性不是人工引用支持率，不能作为金融反幻觉发布达标依据。"}
    finally:
        store.close()


def compare_reports(keyword: dict, hybrid: dict) -> dict:
    if keyword["dataset_hash"] != hybrid["dataset_hash"]:
        raise ValueError("comparison requires the same frozen dataset")
    baseline_recall, hybrid_recall = keyword["recall_at_10"]["value"], hybrid["recall_at_10"]["value"]
    covered = hybrid["hybrid_question_count"] >= hybrid["recall_at_10"]["denominator"] > 0
    eligible = (baseline_recall is not None and hybrid_recall is not None and hybrid_recall >= .9
                and hybrid_recall > baseline_recall and covered and hybrid["isolation_and_time_error_events"] == 0
                and hybrid.get("truncated_question_count", 0) == 0)
    return {"schema_version": "research-knowledge-comparison.v1", "dataset_hash": hybrid["dataset_hash"],
            "recall_unit": "DOCUMENT_RELEVANCE_PROGRAMMATIC_LABELS_NOT_HUMAN_FRAGMENT_SUPPORT",
            "keyword_recall_at_10": baseline_recall, "hybrid_recall_at_10": hybrid_recall,
            "recall_improvement": hybrid_recall - baseline_recall if baseline_recall is not None and hybrid_recall is not None else None,
            "retrieval_gate": "PASS" if eligible else "UNVERIFIED", "automatic_enablement": False,
            "human_financial_correctness_gate": "NOT_EVALUATED",
            "notice": "仅比较冻结合成语料的检索质量；不自动启用生产混合检索，不代表人工金融事实和引用支持发布门槛已通过。"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(hybrid=args.hybrid)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
