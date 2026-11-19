"""Fenced execution, separately retained billing uncertainty and late evidence."""

from datetime import timedelta
import json
from jsonschema import ValidationError
from ..domain import repository as r
from ..events.audit import audit
from .funds import settle, observe_unknown_cost
from .queue import _job_lock, now
from .publish import publish
from .diagnostics import safe_diagnostics


async def _late_history(con, c, job, result):
    if (
        c["deleted"]
        or job["kind"] != "class_analytics"
        or str(c["selected_summary_job_id"]) == str(job["id"])
        or result.outcome != "success"
    ):
        return
    from ..analytics.validation import validate_pair

    snapshot = r.decode(
        await con.fetchval(
            "SELECT payload FROM pilot_snapshots WHERE id=$1", job["snapshot_id"]
        )
    )
    try:
        validate_pair(snapshot, result.payload)
    except (ValidationError, ValueError, KeyError, TypeError):
        return
    await con.execute(
        "INSERT INTO pilot_analytics_results(job_id,snapshot_id,result) VALUES($1,$2,$3::jsonb) ON CONFLICT(job_id) DO NOTHING",
        job["id"],
        job["snapshot_id"],
        json.dumps(result.payload),
    )


async def complete(svc, claim, result):
    old = claim["job"]
    aid = claim["attempt_id"]
    async with svc.pool.acquire() as con, con.transaction():
        c = await r.load_check(con, old["check_id"], lock=True, include_deleted=True)
        job = await _job_lock(con, old)
        a = await con.fetchrow(
            "SELECT * FROM pilot_attempts WHERE id=$1 FOR UPDATE", aid
        )
        diagnostics = safe_diagnostics(result)
        await con.execute(
            "UPDATE pilot_attempts SET provider_request_id=$2,raw_response=$3,ended_at=$4,diagnostics=$5::jsonb WHERE id=$1",
            aid,
            result.provider_request_id,
            result.raw_envelope or result.raw,
            now(svc),
            json.dumps(diagnostics),
        )
        outcome = result.outcome
        fenced = (
            job["epoch"] == old["epoch"]
            and job["state"] == "running"
            and await r.current_job(con, c, job)
        )
        if not fenced or outcome == "unknown":
            if diagnostics["actual_cost_rub"] is not None:
                await observe_unknown_cost(con, aid, diagnostics["actual_cost_rub"])
        if not fenced:
            await _late_history(con, c, job, result)
            if a["state"] not in ("settled", "rejected"):
                await con.execute(
                    "UPDATE pilot_attempts SET state='unknown',billing_state='unknown' WHERE id=$1",
                    aid,
                )
            await audit(
                con,
                "late_attempt_evidence",
                check_id=c["id"],
                entity_id=aid,
                payload={"cost_observed": diagnostics["actual_cost_rub"] is not None},
            )
            return False
        if outcome == "unknown":
            await con.execute(
                "UPDATE pilot_attempts SET state='unknown',billing_state='unknown' WHERE id=$1",
                aid,
            )
        else:
            # A valid response with missing cost remains useful. Its execution
            # finishes, its slot is free, and its billing reserve is retained.
            await settle(
                con,
                aid,
                result.actual_cost_rub,
                rejected=outcome in ("temporary_failure", "rejected"),
                mode=svc.mode,
            )
            await con.execute(
                "UPDATE pilot_slots SET attempt_id=NULL,job_id=NULL,epoch=NULL WHERE attempt_id=$1",
                aid,
            )
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
            payload={
                "outcome": outcome,
                "billing_known": result.actual_cost_rub is not None,
            },
        )
        return True
