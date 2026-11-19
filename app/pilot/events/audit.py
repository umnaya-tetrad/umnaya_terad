"""Safe audit facts and transactional outbox. Never accepts domain text."""
import json
from uuid import uuid4,UUID
async def audit(con,name,*,actor=None,request_id=None,check_id=None,entity_id=None,payload=None):
    eid=uuid4();rid=request_id or uuid4()
    cid=UUID(str(check_id)) if check_id else None;entity=UUID(str(entity_id)) if entity_id else None
    await con.execute('INSERT INTO pilot_audit(id,actor_id,role,request_id,name,check_id,entity_id,payload) VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb)',eid,actor.user_id if actor else None,actor.role if actor else 'system',rid,name,cid,entity,json.dumps(payload or {}))
    await con.execute('INSERT INTO pilot_outbox(id,event_name,check_id,entity_id,payload) VALUES($1,$2,$3,$4,$5::jsonb)',eid,name,cid,entity,json.dumps({'request_id':str(rid),'actor_id':str(actor.user_id) if actor else None,'role':actor.role if actor else 'system',**(payload or {})}))
