from uuid import uuid4
from fastapi import APIRouter,Request,Depends
from ..domain.access import get_services,require_actor
from ..domain.revision import verify_origin
from ..domain.errors import DomainError
from ..events.receiver import ingest_events
router=APIRouter()
@router.post('/events',status_code=202,operation_id='ingestEvents')
async def events(request:Request,actor=Depends(require_actor)):
    svc=get_services(request);verify_origin(request,svc)
    try:payload=await request.json()
    except Exception:raise DomainError(422,'invalid_input','Нужен корректный JSON.')
    return await ingest_events(svc,actor,payload,request_id=uuid4())
