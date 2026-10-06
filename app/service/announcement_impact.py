"""Document revisions link to server-held portfolio exposure, never price forecasts."""
from datetime import datetime
from difflib import SequenceMatcher
from decimal import Decimal
import re

from pydantic import Field

from app.portfolio.exposure import calculate_exposure
from app.service.personal_research import _Model
from app.service.research_lab_store import LabInvalid, LabNotFound, digest


class AnnouncementInput(_Model):
    document_id: str = Field(pattern=r"^knowledge:[0-9a-f]{32}$")
    document_revision: int = Field(ge=1)


class AnnouncementImpact:
    def __init__(self, records, knowledge, portfolio_context):
        self.records,self.knowledge,self.portfolio_context=records,knowledge,portfolio_context

    def analyze(self,owner,body):
        document=self.knowledge.get(owner,body.document_id)
        if document is None:
            raise LabNotFound('资料不存在或不可访问。')
        original=document['original']
        if document['revision']!=body.document_revision:
            raise LabInvalid('公告版本已变化，请刷新后分析。')
        if original['kind'] not in {'ANNOUNCEMENT','FINANCIAL_REPORT'}:
            raise LabInvalid('请选择公司公告或财务报告。')
        if datetime.fromisoformat(original['published_at'])>self.records.clock():
            raise LabInvalid('资料发布时间晚于当前分析时点。')
        subject=original.get('subject') or ''
        if not re.fullmatch(r'\d{6}(?:\.(SH|SZ|BJ))?',subject):
            raise LabInvalid('资料缺少明确六位公司代码，请先修订资料主体。')
        subject=subject.split('.')[0]
        context=self.portfolio_context(owner)
        bundle=context['bundle']
        if bundle.position_snapshot.as_of>self.records.clock():
            raise LabInvalid('组合时点晚于当前分析时点。')
        exposure=calculate_exposure(bundle,calculated_at=self.records.clock())
        if exposure.report is None:
            raise LabInvalid('当前组合无法计算已披露敞口。')
        contributions=[c for c in exposure.report.contributions if c.asset_id.split('.')[0]==subject and c.basis.value!='UNLOOKED_THROUGH']
        matched=sum((c.market_value for c in contributions),Decimal('0'))
        total=exposure.report.total_market_value
        previous=self.knowledge.get_version(owner,body.document_id,document['revision']-1) if document['revision']>1 else None
        before=previous['original']['text'].splitlines() if previous else []
        after=original['text'].splitlines()
        changes=[]
        for op,a,b,c,d in SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
            if op!='equal':
                changes.append({'operation':op,'previous_lines':before[a:b][:10],'current_lines':after[c:d][:10],
                                'current_paragraph':c+1,'truncated':max(b-a,d-c)>10})
                if len(changes)>=40:
                    break
        linked=[{'hypothesis_id':r['record_id'],'name':r['payload']['name'],'status':r['payload']['status']} for r in self.records.list(owner,'hypothesis') if r['payload']['config']['subject']==subject]
        snapshots={s.snapshot_id:s for s in bundle.fund_holdings}
        paths=[]
        for c in contributions:
            snapshot=snapshots.get(c.source_fund_snapshot_id)
            paths.append({'asset_id':c.asset_id,'asset_name':c.asset_name,'basis':c.basis.value,'parent_asset_id':c.parent_asset_id,
                          'value_cny':str(c.market_value),'weight_pct':str(c.portfolio_weight_pct),'position_ids':list(c.source_position_ids),
                          'disclosure_as_of':snapshot.as_of.isoformat() if snapshot else bundle.position_snapshot.as_of.isoformat(),
                          'source':snapshot.source if snapshot else bundle.position_snapshot.source})
        payload={'name':original['title'],'status':'RELATED' if contributions else 'NO_DISCLOSED_MATCH','document_id':body.document_id,
                 'document_revision':document['revision'],'document_hash':document['content_hash'],'published_at':original['published_at'],
                 'source':original['source'],'source_url':original.get('source_url'),'subject':subject,'changes':changes,'paths':paths,
                 'known_exposure_cny':str(matched),'known_exposure_pct':str((matched/total*100).quantize(Decimal('.00000001'))),
                 'unlooked_through_cny':str(sum((c.market_value for c in exposure.report.contributions if c.basis.value=='UNLOOKED_THROUGH'),Decimal(0))),
                 'fund_coverage':[{'parent_asset_id':s.parent_asset_id,'coverage_pct':str(s.coverage_pct),'as_of':s.as_of.isoformat()} for s in bundle.fund_holdings],
                 'linked_hypotheses':linked,'portfolio_hash':digest(bundle.model_dump(mode='json')),'is_synthetic':context['is_synthetic'],
                 'notice':'仅展示公告变化与已披露持仓的关联；未披露部分不外推，文本关系不表示股价因果。'}
        record_id=digest({'document':body.document_id,'revision':document['revision'],'portfolio':payload['portfolio_hash']})[:40]
        try:
            return self.records.get(owner,'announcement',record_id)
        except LabNotFound:
            return self.records.write(owner,'announcement',record_id,0,payload)

    def list(self,owner):
        result=[]
        for row in self.records.list(owner,'announcement'):
            document=self.knowledge.get(owner,row['payload']['document_id'])
            if document is None or document['revision']!=row['payload']['document_revision']:
                row={**row,'payload':{'name':'已失效的公告关联记录','status':'INVALIDATED','document_id':row['payload']['document_id'],
                                    'notice':'原资料已删除或更正，请使用可访问的当前版本重新分析。'}}
            result.append(row)
        return result
