"""Research platform routes with server-owned user and administration boundaries."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.service.skill_registry import SkillMetadata, SkillRegistry, SkillUnavailable
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

    return router
