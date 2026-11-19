"""Authorized read facade. GET never enqueues or dispatches model work."""

import base64, json
from uuid import UUID
from . import repository as r
from .access import require_staff
from .errors import DomainError, not_found
from .completion import completion
from .storage import PrivatePhoto
from ..events.audit import audit


async def _summary(con, c, job_id=None):
    jid = job_id or c["selected_summary_job_id"]
    empty = {
        "state": "not_started",
        "stale": False,
        "snapshot_id": None,
        "job_id": None,
        "data_revision": None,
        "can_retry": False,
        "can_refresh": False,
        "result": None,
    }
    if not jid:
        return empty
    row = await con.fetchrow(
        "SELECT j.*,s.data_revision FROM pilot_jobs j JOIN pilot_snapshots s ON s.id=j.snapshot_id WHERE j.id=$1",
        r.uuid(jid),
    )
    unsafe = await con.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pilot_attempts WHERE job_id=$1 AND (state IN ('started','unknown') OR (dispatched AND state NOT IN ('settled','rejected'))))",
        row["id"],
    )
    # Even a cancelled/terminal job cannot bypass an unknown paid attempt.
    stale = row["data_revision"] != c["data_revision"]
    final = c["phase"] == "finalized"
    terminal = row["state"] in ("succeeded", "failed", "cancelled", "superseded")
    unsent = row["state"] in ("queued", "blocked") and not await con.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pilot_attempts WHERE job_id=$1 AND dispatched)",
        row["id"],
    )
    result = await con.fetchval(
        "SELECT result FROM pilot_analytics_results WHERE job_id=$1", row["id"]
    )
    return {
        "state": row["state"],
        "stale": stale,
        "snapshot_id": str(row["snapshot_id"]),
        "job_id": str(row["id"]),
        "data_revision": row["data_revision"],
        "can_retry": bool(
            final and not stale and row["state"] == "failed" and not unsafe
        ),
        "can_refresh": bool(final and stale and not unsafe and (terminal or unsent)),
        "result": r.decode(result) if result else None,
    }


async def _dto(con, c):
    await r.synchronize_jobs(con, c)
    return {
        "id": str(c["id"]),
        "title": c["title"],
        "phase": c["phase"],
        "revision": c["revision"],
        "created_at": c["created_at"].isoformat().replace("+00:00", "Z"),
        "data_revision": c["data_revision"],
        "notebooks": c["graph"]["notebooks"],
        "completion": completion(c),
        "summary": await _summary(con, c),
    }


async def get_check(svc, actor, check_id, *, request_id):
    async with svc.pool.acquire() as con, con.transaction(
        isolation="repeatable_read", readonly=True
    ):
        return await _dto(con, await r.load_check(con, check_id, actor))


def _list_item(row):
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "phase": row["phase"],
        "revision": row["revision"],
        "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
    }


def _cursor_decode(cursor):
    if not cursor:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor))
        return UUID(value["id"])
    except Exception as e:
        raise DomainError(422, "invalid_input", "Некорректный курсор.") from e


async def list_checks(svc, actor, *, cursor=None, limit=30, request_id):
    if actor.role != "teacher":
        raise DomainError(403, "forbidden", "Откройте раздел поддержки.")
    if not 1 <= limit <= 100:
        raise DomainError(422, "invalid_input", "Некорректный размер страницы.")
    cid = _cursor_decode(cursor)
    rows = await svc.pool.fetch(
        "SELECT * FROM pilot_checks WHERE owner_id=$1 AND NOT deleted AND ($2::uuid IS NULL OR (created_at,id)<(SELECT created_at,id FROM pilot_checks WHERE id=$2 AND owner_id=$1 AND NOT deleted)) ORDER BY created_at DESC,id DESC LIMIT $3",
        actor.user_id,
        cid,
        limit + 1,
    )
    nxt = (
        base64.urlsafe_b64encode(
            json.dumps({"id": str(rows[limit - 1]["id"])}).encode()
        ).decode()
        if len(rows) > limit
        else None
    )
    return {"items": [_list_item(x) for x in rows[:limit]], "next_cursor": nxt}


async def get_job(svc, actor, job_id, *, request_id):
    async with svc.pool.acquire() as con, con.transaction():
        cid = await r.locate_check(con, "job", job_id)
        c = await r.load_check(con, cid, actor, staff=True)
        row = await con.fetchrow("SELECT * FROM pilot_jobs WHERE id=$1", r.uuid(job_id))
        retry = False
        if row["kind"] == "page_check":
            _, b, _ = r.find(c, "bundle", row["bundle_id"])
            retry = bool(
                b["job"]
                and b["job"]["id"] == str(row["id"])
                and await r.page_can_retry(con, c, b, row)
            )
        else:
            retry = (await _summary(con, c, job_id))["can_retry"]
        if actor.role == "staff":
            await audit(
                con,
                "staff_read_job",
                actor=actor,
                request_id=request_id,
                check_id=cid,
                entity_id=job_id,
            )
        return r.job_dto(row, retry=retry)


async def get_summary(svc, actor, check_id, *, request_id):
    async with svc.pool.acquire() as con, con.transaction(
        isolation="repeatable_read", readonly=True
    ):
        return await _summary(con, await r.load_check(con, check_id, actor))


async def get_summary_history(svc, actor, check_id, *, request_id):
    require_staff(actor)
    async with svc.pool.acquire() as con, con.transaction():
        c = await r.load_check(con, check_id, actor, staff=True)
        rows = await con.fetch(
            "SELECT id,created_at FROM pilot_jobs WHERE check_id=$1 AND kind='class_analytics' ORDER BY created_at,id",
            c["id"],
        )
        items = [
            {
                "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
                "summary": await _summary(con, c, row["id"]),
            }
            for row in rows
        ]
        await audit(
            con,
            "staff_read_summary_history",
            actor=actor,
            request_id=request_id,
            check_id=c["id"],
        )
        return {"items": items}


async def get_bundle_history(svc, actor, bundle_id, *, request_id):
    require_staff(actor)
    async with svc.pool.acquire() as con, con.transaction():
        cid = await r.locate_check(con, "bundle", bundle_id)
        c = await r.load_check(con, cid, actor, staff=True)
        r.find(c, "bundle", bundle_id)
        versions = []
        for v in await con.fetch(
            "SELECT * FROM pilot_input_versions WHERE bundle_id=$1 AND state='sealed' ORDER BY created_at,id",
            r.uuid(bundle_id),
        ):
            runs = []
            for j in await con.fetch(
                "SELECT * FROM pilot_jobs WHERE input_version_id=$1 ORDER BY created_at,id",
                v["id"],
            ):
                rep = await con.fetchrow(
                    "SELECT * FROM pilot_bundle_reports WHERE job_id=$1", j["id"]
                )
                tasks = []
                deleted = []
                for t in await con.fetch(
                    "SELECT t.*,v.state review_state,v.comment FROM pilot_task_analyses t LEFT JOIN pilot_reviews v ON t.id=v.analysis_id WHERE job_id=$1 ORDER BY t.id",
                    j["id"],
                ):
                    if t["deleted"]:
                        deleted.append(str(t["task_id"]))
                    else:
                        tasks.append(
                            {
                                "task_id": str(t["task_id"]),
                                "analysis_id": str(t["id"]),
                                "analysis": r.decode(t["analysis"]),
                                "review": (
                                    {
                                        "state": t["review_state"],
                                        "comment": t["comment"],
                                    }
                                    if t["review_state"]
                                    else None
                                ),
                                "skipped": t["skipped"],
                            }
                        )
                runs.append(
                    {
                        "job": r.job_dto(j),
                        "result": (
                            {
                                "id": str(rep["id"]),
                                "input_version_id": str(rep["input_version_id"]),
                                "report": r.decode(rep["report"]),
                            }
                            if rep
                            else None
                        ),
                        "tasks": tasks,
                        "deleted_task_ids": deleted,
                    }
                )
            versions.append({"input": r.decode(v["payload"]), "runs": runs})
        await audit(
            con,
            "staff_read_bundle_history",
            actor=actor,
            request_id=request_id,
            check_id=cid,
            entity_id=bundle_id,
        )
        return {"bundle_id": str(bundle_id), "versions": versions}


async def open_photo(svc, actor, photo_id, *, request_id):
    from pathlib import Path

    async with svc.pool.acquire() as con, con.transaction():
        row = await con.fetchrow(
            "SELECT * FROM pilot_photo_assets WHERE id=$1", r.uuid(photo_id)
        )
        if not row:
            not_found()
        c = await r.load_check(con, row["check_id"], actor, staff=True)
        _, b, _ = r.find(c, "bundle", row["bundle_id"])
        # A deleted draft link does not reveal unreferenced private files.
        linked = await con.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pilot_version_photos p JOIN pilot_input_versions v ON p.version_id=v.id WHERE p.photo_id=$1 AND NOT v.discarded)",
            row["id"],
        )
        if not linked:
            not_found()
        if actor.role == "staff":
            await audit(
                con,
                "staff_read_photo",
                actor=actor,
                request_id=request_id,
                check_id=c["id"],
                entity_id=photo_id,
            )
        path = Path(row["normalized_path"]).resolve()
        if not path.is_relative_to(svc.storage_root.resolve()) or not path.is_file():
            not_found()
        return PrivatePhoto(path, row["media_type"])


async def list_staff_checks(
    svc, actor, *, owner_login=None, cursor=None, limit=30, request_id
):
    require_staff(actor)
    if not 1 <= limit <= 100:
        raise DomainError(422, "invalid_input", "Некорректный размер страницы.")
    cid = _cursor_decode(cursor)
    async with svc.pool.acquire() as con, con.transaction():
        rows = await con.fetch(
            "SELECT c.*,u.username FROM pilot_checks c JOIN users u ON c.owner_id=u.id WHERE NOT c.deleted AND ($1::text IS NULL OR u.username=$1) AND ($2::uuid IS NULL OR (c.created_at,c.id)<(SELECT created_at,id FROM pilot_checks WHERE id=$2)) ORDER BY c.created_at DESC,c.id DESC LIMIT $3",
            owner_login,
            cid,
            limit + 1,
        )
        await audit(con, "staff_list_checks", actor=actor, request_id=request_id)
        nxt = (
            base64.urlsafe_b64encode(
                json.dumps({"id": str(rows[limit - 1]["id"])}).encode()
            ).decode()
            if len(rows) > limit
            else None
        )
        return {
            "items": [
                {
                    "owner": {
                        "user_id": str(row["owner_id"]),
                        "login": row["username"],
                    },
                    "check": _list_item(row),
                }
                for row in rows[:limit]
            ],
            "next_cursor": nxt,
        }


async def get_staff_check(svc, actor, check_id, *, request_id):
    require_staff(actor)
    async with svc.pool.acquire() as con, con.transaction():
        c = await r.load_check(con, check_id, actor, staff=True)
        login = await con.fetchval(
            "SELECT username FROM users WHERE id=$1", c["owner_id"]
        )
        await audit(
            con,
            "staff_read_check",
            actor=actor,
            request_id=request_id,
            check_id=c["id"],
        )
        return {
            "owner": {"user_id": str(c["owner_id"]), "login": login},
            "check": await _dto(con, c),
        }
