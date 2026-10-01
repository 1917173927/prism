"""One real, bounded public crawl; retains safe success and failure evidence."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from app.service.knowledge import KnowledgeService
from app.service.knowledge_crawler import KnowledgeCrawler
from app.store.sqlite import SQLiteDecisionEventStore
from tools.evaluate_research_knowledge import KeywordOnlyEmbedder


async def verify_public_sources():
    database_dir = Path("data/private/research-verification")
    database_dir.mkdir(parents=True, exist_ok=True)
    store = SQLiteDecisionEventStore(database_dir / ("public-crawl-" + uuid4().hex + ".sqlite"))
    service = KnowledgeService(store, embedder=KeywordOnlyEmbedder())
    crawler = KnowledgeCrawler(service)
    try:
        result = await crawler.run_once("research-source-verification")
        sources = crawler.list_sources()
        documents = service.list_documents("research-source-verification")
        return {"schema_version": "research-public-source-verification.v1", "generated_at": datetime.now(UTC).isoformat(),
                "execution": "REAL_PUBLIC_NETWORK_NO_FIXTURE_TRANSPORT", "result": result,
                "source_statuses": sources, "stored_document_count": len(documents),
                "stored_chunk_count": store._connection.execute("SELECT COUNT(*) AS count FROM knowledge_chunks").fetchone()["count"],
                "embedding_mode": "DISABLED_FOR_NETWORK_INGESTION_VALIDATION",
                "limitations": "单轮受控来源采集；失败状态如实保留。不证明来源覆盖完整、金融声明真实性或长期采集稳定性。"}
    finally:
        await crawler.close()
        store.close()


def main():
    result = asyncio.run(verify_public_sources())
    destination = Path("output/research/crawler-live.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["result"]["status"], "stored_documents": result["stored_document_count"],
                      "stored_chunks": result["stored_chunk_count"], "sources": result["result"]["sources"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
