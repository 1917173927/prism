"""Research platform routes with server-owned user and administration boundaries."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.service.skill_registry import SkillMetadata, SkillRegistry, SkillUnavailable
from app.service.live_research import (LiveResearchRequest, ResearchRunNotFound, ResearchAsOfError,
                                       build_live_research_request, live_research_templates)
from app.service.research_runtime import ResearchCapacityError
from app.store.sqlite import StoreConflictError


class SkillInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metadata: SkillMetadata
    expected_revision: int = Field(default=0, ge=0)


class SkillMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["enable", "disable", "uninstall"]
    expected_revision: int = Field(ge=1)


class SkillSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    expected_revision: int = Field(default=0, ge=0)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class TemplateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=30)
    budget_seconds: float = Field(default=60, gt=0, le=60)
    as_of: datetime | None = None


def create_research_router(*, store, provider, owner_dependency, auth_enabled=False,
                           clock=None, registry=None, runtime=None, live_service=None):
    """Use the shared registry instance when binding provider and UI routes."""
    registry = registry or SkillRegistry(store, clock=clock)
    router = APIRouter(prefix="/api/v1")

    def administrator(request: Request, owner_id=Depends(owner_dependency)):
        if auth_enabled and not getattr(getattr(request.state, "account", None), "admin", False):
            raise HTTPException(403, detail="ADMIN_REQUIRED")
        return owner_id

    def call(operation):
        try:
            return operation()
        except StoreConflictError:
            raise HTTPException(409, detail="SKILL_REVISION_CONFLICT") from None
        except SkillUnavailable:
            raise HTTPException(409, detail="SKILL_UNAVAILABLE") from None

    @router.get("/skills")
    def list_skills(owner_id=Depends(owner_dependency)):
        return {"items": registry.list(owner_id), "execution_mode": "CONTROLLED_API_ADAPTER"}

    @router.post("/skills")
    def install_skill(body: SkillInstallRequest, owner_id=Depends(administrator)):
        return call(lambda: registry.install(body.metadata, body.expected_revision))

    @router.get("/skills/{skill_id}/{version}")
    def skill_detail(skill_id: str, version: str, owner_id=Depends(owner_dependency)):
        return call(lambda: registry.get(skill_id, version))

    @router.patch("/skills/{skill_id}/{version}")
    def mutate_skill(skill_id: str, version: str, body: SkillMutationRequest, owner_id=Depends(administrator)):
        return call(lambda: registry.update(skill_id, version, action=body.action, expected_revision=body.expected_revision))

    @router.post("/skills/{skill_id}/{version}/verify")
    async def verify_skill(skill_id: str, version: str, body: RevisionRequest, owner_id=Depends(administrator)):
        try:
            return await registry.probe(skill_id, version, expected_revision=body.expected_revision, provider=provider)
        except StoreConflictError:
            raise HTTPException(409, detail="SKILL_REVISION_CONFLICT") from None
        except SkillUnavailable:
            raise HTTPException(409, detail="SKILL_UNAVAILABLE") from None

    @router.put("/skills/{skill_id}/selection")
    def select_skill(skill_id: str, body: SkillSelectionRequest, owner_id=Depends(owner_dependency)):
        return call(lambda: registry.select(owner_id, skill_id, enabled=body.enabled, expected_revision=body.expected_revision))

    if runtime is not None:
        @router.get("/research/runtime")
        def runtime_status(owner_id=Depends(owner_dependency)):
            return runtime.snapshot()

        @router.get("/runtime/research-metrics")
        def administration_runtime_status(owner_id=Depends(administrator)):
            return runtime.snapshot()

    if live_service is not None:
        def research_error(code, message):
            return JSONResponse(status_code=422, content={"schema_version": "api-error.v1", "error_code": code,
                                                         "detail": code, "message": message})

        @router.get("/research/templates")
        def get_live_templates(owner_id=Depends(owner_dependency)):
            return {"items": live_research_templates()}

        @router.post("/research/runs/from-template", status_code=202)
        async def create_from_template(body: TemplateRunRequest, owner_id=Depends(owner_dependency)):
            try:
                request = build_live_research_request(body.template_id, body.subject,
                                                     budget_seconds=body.budget_seconds, as_of=body.as_of)
                return live_service.submit(owner_id, request)
            except ResearchAsOfError:
                return research_error("RESEARCH_AS_OF_FUTURE", "研究截止时间不得晚于服务当前时间")
            except ValueError:
                return research_error("RESEARCH_TEMPLATE_INVALID", "研究模板、标的代码或截止时间无效")
            except ResearchCapacityError:
                raise HTTPException(429, detail="RESEARCH_CAPACITY") from None

        @router.post("/research/runs", status_code=202)
        async def create_live_run(body: LiveResearchRequest, owner_id=Depends(owner_dependency)):
            try:
                return live_service.submit(owner_id, body)
            except ResearchCapacityError:
                raise HTTPException(429, detail="RESEARCH_CAPACITY") from None
            except ResearchAsOfError:
                return research_error("RESEARCH_AS_OF_FUTURE", "研究截止时间不得晚于服务当前时间")

        @router.get("/research/runs/{run_id}")
        def get_live_run(run_id: str, owner_id=Depends(owner_dependency)):
            try:
                return live_service.get(owner_id, run_id)
            except ResearchRunNotFound:
                raise HTTPException(404, detail="RESEARCH_RUN_NOT_FOUND") from None

        @router.delete("/research/runs/{run_id}")
        async def cancel_live_run(run_id: str, owner_id=Depends(owner_dependency)):
            try:
                return await live_service.cancel(owner_id, run_id)
            except ResearchRunNotFound:
                raise HTTPException(404, detail="RESEARCH_RUN_NOT_FOUND") from None

    return router
