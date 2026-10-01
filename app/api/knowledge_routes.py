"""Research-library routes; owner identity and administrator role are server-derived."""
from __future__ import annotations

import asyncio
import json
from functools import partial

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.service.knowledge import MAX_UPLOAD_BYTES, KnowledgeDocumentInput, KnowledgeSearchInput
from app.service.knowledge_crawler import KnowledgeSourceInput
from app.store.sqlite import StoreConflictError, StoreCorruptError, StoreOwnerError


class CitationCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    citations: list[dict] = Field(max_length=30)
    as_of: str | None = None


def create_knowledge_router(service, owner_dependency, *, crawler=None, auth_enabled=True):
    router = APIRouter(prefix="/api/v1/research/knowledge", tags=["research-knowledge"])

    def admin(request: Request) -> bool:
        account = getattr(request.state, "account", None)
        return bool(getattr(account, "admin", False)) if account is not None else not auth_enabled

    async def run(function, *args, **kwargs):
        try:
            return await asyncio.to_thread(partial(function, *args, **kwargs))
        except StoreOwnerError:
            raise HTTPException(403, "knowledge permission denied") from None
        except StoreConflictError:
            raise HTTPException(409, "knowledge revision conflict") from None
        except StoreCorruptError:
            raise HTTPException(503, "knowledge integrity validation failed") from None
        except (ValueError, ValidationError):
            raise HTTPException(422, "knowledge input refused") from None

    @router.get("/documents")
    async def documents(owner_id: str = Depends(owner_dependency), limit: int = Query(50, ge=1, le=100)):
        return {"items": await run(service.list_documents, owner_id, limit=limit)}

    @router.post("/documents")
    async def ingest(document: KnowledgeDocumentInput, request: Request, owner_id: str = Depends(owner_dependency)):
        return await run(service.ingest, owner_id, document, admin=admin(request))

    @router.post("/upload")
    async def upload(request: Request, file: UploadFile = File(...), metadata: str = Form(...), owner_id: str = Depends(owner_dependency)):
        try:
            parsed = json.loads(metadata)
            if not isinstance(parsed, dict):
                raise ValueError("invalid metadata")
            content = await file.read(MAX_UPLOAD_BYTES + 1)
            return await run(service.upload, owner_id, file.filename or "", content, parsed, admin=admin(request))
        except (ValueError, TypeError):
            raise HTTPException(422, "upload metadata refused") from None
        finally:
            await file.close()

    @router.get("/documents/{document_id}")
    async def document(document_id: str, owner_id: str = Depends(owner_dependency)):
        result = await run(service.get, owner_id, document_id)
        if result is None:
            raise HTTPException(404, "knowledge document unavailable")
        return result

    @router.delete("/documents/{document_id}")
    async def delete_document(document_id: str, request: Request, expected_revision: int = Query(..., ge=1), owner_id: str = Depends(owner_dependency)):
        result = await run(service.delete, owner_id, document_id, expected_revision=expected_revision, admin=admin(request))
        if not result:
            raise HTTPException(404, "knowledge document unavailable")
        return {"status": "DELETED", "document_id": document_id}

    @router.post("/search")
    async def search(body: KnowledgeSearchInput, owner_id: str = Depends(owner_dependency)):
        return await run(service.search, owner_id, **body.model_dump())

    @router.post("/citations/check")
    async def citations(body: CitationCheckInput, owner_id: str = Depends(owner_dependency)):
        return await run(service.verify_citations, owner_id, body.citations, as_of=body.as_of)

    @router.post("/indexes/rebuild")
    async def rebuild(request: Request, owner_id: str = Depends(owner_dependency)):
        return await run(service.rebuild_embeddings, owner_id, admin=admin(request))

    if crawler is not None:
        @router.get("/sources")
        async def sources(request: Request, owner_id: str = Depends(owner_dependency)):
            if not admin(request):
                raise HTTPException(403, "administrator required")
            return {"items": await run(crawler.list_sources)}

        @router.post("/sources/crawl")
        async def crawl(request: Request, owner_id: str = Depends(owner_dependency)):
            if not admin(request):
                raise HTTPException(403, "administrator required")
            return await crawler.run_once(owner_id)

        @router.put("/sources/{source_id}")
        async def configure_source(source_id: str, body: KnowledgeSourceInput, request: Request, owner_id: str = Depends(owner_dependency)):
            if not admin(request):
                raise HTTPException(403, "administrator required")
            return await run(crawler.configure_source, source_id, body)

    return router
