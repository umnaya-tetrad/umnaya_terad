"""All writes share one parent lock and transaction with intent and outbox."""
import hashlib,json,shutil
from uuid import UUID,uuid4
from . import repository as r
from .access import check_access
from .errors import DomainError,invalid,not_found
from .schema import validate
from .completion import completion,build_snapshot
from .storage import persist_photo,discard_prepared
from ..events.audit import audit

METHODS={'create_check':('POST','checks'),'create_notebook':('POST','checks/{}/notebooks'),'create_bundle':('POST','notebooks/{}/bundles'),'create_input_version':('POST','bundles/{}/versions'),'upload_photo':('POST','input-versions/{}/photos'),'reorder_photos':('PATCH','input-versions/{}'),'discard_draft':('DELETE','input-versions/{}'),'delete_draft_photo':('DELETE','input-versions/{}/photos'),'save_review':('PUT','tasks/{}/review'),'skip_task':('POST','tasks/{}/skip'),'delete_task':('DELETE','tasks/{}'),'delete_bundle':('DELETE','bundles/{}'),'delete_notebook':('DELETE','notebooks/{}'),'delete_check':('DELETE','checks/{}'),'submit_bundle':('POST','bundles/{}/submit'),'retry_bundle':('POST','bundles/{}/retry'),'skip_bundle':('POST','bundles/{}/skip'),'begin_completion':('POST','checks/{}/begin-completion'),'finalize_check':('POST','checks/{}/finalize'),'refresh_summary':('POST','checks/{}/summary/refresh'),'retry_summary':('POST','checks/{}/summary/retry')}

def hash_payload(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()).hexdigest()
async def _intent(con,ctx,method,path,digest):
    row=await con.fetchrow('SELECT payload_hash,body FROM pilot_idempotency WHERE actor_id=$1 AND method=$2 AND path=$3 AND key=$4',ctx.actor.user_id,method,path,ctx.idempotency_key)
    if not row:return None
    if row['payload_hash']!=digest:invalid('Это намерение уже использовано с другими данными.','idempotency_conflict')
    return r.decode(row['body'])
async def _store_intent(con,ctx,method,path,digest,body,status):
    await con.execute('INSERT INTO pilot_idempotency(actor_id,method,path,key,payload_hash,body,status) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7)',ctx.actor.user_id,method,path,ctx.idempotency_key,digest,json.dumps(body),status)
async def _new_job(con,c,kind,*,bundle=None,input_id=None,snapshot_id=None):
    jid=uuid4()
    row=await con.fetchrow('INSERT INTO pilot_jobs(id,check_id,bundle_id,kind,input_version_id,snapshot_id) VALUES($1,$2,$3,$4,$5,$6) RETURNING *',jid,c['id'],r.uuid(bundle['id']) if bundle else None,kind,r.uuid(input_id) if input_id else None,r.uuid(snapshot_id) if snapshot_id else None)
    return r.job_dto(row)
async def _cancel_jobs(con,c,bundle_ids=None,*,reason='deleted'):
    sql="UPDATE pilot_jobs SET state='cancelled',reason=$2,epoch=epoch+1 WHERE check_id=$1 AND state NOT IN ('succeeded','failed','cancelled','superseded')"
    args=[c['id'],reason]
    if bundle_ids is not None:sql+=' AND bundle_id=ANY($3::uuid[])';args.append([r.uuid(x) for x in bundle_ids])
    await con.execute(sql,*args)
    # Cancellation is never proof that a dispatched provider call was free.
    await con.execute("UPDATE pilot_attempts SET state='unknown' WHERE state='started' AND dispatched AND job_id IN (SELECT id FROM pilot_jobs WHERE check_id=$1 AND state='cancelled')",c['id'])
async def _snapshot_job(con,c):
    sid=uuid4();payload=build_snapshot(c,sid)
    await con.execute('INSERT INTO pilot_snapshots(id,check_id,data_revision,payload) VALUES($1,$2,$3,$4::jsonb)',sid,c['id'],c['data_revision'],json.dumps(payload))
    job=await _new_job(con,c,'class_analytics',snapshot_id=sid);c['selected_summary_job_id']=r.uuid(job['id'])
    return job
async def _mutate(svc,ctx,op,kind,entity_id,payload,handler,*,data=False,status=200,allow_final=False):
    method,template=METHODS[op];path='/'+template.format(entity_id)
    digest=hash_payload(payload)
    async with svc.pool.acquire() as con,con.transaction():
        # One idempotency intent is serialized even for create and deleted resources.
        await con.execute('SELECT pg_advisory_xact_lock(hashtext($1))',str(ctx.actor.user_id)+method+path+str(ctx.idempotency_key))
        old=await _intent(con,ctx,method,path,digest)
        if old is not None:return old
        if ctx.actor.role!='teacher':raise DomainError(403,'forbidden','Поддержка может только просматривать.')
        cid=await r.locate_check(con,kind,entity_id)
        c=await r.load_check(con,cid,ctx.actor,lock=True)
        if ctx.expected_revision!=c['revision']:invalid('Проверка изменилась. Обновите данные.','revision_conflict',c['revision'])
        if c['phase']=='finalized' and not allow_final:invalid('Состав проверки уже зафиксирован.',revision=c['revision'])
        await r.synchronize_jobs(con,c)
        result=await handler(con,c)
        entity,job,changed,changed_data=result
        if changed:
            await r.save_check(con,c,data=changed_data if changed_data is not None else data)
            await audit(con,op,actor=ctx.actor,request_id=ctx.request_id,check_id=c['id'],entity_id=entity,payload={'job_id':job['id']} if job else None)
        body={'check_id':str(c['id']),'check_revision':c['revision'],'entity_id':str(entity) if entity else None,'job':job}
        await _store_intent(con,ctx,method,path,digest,body,status)
        return body
async def create_check(svc,ctx,payload):
    validate(payload,'Title');method,path='POST','/checks';digest=hash_payload(payload)
    async with svc.pool.acquire() as con,con.transaction():
        await con.execute('SELECT pg_advisory_xact_lock(hashtext($1))',str(ctx.actor.user_id)+method+path+str(ctx.idempotency_key))
        old=await _intent(con,ctx,method,path,digest)
        if old is not None:return old
        if ctx.actor.role!='teacher':raise DomainError(403,'forbidden','Поддержка может только просматривать.')
        cid=uuid4();await con.execute('INSERT INTO pilot_checks(id,owner_id,title) VALUES($1,$2,$3)',cid,ctx.actor.user_id,payload['title'])
        body={'check_id':str(cid),'check_revision':0,'entity_id':None,'job':None}
        await audit(con,'create_check',actor=ctx.actor,request_id=ctx.request_id,check_id=cid)
        await _store_intent(con,ctx,method,path,digest,body,201)
        return body
async def create_notebook(svc,ctx,check_id):
    async def go(con,c):
        n={'id':r.uid(),'number':c['next_notebook_number'],'bundles':[]};c['next_notebook_number']+=1;c['graph']['notebooks'].append(n)
        await con.execute('INSERT INTO pilot_notebooks(id,check_id,number) VALUES($1,$2,$3)',r.uuid(n['id']),c['id'],n['number'])
        return n['id'],None,True,None
    return await _mutate(svc,ctx,'create_notebook','check',check_id,None,go,data=True,status=201)
async def create_bundle(svc,ctx,notebook_id):
    async def go(con,c):
        n,_,_=r.find(c,'notebook',notebook_id)
        version={'id':r.uid(),'state':'draft','photos':[]};b={'id':r.uid(),'draft':version,'current_input':None,'job':None,'result':None,'tasks':[],'skipped':False};n['bundles'].append(b)
        await con.execute('INSERT INTO pilot_bundles(id,check_id,notebook_id) VALUES($1,$2,$3)',r.uuid(b['id']),c['id'],r.uuid(n['id']))
        await con.execute('INSERT INTO pilot_input_versions(id,bundle_id,state,payload) VALUES($1,$2,$3,$4::jsonb)',r.uuid(version['id']),r.uuid(b['id']),'draft',json.dumps(version))
        return b['id'],None,True,None
    return await _mutate(svc,ctx,'create_bundle','notebook',notebook_id,None,go,status=201)
async def _update_version(con,v):
    await con.execute('UPDATE pilot_input_versions SET payload=$2::jsonb WHERE id=$1',r.uuid(v['id']),json.dumps(v))
async def create_input_version(svc,ctx,bundle_id,payload):
    validate(payload,'VersionCreate')
    async def go(con,c):
        _,b,_=r.find(c,'bundle',bundle_id)
        if b['draft']:invalid('Черновик уже существует.')
        if not b['current_input']:invalid()
        photos={p['id']:p for p in b['current_input']['photos']}
        if len(set(payload['photo_ids']))!=len(payload['photo_ids']) or not set(payload['photo_ids'])<=photos.keys():raise DomainError(422,'invalid_input','Можно выбрать фото только текущего комплекта.')
        v={'id':r.uid(),'state':'draft','photos':[photos[x] for x in payload['photo_ids']]};b['draft']=v
        await con.execute('INSERT INTO pilot_input_versions(id,bundle_id,state,payload) VALUES($1,$2,$3,$4::jsonb)',r.uuid(v['id']),r.uuid(b['id']),'draft',json.dumps(v))
        for pos,p in enumerate(v['photos'],1):await con.execute('INSERT INTO pilot_version_photos VALUES($1,$2,$3)',r.uuid(v['id']),r.uuid(p['id']),pos)
        return v['id'],None,True,None
    return await _mutate(svc,ctx,'create_input_version','bundle',bundle_id,payload,go,status=201)
async def upload_photo(svc,ctx,input_version_id,prepared):
    created=[]
    async def go(con,c):
        _,b,v=r.find(c,'input',input_version_id)
        if v['state']!='draft':invalid('Отправленные фото нельзя изменять.')
        pid=r.uid();original,normalized=persist_photo(svc,prepared,pid);created.append(original.parent)
        await con.execute('INSERT INTO pilot_photo_assets(id,check_id,bundle_id,original_path,normalized_path,media_type,sha256,byte_count,width,height) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',r.uuid(pid),c['id'],r.uuid(b['id']),str(original),str(normalized),prepared.media_type,prepared.sha256,prepared.byte_count,prepared.width,prepared.height)
        v['photos'].append({'id':pid,'media_type':prepared.media_type})
        await con.execute('INSERT INTO pilot_version_photos VALUES($1,$2,$3)',r.uuid(v['id']),r.uuid(pid),len(v['photos']));await _update_version(con,v)
        return pid,None,True,None
    try:return await _mutate(svc,ctx,'upload_photo','input',input_version_id,{'sha256':prepared.sha256,'version':str(input_version_id)},go,status=201)
    except BaseException:
        for folder in created:
            if folder.resolve().is_relative_to(svc.storage_root.resolve()):shutil.rmtree(folder)
        raise
    finally:discard_prepared(prepared)
async def reorder_photos(svc,ctx,input_version_id,payload):
    validate(payload,'PhotoOrder')
    async def go(con,c):
        _,_,v=r.find(c,'input',input_version_id)
        if v['state']!='draft':invalid()
        ids=payload['photo_ids'];old=[p['id'] for p in v['photos']]
        if len(ids)!=len(old) or set(ids)!=set(old):raise DomainError(422,'invalid_input','Нужен полный порядок всех фото.')
        if ids==old:return v['id'],None,False,None
        byid={p['id']:p for p in v['photos']};v['photos']=[byid[x] for x in ids]
        await con.execute('DELETE FROM pilot_version_photos WHERE version_id=$1',r.uuid(v['id']))
        for pos,p in enumerate(v['photos'],1):await con.execute('INSERT INTO pilot_version_photos VALUES($1,$2,$3)',r.uuid(v['id']),r.uuid(p['id']),pos)
        await _update_version(con,v);return v['id'],None,True,None
    return await _mutate(svc,ctx,'reorder_photos','input',input_version_id,payload,go)
async def discard_draft(svc,ctx,input_version_id):
    async def go(con,c):
        _,b,v=r.find(c,'input',input_version_id)
        if v['state']!='draft':invalid()
        b['draft']=None;await con.execute('UPDATE pilot_input_versions SET discarded=true WHERE id=$1',r.uuid(v['id']))
        return v['id'],None,True,None
    return await _mutate(svc,ctx,'discard_draft','input',input_version_id,None,go)
async def delete_draft_photo(svc,ctx,input_version_id,photo_id):
    async def go(con,c):
        _,_,v=r.find(c,'input',input_version_id)
        if v['state']!='draft':invalid()
        if not any(p['id']==str(photo_id) for p in v['photos']):not_found()
        v['photos']=[p for p in v['photos'] if p['id']!=str(photo_id)]
        await con.execute('DELETE FROM pilot_version_photos WHERE version_id=$1',r.uuid(v['id']))
        for pos,p in enumerate(v['photos'],1):await con.execute('INSERT INTO pilot_version_photos VALUES($1,$2,$3)',r.uuid(v['id']),r.uuid(p['id']),pos)
        await _update_version(con,v);return photo_id,None,True,None
    return await _mutate(svc,ctx,'delete_draft_photo','input',input_version_id,{'photo_id':str(photo_id)},go)
async def save_review(svc,ctx,task_id,payload):
    validate(payload,'ReviewWrite')
    async def go(con,c):
        _,_,t=r.find(c,'task',task_id)
        if t['analysis_id']!=payload['analysis_id']:invalid('Разбор уже изменился.','stale_analysis')
        if t['analysis']['result']=='not_assessed':invalid('Для этой задачи доступен пропуск.')
        review={'state':payload['state'],'comment':payload['comment']}
        if t['review']==review:return task_id,None,False,False
        data=not t['review'] or t['review']['state']!=review['state'];t['review']=review
        await con.execute('INSERT INTO pilot_reviews(analysis_id,state,comment) VALUES($1,$2,$3) ON CONFLICT(analysis_id) DO UPDATE SET state=excluded.state,comment=excluded.comment',r.uuid(t['analysis_id']),review['state'],review['comment'])
        return task_id,None,True,data
    return await _mutate(svc,ctx,'save_review','task',task_id,payload,go,allow_final=True)
async def skip_task(svc,ctx,task_id,payload):
    validate(payload,'AnalysisTarget')
    async def go(con,c):
        _,_,t=r.find(c,'task',task_id)
        if t['analysis_id']!=payload['analysis_id']:invalid('Разбор уже изменился.','stale_analysis')
        if t['analysis']['result']!='not_assessed':invalid()
        old=t['skipped'];t['skipped']=True
        await con.execute('UPDATE pilot_task_analyses SET skipped=true WHERE id=$1',r.uuid(t['analysis_id']))
        return task_id,None,not old,True
    return await _mutate(svc,ctx,'skip_task','task',task_id,payload,go,data=True)
async def _delete(svc,ctx,kind,eid):
    async def go(con,c):
        if kind=='check':c['deleted']=True;await _cancel_jobs(con,c);return None,None,True,True
        n,b,item=r.find(c,kind,eid)
        if kind=='task':
            b['tasks'].remove(item);await con.execute('UPDATE pilot_task_analyses SET deleted=true WHERE task_id=$1',r.uuid(eid))
        elif kind=='bundle':
            n['bundles'].remove(b);await con.execute('UPDATE pilot_bundles SET deleted=true WHERE id=$1',r.uuid(eid));await _cancel_jobs(con,c,[eid])
        else:
            c['graph']['notebooks'].remove(n);await con.execute('UPDATE pilot_notebooks SET deleted=true WHERE id=$1',r.uuid(eid));await con.execute('UPDATE pilot_bundles SET deleted=true WHERE notebook_id=$1',r.uuid(eid));await _cancel_jobs(con,c,[x['id'] for x in n['bundles']])
        return eid,None,True,True
    return await _mutate(svc,ctx,'delete_'+kind,kind,eid,None,go,data=True,allow_final=kind=='check')
async def delete_check(svc,ctx,check_id):return await _delete(svc,ctx,'check',check_id)
async def delete_notebook(svc,ctx,notebook_id):return await _delete(svc,ctx,'notebook',notebook_id)
async def delete_bundle(svc,ctx,bundle_id):return await _delete(svc,ctx,'bundle',bundle_id)
async def delete_task(svc,ctx,task_id):return await _delete(svc,ctx,'task',task_id)
async def submit_bundle(svc,ctx,bundle_id,payload):
    validate(payload,'Submit')
    async def go(con,c):
        _,b,_=r.find(c,'bundle',bundle_id);v=b['draft']
        if not v or v['id']!=payload['input_version_id'] or not v['photos']:invalid('Нужен непустой актуальный черновик.')
        await _cancel_jobs(con,c,[b['id']],reason='replaced')
        v['state']='sealed';await con.execute("UPDATE pilot_input_versions SET payload=$2::jsonb,state='sealed' WHERE id=$1",r.uuid(v['id']),json.dumps(v))
        b.update(draft=None,current_input=v,job=None,result=None,tasks=[],skipped=False)
        job=await _new_job(con,c,'page_check',bundle=b,input_id=v['id']);b['job']=job
        return b['id'],job,True,True
    return await _mutate(svc,ctx,'submit_bundle','bundle',bundle_id,payload,go,data=True,status=202)
async def retry_bundle(svc,ctx,bundle_id,payload):
    validate(payload,'InputTarget')
    async def go(con,c):
        _,b,_=r.find(c,'bundle',bundle_id)
        if not b['current_input'] or b['current_input']['id']!=payload['input_version_id']:invalid('Вход уже изменился.')
        if not b['job'] or not b['job']['can_retry']:invalid('Повтор сейчас недоступен.')
        b.update(result=None,tasks=[],skipped=False)
        job=await _new_job(con,c,'page_check',bundle=b,input_id=b['current_input']['id']);b['job']=job
        return b['id'],job,True,True
    return await _mutate(svc,ctx,'retry_bundle','bundle',bundle_id,payload,go,data=True,status=202)
async def skip_bundle(svc,ctx,bundle_id,payload):
    validate(payload,'InputTarget')
    async def go(con,c):
        _,b,_=r.find(c,'bundle',bundle_id)
        if not b['current_input'] or b['current_input']['id']!=payload['input_version_id']:invalid()
        if b['skipped']:return b['id'],b['job'],False,False
        j=b['job'];res=b['result']
        if j['state'] not in ('failed','blocked','unknown') and not(j['state']=='succeeded' and res and (res['report']['status']=='uncheckable' or not res['report']['tasks'])):invalid()
        b['skipped']=True
        if j['state'] in ('blocked','unknown'):
            await _cancel_jobs(con,c,[b['id']],reason='skipped');j.update(state='cancelled',reason='skipped',can_retry=False)
        return b['id'],j,True,True
    return await _mutate(svc,ctx,'skip_bundle','bundle',bundle_id,payload,go,data=True)
async def begin_completion(svc,ctx,check_id):
    async def go(con,c):
        if c['phase']=='review':return None,None,False,False
        c['phase']='review';return None,None,True,False
    return await _mutate(svc,ctx,'begin_completion','check',check_id,None,go)
async def finalize_check(svc,ctx,check_id):
    async def go(con,c):
        if not completion(c)['can_finalize']:invalid('Сначала завершите просмотр всех результатов.','completion_blocked')
        c['phase']='finalized';job=await _snapshot_job(con,c)
        return None,job,True,False
    return await _mutate(svc,ctx,'finalize_check','check',check_id,None,go,status=202)
async def refresh_summary(svc,ctx,check_id):
    async def go(con,c):
        from .queries import _summary
        summary=await _summary(con,c)
        if not summary['can_refresh']:invalid('Обновление сводки сейчас недоступно.')
        old=r.uuid(summary['job_id'])
        await con.execute("UPDATE pilot_jobs SET state='superseded',reason='replaced',epoch=epoch+1 WHERE id=$1 AND state IN ('queued','blocked')",old)
        job=await _snapshot_job(con,c);return None,job,True,False
    return await _mutate(svc,ctx,'refresh_summary','check',check_id,None,go,status=202,allow_final=True)
async def retry_summary(svc,ctx,check_id):
    async def go(con,c):
        from .queries import _summary
        summary=await _summary(con,c)
        if not summary['can_retry']:invalid('Повтор сводки сейчас недоступен.')
        job=await _new_job(con,c,'class_analytics',snapshot_id=summary['snapshot_id']);c['selected_summary_job_id']=r.uuid(job['id']);return None,job,True,False
    return await _mutate(svc,ctx,'retry_summary','check',check_id,None,go,status=202,allow_final=True)
