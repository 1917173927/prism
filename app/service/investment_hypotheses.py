"""Confirmed hypotheses, bounded monitoring and deduplicated evidence changes."""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from pydantic import Field, model_validator

from app.service.personal_research import _Model, PersonalResearchDefinition, PersonalResearchRun, _period
from app.service.research_lab_store import LabInvalid, digest
from app.store.sqlite import StoreConflictError


class HypothesisInput(_Model):
    name: str = Field(min_length=1,max_length=100)
    rationale: str = Field(min_length=1,max_length=1000)
    system_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    system_revision: int = Field(ge=1)
    subject: str = Field(pattern=r"^\d{6}$")
    indicator_id: str = Field(min_length=1,max_length=40)
    periods: tuple[str,...] = Field(min_length=1,max_length=3)
    condition: str = Field(pattern=r"^(AT_LEAST|AT_MOST|INCREASING|DECREASING)$")
    threshold: Decimal | None = None
    interval_seconds: int = Field(default=86400,ge=60,le=604800)
    enabled: bool = False
    follow_new_reports: bool = True
    expected_revision: int = Field(default=0,ge=0)

    @model_validator(mode="after")
    def condition_inputs(self):
        normalized=[_period(p) for p in self.periods]
        if sorted(set(normalized))!=normalized:
            raise ValueError("periods must be unique and increasing")
        if self.condition in {'INCREASING','DECREASING'} and len(self.periods)!=3:
            raise ValueError("two-period changes require three reporting periods")
        if self.condition in {'AT_LEAST','AT_MOST'} and (len(self.periods)!=1 or self.threshold is None):
            raise ValueError("threshold condition requires one period and an explicit threshold")
        if self.condition in {'INCREASING','DECREASING'} and self.threshold is not None:
            raise ValueError("trend conditions do not use a threshold")
        return self


def judge_hypothesis(config, results):
    if any(item['status']!='CALCULATED' for item in results):
        return 'INSUFFICIENT_DATA'
    if len({item['unit'] for item in results})!=1:
        return 'INSUFFICIENT_DATA'
    values=[Decimal(item['value']) for item in results]
    condition=config['condition']
    if condition=='AT_LEAST':
        matched=values[0]>=Decimal(config['threshold'])
    elif condition=='AT_MOST':
        matched=values[0]<=Decimal(config['threshold'])
    elif condition=='INCREASING':
        matched=all(a<b for a,b in zip(values,values[1:]))
    else:
        matched=all(a>b for a,b in zip(values,values[1:]))
    return 'SUPPORTED' if matched else 'CONTRADICTED'


class HypothesisMonitor:
    def __init__(self, records, personal, knowledge=None):
        self.records,self.personal,self.knowledge=records,personal,knowledge
        self._task=None
        self._running={}
        self._closed=False

    def save(self,owner,record_id,body):
        if body.enabled:
            system=self.personal.get(owner,body.system_id)
            if system['revision']!=body.system_revision:
                raise StoreConflictError('研究方法已变化。')
            definition=PersonalResearchDefinition.model_validate(system['definition'])
            self.personal._validate_skills(owner,definition,require_callable=True)
            if body.indicator_id not in {i.indicator_id for i in definition.indicators}:
                raise LabInvalid('观察指标不属于已确认研究方法。')
        if body.enabled and sum(row['payload']['config']['enabled'] for row in self.records.list(owner,'hypothesis') if row['record_id']!=record_id)>=32:
            raise LabInvalid('每账户最多启用32个假设订阅。')
        config=body.model_dump(mode='json',exclude={'expected_revision'})
        payload={'name':body.name,'config':config,'status':'PENDING','next_check_at':self.records.clock().isoformat(),
                 'last_checked_at':None,'latest':None,'notice':'监测结果是研究观察，不能代替买卖决定。'}
        result=self.records.write(owner,'hypothesis',record_id,body.expected_revision,payload)
        task=self._running.get((owner,record_id))
        if task:
            task.get_loop().call_soon_threadsafe(task.cancel)
        return result

    async def evaluate(self,owner,record_id):
        base=self.records.get(owner,'hypothesis',record_id)
        try:
            async with asyncio.timeout(60):
                return await self._evaluate(owner,record_id)
        except TimeoutError:
            now=self.records.clock()
            return self.records.write(owner,'hypothesis',record_id,base['revision'],{**base['payload'],'status':'INSUFFICIENT_DATA',
                'last_checked_at':now.isoformat(),'next_check_at':(now+timedelta(seconds=base['payload']['config']['interval_seconds'])).isoformat(),
                'latest':{'status':'TIMED_OUT','notice':'本次复核超过60秒预算，未形成有效结论。'}})

    async def _evaluate(self,owner,record_id):
        if self._closed:
            raise LabInvalid('监测服务已关闭。')
        if (owner,record_id) in self._running:
            raise LabInvalid('该假设正在复核，请稍后刷新。')
        row=self.records.get(owner,'hypothesis',record_id)
        config=row['payload']['config']
        if not config['enabled']:
            raise LabInvalid('假设已停止，请确认订阅后复核。')
        task=asyncio.current_task()
        self._running[(owner,record_id)]=task
        try:
            results,runs,source_data=[],[],[]
            status='INSUFFICIENT_DATA'
            try:
                system=self.personal.get(owner,config['system_id'])
                if system['revision']!=config['system_revision']:
                    status='STALE_METHOD'
                else:
                    for period in config['periods']:
                        run=await self.personal.run_and_wait(owner,config['system_id'],PersonalResearchRun(expected_revision=config['system_revision'],subject=config['subject'],period=period))
                        result=next((i for i in run['indicators'] if i['indicator_id']==config['indicator_id']),
                                    {'indicator_id':config['indicator_id'],'status':'UNAVAILABLE','period':period,'value':None,'unit':None})
                        results.append(result)
                        runs.append({'run_id':run['run_id'],'period':period,'status':run['status'],'is_synthetic':run['is_synthetic']})
                        source_data.append([{'metric':o.get('metric'),'value':o.get('value'),'unit':o.get('unit'),'period':o.get('period'),
                                             'observed_at':o.get('observed_at'),'actual_source':o.get('actual_source')} for a in run['data_agents'] for o in a.get('observations',[])])
                    status=judge_hypothesis(config,results)
            except asyncio.CancelledError:
                raise
            except Exception:
                status='INSUFFICIENT_DATA'
            now=self.records.clock()
            signature=digest({'config':config,'status':status,'sources':source_data,
                              'values':[{k:r.get(k) for k in ('indicator_id','status','value','unit','period')} for r in results]})
            changed=row['payload'].get('signature')!=signature
            latest={'status':status,'indicators':results,'runs':runs,'changed':changed,'observed_at':now.isoformat(),
                    'is_synthetic':any(r['is_synthetic'] for r in runs),'source_signature':signature}
            updated=self.records.write(owner,'hypothesis',record_id,row['revision'],{**row['payload'],'status':status,'latest':latest,'signature':signature,
                'last_checked_at':now.isoformat(),'next_check_at':(now+timedelta(seconds=config['interval_seconds'])).isoformat()})
            if changed:
                events=self.records.list(owner,'hypothesis-event')
                # One account retains at most 200 immutable event identities.
                if len(events)<200:
                    self.records.write(owner,'hypothesis-event',uuid4().hex,0,{'name':config['name'],'hypothesis_id':record_id,'system_revision':config['system_revision'],**latest})
            return updated
        finally:
            self._running.pop((owner,record_id),None)

    async def tick(self):
        with self.records.store._lock:
            rows=self.records.store._connection.execute("SELECT DISTINCT owner_id FROM research_lab_versions WHERE kind='hypothesis'").fetchall()
        owner_due=[]
        for row in rows:
            owner=row['owner_id']
            if self.knowledge is not None:
                documents=self.knowledge.list_documents(owner,limit=100)
                for hypothesis in self.records.list(owner,'hypothesis'):
                    config=hypothesis['payload']['config']
                    if not config['enabled'] or not config.get('follow_new_reports'):
                        continue
                    candidates=[]
                    for document in documents:
                        if ((document.get('subject') or '').split('.')[0]!=config['subject'] or not document.get('period') or
                            datetime.fromisoformat(document['published_at'])>self.records.clock()):
                            continue
                        source=self.knowledge.get(owner,document['document_id'])
                        if source is None or source['original']['kind']!='FINANCIAL_REPORT':
                            continue
                        try:
                            period=_period(document['period'])
                        except ValueError:
                            continue
                        if period>_period(config['periods'][-1]) and period<=self.records.clock().date().isoformat():
                            candidates.append(document['period'])
                    if candidates:
                        count=len(config['periods'])
                        periods=sorted(set([*config['periods'],*candidates]),key=_period)[-count:]
                        self.records.write(owner,'hypothesis',hypothesis['record_id'],hypothesis['revision'],{
                            **hypothesis['payload'],'config':{**config,'periods':periods},'next_check_at':self.records.clock().isoformat()})
            owner_due.append([(owner,r['record_id']) for r in self.records.list(owner,'hypothesis') if r['payload']['config']['enabled'] and datetime.fromisoformat(r['payload']['next_check_at'])<=self.records.clock()])
        due=[]
        while any(owner_due) and len(due)<64:
            for queue in owner_due:
                if queue and len(due)<64:
                    due.append(queue.pop(0))
        semaphore=asyncio.Semaphore(4)
        async def execute(owner,record_id):
            async with semaphore:
                try:
                    await self.evaluate(owner,record_id)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
        await asyncio.gather(*(execute(owner,record_id) for owner,record_id in due))

    async def _loop(self):
        while True:
            await asyncio.sleep(10)
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

    async def start(self):
        if self._task is None:
            self._closed=False
            self._task=asyncio.create_task(self._loop())

    async def close(self):
        self._closed=True
        tasks={*self._running.values()}
        if self._task:
            tasks.add(self._task)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks,return_exceptions=True)
        self._task=None
