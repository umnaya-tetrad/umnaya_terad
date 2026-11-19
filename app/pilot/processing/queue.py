"""Durable PostgreSQL queue. Lock order: Check, Bundle, Job, Attempt, wallet, slot."""

from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import json
from ..domain import repository as r
from ..events.audit import audit
from .providers import bound_for_request
from .funds import reserve

LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 10
HEALTH_STALE_SECONDS = 30
GLOBAL_SLOTS = 2


def now(svc):
    return svc.clock() if svc.clock else datetime.now(timezone.utc)


async def input_payload(con, job):
    if job["kind"] == "class_analytics":
        return r.decode(
            await con.fetchval(
                "SELECT payload FROM pilot_snapshots WHERE id=$1", job["snapshot_id"]
            )
        )
    rows = await con.fetch(
        "SELECT a.normalized_path FROM pilot_version_photos p JOIN pilot_photo_assets a ON p.photo_id=a.id WHERE p.version_id=$1 ORDER BY p.position",
        job["input_version_id"],
    )
    return {"images": [Path(x["normalized_path"]) for x in rows]}


async def _job_lock(con, job):
    if job["bundle_id"]:
        await con.fetchrow(
            "SELECT id FROM pilot_bundles WHERE id=$1 FOR UPDATE", job["bundle_id"]
        )
    return await con.fetchrow(
        "SELECT * FROM pilot_jobs WHERE id=$1 FOR UPDATE SKIP LOCKED", job["id"]
    )


async def claim(svc, worker_id):
    # Page through all eligible work: stale or expensive blocked jobs must not
    # monopolize the first bounded chunk and starve another teacher/kind.
    after = None
    while True:
        candidates = await svc.pool.fetch(
            "SELECT j.* FROM pilot_jobs j JOIN pilot_checks c ON c.id=j.check_id "
            "LEFT JOIN pilot_snapshots s ON s.id=j.snapshot_id "
            "WHERE j.state IN ('queued','blocked','retry_wait') AND j.next_run_at<=$1 "
            "AND (j.kind='page_check' OR (c.selected_summary_job_id=j.id AND s.data_revision=c.data_revision)) "
            "AND ($2::timestamptz IS NULL OR (j.next_run_at,j.created_at,j.id)>($2,$3,$4)) "
            "ORDER BY j.next_run_at,j.created_at,j.id LIMIT 100",
            now(svc),
            after[0] if after else None,
            after[1] if after else None,
            after[2] if after else None,
        )
        if not candidates:
            return None
        for candidate in candidates:
            item = await _claim_candidate(svc, worker_id, candidate)
            if item is not None:
                return item
        last = candidates[-1]
        after = (last["next_run_at"], last["created_at"], last["id"])


async def _claim_candidate(svc, worker_id, candidate):
    async with svc.pool.acquire() as con, con.transaction():
        row = await con.fetchrow(
            "SELECT * FROM pilot_checks WHERE id=$1 FOR UPDATE SKIP LOCKED",
            candidate["check_id"],
        )
        if not row:
            return None
        c = r.record_check(row)
        job = await _job_lock(con, candidate)
        if (
            not job
            or job["state"] not in ("queued", "blocked", "retry_wait")
            or job["next_run_at"] > now(svc)
        ):
            return None
        if not await r.current_job(con, c, job):
            await con.execute(
                "UPDATE pilot_jobs SET state='cancelled',reason='deleted',epoch=epoch+1 WHERE id=$1",
                job["id"],
            )
            return None
        if job["kind"] == "class_analytics":
            revision = await con.fetchval(
                "SELECT data_revision FROM pilot_snapshots WHERE id=$1",
                job["snapshot_id"],
            )
            if revision != c["data_revision"]:
                return None
        payload = await input_payload(con, job)
        bound = bound_for_request(svc, dict(job), payload)
        wallet = await con.fetchrow(
            "SELECT * FROM pilot_processing_budget WHERE mode=$1 FOR UPDATE", svc.mode
        )
        reason = "service_paused" if wallet["paused"] else "funds_unavailable"
        funded = (
            bound is not None
            and not wallet["paused"]
            and wallet["spend_limit_rub"] - wallet["spent_rub"] - wallet["held_rub"]
            >= bound
        )
        if not funded:
            if job["state"] != "blocked" or job["reason"] != reason:
                await con.execute(
                    "UPDATE pilot_jobs SET state='blocked',reason=$2 WHERE id=$1",
                    job["id"],
                    reason,
                )
                await r.save_check(con, c)
                await audit(
                    con,
                    "job_blocked",
                    check_id=c["id"],
                    entity_id=job["id"],
                    payload={"reason": reason},
                )
            return None
        slot = await con.fetchrow(
            "SELECT id FROM pilot_slots WHERE attempt_id IS NULL ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
        )
        if not slot:
            return None
        ordinal = await con.fetchval(
            "SELECT COALESCE(max(ordinal),0)+1 FROM pilot_attempts WHERE job_id=$1",
            job["id"],
        )
        aid = uuid4()
        epoch = job["epoch"] + 1
        await con.execute(
            "INSERT INTO pilot_attempts(id,job_id,ordinal,epoch,state,dispatched,transport_mode) VALUES($1,$2,$3,$4,'started',true,$5)",
            aid,
            job["id"],
            ordinal,
            epoch,
            svc.mode,
        )
        await reserve(con, svc, aid, bound, wallet)
        await con.execute(
            "UPDATE pilot_slots SET attempt_id=$2,job_id=$3,epoch=$4 WHERE id=$1",
            slot["id"],
            aid,
            job["id"],
            epoch,
        )
        await con.execute(
            "UPDATE pilot_jobs SET state='running',reason=NULL,epoch=$2,worker_id=$3,lease_until=$4 WHERE id=$1",
            job["id"],
            epoch,
            worker_id,
            now(svc) + timedelta(seconds=LEASE_SECONDS),
        )
        await r.save_check(con, c)
        await audit(
            con,
            "attempt_dispatch",
            check_id=c["id"],
            entity_id=aid,
            payload={"job_id": str(job["id"]), "epoch": epoch},
        )
        return {
            "job": {
                **dict(job),
                "epoch": epoch,
                "state": "running",
                "worker_id": worker_id,
            },
            "attempt_id": aid,
            "payload": payload,
        }
    return None


async def renew(svc, job, worker_id):
    # Lease heartbeat does not change the public revision; the dispatch epoch is fenced.
    status = await svc.pool.execute(
        "UPDATE pilot_jobs SET lease_until=$4 WHERE id=$1 AND epoch=$2 AND worker_id=$3 AND state='running'",
        job["id"],
        job["epoch"],
        worker_id,
        now(svc) + timedelta(seconds=LEASE_SECONDS),
    )
    return status == "UPDATE 1"


async def recover_expired(svc):
    jobs = await svc.pool.fetch(
        "SELECT * FROM pilot_jobs WHERE lease_until<$1 AND state='running'", now(svc)
    )
    for old in jobs:
        async with svc.pool.acquire() as con, con.transaction():
            c = await r.load_check(
                con, old["check_id"], lock=True, include_deleted=True
            )
            job = await _job_lock(con, old)
            if not job or job["state"] != "running" or job["lease_until"] >= now(svc):
                continue
            a = await con.fetchrow(
                "SELECT * FROM pilot_attempts WHERE job_id=$1 AND epoch=$2 FOR UPDATE",
                job["id"],
                job["epoch"],
            )
            if not a:
                continue
            if a["dispatched"]:
                await con.execute(
                    "UPDATE pilot_attempts SET state='unknown',billing_state='unknown',ended_at=$2,diagnostics=$3::jsonb WHERE id=$1",
                    a["id"],
                    now(svc),
                    json.dumps(
                        {
                            "outcome": "unknown",
                            "error_code": "lease_expired",
                            "usage": {},
                            "http_status": None,
                            "elapsed_seconds": None,
                            "finish_reason": None,
                            "actual_cost_rub": None,
                        }
                    ),
                )
                await con.execute(
                    "UPDATE pilot_jobs SET state='unknown',reason='provider_outcome_unknown',epoch=epoch+1 WHERE id=$1",
                    job["id"],
                )
            else:
                from .funds import settle

                await settle(con, a["id"], 0, rejected=True)
                await con.execute(
                    "UPDATE pilot_jobs SET state='queued',reason=NULL,epoch=epoch+1 WHERE id=$1",
                    job["id"],
                )
                await con.execute(
                    "UPDATE pilot_slots SET attempt_id=NULL,job_id=NULL,epoch=NULL WHERE attempt_id=$1",
                    a["id"],
                )
            await r.save_check(con, c)
            await audit(
                con,
                "lease_recovered",
                check_id=c["id"],
                entity_id=a["id"],
                payload={"unknown": a["dispatched"]},
            )
