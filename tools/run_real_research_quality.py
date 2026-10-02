"""Execute a frozen real-document corpus through the existing research tool.

Answers come from the application's tool and extractor, never the relevance
labels. This is a document-path evaluation, not a real-model planning benchmark.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, UTC
from hashlib import sha256
import json
from pathlib import Path
import time

from app.llm.agent import CopilotAgent
from app.service.knowledge import KnowledgeDocumentInput, KnowledgeService
from app.service.knowledge_embedding import LocalKnowledgeEmbedder
from app.store.sqlite import SQLiteDecisionEventStore


class KeywordBaseline:
    model_id, revision = "keyword-baseline", "none"

    def encode(self, *_args, **_kwargs):
        raise RuntimeError("baseline intentionally has no vectors")


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_frozen(frozen):
    if frozen.get("schema_version") != "research-real-cases.v1":
        raise ValueError("unsupported frozen case schema")
    stamp = datetime.fromisoformat(frozen["frozen_at"])
    if stamp.utcoffset() is None:
        raise ValueError("freeze requires an aware timestamp")
    for collection in ("documents", "questions"):
        ids = [item["id"] for item in frozen[collection]]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError(f"{collection} identifiers must be unique")
    document_ids = {item["id"] for item in frozen["documents"]}
    for item in frozen["documents"]:
        document = KnowledgeDocumentInput.model_validate(item["document"])
        if item["extract_sha256"] != sha256(document.text.encode()).hexdigest():
            raise ValueError("frozen original extract hash mismatch")
        if not item.get("provenance", {}).get("raw_sha256"):
            raise ValueError("original downloaded source hash is required")
        for field in item.get("numeric_fields", []):
            if str(field.get("reference_revision", "")).startswith("SAME_VINTAGE") and str(field.get("reference_version_relation", "")).startswith("LATER_REVISED"):
                raise ValueError("resolved same-vintage reference retains a contradictory revision marker")
    for item in frozen["questions"]:
        if "answer" in item or "assessment" in item:
            raise ValueError("questions must be frozen before answers or review")
        if len(item["relevant_documents"]) > 10:
            raise ValueError("at most ten frozen relevant documents")
        if (set(item["relevant_documents"]) | set(item.get("forbidden_documents", []))) - document_ids:
            raise ValueError("unknown frozen document")
    return frozen


def _claims(question_id, matches, document_metadata):
    """Inventory every returned extract; numeric fields are reviewed separately.

    Field inventories originate in frozen source annotations, independently of
    retrieval. They contain no answer labels and are subject to separate audit.
    """
    claims = []
    for match in matches:
        source = document_metadata[match["document_id"]]
        fields = source.get("numeric_fields", [])
        # Preserve an exact quotation as a distinct attributed-text statement.
        claims.append({"id": f"{question_id}.claim{len(claims) + 1}",
                       "text": match["text"], "citation_ids": [match["chunk_id"]],
                       "critical_financial_numeric": False, "assessment": {},
                       "claim_type": "ATTRIBUTED_ORIGINAL_EXTRACT"})
        for field in fields:
            if field["token"] not in match["text"]:
                continue
            claims.append({"id": f"{question_id}.claim{len(claims) + 1}",
                           "text": field["statement"], "citation_ids": [match["chunk_id"]],
                           "critical_financial_numeric": True, "assessment": {},
                           "claim_type": "QUOTED_NUMERIC_FIELD", "numeric_field": field})
    if not matches:
        claims.append({"id": f"{question_id}.claim1",
                       "text": "未取得当前仍有效的可见原文；本轮不形成有依据结论。",
                       "citation_ids": [], "critical_financial_numeric": False,
                       "claim_type": "EXECUTION_ABSTENTION", "assessment": {}})
    return claims


async def execute(frozen, *, hybrid=False, embedder=None):
    validate_frozen(frozen)
    stamp = datetime.fromisoformat(frozen["frozen_at"])
    store = SQLiteDecisionEventStore()
    local_embedder = embedder or (LocalKnowledgeEmbedder() if hybrid else KeywordBaseline())
    service = KnowledgeService(store, clock=lambda: stamp, embedder=local_embedder,
                               hybrid_enabled=hybrid)
    ids, metadata, chunks = {}, {}, {}
    try:
        for item in frozen["documents"]:
            record = service.ingest(item["owner_id"], KnowledgeDocumentInput.model_validate(item["document"]),
                                    admin=item["document"]["visibility"] == "PUBLIC")
            ids[item["id"]] = record["document_id"]
            metadata[record["document_id"]] = item
            rows = store._connection.execute("SELECT chunk_id,text FROM knowledge_chunks WHERE document_id=? ORDER BY paragraph,chunk_id",
                                             (record["document_id"],)).fetchall()
            chunks[item["id"]] = [dict(row) for row in rows]
            if len(rows) != 1:
                raise ValueError("real evaluation extracts must each be one original chunk")
        # Gold chunk identities exist before the first search; search cannot
        # contribute to relevance assignment or change the frozen questions.
        gold = {case["id"]: [chunks[key][0]["chunk_id"] for key in case["relevant_documents"]]
                for case in frozen["questions"]}
        records, items, latency = [], [], []
        for case in frozen["questions"]:
            args = {key: case[key] for key in ("query", "subject", "period", "as_of") if case.get(key) is not None}
            agent = CopilotAgent().with_owner(case["owner_id"], knowledge_service=service)
            started = time.perf_counter()
            result = await agent._execute_tool("search_research_knowledge", args, {}, None)
            answer = agent._synthesize_grounded_response(case["question"], {},
                        [{"tool": "search_research_knowledge", "args": args, "result": result}], None)
            elapsed_ms = (time.perf_counter() - started) * 1000
            latency.append(elapsed_ms)
            matches = result.get("matches", [])
            retrieved_ids = [match["chunk_id"] for match in matches]
            forbidden = {ids[key] for key in case.get("forbidden_documents", [])}
            invalid = [match["document_id"] for match in matches if match["document_id"] in forbidden]
            reference_keys = set(case["relevant_documents"]) | set(case.get("review_documents", []))
            docs = {}
            for key in reference_keys:
                source = next(item for item in frozen["documents"] if item["id"] == key)
                original = source["document"]
                chunk = chunks[key][0]
                docs[chunk["chunk_id"]] = {"id": chunk["chunk_id"], "title": original["title"],
                    "text": chunk["text"], "source_url": original["source_url"],
                    "published_at": original["published_at"], "provenance": source["provenance"],
                    "evaluation_access": {"owner": source["owner_id"], "visibility": original["visibility"]}}
            checks = []
            for match in matches:
                docs[match["chunk_id"]] = {"id": match["chunk_id"], "title": match["title"],
                    "text": match["text"], "source_url": match["source_url"],
                    "published_at": match["published_at"], "provenance": metadata[match["document_id"]]["provenance"]}
                checks.append(service.verify_citations(case["owner_id"], [{**match, "quote": match["text"]}],
                                                        as_of=case.get("as_of")))
            items.append({"id": case["id"], "scenario": case["scenario"], "question": case["question"],
                "answer": answer, "source_documents": list(docs.values()),
                "retrieved_evidence_ids": retrieved_ids, "relevant_evidence_ids": gold[case["id"]],
                "atomic_claims": _claims(case["id"], matches, metadata), "annotation": {},
                "review_context": {key: case[key] for key in ("owner_id", "subject", "period", "as_of", "expected_behavior", "controlled_context") if key in case}})
            records.append({"question_id": case["id"], "request": args,
                "authorized_owner": case["owner_id"], "tool_result": result, "answer": answer,
                "answer_sha256": sha256(answer.encode()).hexdigest(), "citation_checks": checks,
                "gold_chunk_ids": gold[case["id"]], "forbidden_returned": invalid,
                "elapsed_ms": round(elapsed_ms, 3)})
        recall_values = [len(set(item["retrieved_evidence_ids"][:10]) & set(item["relevant_evidence_ids"])) /
                         len(item["relevant_evidence_ids"]) for item in items if item["relevant_evidence_ids"]]
        latency.sort()
        pack = {"schema_version": "research-quality-review.v1", "dataset_id": frozen["dataset_id"] + (".hybrid" if hybrid else ".keyword"),
                "corpus_kind": "REAL_CORPUS", "frozen_at": frozen["frozen_at"], "reviewer": "",
                "review_method": "UNREVIEWED", "items": items,
                "evaluation_scope": "EXISTING_DOCUMENT_TOOL_AND_GROUNDED_EXTRACTOR_NO_LLM_PLANNER",
                "source_dataset_hash": digest(frozen)}
        report = {"schema_version": "research-real-execution.v1", "dataset_id": frozen["dataset_id"],
                  "generated_at": datetime.now(UTC).isoformat(), "frozen_input_hash": digest(frozen),
                  "review_pack_hash": digest(pack), "execution_scope": pack["evaluation_scope"],
                  "question_count": len(items), "scenarios": dict(Counter(item["scenario"] for item in items)),
                  "modes": dict(Counter(record["tool_result"].get("mode", "ERROR") for record in records)),
                  "recall_at_10": sum(recall_values) / len(recall_values) if recall_values else None,
                  "recall_denominator": len(recall_values), "gold_origin": "FROZEN_SOURCE_LABELS_BEFORE_RETRIEVAL_PENDING_INDEPENDENT_REVIEW",
                  "isolation_time_forbidden_events": sum(len(record["forbidden_returned"]) for record in records),
                  "latency_ms": {"p50": latency[max(0, int(len(latency) * .5) - 1)],
                                 "p95": latency[max(0, int(len(latency) * .95) - 1)],
                                 "p99": latency[max(0, int(len(latency) * .99) - 1)]},
                  "human_quality_gate": "NOT_EVALUATED", "production_hybrid_enabled": False,
                  "records": records}
        return pack, report
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hybrid", action="store_true")
    args = parser.parse_args()
    frozen = json.loads(args.cases.read_text(encoding="utf-8-sig"))
    pack, report = asyncio.run(execute(frozen, hybrid=args.hybrid))
    mode = "hybrid" if args.hybrid else "keyword"
    save(args.output_dir / f"{mode}-review.json", pack)
    save(args.output_dir / f"{mode}-execution.json", report)
    print(json.dumps({key: report[key] for key in ("question_count", "scenarios", "modes", "recall_at_10", "isolation_time_forbidden_events", "latency_ms")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
