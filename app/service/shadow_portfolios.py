"""Forward-only virtual strategy experiments with equal baselines and real gates."""
from copy import deepcopy
import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
import re

from pydantic import Field,model_validator

from app.gates import GateStatus
from app.portfolio import AssetType,PortfolioImportBundle,calculate_exposure
from app.risk import calculate_concentration,assess_risk_budget
from app.portfolio.health import PortfolioHealthRequest,calculate_portfolio_health
from app.rebalancing.contracts import PortfolioRebalancingRequest
from app.service.personal_research import _Model,PersonalResearchRun,PersonalResearchDefinition,_period
from app.service.research_lab_store import LabInvalid,digest
from app.service.portfolio_rebalancing import PortfolioRebalancingService


class StrategyRule(_Model):
    name:str=Field(min_length=1,max_length=80)
    system_id:str=Field(pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')
    system_revision:int=Field(ge=1)
    subject:str=Field(pattern=r'^\d{6}$')
    period:str
    indicator_id:str
    comparison:str=Field(pattern=r'^(AT_LEAST|AT_MOST)$')
    threshold:Decimal
    unit:str=Field(default='%',min_length=1,max_length=20)
    matched_weights:dict[str,Decimal]=Field(min_length=1,max_length=100)
    unmatched_weights:dict[str,Decimal]=Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def targets(self):
        _period(self.period)
        for weights in (self.matched_weights,self.unmatched_weights):
            if any(not v.is_finite() or v<0 or v>100 for v in weights.values()) or sum(weights.values())!=100:
                raise ValueError('strategy weights must close to exactly 100%')
        return self


class ExperimentInput(_Model):
    name:str=Field(min_length=1,max_length=100)
    strategies:tuple[StrategyRule,...]=Field(min_length=2,max_length=5)
    deadband_pct:Decimal=Field(default=Decimal('.5'),ge=0,le=100)
    max_turnover_pct:Decimal=Field(default=Decimal('50'),ge=0,le=100)
    minimum_cash_pct:Decimal=Field(default=Decimal('0'),ge=0,le=100)
    policy_revision:int|None=Field(default=None,ge=1)

    @model_validator(mode='after')
    def names(self):
        if len({s.name for s in self.strategies})!=len(self.strategies):
            raise ValueError('strategy names must be distinct')
        return self


class ExperimentStep(_Model):
    expected_revision:int=Field(ge=1)


def _amount(value):
    return value.quantize(Decimal('.01'))


class ShadowPortfolios:
    def __init__(self,records,personal,memory,context,request_builder):
        self.records,self.personal,self.memory,self.context,self.request_builder=records,personal,memory,context,request_builder
        self.planner=PortfolioRebalancingService()

    def list(self,owner):
        rows=self.records.list(owner,'shadow')
        try:
            context=self.context(owner)
        except Exception:
            context=None
        for row in rows:
            payload=row['payload']
            stale=context is None or context['data_mode']!=payload['data_mode'] or context.get('profile_hash')!=payload['profile_hash']
            try:
                if payload['config'].get('policy_revision'):
                    self.memory.resolve_policy(owner,payload['config']['policy_revision'])
                for strategy in payload['config']['strategies']:
                    system=self.personal.get(owner,strategy['system_id'])
                    if system['revision']!=strategy['system_revision']:
                        stale=True
                    self.personal._validate_skills(owner,PersonalResearchDefinition.model_validate(system['definition']),require_callable=True)
            except Exception:
                stale=True
            if stale:
                payload.update(status='STALE_CONTEXT',notice='当前模式、画像、政策或研究权限已变化；以下为历史模拟，请以新条件创建实验。')
        return rows

    def create(self,owner,body):
        context=self.context(owner)
        bundle=context['bundle']
        if not context['profile_ready']:
            raise LabInvalid('请先确认投资者画像，再创建模拟实验。')
        positions=bundle.position_snapshot.positions
        if any(p.asset_type not in {AssetType.STOCK,AssetType.ETF,AssetType.CASH} or
               (p.asset_type!=AssetType.CASH and (not re.fullmatch(r'\d{6}(?:\.(SH|SZ|BJ))?',p.asset_id) or p.quantity!=p.quantity.to_integral_value())) for p in positions):
            raise LabInvalid('首期模拟支持具有可信报价的股票、ETF整数持仓及人民币现金。')
        assets={p.asset_id for p in positions}|{'CASH-CNY'}
        for strategy in body.strategies:
            system=self.personal.get(owner,strategy.system_id)
            definition=PersonalResearchDefinition.model_validate(system['definition'])
            self.personal._validate_skills(owner,definition,require_callable=True)
            if system['revision']!=strategy.system_revision or strategy.indicator_id not in {i.indicator_id for i in definition.indicators}:
                raise LabInvalid('研究方法版本或指标已变化。')
            if any(set(weights)-assets for weights in (strategy.matched_weights,strategy.unmatched_weights)):
                raise LabInvalid('首期仅使用当前组合中的已知报价资产。')
        if body.policy_revision is not None:
            self.memory.resolve_policy(owner,body.policy_revision)
        from app.api.investment_memory_routes import PersonalRebalancingPreview
        bound=self.request_builder(owner,PersonalRebalancingPreview(expected_policy_revision=body.policy_revision or 1,target_weights=body.strategies[0].matched_weights))
        cash=sum((p.market_value for p in positions if p.asset_type==AssetType.CASH),Decimal(0))
        quantities={p.asset_id:str(p.quantity) for p in positions if p.asset_type!=AssetType.CASH}
        total=sum((p.market_value for p in positions),Decimal(0))
        baseline={'quantities':quantities,'cash_cny':str(cash),'equity_cny':str(total)}
        accounts=[{'name':s.name,**deepcopy(baseline),'fees_cny':'0','cumulative_turnover_pct':'0','peak_equity_cny':str(total),'max_drawdown_pct':'0','timeline':[]} for s in body.strategies]
        payload={'name':body.name,'config':body.model_dump(mode='json'),'baseline_bundle':bundle.model_dump(mode='json'),'baseline':baseline,
                 'baseline_hash':digest(bundle.model_dump(mode='json')),'data_mode':context['data_mode'],'is_synthetic':context['is_synthetic'],
                 'profile_hash':digest(bound.confirmed_profile.model_dump(mode='json')),
                 'accounts':accounts,'status':'READY','last_quote_at':None,'last_frame':None,
                 'notice':'从启用后逐次记录虚拟组合，不提交真实订单；不表示历史回测或未来投资收益。'}
        return self.records.write(owner,'shadow',uuid4().hex,0,payload)

    async def step(self,owner,record_id,body):
        async with asyncio.timeout(60):
            return await self._step(owner,record_id,body)

    async def _step(self,owner,record_id,body):
        row=self.records.get(owner,'shadow',record_id)
        if row['revision']!=body.expected_revision:
            from app.store.sqlite import StoreConflictError
            raise StoreConflictError('模拟账本已变化。')
        payload=deepcopy(row['payload'])
        context=self.context(owner)
        if context['data_mode']!=payload['data_mode']:
            raise LabInvalid('数据模式已变化，请另建同基线实验。')
        quoted=context['bundle']
        quote_time=quoted.position_snapshot.as_of
        if quote_time>self.records.clock() or (payload['last_quote_at'] and quote_time<datetime.fromisoformat(payload['last_quote_at'])):
            raise LabInvalid('报价时点倒退或来自未来，不能推进虚拟账本。')
        metadata={p.asset_id:p for p in quoted.position_snapshot.positions}
        prices={p.asset_id:p.market_value/p.quantity for p in metadata.values() if p.asset_type!=AssetType.CASH}
        initial=PortfolioImportBundle.model_validate(payload['baseline_bundle'])
        if any(p.asset_id not in prices or prices[p.asset_id]<=0 for p in initial.position_snapshot.positions if p.asset_type!=AssetType.CASH):
            raise LabInvalid('模拟资产缺少当前可信报价，暂不能推进。')
        frame=digest({'quote_time':quote_time.isoformat(),'prices':prices})
        if any(len(account['timeline'])>=1000 for account in payload['accounts']):
            raise LabInvalid('模拟已达到1000个记录点，请归档后新建实验。')
        config=ExperimentInput.model_validate(payload['config'])
        from app.api.investment_memory_routes import PersonalRebalancingPreview
        # This builder supplies the current confirmed risk profile and bound prices.
        bound=self.request_builder(owner,PersonalRebalancingPreview(expected_policy_revision=config.policy_revision or 1,
            target_weights=config.strategies[0].matched_weights))
        if digest(bound.confirmed_profile.model_dump(mode='json'))!=payload['profile_hash']:
            raise LabInvalid('投资者画像已变化，请以新条件创建实验。')
        policy=self.memory.resolve_policy(owner,config.policy_revision) if config.policy_revision else None
        for strategy in config.strategies:
            system=self.personal.get(owner,strategy.system_id)
            if system['revision']!=strategy.system_revision:
                raise LabInvalid('研究方法已变化，请另建实验。')
            self.personal._validate_skills(owner,PersonalResearchDefinition.model_validate(system['definition']),require_callable=True)
        if frame==payload['last_frame']:
            return {**row,'duplicate_quote':True}
        benchmark=_amount(Decimal(payload['baseline']['cash_cny'])+sum((Decimal(qty)*prices[asset] for asset,qty in payload['baseline']['quantities'].items()),Decimal(0)))
        for account,strategy in zip(payload['accounts'],config.strategies):
            before=_amount(Decimal(account['cash_cny'])+sum((Decimal(qty)*prices[asset] for asset,qty in account['quantities'].items()),Decimal(0)))
            point={'quoted_at':quote_time.isoformat(),'status':'INSUFFICIENT_DATA','equity_cny':str(before),'benchmark_equity_cny':str(benchmark)}
            try:
                run=await self.personal.run_and_wait(owner,strategy.system_id,PersonalResearchRun(expected_revision=strategy.system_revision,
                    subject=strategy.subject,period=strategy.period,as_of=quote_time))
                if run['is_synthetic'] and not context['is_synthetic']:
                    raise LabInvalid('真实模拟不能使用受控财务输入。')
                indicator=next((i for i in run['indicators'] if i['indicator_id']==strategy.indicator_id),None)
                if indicator is None or indicator['status']!='CALCULATED' or indicator['unit']!=strategy.unit:
                    raise LabInvalid('研究指标或单位不可用。')
                matched=Decimal(indicator['value'])>=strategy.threshold if strategy.comparison=='AT_LEAST' else Decimal(indicator['value'])<=strategy.threshold
                target=strategy.matched_weights if matched else strategy.unmatched_weights
                current_positions=[]
                for asset,qty in account['quantities'].items():
                    qty=Decimal(qty)
                    if qty>0:
                        current_positions.append(metadata[asset].model_copy(update={'quantity':qty,'market_value':_amount(qty*prices[asset])}))
                if Decimal(account['cash_cny'])>0:
                    from app.portfolio.contracts import Position
                    current_positions.append(Position(position_id='virtual-cash',owner_id=owner,asset_id='CASH-CNY',asset_type='CASH',asset_name='虚拟现金',
                        quantity=Decimal(account['cash_cny']),market_value=Decimal(account['cash_cny']),currency='CNY',sector='Cash',as_of=quote_time,source='shadow-ledger'))
                virtual=quoted.model_copy(update={'fund_holdings':tuple(s for s in quoted.fund_holdings if any(p.asset_id==s.parent_asset_id for p in current_positions)),
                    'position_snapshot':quoted.position_snapshot.model_copy(update={'positions':tuple(current_positions)})})
                request=PortfolioRebalancingRequest(request_id='virtual:'+uuid4().hex,owner_id=owner,generated_at=quote_time,bundle=virtual,target_weights=target,
                    deadband_pct=config.deadband_pct,max_turnover_pct=config.max_turnover_pct,minimum_cash_pct=config.minimum_cash_pct,
                    prices_cny=prices,asset_types={**{a:p.asset_type for a,p in metadata.items()},'CASH-CNY':AssetType.CASH},round_to_lot=True)
                if policy:
                    request,_=self.memory.apply_policy(request,policy)
                plan=self.planner.plan_rebalancing(request)
                quantities={a:Decimal(q) for a,q in account['quantities'].items()}
                for action in plan.actions:
                    if action.asset_type!=AssetType.CASH and action.executable and action.shares:
                        quantities[action.asset_id]=quantities.get(action.asset_id,Decimal(0))+action.shares*(-1 if action.cash_delta_cny<0 else 1)
                cash=plan.metrics.cash_after_cny
                post=[metadata[a].model_copy(update={'quantity':q,'market_value':_amount(q*prices[a])}) for a,q in quantities.items() if q>0]
                if cash>0:
                    from app.portfolio.contracts import Position
                    post.append(Position(position_id='virtual-cash',owner_id=owner,asset_id='CASH-CNY',asset_type='CASH',asset_name='虚拟现金',
                        quantity=cash,market_value=cash,currency='CNY',sector='Cash',as_of=quote_time,source='shadow-ledger'))
                post_bundle=virtual.model_copy(update={'position_snapshot':virtual.position_snapshot.model_copy(update={'positions':tuple(post)}),
                    'fund_holdings':tuple(s for s in quoted.fund_holdings if any(p.asset_id==s.parent_asset_id for p in post))})
                health=calculate_portfolio_health(PortfolioHealthRequest(request_id='virtual-health:'+uuid4().hex,owner_id=owner,calculated_at=quote_time,
                    portfolio=post_bundle,profile=bound.confirmed_profile))
                budget=assess_risk_budget(bound.confirmed_profile,calculate_concentration(calculate_exposure(post_bundle)))
                applied=plan.status==GateStatus.PASS and health.status=='PASS' and not budget.breaches and cash>=0 and all(q>=0 for q in quantities.values())
                point.update(status=('APPLIED' if plan.execution_steps else 'HELD') if applied else 'REVIEW_REQUIRED',run_id=run['run_id'],indicator_value=indicator['value'],
                             matched=matched,plan=plan.model_dump(mode='json'),health=health.model_dump(mode='json'),risk_budget=budget.model_dump(mode='json'))
                if applied:
                    account.update(quantities={a:str(q) for a,q in quantities.items()},cash_cny=str(cash),
                        fees_cny=str(Decimal(account['fees_cny'])+plan.metrics.net_turnover_cost),
                        cumulative_turnover_pct=str(Decimal(account['cumulative_turnover_pct'])+plan.metrics.total_turnover_pct))
                    point['equity_cny']=str(_amount(cash+sum((q*prices[a] for a,q in quantities.items()),Decimal(0))))
            except asyncio.CancelledError:
                raise
            except Exception:
                point['notice']='方法、资料或风险条件不足，本次未模拟成交。'
            equity=Decimal(point['equity_cny'])
            peak=max(Decimal(account['peak_equity_cny']),equity)
            account.update(equity_cny=str(equity),peak_equity_cny=str(peak),
                max_drawdown_pct=str(max(Decimal(account['max_drawdown_pct']),(1-equity/peak)*100)),
                net_return_pct=str((equity/Decimal(payload['baseline']['equity_cny'])-1)*100))
            account['timeline'].append(point)
        payload.update(last_quote_at=quote_time.isoformat(),last_frame=frame,status='UPDATED',benchmark_equity_cny=str(benchmark))
        return self.records.write(owner,'shadow',record_id,row['revision'],payload)
