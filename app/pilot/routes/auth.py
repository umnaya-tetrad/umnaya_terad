from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from auth import SESSION_COOKIE_NAME
from pilot.contracts import Session
from pilot.domain import auth
from pilot.domain.access import Actor, get_services, require_actor
from pilot.domain.services import Services
from pilot.services.application import require_origin
from pilot.services.payloads import LoginBody

router = APIRouter(prefix="/auth")
Service = Annotated[Services, Depends(get_services)]


def secure_cookie(request: Request) -> bool:
    return request.url.scheme == "https" or request.app.state.pilot_settings.visitor_cookie_secure


@router.post("/login", operation_id="login", dependencies=[Depends(require_origin)])
async def login(payload: LoginBody, request: Request, response: Response, svc: Service) -> Session:
    grant = await auth.authenticate(svc, payload["login"], payload["password"])
    response.set_cookie(
        SESSION_COOKIE_NAME,
        grant.token,
        httponly=True,
        samesite="lax",
        secure=secure_cookie(request),
        max_age=request.app.state.pilot_settings.auth_session_days * 86_400,
    )
    response.headers["Cache-Control"] = "no-store"
    return grant.session


@router.get("/session", operation_id="getSession")
async def session(response: Response, actor: Annotated[Actor, Depends(require_actor)]) -> Session:
    response.headers["Cache-Control"] = "no-store"
    return {"user_id": str(actor.user_id), "role": actor.role}


@router.post("/logout", operation_id="logout", status_code=204, dependencies=[Depends(require_origin)])
async def logout(request: Request, svc: Service) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await auth.revoke(svc, token)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(SESSION_COOKIE_NAME, httponly=True, secure=secure_cookie(request), samesite="lax")
    return response
