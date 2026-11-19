"""Attempt financial evidence survives stale/deleted publication guards."""

from datetime import timedelta
import json
from ..domain import repository as r
from ..events.audit import audit
from .funds import settle, finite_amount
from .queue import _job_lock, now
from .publish import publish


async def complete(svc, claim, result):
    old = claim["job"]
    aid = claim["attempt_id"]
    async with svc.pool.acquire() as con, con.transaction():
        c = await r.load_check(con, old["check_id"], lock=True, include_deleted=True)
        job = await _job_lock(con, old)
        a = await con.fetchrow(
            "SELECT * FROM pilot_attempts WHERE id=$1 FOR UPDATE", aid
        )
        if a["state"] in ("settled", "rejected"):
            return False
        await con.execute(
            "UPDATE pilot_attempts SET provider_request_id=$2,raw_response=$3 WHERE id=$1",
            aid,
            result.provider_request_id,
            result.raw_envelope or result.raw,
        )
        outcome = result.outcome
        amount = result.actual_cost_rub
        known = amount is not None
        if known:
            amount = finite_amount(amount)
            await settle(
                con,
                aid,
                amount,
                rejected=outcome in ("temporary_failure", "rejected") and amount == 0,
            )
            await con.execute(
                "UPDATE pilot_slots SET attempt_id=NULL,job_id=NULL,epoch=NULL WHERE attempt_id=$1",
                aid,
            )
        else:
            await con.execute(
                "UPDATE pilot_attempts SET state='unknown' WHERE id=$1", aid
            )
            outcome = "unknown"
        fenced = (
            job["epoch"] == old["epoch"]
            and job["state"] == "running"
            and await r.current_job(con, c, job)
        )
        if not fenced:
            await audit(
                con,
                "late_attempt_evidence",
                check_id=c["id"],
                entity_id=aid,
                payload={"known_cost": known},
            )
            return False
        if outcome == "success":
            reason = (
                "input_uncheckable"
                if job["kind"] == "page_check"
                and result.payload["status"] == "uncheckable"
                else None
            )
            await con.execute(
                "UPDATE pilot_jobs SET state='succeeded',reason=$2 WHERE id=$1",
                job["id"],
                reason,
            )
            await publish(con, c, job, result.payload)
        elif outcome == "temporary_failure" and job["auto_retry_count"] == 0:
            await con.execute(
                "UPDATE pilot_jobs SET state='retry_wait',reason='temporary_failure',auto_retry_count=1,next_run_at=$2 WHERE id=$1",
                job["id"],
                now(svc) + timedelta(seconds=1),
            )
            await r.save_check(con, c)
        else:
            state = "unknown" if outcome == "unknown" else "failed"
            reason = {
                "unknown": "provider_outcome_unknown",
                "temporary_failure": "temporary_failure",
                "rejected": "provider_rejected",
                "invalid_response": "invalid_response",
            }.get(outcome, "invalid_response")
            await con.execute(
                "UPDATE pilot_jobs SET state=$2,reason=$3 WHERE id=$1",
                job["id"],
                state,
                reason,
            )
            await r.save_check(con, c)
        await audit(
            con,
            "attempt_completed",
            check_id=c["id"],
            entity_id=aid,
            payload={"outcome": outcome},
        )
        return True
