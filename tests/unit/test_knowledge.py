from datetime import UTC, datetime
from io import BytesIO
import json

import pytest
from fastapi import FastAPI, Header, Request
from fastapi.testclient import TestClient

from app.api.knowledge_routes import create_knowledge_router
from app.service.knowledge import KnowledgeDocumentInput, KnowledgeService
from app.store.sqlite import SQLiteDecisionEventStore, StoreConflictError, StoreCorruptError, StoreOwnerError

NOW = datetime(2026, 10, 1, tzinfo=UTC)


class NoEmbedding:
    model_id = "unavailable"
    revision = "fixture"

    def encode(self, *args, **kwargs):
        raise RuntimeError("not installed")


class TestEmbedding:
    model_id = "test-embedding"
    revision = "test-revision"

    def encode(self, texts, *, query=False):
        return [[float("波动" in text or "volatility" in text), float("持仓" in text), 0.1] for text in texts]


@pytest.fixture
def knowledge():
    store = SQLiteDecisionEventStore()
    service = KnowledgeService(store, clock=lambda: NOW, embedder=NoEmbedding())
    yield service
    store.close()


def document(**overrides):
    return KnowledgeDocumentInput.model_validate({
        "title": "波动率定义", "text": "实现波动率使用已对齐的历史收益。\n\n缺失值不能补零。",
        "source": "本项目方法说明", "canonical_source": "prism:volatility", "kind": "METHOD",
        "published_at": "2026-09-30T00:00:00+00:00", **overrides,
    })


def citation(service, owner="alice", query="波动率"):
    match = service.search(owner, query)["matches"][0]
    return {**{key: match[key] for key in ("document_id", "chunk_id", "revision", "content_hash")}, "quote": match["text"]}


def test_revision_history_idempotence_and_citation_invalidation(knowledge):
    saved = knowledge.ingest("alice", document())
    assert knowledge.ingest("alice", document())["created"] is False
    reference = citation(knowledge)
    assert knowledge.verify_citations("alice", [reference])["status"] == "PASS"
    corrected = knowledge.ingest("alice", document(text="波动率计算方法已更正。", expected_revision=1))
    assert corrected["document_id"] == saved["document_id"]
    assert corrected["revision"] == 2
    assert knowledge.verify_citations("alice", [reference])["results"][0]["reason"] == "DOCUMENT_VERSION_CHANGED"
    assert knowledge.store._connection.execute("SELECT COUNT(*) AS n FROM knowledge_document_versions").fetchone()["n"] == 2
    with pytest.raises(StoreConflictError):
        knowledge.delete("alice", saved["document_id"], expected_revision=1)
    assert knowledge.delete("alice", saved["document_id"], expected_revision=2)
    assert knowledge.search("alice", "波动率")["matches"] == []
    assert knowledge.verify_citations("alice", [reference])["results"][0]["reason"] == "DOCUMENT_UNAVAILABLE"


def test_scope_and_time_filters_precede_embedding(knowledge):
    knowledge.embedder = TestEmbedding()
    knowledge.hybrid_enabled = True
    knowledge.ingest("bob", document())
    knowledge.ingest("alice", document(canonical_source="future", published_at="2027-01-01T00:00:00+00:00"))
    assert knowledge.search("alice", "波动率")["candidate_count"] == 0
    shared = knowledge.ingest("admin", document(visibility="PUBLIC", subject="000001.SZ", period="2026H1"), admin=True)
    result = knowledge.search("alice", "波动率", subject="000001.SZ", period="2026H1")
    assert result["mode"] == "HYBRID_RRF"
    assert result["rrf_constant"] == 60
    assert result["matches"][0]["document_id"] == shared["document_id"]
    assert knowledge.search("alice", "波动率", period="2025H1")["matches"] == []
    assert knowledge.search("alice", "波动率", as_of="2026-09-01T00:00:00+00:00")["matches"] == []


def test_public_mutations_require_admin_even_for_original_owner(knowledge):
    with pytest.raises(StoreOwnerError):
        knowledge.ingest("alice", document(visibility="PUBLIC"))
    saved = knowledge.ingest("alice", document(visibility="PUBLIC"), admin=True)
    with pytest.raises(StoreOwnerError):
        knowledge.delete("alice", saved["document_id"])
    with pytest.raises(StoreOwnerError):
        knowledge.ingest("alice", document(document_id=saved["document_id"], visibility="PRIVATE"))
    assert knowledge.get("bob", saved["document_id"]) is not None


def test_private_identity_cannot_be_overwritten_or_read(knowledge):
    saved = knowledge.ingest("alice", document())
    assert knowledge.get("bob", saved["document_id"], admin=True) is None
    assert knowledge.delete("bob", saved["document_id"], admin=True) is False
    with pytest.raises(StoreOwnerError):
        knowledge.ingest("bob", document(document_id=saved["document_id"]), admin=True)


def test_quote_support_does_not_certify_paraphrase_or_financial_truth(knowledge):
    knowledge.ingest("alice", document())
    reference = citation(knowledge)
    reference["quote"] = "股票明日上涨百分之十"
    result = knowledge.verify_citations("alice", [reference])
    assert result["status"] == "UNVERIFIED"
    assert result["results"][0]["reason"] == "QUOTE_NOT_SUPPORTED"
    assert "NOT_FINANCIAL_TRUTH" in result["scope"]
    assert knowledge.verify_citations("alice", [citation(knowledge)], as_of="2026-09-01T00:00:00+00:00")["results"][0]["reason"] == "FUTURE_PUBLICATION"


def test_utf8_upload_and_table_header_survive(knowledge):
    meta = document().model_dump(mode="json", exclude={"text", "pages"})
    text = "| 报告期 | 单位 | 收益 |\n| 2026H1 | % | 缺失 |"
    saved = knowledge.upload("alice", "method.md", text.encode(), meta)
    result = knowledge.search("alice", "报告期")["matches"][0]
    assert result["text"] == text
    assert saved["original"]["text"] == text
    with pytest.raises(ValueError):
        knowledge.upload("alice", "method.exe", b"data", meta)
    with pytest.raises(ValueError):
        knowledge.upload("alice", "method.txt", b"\xff", meta)


def test_pdf_page_coordinates_and_encrypted_rejection(knowledge):
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    meta = document().model_dump(mode="json", exclude={"text", "pages"})
    with pytest.raises(ValueError):
        knowledge.upload("alice", "blank.pdf", output.getvalue(), meta)
    writer.encrypt("private")
    output = BytesIO()
    writer.write(output)
    with pytest.raises(ValueError):
        knowledge.upload("alice", "encrypted.pdf", output.getvalue(), meta)
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = pypdf.PdfWriter()
    for text in ("First page definition", "Second page volatility"):
        page = writer.add_blank_page(width=100, height=100)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 80 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    saved = knowledge.upload("alice", "method.pdf", output.getvalue(), meta)
    matches = knowledge.search("alice", "volatility")["matches"]
    assert matches[0]["page"] == 2
    assert matches[0]["document_id"] == saved["document_id"]


@pytest.mark.parametrize("tamper", ["UPDATE knowledge_documents SET published_at='2000-01-01T00:00:00+00:00'", "UPDATE knowledge_chunks SET text='fake'", "UPDATE knowledge_documents SET content_hash='broken'"])
def test_corrupt_metadata_or_chunks_are_not_returned(knowledge, tamper):
    knowledge.ingest("alice", document())
    knowledge.store._connection.execute(tamper)
    with pytest.raises(StoreCorruptError):
        knowledge.search("alice", "波动率")


def test_unavailable_model_explicit_keyword_mode_and_rebuild(knowledge):
    knowledge.ingest("alice", document())
    result = knowledge.search("alice", "波动率")
    assert result["mode"] == "KEYWORD_ONLY"
    assert result["degraded_reason"] == "LOCAL_EMBEDDING_UNAVAILABLE"
    assert result["matches"][0]["status"] == "RETRIEVED_UNVERIFIED"
    assert knowledge.rebuild_embeddings("alice")["status"] == "UNAVAILABLE"
    knowledge.embedder = TestEmbedding()
    assert knowledge.rebuild_embeddings("alice")["indexed"] == 2
    assert knowledge.search("alice", "volatility")["degraded_reason"] == "HYBRID_RELEASE_GATE_DISABLED"
    knowledge.hybrid_enabled = True
    assert knowledge.search("alice", "volatility")["mode"] == "HYBRID_RRF"


def test_citation_cannot_pass_after_chunk_tampering(knowledge):
    knowledge.ingest("alice", document())
    reference = citation(knowledge)
    knowledge.store._connection.execute("UPDATE knowledge_chunks SET text=? WHERE chunk_id=?", ("伪造金融结论", reference["chunk_id"]))
    reference["quote"] = "伪造金融结论"
    assert knowledge.verify_citations("alice", [reference])["results"][0]["reason"] == "CHUNK_INTEGRITY_FAILED"


def test_two_character_chinese_fts_is_indexed(knowledge):
    knowledge.ingest("alice", document(text="基金穿透需要披露持仓。"))
    assert knowledge.fulltext_backend == "SQLITE_FTS5_BIGRAM"
    hits = knowledge.store._connection.execute("SELECT chunk_id FROM knowledge_fts_bigrams WHERE knowledge_fts_bigrams MATCH ?", ('"基金"',)).fetchall()
    assert hits


def test_api_owner_is_server_derived_and_public_write_is_refused(knowledge):
    app = FastAPI()
    def owner(x_owner_id: str = Header("alice")):
        return x_owner_id
    app.include_router(create_knowledge_router(knowledge, owner))
    with TestClient(app) as client:
        body = document().model_dump(mode="json")
        response = client.post("/api/v1/research/knowledge/documents", json=body)
        assert response.status_code == 200
        document_id = response.json()["document_id"]
        assert client.get(f"/api/v1/research/knowledge/documents/{document_id}", headers={"X-Owner-ID": "bob"}).status_code == 404
        assert client.post("/api/v1/research/knowledge/search", json={"query": "波动率", "owner_id": "bob"}).status_code == 422
        assert client.post("/api/v1/research/knowledge/documents", json={**body, "visibility": "PUBLIC"}).status_code == 403
        assert client.post("/api/v1/research/knowledge/search", json={"query": "波动率"}).json()["matches"]


def test_crawler_configuration_api_requires_admin_and_keeps_allowlist(knowledge):
    from app.service.knowledge_crawler import KnowledgeCrawler
    class Fetcher:
        async def close(self):
            pass
    crawler = KnowledgeCrawler(knowledge, fetcher=Fetcher(), seeds=[])
    def owner():
        return "alice"
    body = {"title": "Approved arXiv feed", "url": "https://arxiv.org/api/query?search_query=cat:q-fin", "format": "ATOM"}
    app = FastAPI()
    app.include_router(create_knowledge_router(knowledge, owner, crawler=crawler))
    with TestClient(app) as client:
        assert client.put("/api/v1/research/knowledge/sources/my-feed", json=body).status_code == 403
    development = FastAPI()
    development.include_router(create_knowledge_router(knowledge, owner, crawler=crawler, auth_enabled=False))
    with TestClient(development) as client:
        assert client.put("/api/v1/research/knowledge/sources/my-feed", json=body).status_code == 200
        assert client.get("/api/v1/research/knowledge/sources").json()["items"][0]["source_id"] == "my-feed"
        assert client.put("/api/v1/research/knowledge/sources/bad", json={**body, "url": "https://127.0.0.1/"}).status_code == 422
