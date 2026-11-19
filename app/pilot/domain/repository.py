"""Current graph representation under a parent Check row lock."""

import copy, json
from uuid import UUID, uuid4
from .errors import DomainError, not_found
from .access import check_access


def uid():
    return str(uuid4())


def uuid(value):
    return UUID(str(value))


def decode(value):
    return json.loads(value) if isinstance(value, str) else copy.deepcopy(value)


def record_check(row):
    d = dict(row)
    d["graph"] = decode(d["graph"])
    return d


async def load_check(
    con, check_id, actor=None, *, lock=False, staff=False, include_deleted=False
):
    row = await con.fetchrow(
        "SELECT * FROM pilot_checks WHERE id=$1" + (" FOR UPDATE" if lock else ""),
        uuid(check_id),
    )
    if not row or (row["deleted"] and not include_deleted):
        not_found()
    if actor:
        check_access(row, actor, staff=staff)
    return record_check(row)


async def locate_check(con, kind, entity_id):
    table = {
        "check": "pilot_checks",
        "notebook": "pilot_notebooks",
        "bundle": "pilot_bundles",
        "input": "pilot_input_versions",
        "task": "pilot_task_analyses",
        "job": "pilot_jobs",
        "photo": "pilot_photo_assets",
    }[kind]
    if kind == "check":
        return uuid(entity_id)
    if kind == "input":
        sql = "SELECT b.check_id FROM pilot_input_versions v JOIN pilot_bundles b ON v.bundle_id=b.id WHERE v.id=$1"
    elif kind == "task":
        sql = "SELECT j.check_id FROM pilot_task_analyses t JOIN pilot_jobs j ON j.id=t.job_id WHERE t.task_id=$1"
    else:
        sql = f"SELECT check_id FROM {table} WHERE id=$1"
    cid = await con.fetchval(sql, uuid(entity_id))
    if cid is None:
        not_found()
    return cid


def find(check, kind, entity_id):
    value = str(entity_id)
    for n in check["graph"]["notebooks"]:
        if kind == "notebook" and n["id"] == value:
            return n, None, n
        for b in n["bundles"]:
            if kind == "bundle" and b["id"] == value:
                return n, b, b
            for key in ("draft", "current_input"):
                if kind == "input" and b.get(key) and b[key]["id"] == value:
                    return n, b, b[key]
            for t in b["tasks"]:
                if kind == "task" and t["task_id"] == value:
                    return n, b, t
    not_found()


async def save_check(con, c, *, data=False):
    c["revision"] += 1
    if data:
        c["data_revision"] += 1
    await con.execute(
        "UPDATE pilot_checks SET phase=$2,revision=$3,data_revision=$4,next_notebook_number=$5,selected_summary_job_id=$6,deleted=$7,graph=$8::jsonb WHERE id=$1",
        c["id"],
        c["phase"],
        c["revision"],
        c["data_revision"],
        c["next_notebook_number"],
        uuid(c["selected_summary_job_id"]) if c["selected_summary_job_id"] else None,
        c["deleted"],
        json.dumps(c["graph"]),
    )


def job_dto(row, *, retry=False):
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "input_id": str(row["input_version_id"] or row["snapshot_id"]),
        "state": row["state"],
        "reason": row["reason"],
        "can_retry": bool(retry),
    }


async def page_can_retry(con, c, b, row):
    if c["phase"] == "finalized" or b["skipped"]:
        return False
    unsafe = await con.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pilot_attempts WHERE job_id=$1 AND state IN ('started','unknown'))",
        row["id"],
    )
    if unsafe:
        return False
    if row["state"] == "failed":
        return True
    return row["state"] == "succeeded" and (
        not b["result"]
        or b["result"]["report"]["status"] == "uncheckable"
        or not b["result"]["report"]["tasks"]
        or any(t["analysis"]["result"] == "not_assessed" for t in b["tasks"])
    )


async def synchronize_jobs(con, c):
    for n in c["graph"]["notebooks"]:
        for b in n["bundles"]:
            if b["job"]:
                row = await con.fetchrow(
                    "SELECT * FROM pilot_jobs WHERE id=$1", uuid(b["job"]["id"])
                )
                b["job"] = job_dto(row, retry=await page_can_retry(con, c, b, row))


async def current_job(con, c, job):
    if c["deleted"]:
        return False
    if job["kind"] == "class_analytics":
        return str(c["selected_summary_job_id"]) == str(job["id"])
    try:
        _, b, _ = find(c, "bundle", job["bundle_id"])
    except DomainError:
        return False
    return bool(
        not b["skipped"]
        and b["current_input"]
        and b["current_input"]["id"] == str(job["input_version_id"])
        and b["job"]
        and b["job"]["id"] == str(job["id"])
    )
