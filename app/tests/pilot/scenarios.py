import asyncio
import copy
import json
from decimal import Decimal
from uuid import UUID, uuid4

from .harness import SHARED


def report(count=1, mixed=False, continuation=False):
    data = json.loads((SHARED/'analytics/fixtures/oracle.input.json').read_text(encoding='utf-8'))
    tasks = [t['analysis'] for n in data['notebooks'] for t in n['tasks']]
    first = next(t for t in tasks if t['result']=='first_error_found')
    result = {'schema_version':'page-check/1.2','status':'ok','message':'Синтетический тест','tasks':[]}
    for i in range(count):
        task = copy.deepcopy(first)
        task['task_id'] = f'task_{i+1}'
        task['photo_indices'] = [1,2] if continuation else [1]
        for item in task['evidence']: item['photo_index']=1
        task['first_error']['photo_index']=1
        if mixed and i==count-1:
            task.update(result='not_assessed', first_error=None, evidence=[], uncheckable_reason='Недостаточно условия', completeness='unknown',detail_level='unknown')
        result['tasks'].append(task)
    return result


class Gateway:
    """Only the paid provider boundary is faked; queue, funds and results are PG."""
    def __init__(self, *outcomes, page_report=None):
        self.outcomes=list(outcomes)
        self.page_report=page_report or report()
        self.calls=[]
        self.active=0
        self.maximum=0
        self.entered=asyncio.Event()
        self.release=None

    async def __call__(self, job, payload):
        from pilot.processing.transport import TransportResult
        self.calls.append((str(job['id']),job['kind'],copy.deepcopy(payload)))
        self.active+=1
        self.maximum=max(self.maximum,self.active)
        self.entered.set()
        try:
            if self.release: await self.release.wait()
            outcome=self.outcomes.pop(0) if self.outcomes else 'success'
            if outcome!='success':
                return TransportResult(outcome,actual_cost_rub=None if outcome=='unknown' else Decimal(0),error_code='synthetic_'+outcome)
            if job['kind']=='page_check': result=copy.deepcopy(self.page_report)
            else:
                # This declared one-notebook fixture is intentionally narrow.
                result={'schema_version':'class-summary/1','notebooks':{'total':1,'with_errors':1,'without_errors':0,'partial':0,'empty':0},'average_errors_per_notebook':1,'incomplete_tasks':0,'disputed_tasks':0,'unassessed_tasks':0,'top_errors':[{'rule':'Синтетическое правило','task_ids':[payload['notebooks'][0]['tasks'][0]['task_id']]}]}
            return TransportResult('success',payload=result,actual_cost_rub=Decimal('0.01'),provider_request_id='synthetic-'+str(len(self.calls)),raw=json.dumps(result))
        finally: self.active-=1


async def wallet(svc, amount='1000'):
    from pilot.processing.funds import fund_wallet, FundsEvidence
    return await fund_wallet(svc,operation='initialize',amount_rub=Decimal(amount),evidence=FundsEvidence(reference='synthetic fixture only',sha256='a'*64,profile_id='fixture'),operator_ref='pytest',request_id=uuid4())


async def ready(h, *, count=1, mixed=False):
    gateway=Gateway(page_report=report(count,mixed))
    h.svc.transport=gateway
    if not await h.svc.pool.fetchval("SELECT initialized FROM pilot_funds WHERE mode='fixture'"):
        await wallet(h.svc)
    ids=await h.create()
    response=await h.submit(ids[2],ids[3],expected=202)
    job_id=response.json()['job']['id']
    for _ in range(20):
        await h.run()
        if await h.svc.pool.fetchval('SELECT state FROM pilot_jobs WHERE id=$1',UUID(job_id)) in ('succeeded','failed','unknown'):
            break
    return ids,gateway,job_id


def tasks(check):
    return [t for n in check['notebooks'] for b in n['bundles'] for t in b['tasks']]


async def finalize(h):
    await h.review_all()
    await h.call('beginCompletion',check_id=h.check_id,expected=200)
    return await h.call('finalizeCheck',check_id=h.check_id,expected=202)
