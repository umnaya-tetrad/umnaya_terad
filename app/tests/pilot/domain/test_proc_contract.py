import asyncio
import io
import json
import shutil
from decimal import Decimal
from uuid import UUID,uuid4

import asyncpg
import pytest
from PIL import Image

from ..harness import ROOT, SHARED, png
from ..scenarios import Gateway,ready,report,tasks,wallet,finalize

pytestmark=pytest.mark.asyncio


async def test_proc_c01(db,tmp_path):
    from pilot.domain.migrate import migrate,MIGRATIONS
    legacy=tmp_path/'legacy';legacy.mkdir()
    for source in sorted(MIGRATIONS.glob('*.sql'))[:7]:shutil.copyfile(source,legacy/source.name)
    await migrate(db,migrations_path=legacy)
    uid=uuid4()
    await db.execute("INSERT INTO users(id,username,password_hash) VALUES($1,'upgrade_user','synthetic_hash')",uid)
    await db.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES($1,$2,now()+interval '1 day')",'a'*64,uid)
    await migrate(db)
    count=await db.fetchval('SELECT count(*) FROM pilot_migrations')
    await migrate(db)
    assert await db.fetchval('SELECT count(*) FROM pilot_migrations')==count
    expected={'pilot_checks','pilot_notebooks','pilot_bundles','pilot_jobs','pilot_attempts','pilot_snapshots','pilot_fund_ledger','pilot_slots'}
    names={r['tablename'] for r in await db.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
    assert expected <= names
    copied=tmp_path/'migrations';shutil.copytree(MIGRATIONS,copied)
    first=sorted(copied.glob('*.sql'))[0]
    first.write_bytes(first.read_bytes()+b'\n-- tampered\n')
    with pytest.raises(RuntimeError,match='checksum'): await migrate(db,migrations_path=copied)
    assert await db.fetchval('SELECT count(*) FROM pilot_migrations')==count
    assert await db.fetchval("SELECT password_hash FROM users WHERE username='upgrade_user'")=='synthetic_hash'
    assert await db.fetchval('SELECT token_hash FROM auth_sessions WHERE user_id=$1',uid)=='a'*64


async def test_proc_c02(h):
    from pilot.processing.worker import heartbeat,healthcheck
    routes=h.app.openapi()['paths']
    operations=[v['operationId'] for methods in routes.values() for v in methods.values()]
    assert len(operations)==len(set(operations))
    assert not any('/api/api/' in path for path in routes)
    await heartbeat(h.svc,uuid4())
    assert await healthcheck(h.svc)
    await h.svc.pool.execute("UPDATE pilot_workers SET heartbeat_at=now()-interval '60 seconds'")
    assert not await healthcheck(h.svc)
    assert (ROOT/'app/pilot/contracts.py').read_bytes()==(SHARED/'api/contracts.py').read_bytes()


async def test_proc_c03(h):
    from pilot.domain.auth import ensure_account,reset_account_password,authenticate
    ids=await h.create()
    await h.call('getCheck',actor='t2',check_id=ids[0],expected=404)
    await h.call('getCheck',actor='anon',check_id=ids[0],expected=401)
    await h.call('getBundleHistory',bundle_id=ids[2],expected=403)
    await h.call('getBundleHistory',actor='staff',bundle_id=ids[2],expected=200)
    await h.call('login',actor='anon',payload={'login':'test_t1','password':'incorrect'},expected=401)
    await ensure_account(h.svc,'test_t1','different-long-password','teacher')
    await authenticate(h.svc,'test_t1','synthetic-test-password-47')
    with pytest.raises(Exception) as error: await ensure_account(h.svc,'test_t1','different-long-password','staff')
    assert error.value.http_status==409
    await reset_account_password(h.svc,login='test_t1',password='new-synthetic-password-49',operator_ref='pytest',request_id=uuid4())
    await h.call('getSession',expected=401)
    await h.call('getSession',actor='t2',expected=200)
    assert (await authenticate(h.svc,'test_t1','new-synthetic-password-49')).session['user_id']==h.ids['t1']
    assert (await h.clients['anon'].post('/api/auth/register',json={})).status_code==404


async def test_proc_c04(h):
    ids=await h.create();key=uuid4();revision=(await h.check())['revision']
    first=await h.submit(ids[2],ids[3],expected=202,key=key,revision=revision)
    replay=await h.submit(ids[2],ids[3],expected=202,key=key,revision=revision)
    assert first.json()==replay.json()
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_jobs')==1
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_idempotency WHERE key=$1",key)==1
    await h.submit(ids[2],str(uuid4()),expected=409,key=key,revision=revision)
    rejected=await h.submit(ids[2],ids[3],expected=409,revision=revision)
    assert rejected.json()['error']['code']=='revision_conflict'


async def test_proc_c06(h):
    await ready(h);task=tasks(await h.check())[0];revision=(await h.check())['revision']
    payload={'analysis_id':task['analysis_id'],'state':'confirmed','comment':''}
    await h.call('saveReview',task_id=task['task_id'],payload=payload,revision=revision,expected=200)
    await h.call('saveReview',task_id=task['task_id'],payload={**payload,'state':'system_error'},revision=revision,expected=409)
    check=await h.check();data=check['data_revision'];revision=check['revision']
    await h.call('saveReview',task_id=task['task_id'],payload=payload,expected=200)
    assert (await h.check())['revision']==revision
    await h.call('saveReview',task_id=task['task_id'],payload={**payload,'comment':'Комментарий'},expected=200)
    assert (await h.check())['data_revision']==data
    r=await h.call('saveReview',task_id=task['task_id'],payload={**payload,'analysis_id':str(uuid4())},expected=409)
    assert r.json()['error']['code']=='stale_analysis'


async def test_proc_c07(h):
    ids=await h.create(photos=0)
    for fmt,mime in [('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')]:
        uploaded=await h.call('uploadPhoto',input_version_id=ids[3],files={'file':('../../synthetic',png(fmt=fmt),mime)},expected=201)
        asset=await h.call('getPhoto',photo_id=uploaded.json()['entity_id'],expected=200)
        assert asset.headers['cache-control']=='no-store'
        assert Image.open(io.BytesIO(asset.content)).size==(64,64)
        await h.call('getPhoto',actor='t2',photo_id=uploaded.json()['entity_id'],expected=404)
    await h.call('uploadPhoto',input_version_id=ids[3],files={'file':('bad.png',b'bad','image/png')},expected=422)
    await h.call('uploadPhoto',input_version_id=ids[3],files={'file':('bad.pdf',b'%PDF','application/pdf')},expected=415)
    await h.call('uploadPhoto',input_version_id=ids[3],files={'file':('tiny.png',png((31,64)),'image/png')},expected=422)
    from ..harness import CommittedAckLostPool
    base=h.svc.pool;revision=(await h.check())['revision'];count=await base.fetchval('SELECT count(*) FROM pilot_photo_assets');key=uuid4()
    h.svc.pool=CommittedAckLostPool(base)
    try:
        with pytest.raises(ConnectionResetError,match='COMMIT'):
            await h.call('uploadPhoto',input_version_id=ids[3],files={'file':('ack-lost.png',png(),'image/png')},revision=revision,key=key)
    finally:h.svc.pool=base
    assert await base.fetchval('SELECT count(*) FROM pilot_photo_assets')==count+1
    replay=await h.call('uploadPhoto',input_version_id=ids[3],files={'file':('ack-lost.png',png(),'image/png')},revision=revision,key=key,expected=201)
    asset=await h.call('getPhoto',photo_id=replay.json()['entity_id'],expected=200)
    assert asset.content==png()
    assert await base.fetchval('SELECT count(*) FROM pilot_photo_assets')==count+1
    assert (await h.check())['revision']==revision+1


async def test_proc_c08(h):
    ids=await h.create(photos=2);b=(await h.check())['notebooks'][0]['bundles'][0]
    photo_ids=[p['id'] for p in b['draft']['photos']][::-1]
    await h.call('reorderPhotos',input_version_id=ids[3],payload={'photo_ids':photo_ids},expected=200)
    await h.call('reorderPhotos',input_version_id=ids[3],payload={'photo_ids':photo_ids[:1]},expected=422)
    await h.submit(ids[2],ids[3],expected=202)
    b=(await h.check())['notebooks'][0]['bundles'][0]
    assert [p['id'] for p in b['current_input']['photos']]==photo_ids
    await h.call('reorderPhotos',input_version_id=ids[3],payload={'photo_ids':photo_ids},expected=409)
    draft=await h.call('createInputVersion',bundle_id=ids[2],payload={'photo_ids':photo_ids},expected=201)
    await h.call('discardDraft',input_version_id=draft.json()['entity_id'],expected=200)
    assert (await h.check())['notebooks'][0]['bundles'][0]['current_input']['id']==ids[3]


async def test_proc_c10(h):
    ids,gateway,_=await ready(h,count=2);await h.review_all();old={t['task_id'] for t in tasks(await h.check())}
    photo=(await h.check())['notebooks'][0]['bundles'][0]['current_input']['photos'][0]['id']
    draft=await h.call('createInputVersion',bundle_id=ids[2],payload={'photo_ids':[photo]},expected=201)
    assert all(t['review'] for t in tasks(await h.check()))
    await h.submit(ids[2],draft.json()['entity_id'],expected=202)
    assert tasks(await h.check())==[]
    gateway.page_report=report(3);await h.run();new=tasks(await h.check())
    assert len(new)==3 and not old.intersection(t['task_id'] for t in new)
    assert all(t['review'] is None for t in new)
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_bundle_reports')==2


async def test_proc_c11(h):
    ids,gateway,_=await ready(h,count=2,mixed=True);task=tasks(await h.check())[0]
    await h.call('deleteTask',task_id=task['task_id'],expected=200)
    await h.call('retryBundle',bundle_id=ids[2],payload={'input_version_id':ids[3]},expected=202)
    await h.run();assert task['task_id'] not in {t['task_id'] for t in tasks(await h.check())}
    history=(await h.call('getBundleHistory',actor='staff',bundle_id=ids[2],expected=200)).json()
    assert len(history['versions'])==1 and len(history['versions'][0]['runs'])==2
    assert task['task_id'] in history['versions'][0]['runs'][0]['deleted_task_ids']


async def test_proc_c12(h):
    _,_,_=await ready(h,count=2,mixed=True);items=tasks(await h.check());bad=items[-1]
    await h.call('saveReview',task_id=bad['task_id'],payload={'analysis_id':bad['analysis_id'],'state':'confirmed','comment':''},expected=409)
    await h.review_all();await h.call('beginCompletion',check_id=h.check_id,expected=200)
    await h.call('finalizeCheck',check_id=h.check_id,expected=202)
    snapshot=json.loads(await h.svc.pool.fetchval('SELECT payload FROM pilot_snapshots'))
    assert len(snapshot['notebooks'][0]['tasks'])==2
    assert snapshot['notebooks'][0]['tasks'][-1]['review_state'] is None


async def test_proc_c13(h):
    ids,_,_=await ready(h,count=2);items=tasks(await h.check())
    photo=(await h.check())['notebooks'][0]['bundles'][0]['current_input']['photos'][0]['id']
    await h.call('deleteTask',task_id=items[0]['task_id'],expected=200)
    assert len(tasks(await h.check()))==1
    await h.call('getPhoto',photo_id=photo,expected=200)
    await h.call('deleteTask',task_id=items[1]['task_id'],expected=200)
    assert tasks(await h.check())==[]
    await h.call('deleteNotebook',notebook_id=ids[1],expected=200)
    created=await h.call('createNotebook',check_id=ids[0],expected=201)
    assert (await h.check())['notebooks'][0]['number']==2


async def test_proc_c14(h):
    ids=await h.create();submitted=await h.submit(ids[2],ids[3],expected=202);key=uuid4();rev=(await h.check())['revision']
    deleted=await h.call('deleteCheck',check_id=ids[0],key=key,revision=rev,expected=200)
    await h.call('getCheck',check_id=ids[0],expected=404)
    await h.call('getJob',job_id=submitted.json()['job']['id'],expected=404)
    replay=await h.call('deleteCheck',check_id=ids[0],key=key,revision=rev,expected=200)
    assert deleted.json()==replay.json()
    assert not await h.run()


async def test_proc_c20(h):
    ids=await h.create(photos=0)
    await h.call('finalizeCheck',check_id=ids[0],expected=409)
    await h.call('beginCompletion',check_id=ids[0],expected=200)
    check=await h.check();assert check['phase']=='review' and not check['completion']['can_finalize']
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_snapshots')==0
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_jobs WHERE kind='class_analytics'")==0


async def test_proc_c21(h,monkeypatch):
    from pilot.domain import repository
    original=repository.load_check
    for first_operation in ('finalizeCheck','saveReview'):
        await ready(h);await h.review_all();await h.call('beginCompletion',check_id=h.check_id,expected=200)
        rev=(await h.check())['revision'];task=tasks(await h.check())[0]
        locked=asyncio.Event();release=asyncio.Event();second_entered=asyncio.Event()
        async def gated(*args,**kwargs):
            name=asyncio.current_task().get_name()
            if name=='second-mutation':second_entered.set()
            value=await original(*args,**kwargs)
            if name=='first-mutation' and kwargs.get('lock'):
                locked.set();await release.wait()
            return value
        monkeypatch.setattr(repository,'load_check',gated)
        async def invoke(operation):
            if operation=='finalizeCheck':return await h.call(operation,check_id=h.check_id,revision=rev)
            return await h.call(operation,task_id=task['task_id'],revision=rev,payload={'analysis_id':task['analysis_id'],'state':'system_error','comment':''})
        one=asyncio.create_task(invoke(first_operation),name='first-mutation')
        await asyncio.wait_for(locked.wait(),10)
        two=asyncio.create_task(invoke('saveReview' if first_operation=='finalizeCheck' else 'finalizeCheck'),name='second-mutation')
        try:await asyncio.wait_for(second_entered.wait(),10)
        finally:release.set()
        first,second=await asyncio.gather(one,two)
        assert first.status_code==(202 if first_operation=='finalizeCheck' else 200)
        assert second.status_code==409 and second.json()['error']['code']=='revision_conflict'
        snapshots=await h.svc.pool.fetchval('SELECT count(*) FROM pilot_snapshots WHERE check_id=$1',UUID(h.check_id))
        assert snapshots==(1 if first_operation=='finalizeCheck' else 0)
        monkeypatch.setattr(repository,'load_check',original)


async def test_proc_c22(h):
    await ready(h);await h.review_all();await h.call('beginCompletion',check_id=h.check_id,expected=200)
    rev=(await h.check())['revision'];keys=[uuid4(),uuid4()]
    results=await asyncio.gather(*(h.call('finalizeCheck',check_id=h.check_id,revision=rev,key=k) for k in keys))
    assert sorted(r.status_code for r in results)==[202,409]
    winner=next(i for i,r in enumerate(results) if r.status_code==202)
    replay=await h.call('finalizeCheck',check_id=h.check_id,revision=rev,key=keys[winner],expected=202)
    assert replay.json()==results[winner].json()
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_snapshots')==1
    snap=json.loads(await h.svc.pool.fetchval('SELECT payload FROM pilot_snapshots'))
    assert not any(x in json.dumps(snap) for x in ['comment','Синтетическая проверка','normalized_path'])
    before=await h.svc.pool.fetchval('SELECT count(*) FROM pilot_jobs')
    for _ in range(10): await h.call('getSummary',check_id=h.check_id,expected=200)
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_jobs')==before


async def test_proc_c24(h,caplog):
    ids,_,_=await ready(h);before=(await h.check())['revision']
    await h.call('getBundleHistory',actor='staff',bundle_id=ids[2],expected=200)
    photo=(await h.check())['notebooks'][0]['bundles'][0]['current_input']['photos'][0]['id']
    await h.call('getPhoto',actor='staff',photo_id=photo,expected=200)
    await h.call('getPhoto',actor='t2',photo_id=photo,expected=404)
    assert (await h.check())['revision']==before
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_audit WHERE role='staff'")>=2
    assert 'synthetic-test-password-47' not in caplog.text
