"""Closed, read-only staff routes. Mutations are intentionally absent."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from pilot.contracts import StaffCheck, StaffChecks
from pilot.domain.access import Actor, get_services, require_actor, require_staff
from pilot.domain.services import Services
from pilot.services import staff
from pilot.services.application import request_id

router = APIRouter(prefix="/staff")
Service = Annotated[Services, Depends(get_services)]


def staff_actor(actor: Annotated[Actor, Depends(require_actor)]) -> Actor:
    """Defense in depth: the release surface refuses a teacher before any query."""
    require_staff(actor)
    return actor


CurrentActor = Annotated[Actor, Depends(staff_actor)]


@router.get("/checks", operation_id="listStaffChecks")
async def list_staff_checks(
    request: Request,
    svc: Service,
    actor: CurrentActor,
    owner_login: str | None = Query(default=None, min_length=1, max_length=128),
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> StaffChecks:
    return await staff.list_checks(
        svc,
        actor,
        owner_login=owner_login.strip() if owner_login else None,
        cursor=cursor,
        limit=limit,
        request_id=request_id(request),
    )


@router.get("/checks/{check_id}", operation_id="getStaffCheck")
async def get_staff_check(
    check_id: UUID, request: Request, response: Response, svc: Service, actor: CurrentActor
) -> StaffCheck:
    check = await staff.get_check(svc, actor, check_id, request_id=request_id(request))
    response.headers["ETag"] = f'"{check["check"]["revision"]}"'
    response.headers["Cache-Control"] = "private, no-store"
    return check
