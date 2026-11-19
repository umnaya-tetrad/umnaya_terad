"""Fenced publication; immutable report rows precede current generation update."""
import json
from uuid import uuid4
from ..domain import repository as r
from ..events.audit import audit
async def publish(con,c,job,payload):
    if not await r.current_job(con,c,job):return False
    if job['kind']=='class_analytics':
        exists=await con.fetchval('SELECT EXISTS(SELECT 1 FROM pilot_analytics_results WHERE job_id=$1)',job['id'])
        if exists:return False
        await con.execute('INSERT INTO pilot_analytics_results(job_id,snapshot_id,result) VALUES($1,$2,$3::jsonb)',job['id'],job['snapshot_id'],json.dumps(payload))
        await r.save_check(con,c)
    else:
        if await con.fetchval('SELECT EXISTS(SELECT 1 FROM pilot_bundle_reports WHERE job_id=$1)',job['id']):return False
        _,b,_=r.find(c,'bundle',job['bundle_id']);report_id=uuid4()
        await con.execute('INSERT INTO pilot_bundle_reports(id,job_id,input_version_id,report) VALUES($1,$2,$3,$4::jsonb)',report_id,job['id'],job['input_version_id'],json.dumps(payload))
        tasks=[]
        for analysis in payload['tasks']:
            task_id,analysis_id=uuid4(),uuid4()
            await con.execute('INSERT INTO pilot_task_analyses(id,task_id,job_id,report_id,analysis) VALUES($1,$2,$3,$4,$5::jsonb)',analysis_id,task_id,job['id'],report_id,json.dumps(analysis))
            tasks.append({'task_id':str(task_id),'analysis_id':str(analysis_id),'analysis':analysis,'review':None,'skipped':False})
        b['tasks']=tasks;b['result']={'id':str(report_id),'input_version_id':str(job['input_version_id']),'report':payload}
        b['job']=r.job_dto({**dict(job),'state':'succeeded','reason':'input_uncheckable' if payload['status']=='uncheckable' else None})
        await r.save_check(con,c,data=True)
    await audit(con,'job_published',check_id=c['id'],entity_id=job['id'],payload={'kind':job['kind']})
    return True
