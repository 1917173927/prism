"""Authenticated routes for private reusable research systems and indicators."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.service.personal_research import (PersonalResearchFactRun, PersonalResearchInvalid,
    PersonalResearchNotFound, PersonalResearchRun, PersonalResearchSave)
from app.service.research_facts import ResearchFactNotFound
from app.service.research_runtime import ResearchCapacityError
from app.service.skill_registry import SkillUnavailable
from app.store.sqlite import StoreConflictError


def create_personal_research_router(*, service, owner_dependency):
    router = APIRouter(prefix="/api/v1/personal-research")

    def failure(error):
        for kind, status, detail in (
            ((PersonalResearchNotFound, ResearchFactNotFound), 404, "PERSONAL_RESEARCH_NOT_FOUND"),
            (StoreConflictError, 409, "PERSONAL_RESEARCH_REVISION_CONFLICT"),
            (SkillUnavailable, 409, "PERSONAL_RESEARCH_SKILL_UNAVAILABLE"),
            (PersonalResearchInvalid, 422, "PERSONAL_RESEARCH_INVALID"),
            (ResearchCapacityError, 429, "RESEARCH_CAPACITY"),
        ):
            if isinstance(error, kind):
                raise HTTPException(status, detail=detail) from None
        raise error

    def call(operation):
        try:
            return operation()
        except Exception as error:
            failure(error)

    @router.get("/catalog")
    def catalog(owner_id=Depends(owner_dependency)):
        return service.catalog(owner_id)

    @router.get("/systems")
    def list_systems(owner_id=Depends(owner_dependency)):
        return {"items": service.list(owner_id)}

    @router.get("/systems/{system_id}")
    def get_system(system_id: str, revision: int | None = Query(default=None, ge=1), owner_id=Depends(owner_dependency)):
        return call(lambda: service.get(owner_id, system_id, revision))

    @router.put("/systems/{system_id}")
    def save_system(system_id: str, body: PersonalResearchSave, owner_id=Depends(owner_dependency)):
        return call(lambda: service.save(owner_id, system_id, body))

    @router.post("/systems/{system_id}/runs", status_code=202)
    async def run_system(system_id: str, body: PersonalResearchRun, owner_id=Depends(owner_dependency)):
        return call(lambda: service.submit(owner_id, system_id, body))

    @router.post("/systems/{system_id}/fact-runs")
    async def run_stored_facts(system_id: str, body: PersonalResearchFactRun, owner_id=Depends(owner_dependency)):
        try:
            return await service.from_facts(owner_id, system_id, body)
        except Exception as error:
            failure(error)

    @router.get("/runs/{run_id}")
    def get_run(run_id: str, owner_id=Depends(owner_dependency)):
        return call(lambda: service.get_run(owner_id, run_id))

    @router.delete("/runs/{run_id}")
    async def cancel_run(run_id: str, owner_id=Depends(owner_dependency)):
        try:
            return await service.cancel(owner_id, run_id)
        except PersonalResearchNotFound:
            raise HTTPException(404, detail="PERSONAL_RESEARCH_NOT_FOUND") from None

    return router
