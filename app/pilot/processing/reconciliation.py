from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
import json
from .funds import finite_amount, evidence_dict, digest, settle
from ..domain import repository as r
from ..domain.errors import DomainError, invalid, not_found
from ..events.audit import audit


@dataclass(frozen=True)
class ReconciliationEvidence:
    reference: str
    sha256: str
    actual_cost_rub: Decimal | None = None
    provider_request_id: str | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    attempt_id: UUID
    state: str
    held_rub: Decimal
    changed: bool


async def reconcile_attempt(
    svc, *, attempt_id, outcome, evidence, operator_ref, request_id
):
    ev = evidence_dict(evidence)
    if outcome not in ("rejected", "settled") or not operator_ref:
        raise DomainError(422, "invalid_input", "Недопустимая сверка.")
    if outcome == "settled" and ev.get("actual_cost_rub") is None:
        raise DomainError(422, "invalid_input", "Нужна подтвержденная стоимость.")
    amount = finite_amount(ev.get("actual_cost_rub") or 0)
    if outcome == "rejected" and amount != 0:
        raise DomainError(
            422, "invalid_input", "Отказ должен подтверждать отсутствие списания."
        )
    ev["outcome"] = outcome
    hashed = digest(ev)
    async with svc.pool.acquire() as con, con.transaction():
        info = await con.fetchrow(
            "SELECT j.* FROM pilot_jobs j JOIN pilot_attempts a ON a.job_id=j.id WHERE a.id=$1",
            r.uuid(attempt_id),
        )
        if not info:
            not_found()
        c = await r.load_check(con, info["check_id"], lock=True, include_deleted=True)
        await con.fetchrow(
            "SELECT id FROM pilot_jobs WHERE id=$1 FOR UPDATE", info["id"]
        )
        a = await con.fetchrow(
            "SELECT * FROM pilot_attempts WHERE id=$1 FOR UPDATE", r.uuid(attempt_id)
        )
        stored = r.decode(a["evidence"]) if a["evidence"] else None
        if stored and stored.get("reconciliation_hash"):
            if stored["reconciliation_hash"] != hashed:
                invalid("Попытка уже сверена иначе.")
            changed = False
        else:
            if a["state"] != "unknown":
                invalid("Сверка разрешена для неизвестного исхода.")
            changed = await settle(
                con,
                a["id"],
                amount,
                request_id=request_id,
                evidence=ev,
                rejected=outcome == "rejected",
            )
            await con.execute(
                "UPDATE pilot_slots SET attempt_id=NULL,job_id=NULL,epoch=NULL WHERE attempt_id=$1",
                a["id"],
            )
            await con.execute(
                "UPDATE pilot_attempts SET evidence=$2::jsonb,provider_request_id=COALESCE($3,provider_request_id) WHERE id=$1",
                a["id"],
                json.dumps({"reconciliation_hash": hashed, **ev}),
                ev.get("provider_request_id"),
            )
            if info["state"] == "unknown" and await r.current_job(con, c, info):
                # A known rejected/charged attempt ends safely. A new request is explicit.
                await con.execute(
                    "UPDATE pilot_jobs SET state='failed',reason='provider_rejected' WHERE id=$1",
                    info["id"],
                )
                await r.save_check(con, c)
            await audit(
                con,
                "attempt_reconciled",
                request_id=request_id,
                check_id=c["id"],
                entity_id=a["id"],
                payload={"operator_ref": operator_ref, "outcome": outcome},
            )
        a = await con.fetchrow(
            "SELECT * FROM pilot_attempts WHERE id=$1", r.uuid(attempt_id)
        )
        held = await con.fetchval(
            "SELECT CASE WHEN active THEN amount_rub ELSE 0 END FROM pilot_fund_reservations WHERE attempt_id=$1",
            a["id"],
        )
        return ReconciliationResult(a["id"], a["state"], held or Decimal(0), changed)
