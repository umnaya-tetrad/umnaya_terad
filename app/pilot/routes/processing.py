"""Processing-owned routes, mounted once by application with /api prefix."""
from uuid import UUID,uuid4
from fastapi import APIRouter,Request,Depends
from fastapi.responses import JSONResponse
from ..domain.access import require_actor,get_services
from ..domain.revision import context_for_request,verify_origin
from ..domain import mutations,queries
from ..domain.errors import DomainError
from ..domain.schema import validate
router=APIRouter()

def _id(request,name):
    try:return UUID(request.path_params[name])
    except (ValueError,KeyError):raise DomainError(422,'invalid_input','Недопустимый идентификатор.')

def _register(path,operation_id,method,argument,*,body=False,status=200):
    async def endpoint(request:Request,actor=Depends(require_actor)):
        svc=get_services(request);verify_origin(request,svc);ctx=context_for_request(request,actor)
        args=[svc,ctx,_id(request,argument)]
        if body:
            try:args.append(await request.json())
            except Exception:raise DomainError(422,'invalid_input','Нужен корректный JSON.')
        else:
            if await request.body():raise DomainError(422,'invalid_input','Тело запроса не требуется.')
        result=await getattr(mutations,method)(*args);validate(result,'Mutation')
        return JSONResponse(result,status_code=status)
    router.add_api_route(path,endpoint,methods=['POST'],operation_id=operation_id,name=operation_id)
for spec in [
    ('/bundles/{bundle_id}/submit','submitBundle','submit_bundle','bundle_id',True,202),
    ('/bundles/{bundle_id}/retry','retryBundle','retry_bundle','bundle_id',True,202),
    ('/bundles/{bundle_id}/skip','skipBundle','skip_bundle','bundle_id',True,200),
    ('/tasks/{task_id}/skip','skipTask','skip_task','task_id',True,200),
    ('/checks/{check_id}/begin-completion','beginCompletion','begin_completion','check_id',False,200),
    ('/checks/{check_id}/finalize','finalizeCheck','finalize_check','check_id',False,202),
    ('/checks/{check_id}/summary/refresh','refreshSummary','refresh_summary','check_id',False,202),
    ('/checks/{check_id}/summary/retry','retrySummary','retry_summary','check_id',False,202),
]:_register(*spec[:4],body=spec[4],status=spec[5])
@router.get('/jobs/{job_id}',operation_id='getJob')
async def get_job(request:Request,actor=Depends(require_actor)):
    result=await queries.get_job(get_services(request),actor,_id(request,'job_id'),request_id=uuid4());return validate(result,'Job')
@router.get('/checks/{check_id}/summary',operation_id='getSummary')
async def get_summary(request:Request,actor=Depends(require_actor)):
    result=await queries.get_summary(get_services(request),actor,_id(request,'check_id'),request_id=uuid4());return validate(result,'Summary')
@router.get('/checks/{check_id}/summary/history',operation_id='getSummaryHistory')
async def get_summary_history(request:Request,actor=Depends(require_actor)):
    result=await queries.get_summary_history(get_services(request),actor,_id(request,'check_id'),request_id=uuid4());return validate(result,'SummaryHistory')
