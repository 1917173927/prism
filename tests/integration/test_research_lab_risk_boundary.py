from decimal import Decimal
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.service.personal_research import PersonalResearchSave,profitability_template
from app.store.sqlite import SQLiteDecisionEventStore
from app.runtime.mode import reset_runtime_mode_controller,DataMode
from tests.integration.test_research_lab_planning import seed,strategy,NOW


def test_full_budget_can_block_even_when_post_trade_health_passes(tmp_path):
    store=SQLiteDecisionEventStore(tmp_path/'risk.db')
    seed(store,conservative=True)
    reset_runtime_mode_controller(DataMode.MOCK)
    app=create_app(store=store,auth_enabled=False,clock=lambda:NOW)
    with TestClient(app) as client:
        app.state.personal_research_service.save('alice','profit',PersonalResearchSave(definition=profitability_template(),expected_revision=0))
        async def run(*args):
            return {'run_id':'controlled','is_synthetic':True,'indicators':[{'indicator_id':'margin','status':'CALCULATED','value':'20','unit':'%'}]}
        app.state.personal_research_service.run_and_wait=run
        target={f'60000{i+1}.SH':str(10 if i==0 else 13) for i in range(6)}|{'CASH-CNY':'25'}
        headers={'X-Owner-ID':'alice'}
        created=client.post('/api/v1/research-lab/experiments',headers=headers,json={'name':'预算阻断','strategies':[strategy('规则一',15,target),strategy('规则二',15,target)]}).json()
        result=client.post('/api/v1/research-lab/experiments/'+created['record_id']+'/steps',headers=headers,json={'expected_revision':1}).json()
        for account in result['payload']['accounts']:
            point=account['timeline'][0]
            assert point['health']['status']=='PASS'
            assert point['risk_budget']['breaches']
            assert point['status']=='REVIEW_REQUIRED'
            assert Decimal(account['fees_cny'])==0 and Decimal(account['cash_cny'])==15000
            assert account['quantities']==created['payload']['baseline']['quantities']
    store.close()
