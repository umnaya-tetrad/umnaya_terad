import asyncio
import io
import json
import shutil
import os
import sys
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from PIL import Image

from ..harness import ROOT, SHARED, png
from ..scenarios import Gateway, ready, report, tasks, wallet, finalize

pytestmark = pytest.mark.asyncio


async def test_proc_c01(db, pg_factory, tmp_path):
    from pilot.domain.migrate import migrate, MIGRATIONS

    legacy = tmp_path / "legacy"
    legacy.mkdir()
    for source in sorted(MIGRATIONS.glob("*.sql"))[:7]:
        shutil.copyfile(source, legacy / source.name)
    await migrate(db, migrations_path=legacy)
    uid = uuid4()
    await db.execute(
        "INSERT INTO users(id,username,password_hash) VALUES($1,'upgrade_user','synthetic_hash')",
        uid,
    )
    await db.execute(
        "INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES($1,$2,now()+interval '1 day')",
        "a" * 64,
        uid,
    )
    await migrate(db)
    clean = await pg_factory()
    await migrate(clean)
    await migrate(clean)
    count = await db.fetchval("SELECT count(*) FROM pilot_migrations")
    await migrate(db)
    assert await db.fetchval("SELECT count(*) FROM pilot_migrations") == count
    expected = {
        "pilot_checks",
        "pilot_notebooks",
        "pilot_bundles",
        "pilot_jobs",
        "pilot_attempts",
        "pilot_snapshots",
        "pilot_fund_ledger",
        "pilot_slots",
    }
    names = {
        r["tablename"]
        for r in await db.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
    }
    assert expected <= names
    copied = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, copied)
    first = sorted(copied.glob("*.sql"))[0]
    first.write_bytes(first.read_bytes() + b"\n-- tampered\n")
    with pytest.raises(RuntimeError, match="checksum"):
        await migrate(db, migrations_path=copied)
    assert await db.fetchval("SELECT count(*) FROM pilot_migrations") == count
    assert (
        await db.fetchval(
            "SELECT password_hash FROM users WHERE username='upgrade_user'"
        )
        == "synthetic_hash"
    )
    assert (
        await db.fetchval("SELECT token_hash FROM auth_sessions WHERE user_id=$1", uid)
        == "a" * 64
    )
    assert await clean.fetchval("SELECT count(*) FROM pilot_migrations") == count
    # Constraints are exercised by real SQL, including immutable evidence.
    cid, nid, bid, vid, pid, jid, aid, rid = [uuid4() for _ in range(8)]
    await db.execute(
        "INSERT INTO pilot_checks(id,owner_id,title) VALUES($1,$2,'constraints')",
        cid,
        uid,
    )
    await db.execute(
        "INSERT INTO pilot_notebooks(id,check_id,number) VALUES($1,$2,1)", nid, cid
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(
            "INSERT INTO pilot_notebooks(id,check_id,number) VALUES($1,$2,1)",
            uuid4(),
            cid,
        )
    await db.execute(
        "INSERT INTO pilot_bundles(id,check_id,notebook_id) VALUES($1,$2,$3)",
        bid,
        cid,
        nid,
    )
    await db.execute(
        "INSERT INTO pilot_input_versions(id,bundle_id,state,payload) VALUES($1,$2,'draft','{}')",
        vid,
        bid,
    )
    await db.execute(
        "INSERT INTO pilot_photo_assets(id,check_id,bundle_id,original_path,normalized_path,media_type,sha256,byte_count,width,height) VALUES($1,$2,$3,'synthetic-original','synthetic-normalized','image/png','synthetic',1,64,64)",
        pid,
        cid,
        bid,
    )
    await db.execute(
        "INSERT INTO pilot_version_photos(version_id,photo_id,position) VALUES($1,$2,1)",
        vid,
        pid,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(
            "INSERT INTO pilot_version_photos(version_id,photo_id,position) VALUES($1,$2,1)",
            vid,
            pid,
        )
    await db.execute("UPDATE pilot_input_versions SET state='sealed' WHERE id=$1", vid)
    with pytest.raises(asyncpg.RaiseError):
        await db.execute(
            "UPDATE pilot_version_photos SET position=2 WHERE version_id=$1", vid
        )
    await db.execute(
        "INSERT INTO pilot_jobs(id,check_id,bundle_id,kind,input_version_id) VALUES($1,$2,$3,'page_check',$4)",
        jid,
        cid,
        bid,
        vid,
    )
    await db.execute(
        "INSERT INTO pilot_attempts(id,job_id,ordinal,epoch,state) VALUES($1,$2,1,1,'started')",
        aid,
        jid,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(
            "INSERT INTO pilot_attempts(id,job_id,ordinal,epoch,state) VALUES($1,$2,1,2,'started')",
            uuid4(),
            jid,
        )
    await db.execute(
        "INSERT INTO pilot_bundle_reports(id,job_id,input_version_id,report) VALUES($1,$2,$3,'{}')",
        rid,
        jid,
        vid,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(
            "INSERT INTO pilot_bundle_reports(id,job_id,input_version_id,report) VALUES($1,$2,$3,'{}')",
            uuid4(),
            jid,
            vid,
        )
    with pytest.raises(asyncpg.RaiseError):
        await db.execute(
            "UPDATE pilot_bundle_reports SET report=report WHERE id=$1", rid
        )
    await db.execute(
        "INSERT INTO pilot_fund_ledger(id,mode,request_id,attempt_id,operation,amount_rub,payload_hash,evidence) VALUES($1,'fixture',$2,$3,'settlement',0,'synthetic','{}')",
        uuid4(),
        uuid4(),
        aid,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(
            "INSERT INTO pilot_fund_ledger(id,mode,request_id,attempt_id,operation,amount_rub,payload_hash,evidence) VALUES($1,'fixture',$2,$3,'settlement',0,'synthetic','{}')",
            uuid4(),
            uuid4(),
            aid,
        )
    with pytest.raises(asyncpg.RaiseError):
        await db.execute(
            "UPDATE pilot_fund_ledger SET amount_rub=1 WHERE attempt_id=$1", aid
        )
    for value in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(asyncpg.CheckViolationError):
            await db.execute("UPDATE pilot_funds SET balance_rub=$1::numeric", value)


async def test_proc_c02(h):
    from pilot.processing.worker import heartbeat, healthcheck

    routes = h.app.openapi()["paths"]
    operations = [
        v["operationId"] for methods in routes.values() for v in methods.values()
    ]
    assert len(operations) == len(set(operations))
    assert not any("/api/api/" in path for path in routes)
    await heartbeat(h.svc, uuid4())
    assert await healthcheck(h.svc)

    async def cli(database_url):
        env = {
            **os.environ,
            "DATABASE_URL": database_url,
            "PILOT_TRANSPORT": "fixture",
            "PYTHONPATH": str(ROOT / "app"),
        }
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pilot.processing.worker",
            "--healthcheck",
            cwd=ROOT / "app",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(child.communicate(), 15)
        return child.returncode

    assert await cli(h.svc.test_database_url) == 0
    await h.svc.pool.execute(
        "UPDATE pilot_workers SET heartbeat_at=now()-interval '60 seconds'"
    )
    assert not await healthcheck(h.svc)
    assert await cli(h.svc.test_database_url) != 0
    assert (
        await cli("postgresql://pilot_test_admin@127.0.0.1:1/pilot_test_unavailable")
        != 0
    )
    assert (ROOT / "app/pilot/contracts.py").read_bytes() == (
        SHARED / "api/contracts.py"
    ).read_bytes()


async def test_proc_c03(h):
    from pilot.domain.auth import ensure_account, reset_account_password, authenticate

    ids = await h.create()
    await h.call("getCheck", actor="t2", check_id=ids[0], expected=404)
    await h.call("getCheck", actor="anon", check_id=ids[0], expected=401)
    await h.call("getBundleHistory", bundle_id=ids[2], expected=403)
    await h.call("getBundleHistory", actor="staff", bundle_id=ids[2], expected=200)
    login = await h.call(
        "login",
        payload={"login": "test_t1", "password": "synthetic-test-password-47"},
        expected=200,
    )
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert ("secure" in cookie) == h.svc.settings.visitor_cookie_secure
    revision = (await h.check())["revision"]
    denied = await h.clients["t1"].post(
        "/api/checks/" + ids[0] + "/begin-completion",
        headers={
            "Origin": "https://synthetic-untrusted.invalid",
            "Idempotency-Key": str(uuid4()),
            "If-Match": f'"{revision}"',
        },
    )
    assert denied.status_code == 403
    assert (await h.check())["revision"] == revision
    await h.call("createNotebook", actor="staff", check_id=ids[0], expected=403)
    await h.call(
        "login",
        actor="anon",
        payload={"login": "test_t1", "password": "incorrect"},
        expected=401,
    )
    await ensure_account(h.svc, "test_t1", "different-long-password", "teacher")
    await authenticate(h.svc, "test_t1", "synthetic-test-password-47")
    with pytest.raises(Exception) as error:
        await ensure_account(h.svc, "test_t1", "different-long-password", "staff")
    assert error.value.http_status == 409
    await reset_account_password(
        h.svc,
        login="test_t1",
        password="new-synthetic-password-49",
        operator_ref="pytest",
        request_id=uuid4(),
    )
    await h.call("getSession", expected=401)
    await h.call("getSession", actor="t2", expected=200)
    await h.svc.pool.execute(
        "UPDATE auth_sessions SET expires_at=now()-interval '1 second' WHERE user_id=$1",
        UUID(h.ids["t2"]),
    )
    await h.call("getSession", actor="t2", expected=401)
    hashes = await h.svc.pool.fetch("SELECT password_hash FROM users")
    assert all(
        "synthetic-test-password-47" not in row["password_hash"] for row in hashes
    )
    assert (await authenticate(h.svc, "test_t1", "new-synthetic-password-49")).session[
        "user_id"
    ] == h.ids["t1"]
    assert (
        await h.clients["anon"].post("/api/auth/register", json={})
    ).status_code == 404


async def test_proc_c04(h):
    from ..harness import CommittedAckLostPool

    ids = await h.create()
    key = uuid4()
    revision = (await h.check())["revision"]
    base = h.svc.pool
    h.svc.pool = CommittedAckLostPool(base)
    try:
        with pytest.raises(ConnectionResetError, match="COMMIT"):
            await h.submit(ids[2], ids[3], key=key, revision=revision)
    finally:
        h.svc.pool = base
    first = json.loads(
        await base.fetchval("SELECT body FROM pilot_idempotency WHERE key=$1", key)
    )
    replay = await h.submit(ids[2], ids[3], expected=202, key=key, revision=revision)
    assert first == replay.json()
    assert (
        await base.fetchval(
            "SELECT count(*) FROM pilot_outbox WHERE event_name='submit_bundle'"
        )
        == 1
    )
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_jobs") == 1
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_idempotency WHERE key=$1", key
        )
        == 1
    )
    await h.submit(ids[2], str(uuid4()), expected=409, key=key, revision=revision)
    rejected = await h.submit(ids[2], ids[3], expected=409, revision=revision)
    assert rejected.json()["error"]["code"] == "revision_conflict"


async def test_proc_c06(h):
    await ready(h)
    task = tasks(await h.check())[0]
    revision = (await h.check())["revision"]
    data_revision = (await h.check())["data_revision"]
    payload = {"analysis_id": task["analysis_id"], "state": "confirmed", "comment": ""}
    await h.call(
        "saveReview",
        task_id=task["task_id"],
        payload=payload,
        revision=revision,
        expected=200,
    )
    assert (await h.check())["revision"] == revision + 1
    assert (await h.check())["data_revision"] == data_revision + 1
    await h.call(
        "saveReview",
        task_id=task["task_id"],
        payload={**payload, "state": "system_error"},
        revision=revision,
        expected=409,
    )
    check = await h.check()
    data = check["data_revision"]
    revision = check["revision"]
    await h.call("saveReview", task_id=task["task_id"], payload=payload, expected=200)
    assert (await h.check())["revision"] == revision
    await h.call(
        "saveReview",
        task_id=task["task_id"],
        payload={**payload, "comment": "Комментарий"},
        expected=200,
    )
    assert (await h.check())["data_revision"] == data
    r = await h.call(
        "saveReview",
        task_id=task["task_id"],
        payload={**payload, "analysis_id": str(uuid4())},
        expected=409,
    )
    assert r.json()["error"]["code"] == "stale_analysis"


async def test_proc_c07(h):
    ids = await h.create(photos=0)
    for fmt, mime in [
        ("PNG", "image/png"),
        ("JPEG", "image/jpeg"),
        ("WEBP", "image/webp"),
    ]:
        uploaded = await h.call(
            "uploadPhoto",
            input_version_id=ids[3],
            files={"file": ("../../synthetic", png(fmt=fmt), mime)},
            expected=201,
        )
        asset = await h.call(
            "getPhoto", photo_id=uploaded.json()["entity_id"], expected=200
        )
        assert asset.headers["cache-control"] == "no-store"
        assert Image.open(io.BytesIO(asset.content)).size == (64, 64)
        await h.call(
            "getPhoto", actor="t2", photo_id=uploaded.json()["entity_id"], expected=404
        )
    await h.call(
        "uploadPhoto",
        input_version_id=ids[3],
        files={"file": ("bad.png", b"bad", "image/png")},
        expected=422,
    )
    await h.call(
        "uploadPhoto",
        input_version_id=ids[3],
        files={"file": ("bad.pdf", b"%PDF", "application/pdf")},
        expected=415,
    )
    await h.call(
        "uploadPhoto",
        input_version_id=ids[3],
        files={"file": ("tiny.png", png((31, 64)), "image/png")},
        expected=422,
    )
    from ..harness import CommittedAckLostPool

    base = h.svc.pool
    revision = (await h.check())["revision"]
    count = await base.fetchval("SELECT count(*) FROM pilot_photo_assets")
    key = uuid4()
    h.svc.pool = CommittedAckLostPool(base)
    try:
        with pytest.raises(ConnectionResetError, match="COMMIT"):
            await h.call(
                "uploadPhoto",
                input_version_id=ids[3],
                files={"file": ("ack-lost.png", png(), "image/png")},
                revision=revision,
                key=key,
            )
    finally:
        h.svc.pool = base
    assert await base.fetchval("SELECT count(*) FROM pilot_photo_assets") == count + 1
    replay = await h.call(
        "uploadPhoto",
        input_version_id=ids[3],
        files={"file": ("ack-lost.png", png(), "image/png")},
        revision=revision,
        key=key,
        expected=201,
    )
    asset = await h.call("getPhoto", photo_id=replay.json()["entity_id"], expected=200)
    assert asset.content == png()
    assert await base.fetchval("SELECT count(*) FROM pilot_photo_assets") == count + 1
    assert (await h.check())["revision"] == revision + 1


async def test_proc_c08(h):
    ids = await h.create(photos=2)
    b = (await h.check())["notebooks"][0]["bundles"][0]
    photo_ids = [p["id"] for p in b["draft"]["photos"]][::-1]
    await h.call(
        "reorderPhotos",
        input_version_id=ids[3],
        payload={"photo_ids": photo_ids},
        expected=200,
    )
    await h.call(
        "reorderPhotos",
        input_version_id=ids[3],
        payload={"photo_ids": photo_ids[:1]},
        expected=422,
    )
    await h.submit(ids[2], ids[3], expected=202)
    b = (await h.check())["notebooks"][0]["bundles"][0]
    assert [p["id"] for p in b["current_input"]["photos"]] == photo_ids
    await h.call(
        "reorderPhotos",
        input_version_id=ids[3],
        payload={"photo_ids": photo_ids},
        expected=409,
    )
    draft = await h.call(
        "createInputVersion",
        bundle_id=ids[2],
        payload={"photo_ids": photo_ids},
        expected=201,
    )
    await h.call(
        "discardDraft", input_version_id=draft.json()["entity_id"], expected=200
    )
    assert (await h.check())["notebooks"][0]["bundles"][0]["current_input"][
        "id"
    ] == ids[3]


async def test_proc_c10(h):
    ids, gateway, _ = await ready(h, count=2)
    await h.review_all()
    old = {t["task_id"] for t in tasks(await h.check())}
    photo = (await h.check())["notebooks"][0]["bundles"][0]["current_input"]["photos"][
        0
    ]["id"]
    draft = await h.call(
        "createInputVersion",
        bundle_id=ids[2],
        payload={"photo_ids": [photo]},
        expected=201,
    )
    assert all(t["review"] for t in tasks(await h.check()))
    await h.submit(ids[2], draft.json()["entity_id"], expected=202)
    assert tasks(await h.check()) == []
    gateway.page_report = report(3)
    await h.run()
    new = tasks(await h.check())
    assert len(new) == 3 and not old.intersection(t["task_id"] for t in new)
    assert all(t["review"] is None for t in new)
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_bundle_reports") == 2


async def test_proc_c11(h):
    ids, gateway, _ = await ready(h, count=2, mixed=True)
    task = tasks(await h.check())[0]
    await h.call(
        "saveReview",
        task_id=task["task_id"],
        payload={
            "analysis_id": task["analysis_id"],
            "state": "confirmed",
            "comment": "",
        },
        expected=200,
    )
    await h.call("deleteTask", task_id=task["task_id"], expected=200)
    await h.call(
        "retryBundle",
        bundle_id=ids[2],
        payload={"input_version_id": ids[3]},
        expected=202,
    )
    await h.run()
    assert task["task_id"] not in {t["task_id"] for t in tasks(await h.check())}
    history = (
        await h.call("getBundleHistory", actor="staff", bundle_id=ids[2], expected=200)
    ).json()
    assert len(history["versions"]) == 1 and len(history["versions"][0]["runs"]) == 2
    assert task["task_id"] in history["versions"][0]["runs"][0]["deleted_task_ids"]
    assert (
        await h.svc.pool.fetchval(
            "SELECT state FROM pilot_reviews WHERE analysis_id=$1",
            UUID(task["analysis_id"]),
        )
        == "confirmed"
    )
    assert all(t["review"] is None for t in tasks(await h.check()))


async def test_proc_c12(h):
    _, _, _ = await ready(h, count=2, mixed=True)
    items = tasks(await h.check())
    bad = items[-1]
    await h.call(
        "saveReview",
        task_id=bad["task_id"],
        payload={
            "analysis_id": bad["analysis_id"],
            "state": "confirmed",
            "comment": "",
        },
        expected=409,
    )
    await h.review_all()
    await h.call("beginCompletion", check_id=h.check_id, expected=200)
    await h.call("finalizeCheck", check_id=h.check_id, expected=202)
    snapshot = json.loads(
        await h.svc.pool.fetchval("SELECT payload FROM pilot_snapshots")
    )
    assert len(snapshot["notebooks"][0]["tasks"]) == 2
    assert snapshot["notebooks"][0]["tasks"][-1]["review_state"] is None


async def test_proc_c13(h):
    ids, _, _ = await ready(h, count=2)
    items = tasks(await h.check())
    photo = (await h.check())["notebooks"][0]["bundles"][0]["current_input"]["photos"][
        0
    ]["id"]
    await h.call("deleteTask", task_id=items[0]["task_id"], expected=200)
    assert len(tasks(await h.check())) == 1
    await h.call("getPhoto", photo_id=photo, expected=200)
    await h.call("deleteTask", task_id=items[1]["task_id"], expected=200)
    assert tasks(await h.check()) == []
    await h.call("beginCompletion", check_id=ids[0], expected=200)
    await h.call("finalizeCheck", check_id=ids[0], expected=202)
    h.svc.transport = None
    await h.run()
    summary = (await h.call("getSummary", check_id=ids[0], expected=200)).json()
    assert (
        summary["state"] == "succeeded" and summary["result"]["notebooks"]["empty"] == 1
    )
    assert (
        summary["result"]["notebooks"]["without_errors"] == 0
        and summary["result"]["average_errors_per_notebook"] is None
    )
    ids = await h.create(photos=0)
    second = (await h.call("createNotebook", check_id=ids[0], expected=201)).json()[
        "entity_id"
    ]
    await h.call("deleteNotebook", notebook_id=second, expected=200)
    await h.call("createNotebook", check_id=ids[0], expected=201)
    assert [n["number"] for n in (await h.check())["notebooks"]] == [1, 3]


async def test_proc_c14(h):
    ids = await h.create()
    submitted = await h.submit(ids[2], ids[3], expected=202)
    key = uuid4()
    rev = (await h.check())["revision"]
    deleted = await h.call(
        "deleteCheck", check_id=ids[0], key=key, revision=rev, expected=200
    )
    await h.call("getCheck", check_id=ids[0], expected=404)
    await h.call("getJob", job_id=submitted.json()["job"]["id"], expected=404)
    replay = await h.call(
        "deleteCheck", check_id=ids[0], key=key, revision=rev, expected=200
    )
    assert deleted.json() == replay.json()
    assert not await h.run()


async def test_proc_c20(h):
    h.svc.transport = Gateway()
    ids = await h.create(photos=0)
    denied = await h.call("finalizeCheck", check_id=ids[0], expected=409)
    assert denied.json()["error"]["code"] == "invalid_state"
    await h.call("beginCompletion", check_id=ids[0], expected=200)
    check = await h.check()
    assert check["phase"] == "review" and not check["completion"]["can_finalize"]
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_snapshots") == 0
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_jobs WHERE kind='class_analytics'"
        )
        == 0
    )

    async def blocked(field):
        check = await h.check()
        assert (
            check["completion"][field] > 0 and not check["completion"]["can_finalize"]
        )
        before = await h.svc.pool.fetchval("SELECT count(*) FROM pilot_snapshots")
        response = await h.call("finalizeCheck", check_id=h.check_id, expected=409)
        assert response.json()["error"]["code"] == "completion_blocked"
        assert (await h.check())["revision"] == check["revision"]
        assert (
            await h.svc.pool.fetchval("SELECT count(*) FROM pilot_snapshots") == before
        )

    ids = await h.create(photos=1)
    await h.call("beginCompletion", check_id=ids[0], expected=200)
    await blocked("unsent_drafts")
    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    await h.call("beginCompletion", check_id=ids[0], expected=200)
    await blocked("pending_jobs")
    await ready(h)
    await h.call("beginCompletion", check_id=h.check_id, expected=200)
    await blocked("unreviewed_tasks")
    await ready(h, count=2, mixed=True)
    assessed = tasks(await h.check())[0]
    await h.call(
        "saveReview",
        task_id=assessed["task_id"],
        payload={
            "analysis_id": assessed["analysis_id"],
            "state": "system_error",
            "comment": "",
        },
        expected=200,
    )
    await h.call("beginCompletion", check_id=h.check_id, expected=200)
    await blocked("unresolved_tasks")
    unresolved = tasks(await h.check())[-1]
    await h.call(
        "skipTask",
        task_id=unresolved["task_id"],
        payload={"analysis_id": unresolved["analysis_id"]},
        expected=200,
    )
    await h.call("finalizeCheck", check_id=h.check_id, expected=202)
    # An invalid report is unresolved until the teacher explicitly skips it.
    ids = await h.create()
    h.svc.transport = Gateway(*(["invalid_response"] * 5))
    await h.submit(ids[2], ids[3], expected=202)
    for _ in range(5):
        await h.run()
        current = await h.check()
        if current["notebooks"][0]["bundles"][0]["job"]["state"] == "failed":
            break
    await h.call("beginCompletion", check_id=ids[0], expected=200)
    await blocked("unresolved_bundles")
    await h.call(
        "skipBundle",
        bundle_id=ids[2],
        payload={"input_version_id": ids[3]},
        expected=200,
    )
    await h.call("finalizeCheck", check_id=ids[0], expected=202)
    await h.call("createNotebook", check_id=ids[0], expected=409)
    await h.call(
        "skipBundle",
        bundle_id=ids[2],
        payload={"input_version_id": ids[3]},
        expected=409,
    )


async def test_proc_c21(h, monkeypatch):
    from pilot.domain import repository

    original = repository.load_check
    for first_operation in ("finalizeCheck", "saveReview"):
        await ready(h)
        await h.review_all()
        await h.call("beginCompletion", check_id=h.check_id, expected=200)
        rev = (await h.check())["revision"]
        task = tasks(await h.check())[0]
        locked = asyncio.Event()
        release = asyncio.Event()
        second_entered = asyncio.Event()

        async def gated(*args, **kwargs):
            name = asyncio.current_task().get_name()
            if name == "second-mutation":
                second_entered.set()
            value = await original(*args, **kwargs)
            if name == "first-mutation" and kwargs.get("lock"):
                locked.set()
                await release.wait()
            return value

        monkeypatch.setattr(repository, "load_check", gated)

        async def invoke(operation):
            if operation == "finalizeCheck":
                return await h.call(operation, check_id=h.check_id, revision=rev)
            return await h.call(
                operation,
                task_id=task["task_id"],
                revision=rev,
                payload={
                    "analysis_id": task["analysis_id"],
                    "state": "system_error",
                    "comment": "",
                },
            )

        one = asyncio.create_task(invoke(first_operation), name="first-mutation")
        await asyncio.wait_for(locked.wait(), 10)
        two = asyncio.create_task(
            invoke(
                "saveReview" if first_operation == "finalizeCheck" else "finalizeCheck"
            ),
            name="second-mutation",
        )
        try:
            await asyncio.wait_for(second_entered.wait(), 10)
        finally:
            release.set()
        first, second = await asyncio.gather(one, two)
        assert first.status_code == (202 if first_operation == "finalizeCheck" else 200)
        assert (
            second.status_code == 409
            and second.json()["error"]["code"] == "revision_conflict"
        )
        snapshots = await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_snapshots WHERE check_id=$1", UUID(h.check_id)
        )
        assert snapshots == (1 if first_operation == "finalizeCheck" else 0)
        monkeypatch.setattr(repository, "load_check", original)
    # Upload and publication contend on the same parent lock, in both orders.
    from pilot.processing.queue import claim
    from pilot.processing.attempts import complete
    from pilot.processing.transport import TransportResult

    for operation in ("upload", "publish"):
        for winner in ("finalize", operation):
            await ready(h)
            await h.review_all()
            await h.call("beginCompletion", check_id=h.check_id, expected=200)
            notebook = (
                await h.call("createNotebook", check_id=h.check_id, expected=201)
            ).json()["entity_id"]
            bundle = (
                await h.call("createBundle", notebook_id=notebook, expected=201)
            ).json()["entity_id"]
            version = (await h.check())["notebooks"][-1]["bundles"][0]["draft"]["id"]
            item = None
            if operation == "publish":
                await h.call(
                    "uploadPhoto",
                    input_version_id=version,
                    files={"file": ("synthetic.png", png(), "image/png")},
                    expected=201,
                )
                submitted = await h.submit(bundle, version, expected=202)
                item = await claim(h.svc, uuid4())
                assert str(item["job"]["id"]) == submitted.json()["job"]["id"]
            rev = (await h.check())["revision"]
            locked = asyncio.Event()
            release = asyncio.Event()
            second_entered = asyncio.Event()

            async def gated(*args, **kwargs):
                name = asyncio.current_task().get_name()
                if name == "second-mutation":
                    second_entered.set()
                value = await original(*args, **kwargs)
                if name == "first-mutation" and kwargs.get("lock"):
                    locked.set()
                    await release.wait()
                return value

            monkeypatch.setattr(repository, "load_check", gated)

            async def invoke(which):
                if which == "finalize":
                    return await h.call(
                        "finalizeCheck", check_id=h.check_id, revision=rev
                    )
                if which == "upload":
                    return await h.call(
                        "uploadPhoto",
                        input_version_id=version,
                        files={"file": ("late.png", png(), "image/png")},
                        revision=rev,
                    )
                return await complete(
                    h.svc,
                    item,
                    TransportResult(
                        "success",
                        payload=report(),
                        actual_cost_rub=Decimal(".01"),
                        raw=json.dumps(report()),
                    ),
                )

            one = asyncio.create_task(invoke(winner), name="first-mutation")
            await asyncio.wait_for(locked.wait(), 10)
            two = asyncio.create_task(
                invoke(operation if winner == "finalize" else "finalize"),
                name="second-mutation",
            )
            try:
                await asyncio.wait_for(second_entered.wait(), 10)
            finally:
                release.set()
            first, second = await asyncio.gather(one, two)
            monkeypatch.setattr(repository, "load_check", original)
            if operation == "upload":
                assert first.status_code == (202 if winner == "finalize" else 201)
                assert (
                    second.status_code == 409
                    and second.json()["error"]["code"] == "revision_conflict"
                )
                assert await h.svc.pool.fetchval(
                    "SELECT count(*) FROM pilot_snapshots WHERE check_id=$1",
                    UUID(h.check_id),
                ) == int(winner == "finalize")
                assert await h.svc.pool.fetchval(
                    "SELECT count(*) FROM pilot_photo_assets WHERE check_id=$1",
                    UUID(h.check_id),
                ) == (1 if winner == "finalize" else 2)
            else:
                final_result = first if winner == "finalize" else second
                published = second if winner == "finalize" else first
                assert published is True
                assert final_result.status_code == 409
                assert final_result.json()["error"]["code"] == (
                    "completion_blocked"
                    if winner == "finalize"
                    else "revision_conflict"
                )
                assert (
                    await h.svc.pool.fetchval(
                        "SELECT count(*) FROM pilot_snapshots WHERE check_id=$1",
                        UUID(h.check_id),
                    )
                    == 0
                )
                assert len(tasks(await h.check())) == 2


async def test_proc_c22(h):
    await ready(h)
    await h.review_all()
    await h.call("beginCompletion", check_id=h.check_id, expected=200)
    rev = (await h.check())["revision"]
    keys = [uuid4(), uuid4()]
    results = await asyncio.gather(
        *(
            h.call("finalizeCheck", check_id=h.check_id, revision=rev, key=k)
            for k in keys
        )
    )
    assert sorted(r.status_code for r in results) == [202, 409]
    winner = next(i for i, r in enumerate(results) if r.status_code == 202)
    replay = await h.call(
        "finalizeCheck",
        check_id=h.check_id,
        revision=rev,
        key=keys[winner],
        expected=202,
    )
    assert replay.json() == results[winner].json()
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_snapshots") == 1
    snap = json.loads(await h.svc.pool.fetchval("SELECT payload FROM pilot_snapshots"))
    assert not any(
        x in json.dumps(snap)
        for x in ["comment", "Синтетическая проверка", "normalized_path"]
    )
    before = await h.svc.pool.fetchval("SELECT count(*) FROM pilot_jobs")
    for _ in range(10):
        await h.call("getSummary", check_id=h.check_id, expected=200)
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_jobs") == before


async def test_proc_c24(h, caplog):
    ids, _, _ = await ready(h)
    before = (await h.check())["revision"]
    await h.call("getBundleHistory", actor="staff", bundle_id=ids[2], expected=200)
    photo = (await h.check())["notebooks"][0]["bundles"][0]["current_input"]["photos"][
        0
    ]["id"]
    await h.call("getPhoto", actor="staff", photo_id=photo, expected=200)
    await h.call("getPhoto", actor="t2", photo_id=photo, expected=404)
    assert (await h.check())["revision"] == before
    assert (
        await h.svc.pool.fetchval("SELECT count(*) FROM pilot_audit WHERE role='staff'")
        >= 2
    )
    assert "synthetic-test-password-47" not in caplog.text
