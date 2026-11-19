"""Manual operational pause is independent of cumulative money accounting."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from ..events.audit import audit
from ..domain.errors import DomainError


@dataclass(frozen=True)
class ControlState:
    paused: bool
    available_rub: Decimal
    held_rub: Decimal
    unknown_attempt_ids: tuple[UUID, ...]


async def get_processing_control(svc):
    async with svc.pool.acquire() as con, con.transaction(
        isolation="repeatable_read", readonly=True
    ):
        w = await con.fetchrow(
            "SELECT * FROM pilot_processing_budget WHERE mode=$1", svc.mode
        )
        ids = await con.fetch(
            "SELECT id FROM pilot_attempts WHERE transport_mode=$1 AND (state='unknown' OR billing_state='unknown') ORDER BY id",
            svc.mode,
        )
        return ControlState(
            w["paused"],
            max(w["spend_limit_rub"] - w["spent_rub"] - w["held_rub"], Decimal(0)),
            w["held_rub"],
            tuple(x["id"] for x in ids),
        )


async def set_processing_paused(svc, *, paused, operator_ref, reason, request_id):
    if type(paused) is not bool or not operator_ref or not reason:
        raise DomainError(422, "invalid_input", "Нужны оператор и причина.")
    async with svc.pool.acquire() as con, con.transaction():
        row = await con.fetchrow(
            "SELECT paused FROM pilot_processing_budget WHERE mode=$1 FOR UPDATE",
            svc.mode,
        )
        if row["paused"] != paused:
            await con.execute(
                "UPDATE pilot_processing_budget SET paused=$2 WHERE mode=$1",
                svc.mode,
                paused,
            )
            await audit(
                con,
                "processing_paused" if paused else "processing_resumed",
                request_id=request_id,
                payload={"operator_ref": operator_ref, "mode": svc.mode},
            )
    return await get_processing_control(svc)
