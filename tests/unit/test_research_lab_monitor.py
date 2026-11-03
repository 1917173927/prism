import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.service.investment_hypotheses import HypothesisMonitor,HypothesisInput
from app.service.personal_research import profitability_template
from app.service.research_lab_store import LabRecords,LabInvalid
from app.service.announcement_impact import AnnouncementImpact,AnnouncementInput
from app.service.knowledge import KnowledgeService,KnowledgeDocumentInput
from app.portfolio import PortfolioImportBundle
from app.store.sqlite import SQLiteDecisionEventStore


NOW=datetime(2026,10,6,tzinfo=UTC)


class Personal:
    revision=1
    values={'2025-Q2':'10','2025-Q3':'15','2025-Q4':'20'}
    calls=0
    async def run_and_wait(self,owner,system,request):
        self.calls+=1
        value=self.values[request.period]
        return {'run_id':str(self.calls),'status':'COMPLETED','is_synthetic':True,
                'indicators':[{'indicator_id':'margin','status':'CALCULATED','value':value,'unit':'%','period':request.period}],
                'data_agents':[{'observations':[{'metric':'net_profit','value':value,'unit':'CNY','period':request.period,'observed_at':NOW.isoformat(),'actual_source':'controlled-source'}]}]}
    def get(self,*args):
        return {'revision':self.revision,'definition':profitability_template().model_dump(mode='json')}
    def _validate_skills(self,*args,**kwargs):
        pass


def config(**changes):
    return HypothesisInput.model_validate({'name':'盈利假设','rationale':'观察净利率','system_id':'profit','system_revision':1,
        'subject':'600001','indicator_id':'margin','periods':['2025-Q4'],'condition':'AT_LEAST','threshold':'15','enabled':True,**changes})


def test_monitor_actual_changes_dedup_stop_method_change_and_restart(tmp_path):
    store=SQLiteDecisionEventStore(tmp_path/'monitor.db')
    records=LabRecords(store,lambda:NOW)
    personal=Personal()
    monitor=HypothesisMonitor(records,personal)
    monitor.save('alice','profit',config())
    async def run():
        first=await monitor.evaluate('alice','profit')
        assert first['payload']['status']=='SUPPORTED'
        second=await monitor.evaluate('alice','profit')
        assert second['payload']['latest']['changed'] is False
        assert len(records.list('alice','hypothesis-event'))==1
        personal.values={**personal.values,'2025-Q4':'5'}
        third=await monitor.evaluate('alice','profit')
        assert third['payload']['status']=='CONTRADICTED' and len(records.list('alice','hypothesis-event'))==2
        personal.revision=2
        assert (await monitor.evaluate('alice','profit'))['payload']['status']=='STALE_METHOD'
        await monitor.close()
    asyncio.run(run())
    assert records.list('bob','hypothesis')==[]
    store.close()
    reopened=SQLiteDecisionEventStore(tmp_path/'monitor.db')
    assert LabRecords(reopened).get('alice','hypothesis','profit')['payload']['status']=='STALE_METHOD'
    reopened.close()


def test_trend_requires_three_periods_and_shutdown_cancels_inflight():
    with pytest.raises(ValueError):
        config(periods=['2025-Q3','2025-Q4'],condition='INCREASING',threshold=None)
    store=SQLiteDecisionEventStore()
    records=LabRecords(store,lambda:NOW)
    monitor=HypothesisMonitor(records,Personal())
    monitor.save('alice','trend',config(periods=['2025-Q2','2025-Q3','2025-Q4'],condition='INCREASING',threshold=None))
    async def run():
        assert (await monitor.evaluate('alice','trend'))['payload']['status']=='SUPPORTED'
        entered=asyncio.Event()
        cleaned=asyncio.Event()
        async def blocked(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        monitor.personal.run_and_wait=blocked
        task=asyncio.create_task(monitor.evaluate('alice','trend'))
        await entered.wait()
        await monitor.close()
        assert task.cancelled() and cleaned.is_set() and monitor._running=={}
    asyncio.run(run())
    store.close()


def test_new_accessible_financial_report_moves_subscription_and_stopping_is_always_possible():
    store=SQLiteDecisionEventStore()
    records=LabRecords(store,lambda:NOW)
    knowledge=KnowledgeService(store,clock=lambda:NOW)
    personal=Personal()
    personal.values={**personal.values,'2026-Q1':'8'}
    monitor=HypothesisMonitor(records,personal,knowledge)
    monitor.save('alice','follow',config())
    knowledge.ingest('alice',KnowledgeDocumentInput(title='新财报',text='报告原文',source='controlled-report',kind='FINANCIAL_REPORT',subject='600001',period='2026-Q1',published_at=NOW-timedelta(days=1)))
    async def run():
        await monitor.tick()
        row=records.get('alice','hypothesis','follow')
        assert row['payload']['config']['periods']==['2026-Q1']
        assert row['payload']['status']=='CONTRADICTED'
        personal.revision=2
        monitor.save('alice','follow',config(enabled=False,expected_revision=row['revision']))
        calls=personal.calls
        await monitor.tick()
        assert personal.calls==calls
        await monitor.close()
    asyncio.run(run())
    store.close()


def bundle():
    base={'owner_id':'alice','currency':'CNY','as_of':NOW.isoformat(),'source':'controlled-portfolio'}
    positions=[{**base,'position_id':'direct','asset_id':'600001.SH','asset_type':'STOCK','asset_name':'公司甲','sector':'INDUSTRIALS','quantity':'1000','market_value':'10000'},
               {**base,'position_id':'fund','asset_id':'510001.SH','asset_type':'ETF','asset_name':'基金甲','quantity':'1000','market_value':'10000'}]
    return PortfolioImportBundle.model_validate({'bundle_id':'test','owner_id':'alice','created_at':NOW.isoformat(),
        'position_snapshot':{'snapshot_id':'test','owner_id':'alice','as_of':NOW.isoformat(),'base_currency':'CNY','source':'controlled','positions':positions},
        'fund_holdings':[{'snapshot_id':'fund-report','owner_id':'alice','parent_asset_id':'510001.SH','parent_asset_type':'ETF','as_of':NOW.isoformat(),'source':'controlled-fund-report','coverage_pct':'10',
            'holdings':[{'holding_id':'company','parent_asset_id':'510001.SH','underlying_asset_id':'600001.SH','underlying_name':'公司甲','asset_type':'STOCK','weight_pct':'10','sector':'INDUSTRIALS','as_of':NOW.isoformat(),'source':'controlled-fund-report'}]}]})


def test_announcement_diff_direct_and_fund_exposure_deletion_and_isolation():
    store=SQLiteDecisionEventStore()
    knowledge=KnowledgeService(store,clock=lambda:NOW)
    records=LabRecords(store,lambda:NOW)
    service=AnnouncementImpact(records,knowledge,lambda owner:{'bundle':bundle(),'is_synthetic':True})
    original={'title':'公司公告','text':'净利润同比增长10%','source':'controlled-announcement','kind':'ANNOUNCEMENT','subject':'600001','published_at':NOW-timedelta(days=1)}
    doc=knowledge.ingest('alice',KnowledgeDocumentInput(**original))
    result=service.analyze('alice',AnnouncementInput(document_id=doc['document_id'],document_revision=1))
    assert Decimal(result['payload']['known_exposure_cny'])==11000
    assert Decimal(result['payload']['known_exposure_pct'])==55
    assert Decimal(result['payload']['unlooked_through_cny'])==9000
    assert len(result['payload']['paths'])==2
    assert service.analyze('alice',AnnouncementInput(document_id=doc['document_id'],document_revision=1))['record_id']==result['record_id']
    with pytest.raises(ValueError):
        service.analyze('bob',AnnouncementInput(document_id=doc['document_id'],document_revision=1))
    revised=knowledge.ingest('alice',KnowledgeDocumentInput(**{**original,'text':'净利润同比增长5%','document_id':doc['document_id'],'expected_revision':1}))
    changed=service.analyze('alice',AnnouncementInput(document_id=doc['document_id'],document_revision=2))
    assert changed['payload']['changes'][0]['previous_lines']==['净利润同比增长10%']
    assert changed['payload']['changes'][0]['current_lines']==['净利润同比增长5%']
    knowledge.delete('alice',doc['document_id'],expected_revision=2)
    assert all(row['payload']['status']=='INVALIDATED' and 'changes' not in row['payload'] for row in service.list('alice'))
    store.close()
