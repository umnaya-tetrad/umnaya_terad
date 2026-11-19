"""HTTP-only adaptation for the shared application ports."""
import re
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request

from pilot.domain.access import Actor, require_actor
from pilot.domain.errors import DomainError
from pilot.domain.revision import MutationContext

REVISION = re.compile(r'"([0-9]{1,19})"')


def require_origin(request: Request) -> None:
    supplied = request.headers.getlist("origin")
    if len(supplied) != 1 or supplied[0] not in request.app.state.pilot_origins:
        raise DomainError(403, "forbidden", "Недопустимый источник запроса.")


def request_id(request: Request) -> UUID:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, UUID):
        return existing
    value = uuid4()
    request.state.request_id = value
    return value


def _mutation_context(request: Request, actor: Actor, *, require_revision: bool) -> MutationContext:
    require_origin(request)
    keys = request.headers.getlist("idempotency-key")
    revisions = request.headers.getlist("if-match")
    try:
        if len(keys) != 1:
            raise ValueError
        key = UUID(keys[0])
        expected_revision = None
        if require_revision:
            match = REVISION.fullmatch(revisions[0]) if len(revisions) == 1 else None
            if match is None or int(match[1]) > 2**63 - 1:
                raise ValueError
            expected_revision = int(match[1])
    except ValueError:
        raise DomainError(400, "invalid_input", "Проверьте заголовки запроса.") from None
    return MutationContext(
        actor=actor,
        expected_revision=expected_revision,
        idempotency_key=key,
        request_id=request_id(request),
    )


def existing_mutation(request: Request, actor: Annotated[Actor, Depends(require_actor)]) -> MutationContext:
    return _mutation_context(request, actor, require_revision=True)


def new_check_mutation(request: Request, actor: Annotated[Actor, Depends(require_actor)]) -> MutationContext:
    return _mutation_context(request, actor, require_revision=False)
