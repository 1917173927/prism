"""Dated goals share one cash pool; no inferred returns or duplicate funding."""
from datetime import date
from decimal import Decimal,ROUND_CEILING
from uuid import uuid4

from pydantic import Field,model_validator

from app.portfolio import AssetType
from app.service.personal_research import _Model
from app.service.research_lab_store import LabInvalid,digest
from app.service.portfolio_rebalancing import PortfolioRebalancingService


class FundingGoal(_Model):
    goal_id:str=Field(pattern=r'^[a-z0-9][a-z0-9_-]{0,39}$')
    name:str=Field(min_length=1,max_length=100)
    amount_cny:Decimal=Field(gt=0,le=Decimal('10000000000'))
    due_date:date
    priority:int=Field(default=1,ge=1,le=10)


class ConfirmedCashflow(_Model):
    flow_id:str=Field(pattern=r'^[a-z0-9][a-z0-9_-]{0,39}$')
    name:str=Field(min_length=1,max_length=100)
    amount_cny:Decimal=Field(gt=0,le=Decimal('10000000000'))
    due_date:date
    direction:str=Field(pattern=r'^(INCOME|EXPENSE)$')


class FundingGoalsInput(_Model):
    name:str=Field(min_length=1,max_length=100)
    goals:tuple[FundingGoal,...]=Field(min_length=1,max_length=20)
    confirmed_cashflows:tuple[ConfirmedCashflow,...]=Field(default=(),max_length=64)
    expected_revision:int=Field(default=0,ge=0)

    @model_validator(mode='after')
    def identities(self):
        if len({g.goal_id for g in self.goals})!=len(self.goals) or len({f.flow_id for f in self.confirmed_cashflows})!=len(self.confirmed_cashflows):
            raise ValueError('goal and cashflow identities must be unique')
        return self


def calculate_funding_schedule(config,cash,today):
    """Expenses and goals consume once; confirmed income enters at its date only."""
    events=[]
    for goal in config.goals:
        events.append((goal.due_date,1,goal.priority,goal.goal_id,'GOAL',goal))
    for flow in config.confirmed_cashflows:
        events.append((flow.due_date,0,0,flow.flow_id,flow.direction,flow))
    if any(event[0]<today for event in events):
        raise LabInvalid('目标或现金流日期已过去，请修订后重新规划。')
    balance=cash
    net_required=Decimal(0)
    peak_required=Decimal(0)
    timeline=[]
    for due,_,priority,identity,kind,item in sorted(events,key=lambda e:e[:4]):
        funded=Decimal(0)
        gap=Decimal(0)
        if kind=='INCOME':
            balance+=item.amount_cny
            net_required-=item.amount_cny
        else:
            net_required+=item.amount_cny
            funded=min(max(balance,Decimal(0)),item.amount_cny)
            gap=item.amount_cny-funded
            # A confirmed expense remains a liability; an unfunded goal is not spent.
            balance-=item.amount_cny if kind=='EXPENSE' else funded
        peak_required=max(peak_required,net_required)
        timeline.append({'date':due.isoformat(),'kind':kind,'id':identity,'name':item.name,'amount_cny':str(item.amount_cny),
                         'funded_cny':str(funded),'shortfall_cny':str(gap),'remaining_cash_cny':str(balance)})
    return {'timeline':timeline,'initial_cash_cny':str(cash),'remaining_cash_cny':str(balance),
            'required_initial_cash_cny':str(peak_required),'current_cash_gap_cny':str(max(Decimal(0),peak_required-cash)),
            'status':'FUNDED' if all(Decimal(e['shortfall_cny'])==0 for e in timeline) else 'SHORTFALL',
            'method_version':'dated-funding-pool.v1'}


class FundingGoals:
    def __init__(self,records,memory,context,request_builder):
        self.records,self.memory,self.context,self.request_builder=records,memory,context,request_builder
        self.planner=PortfolioRebalancingService()

    def list(self,owner):
        rows=self.records.list(owner,'goals')
        try:
            context=self.context(owner)
            portfolio_hash=digest(context['bundle'].model_dump(mode='json'))
            memory=self.memory.state(owner)
            revision=memory['policy'].revision if memory['policy_status']=='ACTIVE' else None
        except Exception:
            context,portfolio_hash,revision=None,None,None
        for row in rows:
            latest=row['payload'].get('latest')
            if latest and (context is None or portfolio_hash!=latest['portfolio_hash'] or
                           context.get('profile_hash')!=latest.get('profile_hash') or revision!=latest['policy_revision']):
                row['payload']['latest']={**latest,'stale':True,'adjustment_plan':None,
                    'plan_unavailable_reason':'组合、行情、画像或长期偏好已变化，以下为历史测算，请重新计算。'}
        return rows

    def save(self,owner,record_id,body):
        if any(g.due_date<self.records.clock().date() for g in body.goals) or any(f.due_date<self.records.clock().date() for f in body.confirmed_cashflows):
            raise LabInvalid('请填写当前或未来的目标和现金流日期。')
        return self.records.write(owner,'goals',record_id,body.expected_revision,{'name':body.name,'config':body.model_dump(mode='json',exclude={'expected_revision'}),'status':'CONFIRMED','latest':None})

    def calculate(self,owner,record_id,expected_revision):
        row=self.records.get(owner,'goals',record_id)
        if row['revision']!=expected_revision:
            from app.store.sqlite import StoreConflictError
            raise StoreConflictError('目标台账已变化。')
        body=FundingGoalsInput.model_validate(row['payload']['config'])
        context=self.context(owner)
        bundle=context['bundle']
        total=sum((p.market_value for p in bundle.position_snapshot.positions),Decimal(0))
        cash=sum((p.market_value for p in bundle.position_snapshot.positions if p.asset_type==AssetType.CASH),Decimal(0))
        schedule=calculate_funding_schedule(body,cash,self.records.clock().date())
        needed=Decimal(schedule['required_initial_cash_cny'])
        memory=self.memory.state(owner)
        policy=memory['policy'] if memory['policy_status']=='ACTIVE' else None
        cash_pct=(needed/total*100).quantize(Decimal('.01'),rounding=ROUND_CEILING)
        cash_pct=max(cash_pct,(cash/total*100).quantize(Decimal('.01'),rounding=ROUND_CEILING))
        if policy:
            cash_pct=max(cash_pct,policy.parameters.minimum_cash_pct)
        weights={p.asset_id:p.market_value/total*100 for p in bundle.position_snapshot.positions if p.asset_type!=AssetType.CASH}
        target={}
        plan=None
        reason=None
        if needed>total:
            reason='目标所需初始资金超过组合市值，需调整金额、期限或现金流。'
        elif not context['profile_ready']:
            reason='请先确认投资者画像，才能测算调整方案。'
        elif memory['policy_status']=='STALE':
            reason='长期风格确认已失效，请先重新确认。'
        else:
            noncash=sum(weights.values(),Decimal(0))
            if noncash:
                target={asset:(weight/noncash*(100-cash_pct)).quantize(Decimal('.01')) for asset,weight in weights.items()}
                largest=max(target,key=target.get)
                target[largest]+=100-cash_pct-sum(target.values(),Decimal(0))
            elif cash_pct<100:
                cash_pct=Decimal(100)
            target['CASH-CNY']=cash_pct
            from app.api.investment_memory_routes import PersonalRebalancingPreview
            request=self.request_builder(owner,PersonalRebalancingPreview(expected_policy_revision=policy.revision if policy else 1,target_weights=target,
                minimum_cash_pct=cash_pct,max_turnover_pct=policy.parameters.max_turnover_pct if policy else Decimal(50)))
            if policy:
                request,application=self.memory.apply_policy(request,policy)
            plan=self.planner.plan_rebalancing(request).model_dump(mode='json')
        latest={**schedule,'target_weights':{a:str(w) for a,w in target.items()},'adjustment_plan':plan,'plan_unavailable_reason':reason,
                'policy_revision':policy.revision if policy else None,'portfolio_hash':digest(bundle.model_dump(mode='json')),
                'profile_hash':context.get('profile_hash'),
                'is_synthetic':context['is_synthetic'],'calculated_at':self.records.clock().isoformat(),
                'notice':'按已确认现金流与资金用途测算，不假设资产收益，不提交交易；同一笔资金只分配一次。'}
        return self.records.write(owner,'goals',record_id,row['revision'],{**row['payload'],'latest':latest})
