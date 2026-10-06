"""Authenticated product innovation APIs; owner comes only from session context."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.service.research_lab_store import LabInvalid, LabNotFound
from app.service.personal_research import PersonalResearchNotFound, PersonalResearchInvalid
from app.service.research_method_builder import MethodDraftInput, MethodConfirmInput
from app.service.investment_hypotheses import HypothesisInput
from app.service.announcement_impact import AnnouncementInput
from app.service.skill_registry import SkillUnavailable
from app.store.sqlite import StoreConflictError


def lab_error(error):
    if isinstance(error, (LabNotFound, PersonalResearchNotFound)):
        raise HTTPException(404, detail="研究记录不存在或不可访问。") from None
    if isinstance(error, (StoreConflictError, SkillUnavailable)):
        raise HTTPException(409, detail="资料、权限或版本已变化，请刷新后重试。") from None
    if isinstance(error, (LabInvalid, PersonalResearchInvalid, ValidationError)):
        raise HTTPException(422, detail=str(error) if isinstance(error, LabInvalid) else "研究配置不符合支持的字段、公式或单位契约。") from None
    if isinstance(error, TimeoutError):
        raise HTTPException(504, detail="研究请求超出预算。") from None
    raise error


def create_method_router(builder, owner_dependency):
    router = APIRouter(prefix="/api/v1/research-lab")

    @router.get("/drafts")
    def drafts(owner=Depends(owner_dependency)):
        return {"items":builder.records.list(owner,"method")}

    @router.post("/drafts")
    async def generate(body: MethodDraftInput, owner=Depends(owner_dependency)):
        try:
            return await builder.generate(owner,body)
        except Exception as error:
            lab_error(error)

    @router.post("/drafts/{draft_id}/confirm")
    def confirm(draft_id: str,body: MethodConfirmInput,owner=Depends(owner_dependency)):
        try:
            return builder.confirm(owner,draft_id,body)
        except Exception as error:
            lab_error(error)

    return router


def create_monitor_router(monitor, impacts, owner_dependency):
    router=APIRouter(prefix="/api/v1/research-lab")

    @router.get('/hypotheses')
    def hypotheses(owner=Depends(owner_dependency)):
        return {'items':monitor.records.list(owner,'hypothesis')}

    @router.put('/hypotheses/{record_id}')
    async def save(record_id:str,body:HypothesisInput,owner=Depends(owner_dependency)):
        try:
            return monitor.save(owner,record_id,body)
        except Exception as error:
            lab_error(error)

    @router.post('/hypotheses/{record_id}/evaluate')
    async def evaluate(record_id:str,owner=Depends(owner_dependency)):
        try:
            return await monitor.evaluate(owner,record_id)
        except Exception as error:
            lab_error(error)

    @router.get('/hypothesis-events')
    def events(owner=Depends(owner_dependency)):
        return {'items':monitor.records.list(owner,'hypothesis-event')}

    @router.get('/announcements')
    def announcements(owner=Depends(owner_dependency)):
        return {'items':impacts.list(owner)}

    @router.post('/announcements')
    def analyze(body:AnnouncementInput,owner=Depends(owner_dependency)):
        try:
            return impacts.analyze(owner,body)
        except Exception as error:
            lab_error(error)

    return router
