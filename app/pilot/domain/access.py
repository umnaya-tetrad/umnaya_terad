from dataclasses import dataclass
from uuid import UUID
from fastapi import Request
from .errors import DomainError


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    role: str


def get_services(request: Request):
    return request.app.state.pilot_services


async def require_actor(request: Request):
    from .auth import actor_for_token

    actor = await actor_for_token(
        get_services(request), request.cookies.get("smartnote_session")
    )
    if actor is None:
        raise DomainError(401, "unauthenticated", "Войдите в аккаунт.")
    return actor


def require_staff(actor):
    if actor.role != "staff":
        raise DomainError(403, "forbidden", "Доступ только для поддержки.")


def check_access(record, actor, *, staff=False):
    from .errors import not_found

    if record is None or record["deleted"]:
        not_found()
    if staff and actor.role == "staff":
        return
    if actor.role != "teacher" or str(record["owner_id"]) != str(actor.user_id):
        not_found()
