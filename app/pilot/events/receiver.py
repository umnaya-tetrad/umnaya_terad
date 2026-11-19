"""Atomic bounded client observations; server attribution cannot be supplied."""

import json
from uuid import UUID
from ..domain.schema import validate
from ..domain import repository as r
from ..domain.errors import DomainError, invalid, not_found


async def ingest_events(svc, actor, payload, *, request_id):
    validate(payload, "Events")
    events = payload["events"]
    async with svc.pool.acquire() as con, con.transaction():
        # Consistent advisory order serializes duplicate IDs without cross-batch deadlocks.
        for eid in sorted({e["id"] for e in events}):
            await con.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", str(actor.user_id) + eid
            )
        seen = {}
        for event in events:
            eid = event["id"]
            if eid in seen and seen[eid] != event:
                invalid(
                    "Событие уже принято с другими данными.", "idempotency_conflict"
                )
            seen[eid] = event
            if event["entity_id"] and not event["check_id"]:
                not_found()
            if event["check_id"]:
                c = await r.load_check(con, event["check_id"], actor, staff=True)
                if event["entity_id"]:
                    available = {
                        b["id"] for n in c["graph"]["notebooks"] for b in n["bundles"]
                    } | {
                        t["task_id"]
                        for n in c["graph"]["notebooks"]
                        for b in n["bundles"]
                        for t in b["tasks"]
                    }
                    if event["entity_id"] not in available:
                        not_found()
            old = await con.fetchval(
                "SELECT payload FROM pilot_events WHERE actor_id=$1 AND id=$2",
                actor.user_id,
                UUID(eid),
            )
            if old and r.decode(old) != event:
                invalid(
                    "Событие уже принято с другими данными.", "idempotency_conflict"
                )
        for event in seen.values():
            await con.execute(
                "INSERT INTO pilot_events(actor_id,id,role,payload) VALUES($1,$2,$3,$4::jsonb) ON CONFLICT(actor_id,id) DO NOTHING",
                actor.user_id,
                UUID(event["id"]),
                actor.role,
                json.dumps(event),
            )
    return {"accepted_ids": [e["id"] for e in events]}
