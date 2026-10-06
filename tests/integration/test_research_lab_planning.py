import asyncio
from datetime import UTC,datetime,timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.llm.ocr_portfolio_parser import recalculate_portfolio_values
from app.profile.questionnaire import QUESTIONNAIRE_TEMPLATE,QuestionnaireAnswer,build_questionnaire_snapshot
from app.runtime.mode import reset_runtime_mode_controller,DataMode
from app.service.personal_research import PersonalResearchSave,profitability_template
from app.service.shadow_portfolios import ExperimentInput,ExperimentStep
from app.service.funding_goals import FundingGoalsInput,calculate_funding_schedule
from app.store.sqlite import SQLiteDecisionEventStore


NOW=datetime(2026,10,6,8,tzinfo=UTC)


def seed(store,owner='alice',conservative=False):
    choices={} if conservative else {'Q1':'professional','Q2':'gt_10y','Q3':'stock','Q4':'k500_1000','Q6':'capital_growth'}
    answers=tuple(QuestionnaireAnswer.model_validate({'question_id':q.question_id,**({'score':4} if q.question_type.value=='SCORE' else {'selected_option_ids':[choices.get(q.question_id,q.options[0].option_id)]})}) for q in QUESTIONNAIRE_TEMPLATE.questions)
    store.save_questionnaire_snapshot(build_questionnaire_snapshot(owner,answers,confirmed_at=NOW,snapshot_version=1))
    rows=[{'asset_id':f'60000{i+1}.SH','quantity':2000 if i==0 else 1300,'price':10,'sector':sector,'asset_name':f'资产{i+1}'} for i,sector in enumerate(['Industrials','Financials','Consumer Staples','Health Care','Materials','Energy'])]
    data=recalculate_portfolio_values(rows,Decimal(15000),owner)
    data['portfolio']['created_at']=NOW.isoformat()
    data['portfolio']['position_snapshot']['as_of']=NOW.isoformat()
    for p in data['portfolio']['position_snapshot']['positions']:
        p['as_of']=NOW.isoformat()
        source=next((row for row in rows if row['asset_id']==p['asset_id']),None)
        if source:
            p['sector']=source['sector']
            p['asset_name']=source['asset_name']
    store.save_current_portfolio(owner,'MOCK',data)
    return data


def strategy(name,threshold,target):
    base={f'60000{i+1}.SH':str(20 if i==0 else 13) for i in range(6)}|{'CASH-CNY':'15'}
    return {'name':name,'system_id':'profit','system_revision':1,'subject':'600001','period':'2025-Q4','indicator_id':'margin',
            'comparison':'AT_LEAST','threshold':str(threshold),'matched_weights':target,'unmatched_weights':base}


def test_forward_accounts_equal_baseline_fee_conservation_marks_and_owner_isolation(tmp_path):
    store=SQLiteDecisionEventStore(tmp_path/'plan.db')
    seed(store)
    reset_runtime_mode_controller(DataMode.MOCK)
    now=[NOW]
    app=create_app(store=store,auth_enabled=False,clock=lambda:now[0])
    with TestClient(app) as client:
        personal=app.state.personal_research_service
        personal.save('alice','profit',PersonalResearchSave(definition=profitability_template(),expected_revision=0))
        async def run(owner,system,request):
            return {'run_id':'controlled-run','is_synthetic':True,'indicators':[{'indicator_id':'margin','status':'CALCULATED','value':'20','unit':'%'}]}
        personal.run_and_wait=run
        target={f'60000{i+1}.SH':str(10 if i==0 else 13) for i in range(6)}|{'CASH-CNY':'25'}
        response=client.post('/api/v1/research-lab/experiments',headers={'X-Owner-ID':'alice'},json={'name':'方法比较','strategies':[strategy('盈利观察',15,target),strategy('较高要求',25,target)]})
        assert response.status_code==200,response.text
        created=response.json()
        assert created['payload']['accounts'][0]['quantities']==created['payload']['accounts'][1]['quantities']
        endpoint='/api/v1/research-lab/experiments/'+created['record_id']+'/steps'
        response=client.post(endpoint,headers={'X-Owner-ID':'alice'},json={'expected_revision':1})
        assert response.status_code==200,response.text
        advanced=response.json()
        first,second=advanced['payload']['accounts']
        assert first['timeline'][0]['status']=='APPLIED',first['timeline'][0]
        assert Decimal(first['quantities']['600001.SH'])==1000
        assert Decimal(first['fees_cny'])==Decimal('10.10')
        assert Decimal(first['equity_cny'])==100000-Decimal(first['fees_cny'])
        assert Decimal(second['fees_cny'])==0 and Decimal(second['quantities']['600001.SH'])==2000
        assert second['timeline'][0]['status']=='HELD'
        repeat=client.post(endpoint,headers={'X-Owner-ID':'alice'},json={'expected_revision':2}).json()
        assert repeat['duplicate_quote'] and repeat['revision']==2
        data=store.get_current_portfolio('alice','MOCK')
        now[0]+=timedelta(days=1)
        data['portfolio']['position_snapshot']['as_of']=now[0].isoformat()
        data['portfolio']['position_snapshot']['positions'][0]['market_value']='16000'
        store.save_current_portfolio('alice','MOCK',data)
        result=client.post(endpoint,headers={'X-Owner-ID':'alice'},json={'expected_revision':2}).json()
        assert Decimal(result['payload']['accounts'][0]['max_drawdown_pct'])>0
        assert result['payload']['benchmark_equity_cny']=='96000.00'
        assert client.get('/api/v1/research-lab/experiments',headers={'X-Owner-ID':'bob'}).json()['items']==[]
        assert client.post(endpoint,headers={'X-Owner-ID':'bob'},json={'expected_revision':3}).status_code==404
        assert client.post(endpoint,headers={'X-Owner-ID':'alice'},json={'expected_revision':3,'prices_cny':{'600001.SH':1}}).status_code==422
    store.close()


def goals(**changes):
    return FundingGoalsInput.model_validate({'name':'资金用途','goals':[{'goal_id':'near','name':'近期支出','amount_cny':'40000','due_date':'2026-10-10'},
        {'goal_id':'later','name':'长期目标','amount_cny':'20000','due_date':'2026-11-10'}],
        'confirmed_cashflows':[{'flow_id':'salary','name':'已确认收入','amount_cny':'20000','due_date':'2026-11-01','direction':'INCOME'}],**changes})


def test_dated_goals_do_not_double_spend_or_borrow_future_income():
    result=calculate_funding_schedule(goals(),Decimal(30000),NOW.date())
    assert result['status']=='SHORTFALL' and Decimal(result['required_initial_cash_cny'])==40000
    assert Decimal(result['timeline'][0]['funded_cny'])==30000
    assert Decimal(result['timeline'][0]['shortfall_cny'])==10000
    assert Decimal(result['timeline'][2]['funded_cny'])==20000
    assert sum(Decimal(e['funded_cny']) for e in result['timeline'])==50000
    assert Decimal(result['remaining_cash_cny'])==0
    with pytest.raises(ValueError):
        goals(goals=[{'goal_id':'same','name':'a','amount_cny':10,'due_date':'2026-10-10'},{'goal_id':'same','name':'b','amount_cny':10,'due_date':'2026-10-10'}])


def test_goal_api_revision_calculation_and_plan_binding(tmp_path):
    store=SQLiteDecisionEventStore(tmp_path/'goals.db')
    seed(store)
    reset_runtime_mode_controller(DataMode.MOCK)
    app=create_app(store=store,auth_enabled=False,clock=lambda:NOW)
    with TestClient(app) as client:
        headers={'X-Owner-ID':'alice'}
        saved=client.put('/api/v1/research-lab/goals/uses',headers=headers,json=goals().model_dump(mode='json'))
        assert saved.status_code==200,saved.text
        response=client.post('/api/v1/research-lab/goals/uses/calculate',headers=headers,json={'expected_revision':1})
        assert response.status_code==200,response.text
        result=response.json()['payload']['latest']
        assert result['target_weights']['CASH-CNY']=='40.00'
        assert result['adjustment_plan']['owner_id']=='alice'
        assert result['is_synthetic']
        assert client.post('/api/v1/research-lab/goals/uses/calculate',headers=headers,json={'expected_revision':1}).status_code==409
        assert client.get('/api/v1/research-lab/goals',headers={'X-Owner-ID':'bob'}).json()['items']==[]
        current=store.get_current_portfolio('alice','MOCK')
        current['portfolio']['position_snapshot']['positions'][0]['market_value']='19000'
        store.save_current_portfolio('alice','MOCK',current)
        stale=client.get('/api/v1/research-lab/goals',headers=headers).json()['items'][0]['payload']['latest']
        assert stale['stale'] and stale['adjustment_plan'] is None
    store.close()
