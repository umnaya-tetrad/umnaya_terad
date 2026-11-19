"""Read-only staff orchestration over the shared processing domain ports.

Every function simply forwards to ``pilot.domain.queries`` with the same actor,
rewriting the transport-only ``request_id``. No SQL, no mutation and no second
access check lives here: the domain already enforces ``staff`` role, hides
foreign resources and writes the audit record.
"""
from __future__ import annotations

from uuid import UUID

from pilot.domain import queries
from pilot.domain.access import Actor
from pilot.domain.services import Services


async def list_checks(
    svc: Services,
    actor: Actor,
    *,
    owner_login: str | None,
    cursor: str | None,
    limit: int,
    request_id: UUID,
) -> dict:
    return await queries.list_staff_checks(
        svc,
        actor,
        owner_login=owner_login,
        cursor=cursor,
        limit=limit,
        request_id=request_id,
    )


async def get_check(svc: Services, actor: Actor, check_id: UUID, *, request_id: UUID) -> dict:
    return await queries.get_staff_check(svc, actor, check_id, request_id=request_id)


async def get_bundle_history(svc: Services, actor: Actor, bundle_id: UUID, *, request_id: UUID) -> dict:
    return await queries.get_bundle_history(svc, actor, bundle_id, request_id=request_id)


async def get_summary_history(svc: Services, actor: Actor, check_id: UUID, *, request_id: UUID) -> dict:
    return await queries.get_summary_history(svc, actor, check_id, request_id=request_id)
