import asyncio
import copy
import json
from decimal import Decimal
from uuid import UUID,uuid4
import pytest

from ..harness import SHARED
from ..scenarios import Gateway,ready,tasks,finalize

pytestmark=pytest.mark.asyncio


async def test_proc_c25(h):
    from pilot.analytics.validation import validate_pair
    from pilot.domain.completion import build_snapshot
    from pilot.domain import repository as r
    from pilot.processing.transport import TransportResult
    # Seed domain source graphs with the declared task semantics, then let the
    # server build immutable snapshots; no snapshot payload is posted by a client.
    for name in ['oracle','zero-denominator','mixed','synonyms']:
        sample=json.loads((SHARED/f'analytics/fixtures/{name}.input.json').read_text(encoding='utf-8'))
        expected=json.loads((SHARED/f'analytics/fixtures/{name}.result.json').read_text(encoding='utf-8'))
        ids,gateway,_=await ready(h)
        async with h.svc.pool.acquire() as con,con.transaction():
            c=await r.load_check(con,ids[0],lock=True)
            # Fixture construction is allowed to create otherwise cumbersome
            # reviewed graphs; production snapshot assembly is always exercised.
            notebooks=[]
            for i,n in enumerate(sample['notebooks'],1):
                b={'id':str(uuid4()),'draft':None,'current_input':{'id':str(uuid4()),'state':'sealed','photos':[]},'job':{'id':str(uuid4()),'state':'succeeded'},'result':{'id':str(uuid4()),'input_version_id':str(uuid4()),'report':{'schema_version':'page-check/1.2','status':'ok','tasks':[],'message':''}},'tasks':[],'skipped':False}
                for t in n['tasks']:
                    b['tasks'].append({'task_id':t['task_id'],'analysis_id':t['analysis_id'],'analysis':t['analysis'],'review':{'state':t['review_state'],'comment':''} if t['review_state'] else None,'skipped':t['analysis']['result']=='not_assessed'})
                b['result']['report']['tasks']=[t['analysis'] for t in b['tasks']]
                notebooks.append({'id':n['notebook_id'],'number':i,'bundles':[b] if b['tasks'] else []})
                if n['unresolved_bundles']:
                    skipped=copy.deepcopy(b);skipped.update(id=str(uuid4()),skipped=True,result=None,tasks=[])
                    notebooks[-1]['bundles'].append(skipped)
            c['graph']['notebooks']=notebooks;c['phase']='finalized';sid=uuid4();snapshot=build_snapshot(c,sid)
            validate_pair(snapshot,expected)
            await con.execute('UPDATE pilot_checks SET graph=$2::jsonb,phase=$3 WHERE id=$1',c['id'],json.dumps(c['graph']),'finalized')
            await con.execute('INSERT INTO pilot_snapshots(id,check_id,data_revision,payload) VALUES($1,$2,$3,$4::jsonb)',sid,c['id'],c['data_revision'],json.dumps(snapshot))
            jid=uuid4();await con.execute("INSERT INTO pilot_jobs(id,check_id,kind,snapshot_id) VALUES($1,$2,'class_analytics',$3)",jid,c['id'],sid)
            await con.execute('UPDATE pilot_checks SET selected_summary_job_id=$2 WHERE id=$1',c['id'],jid)
        async def provider(job,payload):
            assert job['kind']=='class_analytics'
            return TransportResult('success',payload=expected,actual_cost_rub=Decimal('.01'),raw=json.dumps(expected))
        h.svc.transport=provider;await h.run()
        summary=(await h.call('getSummary',check_id=ids[0],expected=200)).json()
        assert summary['state']=='succeeded' and summary['result']==expected
        if name=='oracle':assert expected['average_errors_per_notebook']==.5
        if name=='zero-denominator':assert expected['average_errors_per_notebook'] is None


async def test_proc_c26(h):
    await ready(h);await finalize(h)
    gateway=Gateway('invalid_response');h.svc.transport=gateway;await h.run()
    summary=(await h.call('getSummary',check_id=h.check_id,expected=200)).json()
    assert summary['state']=='failed' and summary['can_retry'] and not summary['stale']
    key=uuid4();rev=(await h.check())['revision']
    retry=await h.call('retrySummary',check_id=h.check_id,key=key,revision=rev,expected=202)
    replay=await h.call('retrySummary',check_id=h.check_id,key=key,revision=rev,expected=202)
    assert retry.json()==replay.json() and retry.json()['job']['input_id']==summary['snapshot_id']
    h.svc.transport=Gateway();await h.run()
    assert (await h.call('getSummary',check_id=h.check_id,expected=200)).json()['state']=='succeeded'
    task=tasks(await h.check())[0]
    await h.call('saveReview',task_id=task['task_id'],payload={'analysis_id':task['analysis_id'],'state':'confirmed','comment':'Только комментарий'},expected=200)
    assert not (await h.call('getSummary',check_id=h.check_id,expected=200)).json()['stale']
    await h.call('saveReview',task_id=task['task_id'],payload={'analysis_id':task['analysis_id'],'state':'system_error','comment':''},expected=200)
    stale=(await h.call('getSummary',check_id=h.check_id,expected=200)).json()
    assert stale['stale'] and stale['can_refresh'] and not stale['can_retry']
    await h.call('retrySummary',check_id=h.check_id,expected=409)
    refreshed=await h.call('refreshSummary',check_id=h.check_id,expected=202)
    assert refreshed.json()['job']['input_id']!=summary['snapshot_id']


async def test_proc_c31(h,monkeypatch):
    from pilot.domain import repository
    await ready(h);await finalize(h);task=tasks(await h.check())[0]
    await h.call('saveReview',task_id=task['task_id'],payload={'analysis_id':task['analysis_id'],'state':'system_error','comment':''},expected=200)
    old=(await h.call('getSummary',check_id=h.check_id,expected=200)).json();assert old['can_refresh']
    original=repository.load_check;locked=asyncio.Event();release=asyncio.Event()
    async def gated(*args,**kwargs):
        value=await original(*args,**kwargs)
        if asyncio.current_task().get_name()=='refresh-first' and kwargs.get('lock'):
            locked.set();await release.wait()
        return value
    monkeypatch.setattr(repository,'load_check',gated)
    refreshing=asyncio.create_task(h.call('refreshSummary',check_id=h.check_id,expected=202),name='refresh-first')
    await asyncio.wait_for(locked.wait(),10)
    gateway=Gateway();h.svc.transport=gateway
    try:
        assert not await h.run()
        assert gateway.calls==[]
    finally:release.set()
    refreshed=await refreshing
    monkeypatch.setattr(repository,'load_check',original)
    assert await h.svc.pool.fetchval('SELECT state FROM pilot_jobs WHERE id=$1',UUID(old['job_id']))=='superseded'
    assert refreshed.json()['job']['input_id']!=old['snapshot_id']
    gateway=Gateway();gateway.release=asyncio.Event();h.svc.transport=gateway
    previous_revision=(await h.check())['revision']
    runner=asyncio.create_task(h.run());await asyncio.wait_for(gateway.entered.wait(),10)
    try:
        await h.call('saveReview',task_id=task['task_id'],payload={'analysis_id':task['analysis_id'],'state':'confirmed','comment':''},expected=200)
        current=(await h.call('getSummary',check_id=h.check_id,expected=200)).json()
        assert current['stale'] and not current['can_refresh']
        conflict=await h.call('refreshSummary',check_id=h.check_id,revision=previous_revision,expected=409)
        assert conflict.json()['error']['code']=='revision_conflict'
        await h.call('refreshSummary',check_id=h.check_id,expected=409)
    finally:gateway.release.set();await runner
    assert all(call[0]!=old['job_id'] for call in gateway.calls)
    # Exercise all shared guard combinations using actual Attempt rows, rather
    # than inferring safety from a Job enum alone.
    cases=json.loads((SHARED/'api/fixtures/summary-guards.json').read_text(encoding='utf-8'))
    snapshot_id=UUID(refreshed.json()['job']['input_id'])
    base_revision=await h.svc.pool.fetchval('SELECT data_revision FROM pilot_snapshots WHERE id=$1',snapshot_id)
    for case in cases:
        jid=uuid4()
        await h.svc.pool.execute('INSERT INTO pilot_jobs(id,check_id,kind,snapshot_id,state) VALUES($1,$2,$3,$4,$5)',jid,UUID(h.check_id),'class_analytics',snapshot_id,case['state'])
        if case['has_provider_attempt']:
            state='settled' if case['declared_safe'] else ('unknown' if case['state'] in ('unknown','failed') else 'started')
            await h.svc.pool.execute('INSERT INTO pilot_attempts(id,job_id,ordinal,epoch,state,dispatched) VALUES($1,$2,1,1,$3,true)',uuid4(),jid,state)
        await h.svc.pool.execute('UPDATE pilot_checks SET selected_summary_job_id=$2,phase=$3,data_revision=$4 WHERE id=$1',UUID(h.check_id),jid,case['phase'],base_revision+int(case['stale']))
        summary=(await h.call('getSummary',check_id=h.check_id,expected=200)).json()
        assert summary['can_refresh']==case['can_refresh'],case
        assert summary['can_retry']==case['can_retry'],case


async def test_proc_c32(h):
    ids,gateway,jid=await ready(h)
    job=(await h.call('getJob',job_id=jid,expected=200)).json();assert job['state']=='succeeded'
    result=await finalize(h);summary_id=result.json()['job']['id']
    await h.run()
    summary=(await h.call('getSummary',check_id=ids[0],expected=200)).json()
    assert summary['job_id']==summary_id and summary['state']=='succeeded'
    assert summary['result']['notebooks']['with_errors']==1
    await h.call('getBundleHistory',actor='staff',bundle_id=ids[2],expected=200)
    await h.call('getSummaryHistory',actor='staff',check_id=ids[0],expected=200)
    await h.call('getSummaryHistory',check_id=ids[0],expected=403)
    for table,count in [('pilot_jobs',2),('pilot_attempts',2),('pilot_bundle_reports',1),('pilot_snapshots',1),('pilot_analytics_results',1)]:
        assert await h.svc.pool.fetchval(f'SELECT count(*) FROM {table}')==count
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_fund_ledger WHERE operation='settlement'")==2
    assert len(gateway.calls)==2 and {x[1] for x in gateway.calls}=={'page_check','class_analytics'}
    assert h.svc.mode=='fixture'
    # The ordinary explicit fixture profile must also work end-to-end, without
    # any test gateway override or mathematically fabricated production result.
    h.svc.transport=None
    second=await h.create()
    await h.submit(second[2],second[3],expected=202);await h.run()
    assert len(tasks(await h.check()))>0
    await finalize(h);await h.run()
    normal=(await h.call('getSummary',check_id=second[0],expected=200)).json()
    assert normal['state']=='succeeded' and normal['result'] is not None
