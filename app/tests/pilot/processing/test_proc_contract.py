import asyncio
import copy
import json
import os
import socket
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID,uuid4

import httpx
import pytest
from ..harness import ROOT
from ..scenarios import Gateway,ready,report,tasks,wallet,finalize

pytestmark=pytest.mark.asyncio


async def child(h,mode='once',*args):
    path=h.svc.storage_root.parent/'declared-report.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report()),encoding='utf-8')
    env={**os.environ,'DATABASE_URL':h.svc.test_database_url,'PILOT_STORAGE_ROOT':str(h.svc.storage_root),'PILOT_TEST_REPORT':str(path),'PYTHONPATH':str(ROOT/'app'),'PYTHONPYCACHEPREFIX':str(ROOT.parent/'.cache/processing-bytecode')}
    return await asyncio.create_subprocess_exec(sys.executable,'-m','tests.pilot.child_runtime',mode,*map(str,args),cwd=ROOT/'app',env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)


async def finish(process):
    out,err=await asyncio.wait_for(process.communicate(),30)
    assert process.returncode==0,(out.decode(),err.decode())


async def test_proc_c05(h):
    await wallet(h.svc)
    ids=await h.create();key=uuid4();revision=(await h.check())['revision']
    response=await h.submit(ids[2],ids[3],key=key,revision=revision,expected=202)
    await h.svc.pool.execute('CREATE TABLE test_gateway_calls(job_id UUID,kind TEXT)')
    # The ASGI process genuinely stops and starts, against the same PG/storage.
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    for _ in range(2):
        backend=await child(h,'serve',port)
        try:
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',cookies=h.clients['t1'].cookies) as client:
                for attempt in range(100):
                    try:
                        got=await client.get('/api/checks/'+ids[0]);break
                    except httpx.ConnectError:await asyncio.sleep(.05)
                else:raise AssertionError('child backend did not start')
                assert got.status_code==200,got.text
                assert got.json()['notebooks'][0]['bundles'][0]['current_input']['id']==ids[3]
        finally:
            backend.terminate();await backend.communicate()
    process=await child(h);await finish(process)
    replay=await h.submit(ids[2],ids[3],key=key,revision=revision,expected=202)
    assert replay.json()==response.json()
    assert len(tasks(await h.check()))==1
    assert await h.svc.pool.fetchval('SELECT count(*) FROM test_gateway_calls')==1
    process=await child(h);await finish(process)
    assert await h.svc.pool.fetchval('SELECT count(*) FROM test_gateway_calls')==1


async def test_proc_c09(h):
    await wallet(h.svc)
    for count,photos,continued in [(1,1,False),(2,1,False),(1,2,True),(2,2,True)]:
        h.svc.transport=Gateway(page_report=report(count,continuation=continued))
        ids=await h.create(photos=photos);await h.submit(ids[2],ids[3],expected=202);await h.run()
        items=tasks(await h.check());assert len(items)==count
        assert items[0]['analysis']['photo_indices']==([1,2] if continued else [1])
        assert len(items[0]['analysis']['evidence'])<=4
    invalid=report();invalid['tasks'][0]['photo_indices']=[99]
    h.svc.transport=Gateway(page_report=invalid);ids=await h.create();result=await h.submit(ids[2],ids[3],expected=202);await h.run()
    job=(await h.call('getJob',job_id=result.json()['job']['id'],expected=200)).json()
    assert job['state']=='failed' and job['reason']=='invalid_response'
    assert tasks(await h.check())==[]


async def test_proc_c15(h):
    await wallet(h.svc);ids=await h.create();await h.submit(ids[2],ids[3],expected=202)
    await h.svc.pool.execute('CREATE TABLE test_gateway_calls(job_id UUID,kind TEXT)')
    workers=await asyncio.gather(child(h),child(h))
    await asyncio.gather(*(finish(p) for p in workers))
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_attempts')==1
    assert await h.svc.pool.fetchval('SELECT count(*) FROM test_gateway_calls')==1
    assert len(tasks(await h.check()))==1


async def test_proc_c16(h):
    await wallet(h.svc)
    for outcomes,state in [(('temporary_failure','success'),'succeeded'),(('temporary_failure','temporary_failure'),'failed')]:
        gateway=Gateway(*outcomes);h.svc.transport=gateway
        ids=await h.create();submitted=await h.submit(ids[2],ids[3],expected=202);await h.run()
        await h.svc.pool.execute("UPDATE pilot_jobs SET next_run_at=now() WHERE state='retry_wait'")
        await h.run();await h.run()
        job=await h.call('getJob',job_id=submitted.json()['job']['id'],expected=200)
        assert job.json()['state']==state and len(gateway.calls)==2
        assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_attempts WHERE job_id=$1',UUID(submitted.json()['job']['id']))==2


async def test_proc_c17(h):
    from pilot.processing.worker import recover_expired
    ids,gateway,jid=await ready(h)
    # Another accepted input receives a genuinely unknown provider outcome.
    ids=await h.create();gateway=Gateway('unknown');h.svc.transport=gateway
    response=await h.submit(ids[2],ids[3],expected=202);await h.run()
    job=(await h.call('getJob',job_id=response.json()['job']['id'],expected=200)).json()
    assert job['state']=='unknown' and not job['can_retry']
    hold=await h.svc.pool.fetchval("SELECT held_rub FROM pilot_funds WHERE mode='fixture'")
    assert hold>0
    await recover_expired(h.svc);await h.run();assert len(gateway.calls)==1
    await h.call('skipBundle',bundle_id=ids[2],payload={'input_version_id':ids[3]},expected=200)
    assert await h.svc.pool.fetchval("SELECT held_rub FROM pilot_funds WHERE mode='fixture'")==hold


async def test_proc_c18(h):
    from pilot.processing.queue import claim
    from pilot.processing.worker import recover_expired
    await wallet(h.svc);ids=await h.create();submitted=await h.submit(ids[2],ids[3],expected=202)
    claimed=await claim(h.svc,uuid4())
    assert claimed is not None
    await h.svc.pool.execute("UPDATE pilot_jobs SET lease_until=now()-interval '1 second' WHERE id=$1",UUID(submitted.json()['job']['id']))
    await recover_expired(h.svc)
    job=(await h.call('getJob',job_id=submitted.json()['job']['id'],expected=200)).json()
    assert job['state'] in ('queued','unknown')
    # Dispatched attempts must never be put back into the queue.
    sent=await h.svc.pool.fetchval('SELECT bool_or(dispatched) FROM pilot_attempts WHERE job_id=$1',UUID(submitted.json()['job']['id']))
    if sent:assert job['state']=='unknown'


async def test_proc_c19(h):
    from pilot.processing.providers import build_request
    from pilot.processing.checker import load_prompt
    ids=await h.create(photos=2);await h.submit(ids[2],ids[3],expected=202)
    # Explicit fixture sends no external HTTP and is not selected by missing key.
    await wallet(h.svc);gateway=Gateway();h.svc.transport=gateway;await h.run()
    assert len(gateway.calls)==1 and gateway.calls[0][1]=='page_check'
    images=gateway.calls[0][2]['images'];assert len(images)==2
    request,_=build_request(h.svc,{'kind':'page_check'},gateway.calls[0][2])
    assert request['messages'][0]['content']==load_prompt()
    encoded=request['messages'][1]['content']
    assert [x['image_url']['detail'] for x in encoded if x['type']=='image_url']==['high','high']


async def test_proc_c27(h):
    from pilot.processing.funds import fund_wallet,FundsEvidence
    await wallet(h.svc,'10');h.svc.fixture_request_bound=Decimal('6')
    first=await h.create();await h.submit(first[2],first[3],expected=202)
    second=await h.create(actor='t2');await h.submit(second[2],second[3],actor='t2',expected=202)
    gateway=Gateway();gateway.release=asyncio.Event();h.svc.transport=gateway
    runs=[asyncio.create_task(h.run()),asyncio.create_task(h.run())]
    await asyncio.wait_for(gateway.entered.wait(),10)
    await asyncio.sleep(0)
    state=await h.svc.pool.fetchrow("SELECT * FROM pilot_funds WHERE mode='fixture'")
    assert state['held_rub']==6 and state['balance_rub']-state['held_rub']==4
    assert len(gateway.calls)==1
    req=uuid4();evidence=FundsEvidence(reference='synthetic topup',sha256='b'*64,profile_id='fixture')
    for _ in range(2):await fund_wallet(h.svc,operation='topup',amount_rub=Decimal(5),evidence=evidence,operator_ref='pytest',request_id=req)
    state=await h.svc.pool.fetchrow("SELECT * FROM pilot_funds WHERE mode='fixture'")
    assert state['balance_rub']==15 and state['held_rub']==6
    gateway.release.set();await asyncio.gather(*runs);await h.run()
    assert len(gateway.calls)==2
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_fund_ledger WHERE operation='settlement'")==2
    with pytest.raises(Exception):await h.svc.pool.execute("UPDATE pilot_funds SET held_rub=balance_rub+1 WHERE mode='fixture'")


async def test_proc_c28(h):
    from pilot.processing.control import set_processing_paused,get_processing_control
    await wallet(h.svc);ids=await h.create();await h.submit(ids[2],ids[3],expected=202)
    gateway=Gateway();h.svc.transport=gateway
    pause=await set_processing_paused(h.svc,paused=True,operator_ref='pytest',reason='synthetic',request_id=uuid4())
    await h.run();assert gateway.calls==[]
    await h.check()
    await set_processing_paused(h.svc,paused=False,operator_ref='pytest',reason='synthetic',request_id=uuid4())
    await h.run();assert len(gateway.calls)==1
    assert not (await get_processing_control(h.svc)).paused
    assert (await h.clients['t1'].post('/api/admin/pause')).status_code==404


async def test_proc_c29(h):
    from pilot.processing.funds import fund_wallet,FundsEvidence
    from pilot.processing.reconciliation import reconcile_attempt,ReconciliationEvidence
    await wallet(h.svc,'10');h.svc.transport=Gateway('unknown');ids=await h.create();await h.submit(ids[2],ids[3],expected=202);await h.run()
    attempt=await h.svc.pool.fetchval("SELECT id FROM pilot_attempts WHERE state='unknown'")
    before=await h.svc.pool.fetchval("SELECT held_rub FROM pilot_funds WHERE mode='fixture'")
    assert before>0
    evidence=ReconciliationEvidence(reference='synthetic settled',sha256='c'*64,actual_cost_rub=Decimal('.2'),provider_request_id='synthetic')
    req=uuid4();one=await reconcile_attempt(h.svc,attempt_id=attempt,outcome='settled',evidence=evidence,operator_ref='pytest',request_id=req)
    two=await reconcile_attempt(h.svc,attempt_id=attempt,outcome='settled',evidence=evidence,operator_ref='pytest',request_id=req)
    assert one.changed and not two.changed
    assert await h.svc.pool.fetchval("SELECT held_rub FROM pilot_funds WHERE mode='fixture'")==0
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_fund_ledger WHERE operation='settlement'")==1
    with pytest.raises(Exception):await fund_wallet(h.svc,operation='topup',amount_rub=Decimal('NaN'),evidence=FundsEvidence(reference='bad',sha256='d'*64,profile_id='fixture'),operator_ref='pytest',request_id=uuid4())
    assert await h.svc.pool.fetchval("SELECT balance_rub FROM pilot_funds WHERE mode='polza'")==0


async def test_proc_c30(h):
    await wallet(h.svc);gateway=Gateway(page_report=report(3));h.svc.transport=gateway
    for actor in ('t1','t2'):
        first=await h.create(actor=actor);check_id=first[0];notebooks=[first[1:]]
        for _ in range(29):
            n=(await h.call('createNotebook',actor=actor,check_id=check_id,expected=201)).json()['entity_id']
            b=(await h.call('createBundle',actor=actor,notebook_id=n,expected=201)).json()['entity_id']
            c=await h.check(actor);bundle=next(bu for no in c['notebooks'] for bu in no['bundles'] if bu['id']==b);v=bundle['draft']['id']
            from ..harness import png
            await h.call('uploadPhoto',actor=actor,input_version_id=v,files={'file':('synthetic.png',png(),'image/png')},expected=201)
            notebooks.append((n,b,v))
        for _,b,v in notebooks:await h.submit(b,v,actor=actor,expected=202)
    async def worker():
        while await h.run():pass
    await asyncio.gather(worker(),worker())
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_notebooks')==60
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_bundle_reports')==60
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_task_analyses WHERE NOT deleted')==180
    assert gateway.maximum<=2 and len(gateway.calls)==60
