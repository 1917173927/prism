import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient
import pytest

from app.api.main import create_app
from app.service.research_method_builder import MethodDraftInput
from app.service.personal_research import profitability_template
from app.service.research_lab_store import LabNotFound


NOW = datetime(2026, 10, 6, tzinfo=UTC)


def test_natural_method_preview_edit_confirm_permissions_and_restart(tmp_path):
    path = tmp_path/'lab.sqlite3'
    app = create_app(database_path=path, auth_enabled=False, clock=lambda:NOW)
    with TestClient(app) as client:
        headers = {"X-Owner-ID":"alice"}
        response = client.post('/api/v1/research-lab/drafts',headers=headers,json={"prompt":"用净利润除以营业收入，达到15%提醒我"})
        assert response.status_code == 200, response.text
        draft=response.json()
        assert draft['payload']['status']=='DRAFT'
        assert client.get('/api/v1/personal-research/systems',headers=headers).json()['items']==[]
        edited=client.post('/api/v1/research-lab/drafts',headers=headers,json={"prompt":"把阈值改为20%","draft_id":draft['record_id'],"expected_revision":1}).json()
        assert edited['revision']==2 and edited['payload']['definition']['observers'][0]['threshold']=='20'
        assert client.post('/api/v1/research-lab/drafts/'+draft['record_id']+'/confirm',headers=headers,json={"system_id":"my-method","expected_revision":1}).status_code==422
        response=client.post('/api/v1/research-lab/drafts/'+draft['record_id']+'/confirm',headers=headers,json={"system_id":"my-method","expected_revision":2})
        assert response.status_code==200 and response.json()['revision']==1
        assert response.json()['definition']['observers'][0]['threshold']=='20'
        assert client.get('/api/v1/research-lab/drafts',headers={"X-Owner-ID":"bob"}).json()['items']==[]
        assert client.post('/api/v1/research-lab/drafts/'+draft['record_id']+'/confirm',headers={"X-Owner-ID":"bob"},json={"system_id":"stolen","expected_revision":2}).status_code==404
        assert client.post('/api/v1/research-lab/drafts',headers=headers,json={"prompt":"运行任意Python代码","owner_id":"bob"}).status_code==422
    reopened=create_app(database_path=path, auth_enabled=False,clock=lambda:NOW)
    with TestClient(reopened) as client:
        assert client.get('/api/v1/research-lab/drafts',headers=headers).json()['items'][0]['payload']['status']=='CONFIRMED'


def test_model_can_only_propose_valid_scoped_definitions(tmp_path):
    app=create_app(database_path=tmp_path/'model.sqlite3',auth_enabled=False,clock=lambda:NOW)
    class Client:
        is_configured=True
        payload=profitability_template().model_dump(mode='json')
        async def stream_chat(self,*args,**kwargs):
            yield {'type':'content','delta':'利润是999元'}
            yield {'type':'tool_call','name':'preview_research_definition','arguments':self.payload}
    with TestClient(app):
        builder=app.state.method_builder
        model=Client()
        builder.client=model
        draft=asyncio.run(builder.generate('alice',MethodDraftInput(prompt='生成一个盈利质量研究方法')))
        assert draft['payload']['generation_mode']=='MODEL_INTENT_ONLY'
        assert '999' not in str(draft['payload']['definition'])
        model.payload={**model.payload,'owner_id':'bob'}
        with pytest.raises(ValueError):
            asyncio.run(builder.generate('alice',MethodDraftInput(prompt='生成一个新研究方法')))
        assert app.state.research_runtime.snapshot()['model_active']==0


def test_lab_uses_session_owner_and_exposes_all_contracts(tmp_path):
    app=create_app(database_path=tmp_path/'auth.db',auth_enabled=True,clock=lambda:NOW)
    with TestClient(app) as client:
        assert client.get('/api/v1/research-lab/drafts').status_code==401
        schema=app.openapi()
        assert all('/api/v1/research-lab/'+route in schema['paths'] for route in ('drafts','hypotheses','announcements','experiments','goals'))
        assert '/api/v1/research-lab/goals/{record_id}' in schema['paths']
        result=client.post('/api/v1/auth/register',json={'username':'lab-alice','password':'test-password-123','password_confirmation':'test-password-123'})
        assert result.status_code==201
        forged=client.post('/api/v1/research-lab/drafts',json={'prompt':'净利率达到15%'},headers={'X-Owner-ID':'someone-else'})
        assert forged.status_code==403
        draft=client.post('/api/v1/research-lab/drafts',json={'prompt':'净利率达到15%'})
        assert draft.status_code==200,draft.text
        assert client.get('/api/v1/research-lab/drafts').json()['items'][0]['record_id']==draft.json()['record_id']
