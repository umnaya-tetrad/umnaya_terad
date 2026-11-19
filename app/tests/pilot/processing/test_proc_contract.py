import asyncio
import copy
import json
import os
import socket
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from ..harness import ROOT
from ..scenarios import Gateway, ready, report, tasks, wallet, finalize

pytestmark = pytest.mark.asyncio


async def child(h, mode="once", *args):
    path = h.svc.storage_root.parent / "declared-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report()), encoding="utf-8")
    env = {
        **os.environ,
        "DATABASE_URL": h.svc.test_database_url,
        "PILOT_STORAGE_ROOT": str(h.svc.storage_root),
        "PILOT_TEST_REPORT": str(path),
        "PILOT_TEST_CHILD_OUTCOME": getattr(h.svc, "test_child_outcome", "success"),
        "PILOT_TEST_GATE": "1" if getattr(h.svc, "test_gateway_gate", False) else "0",
        "PILOT_TEST_BARRIER": "1"
        if getattr(h.svc, "test_worker_barrier", False)
        else "0",
        "PYTHONPATH": str(ROOT / "app"),
        "PYTHONPYCACHEPREFIX": str(ROOT.parent / ".cache/processing-bytecode"),
    }
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.pilot.child_runtime",
        mode,
        *map(str, args),
        cwd=ROOT / "app",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def finish(process):
    out, err = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode == 0, (out.decode(), err.decode())


async def wait_sql(h, query, expected):
    async def poll():
        while await h.svc.pool.fetchval(query) != expected:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), 15)


async def test_proc_c05(h):
    ids = await h.create()
    key = uuid4()
    revision = (await h.check())["revision"]
    response = await h.submit(ids[2], ids[3], key=key, revision=revision, expected=202)
    await h.svc.pool.execute("CREATE TABLE test_gateway_calls(job_id UUID,kind TEXT)")
    # The ASGI process genuinely stops and starts, against the same PG/storage.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    for _ in range(2):
        backend = await child(h, "serve", port)
        try:
            cookies = "; ".join(
                f"{key}={value}" for key, value in h.clients["t1"].cookies.items()
            )
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", headers={"Cookie": cookies}
            ) as client:
                for attempt in range(100):
                    try:
                        got = await client.get("/api/checks/" + ids[0])
                        break
                    except httpx.ConnectError:
                        await asyncio.sleep(0.05)
                else:
                    raise AssertionError("child backend did not start")
                assert got.status_code == 200, got.text
                assert (
                    got.json()["notebooks"][0]["bundles"][0]["current_input"]["id"]
                    == ids[3]
                )
        finally:
            backend.terminate()
            await backend.communicate()
    process = await child(h)
    await finish(process)
    replay = await h.submit(ids[2], ids[3], key=key, revision=revision, expected=202)
    assert replay.json() == response.json()
    assert len(tasks(await h.check())) == 1
    assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 1
    process = await child(h)
    await finish(process)
    assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 1


async def test_proc_c09(h):
    for count, photos, continued in [
        (1, 1, False),
        (2, 1, False),
        (1, 2, True),
        (2, 2, True),
    ]:
        h.svc.transport = Gateway(page_report=report(count, continuation=continued))
        ids = await h.create(photos=photos)
        await h.submit(ids[2], ids[3], expected=202)
        await h.run()
        items = tasks(await h.check())
        assert len(items) == count
        assert items[0]["analysis"]["photo_indices"] == ([1, 2] if continued else [1])
        assert len(items[0]["analysis"]["evidence"]) <= 4
    invalid = report()
    invalid["tasks"][0]["photo_indices"] = [99]
    h.svc.transport = Gateway(page_report=invalid)
    ids = await h.create()
    result = await h.submit(ids[2], ids[3], expected=202)
    await h.run()
    job = (
        await h.call("getJob", job_id=result.json()["job"]["id"], expected=200)
    ).json()
    assert job["state"] == "failed" and job["reason"] == "invalid_response"
    assert tasks(await h.check()) == []
    correct = report()
    correct["tasks"][0].update(
        result="all_steps_correct",
        first_error=None,
        completeness="incomplete",
        completeness_note="Решение не завершено",
    )
    h.svc.transport = Gateway(page_report=correct)
    ids = await h.create()
    submitted = await h.submit(ids[2], ids[3], expected=202)
    await h.run()
    incomplete = tasks(await h.check())[0]["analysis"]
    assert (
        incomplete["result"] == "all_steps_correct"
        and incomplete["completeness"] == "incomplete"
        and incomplete["first_error"] is None
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT auto_retry_count FROM pilot_jobs WHERE id=$1",
            UUID(submitted.json()["job"]["id"]),
        )
        == 0
    )


async def test_proc_c15(h):
    from pilot.processing.queue import claim, renew
    from pilot.processing.worker import recover_expired
    from pilot.processing.attempts import complete
    from pilot.processing.transport import TransportResult

    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    await h.svc.pool.execute("CREATE TABLE test_gateway_calls(job_id UUID,kind TEXT)")
    await h.svc.pool.execute("CREATE TABLE test_worker_ready(pid INTEGER)")
    await h.svc.pool.execute(
        "CREATE TABLE test_gateway_control(start_released BOOLEAN,dispatch_released BOOLEAN)"
    )
    await h.svc.pool.execute("INSERT INTO test_gateway_control VALUES(false,true)")
    h.svc.test_worker_barrier = True
    workers = await asyncio.gather(child(h), child(h))
    await wait_sql(h, "SELECT count(*) FROM test_worker_ready", 2)
    await h.svc.pool.execute("UPDATE test_gateway_control SET start_released=true")
    await asyncio.gather(*(finish(p) for p in workers))
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_attempts") == 1
    assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 1
    assert len(tasks(await h.check())) == 1
    # Fault injection before any actual provider call: the old epoch must be
    # fenced after durable recovery and a new process publishes a fresh result.
    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    wid = uuid4()
    old = await claim(h.svc, wid)
    await h.svc.pool.execute(
        "UPDATE pilot_attempts SET dispatched=false WHERE id=$1", old["attempt_id"]
    )
    await h.svc.pool.execute(
        "UPDATE pilot_jobs SET lease_until=now()-interval '1 second' WHERE id=$1",
        old["job"]["id"],
    )
    await recover_expired(h.svc)
    assert not await renew(h.svc, old["job"], wid)
    restarted = await child(h)
    await finish(restarted)
    assert len(tasks(await h.check())) == 1
    before = (await h.check())["revision"]
    stale = TransportResult(
        "success",
        payload=report(),
        actual_cost_rub=Decimal(".01"),
        raw=json.dumps(report()),
    )
    assert not await complete(h.svc, old, stale)
    assert (await h.check())["revision"] == before
    assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 2
    # Three genuinely separate processes contend for three different Jobs,
    # including analytics. A process-local semaphore cannot satisfy this test.
    await ready(h)
    analytic = await finalize(h)
    jobs = [UUID(analytic.json()["job"]["id"])]
    for actor in ("t1", "t2"):
        ids = await h.create(actor=actor)
        accepted = await h.submit(ids[2], ids[3], actor=actor, expected=202)
        jobs.append(UUID(accepted.json()["job"]["id"]))
    await h.svc.pool.execute("TRUNCATE test_worker_ready")
    await h.svc.pool.execute(
        "UPDATE test_gateway_control SET start_released=false,dispatch_released=false"
    )
    h.svc.test_gateway_gate = True
    workers = await asyncio.gather(child(h), child(h), child(h))
    try:
        await wait_sql(h, "SELECT count(*) FROM test_worker_ready", 3)
        await h.svc.pool.execute("UPDATE test_gateway_control SET start_released=true")
        await wait_sql(h, "SELECT count(*) FROM test_gateway_calls", 4)

        async def one_declines():
            while all(p.returncode is None for p in workers):
                await asyncio.sleep(0.01)

        await asyncio.wait_for(one_declines(), 15)
        assert (
            await h.svc.pool.fetchval(
                "SELECT count(*) FROM pilot_slots WHERE attempt_id IS NOT NULL"
            )
            == 2
        )
        assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 4
    finally:
        await h.svc.pool.execute(
            "UPDATE test_gateway_control SET dispatch_released=true,start_released=true"
        )
        await asyncio.gather(*(finish(p) for p in workers))
    last = await child(h)
    await finish(last)
    assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 5
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_jobs WHERE id=ANY($1::uuid[]) AND state='succeeded'",
            jobs,
        )
        == 3
    )


async def test_proc_c16(h):
    await h.svc.pool.execute("CREATE TABLE test_gateway_calls(job_id UUID,kind TEXT)")
    for outcomes, state in [
        (("temporary_failure", "success"), "succeeded"),
        (("temporary_failure", "temporary_failure"), "failed"),
    ]:
        gateway = Gateway(*outcomes)
        h.svc.transport = gateway
        ids = await h.create()
        submitted = await h.submit(ids[2], ids[3], expected=202)
        await h.run()
        await h.svc.pool.execute(
            "UPDATE pilot_jobs SET next_run_at=now() WHERE state='retry_wait'"
        )
        h.svc.test_child_outcome = outcomes[1]
        restarted = await child(h)
        await finish(restarted)
        await h.run()
        job = await h.call("getJob", job_id=submitted.json()["job"]["id"], expected=200)
        assert job.json()["state"] == state and len(gateway.calls) == 1
        assert (
            await h.svc.pool.fetchval(
                "SELECT count(*) FROM test_gateway_calls WHERE job_id=$1",
                UUID(submitted.json()["job"]["id"]),
            )
            == 1
        )
        assert (
            await h.svc.pool.fetchval(
                "SELECT count(*) FROM pilot_attempts WHERE job_id=$1",
                UUID(submitted.json()["job"]["id"]),
            )
            == 2
        )


async def test_proc_c17(h):
    from pilot.processing.worker import recover_expired
    from pilot.processing.budget import get_budget

    ids = await h.create()
    response = await h.submit(ids[2], ids[3], expected=202)
    await h.svc.pool.execute("CREATE TABLE test_gateway_calls(job_id UUID,kind TEXT)")
    await h.svc.pool.execute(
        "CREATE TABLE test_gateway_control(start_released BOOLEAN,dispatch_released BOOLEAN)"
    )
    await h.svc.pool.execute("INSERT INTO test_gateway_control VALUES(true,false)")
    h.svc.test_gateway_gate = True
    worker = await child(h)
    try:
        await wait_sql(h, "SELECT count(*) FROM test_gateway_calls", 1)
    finally:
        worker.terminate()
        await worker.communicate()
    await h.svc.pool.execute(
        "UPDATE pilot_jobs SET lease_until=now()-interval '1 second'"
    )
    await recover_expired(h.svc)
    job = (
        await h.call("getJob", job_id=response.json()["job"]["id"], expected=200)
    ).json()
    assert job["state"] == "unknown" and not job["can_retry"]
    hold = (await get_budget(h.svc)).held_rub
    assert hold == 1
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_attempts WHERE state='unknown' AND actual_cost_rub IS NULL"
        )
        == 1
    )
    await recover_expired(h.svc)
    restarted = await child(h)
    await finish(restarted)
    assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 1
    await h.call(
        "skipBundle",
        bundle_id=ids[2],
        payload={"input_version_id": ids[3]},
        expected=200,
    )
    assert (await get_budget(h.svc)).held_rub == hold
    # Repeat the crash-after-dispatch scenario for class analytics. Its immutable
    # snapshot and unknown cost survive a real worker process restart.
    await ready(h)
    finalized = await finalize(h)
    analytics_id = UUID(finalized.json()["job"]["id"])
    snapshot_id = UUID(finalized.json()["job"]["input_id"])
    worker = await child(h)
    try:
        await wait_sql(h, "SELECT count(*) FROM test_gateway_calls", 2)
    finally:
        worker.terminate()
        await worker.communicate()
    await h.svc.pool.execute(
        "UPDATE pilot_jobs SET lease_until=now()-interval '1 second' WHERE id=$1",
        analytics_id,
    )
    await recover_expired(h.svc)
    summary = (await h.call("getSummary", check_id=h.check_id, expected=200)).json()
    assert (
        summary["state"] == "unknown"
        and not summary["can_retry"]
        and not summary["can_refresh"]
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_snapshots WHERE id=$1", snapshot_id
        )
        == 1
    )
    await h.call("retrySummary", check_id=h.check_id, expected=409)
    restarted = await child(h)
    await finish(restarted)
    assert await h.svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls") == 2
    unknown_before = await h.svc.pool.fetchval(
        "SELECT count(*) FROM pilot_attempts WHERE state='unknown' AND actual_cost_rub IS NULL"
    )
    assert unknown_before == 2
    assert (await get_budget(h.svc)).held_rub == hold + 1
    await h.call("deleteCheck", check_id=h.check_id, expected=200)
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_attempts WHERE state='unknown' AND actual_cost_rub IS NULL"
        )
        == unknown_before
    )
    assert (await get_budget(h.svc)).held_rub == hold + 1


async def test_proc_c18(h):
    from pilot.processing.queue import claim
    from pilot.processing.worker import recover_expired
    from pilot.processing.attempts import complete
    from pilot.processing.transport import TransportResult
    from pilot.processing.budget import get_budget
    from pilot.processing.reconciliation import (
        reconcile_attempt,
        ReconciliationEvidence,
    )

    ids = await h.create()
    submitted = await h.submit(ids[2], ids[3], expected=202)
    claimed = await claim(h.svc, uuid4())
    assert claimed is not None
    await h.svc.pool.execute(
        "UPDATE pilot_jobs SET lease_until=now()-interval '1 second' WHERE id=$1",
        UUID(submitted.json()["job"]["id"]),
    )
    await recover_expired(h.svc)
    job = (
        await h.call("getJob", job_id=submitted.json()["job"]["id"], expected=200)
    ).json()
    assert job["state"] == "unknown"
    hold = (await get_budget(h.svc)).held_rub
    assert hold == 1
    assert (
        await h.svc.pool.fetchval(
            "SELECT actual_cost_rub FROM pilot_attempts WHERE id=$1",
            claimed["attempt_id"],
        )
        is None
    )
    await h.call(
        "skipBundle",
        bundle_id=ids[2],
        payload={"input_version_id": ids[3]},
        expected=200,
    )
    await h.call("beginCompletion", check_id=ids[0], expected=200)
    await h.call("finalizeCheck", check_id=ids[0], expected=202)
    h.svc.transport = None
    assert await h.run()
    summary = (await h.call("getSummary", check_id=ids[0], expected=200)).json()
    assert summary["state"] == "succeeded"
    assert summary["result"]["notebooks"] == {
        "total": 1,
        "with_errors": 0,
        "without_errors": 0,
        "partial": 1,
        "empty": 0,
    }
    assert summary["result"]["average_errors_per_notebook"] is None
    baseline = await h.check()
    reports = await h.svc.pool.fetchval("SELECT count(*) FROM pilot_bundle_reports")
    late = TransportResult(
        "success",
        payload=report(),
        actual_cost_rub=Decimal(".2"),
        provider_request_id="synthetic-late",
        raw=json.dumps(report()),
    )
    assert not await complete(h.svc, claimed, late)
    assert (await get_budget(h.svc)).held_rub == hold
    assert (
        await h.svc.pool.fetchval(
            "SELECT actual_cost_rub FROM pilot_attempts WHERE id=$1",
            claimed["attempt_id"],
        )
        is None
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT state FROM pilot_attempts WHERE id=$1", claimed["attempt_id"]
        )
        == "unknown"
    )
    assert (
        await h.svc.pool.fetchval("SELECT count(*) FROM pilot_bundle_reports")
        == reports
    )
    assert (await h.check())["data_revision"] == baseline["data_revision"]
    assert tasks(await h.check()) == []
    assert (await h.call("getSummary", check_id=ids[0], expected=200)).json() == summary
    evidence = ReconciliationEvidence(
        reference="synthetic verified late evidence",
        sha256="7" * 64,
        actual_cost_rub=Decimal(".2"),
        provider_request_id="synthetic-late",
    )
    rid = uuid4()
    first = await reconcile_attempt(
        h.svc,
        attempt_id=claimed["attempt_id"],
        outcome="settled",
        evidence=evidence,
        operator_ref="pytest",
        request_id=rid,
    )
    second = await reconcile_attempt(
        h.svc,
        attempt_id=claimed["attempt_id"],
        outcome="settled",
        evidence=evidence,
        operator_ref="pytest",
        request_id=rid,
    )
    assert first.changed and not second.changed
    assert (await get_budget(h.svc)).held_rub == 0
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_fund_ledger WHERE attempt_id=$1 AND operation='settlement'",
            claimed["attempt_id"],
        )
        == 1
    )
    assert await h.svc.pool.fetchval(
        "SELECT actual_cost_rub FROM pilot_attempts WHERE id=$1", claimed["attempt_id"]
    ) == Decimal(".2")


async def test_proc_c19(h):
    from pilot.processing.providers import build_request
    from pilot.processing.checker import load_prompt

    ids = await h.create(photos=2)
    await h.submit(ids[2], ids[3], expected=202)
    # Explicit fixture sends no external HTTP and is not selected by missing key.
    gateway = Gateway()
    h.svc.transport = gateway
    await h.run()
    assert len(gateway.calls) == 1 and gateway.calls[0][1] == "page_check"
    images = gateway.calls[0][2]["images"]
    assert len(images) == 2
    h.svc.settings.polza_api_key = "synthetic-builder-only-no-network"
    request, _ = build_request(h.svc, {"kind": "page_check"}, gateway.calls[0][2])
    assert request["messages"][0]["content"] == load_prompt()
    encoded = request["messages"][1]["content"]
    assert [x["image_url"]["detail"] for x in encoded if x["type"] == "image_url"] == [
        "high",
        "high",
    ]


async def test_proc_c27(h):
    """Atomic shared cap, hot CLI update, and the original live worker identities."""
    from pilot.processing.budget import get_budget, set_spend_limit

    initial = await get_budget(h.svc)
    assert (
        initial.spend_limit_rub == 500
        and initial.spent_rub == 0
        and initial.held_rub == 0
    )
    await ready(h)
    await finalize(h)
    analytics_job = (
        await h.call("getSummary", check_id=h.check_id, expected=200)
    ).json()["job_id"]
    second = await h.create(actor="t2")
    page = await h.submit(second[2], second[3], actor="t2", expected=202)
    job_ids = {analytics_job, page.json()["job"]["id"]}
    baseline = (await get_budget(h.svc)).spent_rub
    await set_spend_limit(
        h.svc, spend_limit_rub=baseline + 10, operator_ref="pytest", request_id=uuid4()
    )
    h.svc.fixture_request_bound = Decimal(6)
    gateway = Gateway()
    gateway.release = asyncio.Event()
    h.svc.transport = gateway
    worker_ids = [uuid4(), uuid4()]
    runs = [asyncio.create_task(h.run(wid)) for wid in worker_ids]
    try:
        await asyncio.wait_for(gateway.entered.wait(), 10)
        done, pending = await asyncio.wait(
            runs, timeout=10, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(done) == 1 and not next(iter(done)).result()
        budget = await get_budget(h.svc)
        assert (
            budget.held_rub == 6
            and budget.available_rub == 4
            and len(gateway.calls) == 1
        )
        assert not await h.svc.pool.fetchval(
            "SELECT initialized FROM pilot_funds WHERE mode='fixture'"
        )
        # Change the canonical cap from an actual second Python process while
        # the first worker is still waiting on its accepted provider request.
        request = uuid4()
        env = {
            **os.environ,
            "DATABASE_URL": h.svc.test_database_url,
            "PILOT_TRANSPORT": "fixture",
            "PYTHONPATH": str(ROOT / "app"),
        }
        for _ in range(2):
            cli = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pilot.processing.budget",
                "set-limit",
                "--rub",
                str(baseline + 15),
                "--request-id",
                str(request),
                "--operator-ref",
                "pytest-container-shell",
                cwd=ROOT / "app",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(cli.communicate(), 15)
            assert cli.returncode == 0, (out.decode(), err.decode())
            assert Decimal(json.loads(out)["spend_limit_rub"]) == baseline + 15
        assert (
            await h.svc.pool.fetchval(
                "SELECT count(*) FROM pilot_budget_changes WHERE request_id=$1", request
            )
            == 1
        )
        assert gateway.active == 1
        gateway.entered.clear()
        resumed_id = worker_ids[runs.index(next(iter(done)))]
        runs.append(asyncio.create_task(h.run(resumed_id)))
        await asyncio.wait_for(gateway.entered.wait(), 10)
        budget = await get_budget(h.svc)
        assert budget.held_rub == 12 and budget.available_rub == 3
        assert {c[0] for c in gateway.calls} == job_ids
    finally:
        gateway.release.set()
        await asyncio.gather(*runs)
    budget = await get_budget(h.svc)
    assert budget.spent_rub == baseline + Decimal(".02") and budget.held_rub == 0
    assert not budget.paused
    assert {c[1] for c in gateway.calls} == {"page_check", "class_analytics"}
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_jobs WHERE id=ANY($1::uuid[])",
            [UUID(x) for x in job_ids],
        )
        == 2
    )


async def test_proc_c28(h):
    from pilot.processing.control import set_processing_paused, get_processing_control

    await ready(h)
    await finalize(h)
    for _ in range(2):
        ids = await h.create()
        await h.submit(ids[2], ids[3], expected=202)
    gateway = Gateway()
    gateway.release = asyncio.Event()
    h.svc.transport = gateway
    running = asyncio.create_task(h.run())
    await asyncio.wait_for(gateway.entered.wait(), 10)
    try:
        await set_processing_paused(
            h.svc,
            paused=True,
            operator_ref="pytest",
            reason="synthetic",
            request_id=uuid4(),
        )
        await h.run()
        assert len(gateway.calls) == 1
        await h.check()
    finally:
        gateway.release.set()
        await running
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_attempts WHERE state='settled'"
        )
        == 2
    )
    await set_processing_paused(
        h.svc,
        paused=False,
        operator_ref="pytest",
        reason="synthetic",
        request_id=uuid4(),
    )
    await h.run()
    await h.run()
    assert len(gateway.calls) == 3
    assert not (await get_processing_control(h.svc)).paused
    assert (await h.clients["t1"].post("/api/admin/pause")).status_code == 404


async def test_proc_c29(h):
    """Useful output with missing billing is published, held, then reconciled once."""
    from pilot.processing.reconciliation import (
        reconcile_attempt,
        ReconciliationEvidence,
    )
    from pilot.processing.budget import get_budget

    gateway = Gateway()
    gateway.actual_cost = None
    h.svc.transport = gateway
    ids = await h.create()
    submitted = await h.submit(ids[2], ids[3], expected=202)
    await h.run()
    assert len(tasks(await h.check())) == 1
    assert (
        await h.call("getJob", job_id=submitted.json()["job"]["id"], expected=200)
    ).json()["state"] == "succeeded"
    await finalize(h)
    await h.run()
    summary = (await h.call("getSummary", check_id=ids[0], expected=200)).json()
    assert summary["state"] == "succeeded" and summary["result"] is not None
    attempts = await h.svc.pool.fetch(
        "SELECT * FROM pilot_attempts ORDER BY created_at"
    )
    assert len(attempts) == 2
    assert all(
        a["state"] == "settled"
        and a["billing_state"] == "unknown"
        and a["actual_cost_rub"] is None
        for a in attempts
    )
    budget = await get_budget(h.svc)
    assert (
        budget.spent_rub == 0 and budget.held_rub == 2 and budget.available_rub == 498
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_slots WHERE attempt_id IS NOT NULL"
        )
        == 0
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_fund_ledger WHERE operation='settlement'"
        )
        == 0
    )
    task = tasks(await h.check())[0]
    await h.call(
        "saveReview",
        task_id=task["task_id"],
        payload={
            "analysis_id": task["analysis_id"],
            "state": "system_error",
            "comment": "",
        },
        expected=200,
    )
    stale = (await h.call("getSummary", check_id=ids[0], expected=200)).json()
    assert stale["stale"] and stale["can_refresh"]
    await h.call("refreshSummary", check_id=ids[0], expected=202)
    # A proven execution outcome without a bill does not fabricate a zero cost.
    no_bill = ReconciliationEvidence(
        reference="synthetic execution proved; billing pending",
        sha256="c" * 64,
        actual_cost_rub=None,
        provider_request_id="synthetic-no-bill",
    )
    await reconcile_attempt(
        h.svc,
        attempt_id=attempts[0]["id"],
        outcome="settled",
        evidence=no_bill,
        operator_ref="pytest",
        request_id=uuid4(),
    )
    assert (await get_budget(h.svc)).held_rub == 2
    for a in attempts:
        evidence = ReconciliationEvidence(
            reference="synthetic final invoice",
            sha256="d" * 64,
            actual_cost_rub=Decimal(".2"),
            provider_request_id="synthetic-known",
        )
        request = uuid4()
        first = await reconcile_attempt(
            h.svc,
            attempt_id=a["id"],
            outcome="settled",
            evidence=evidence,
            operator_ref="pytest",
            request_id=request,
        )
        replay = await reconcile_attempt(
            h.svc,
            attempt_id=a["id"],
            outcome="settled",
            evidence=evidence,
            operator_ref="pytest",
            request_id=request,
        )
        assert first.changed and not replay.changed
        assert await h.svc.pool.fetchval(
            "SELECT actual_cost_rub FROM pilot_attempts WHERE id=$1", a["id"]
        ) == Decimal(".2")
        assert (
            await h.svc.pool.fetchval(
                "SELECT count(*) FROM pilot_fund_ledger WHERE attempt_id=$1 AND operation='settlement'",
                a["id"],
            )
            == 1
        )
    budget = await get_budget(h.svc)
    assert (
        budget.spent_rub == Decimal(".4") and budget.held_rub == 0 and not budget.paused
    )
    history = (
        await h.call("getSummaryHistory", actor="staff", check_id=ids[0], expected=200)
    ).json()
    assert (
        next(
            x["summary"]
            for x in history["items"]
            if x["summary"]["job_id"] == summary["job_id"]
        )["result"]
        == summary["result"]
    )
    assert not await h.svc.pool.fetchval(
        "SELECT initialized FROM pilot_funds WHERE mode='fixture'"
    )


async def test_proc_c30(h):
    gateway = Gateway(page_report=report(3))
    h.svc.transport = gateway
    for actor in ("t1", "t2"):
        first = await h.create(actor=actor)
        check_id = first[0]
        notebooks = [first[1:]]
        for _ in range(29):
            n = (
                await h.call(
                    "createNotebook", actor=actor, check_id=check_id, expected=201
                )
            ).json()["entity_id"]
            b = (
                await h.call("createBundle", actor=actor, notebook_id=n, expected=201)
            ).json()["entity_id"]
            c = await h.check(actor)
            bundle = next(
                bu for no in c["notebooks"] for bu in no["bundles"] if bu["id"] == b
            )
            v = bundle["draft"]["id"]
            from ..harness import png

            await h.call(
                "uploadPhoto",
                actor=actor,
                input_version_id=v,
                files={"file": ("synthetic.png", png(), "image/png")},
                expected=201,
            )
            notebooks.append((n, b, v))
        for _, b, v in notebooks:
            await h.submit(b, v, actor=actor, expected=202)

    async def worker():
        while await h.run():
            pass

    await asyncio.gather(worker(), worker())
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_notebooks") == 60
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_bundle_reports") == 60
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_task_analyses WHERE NOT deleted"
        )
        == 180
    )
    assert gateway.maximum <= 2 and len(gateway.calls) == 60
    # More stale candidates than the former LIMIT100 must not starve either
    # kind behind them. Stale snapshots must consume neither POSTs nor money.
    stale = []
    async with h.svc.pool.acquire() as con, con.transaction():
        for _ in range(105):
            cid, sid, jid = uuid4(), uuid4(), uuid4()
            stale.append(jid)
            await con.execute(
                "INSERT INTO pilot_checks(id,owner_id,title,phase,data_revision) VALUES($1,$2,'synthetic stale','finalized',1)",
                cid,
                UUID(h.ids["t1"]),
            )
            await con.execute(
                "INSERT INTO pilot_snapshots(id,check_id,data_revision,payload) VALUES($1,$2,0,'{}')",
                sid,
                cid,
            )
            await con.execute(
                "INSERT INTO pilot_jobs(id,check_id,kind,snapshot_id,next_run_at) VALUES($1,$2,'class_analytics',$3,now()-interval '1 day')",
                jid,
                cid,
                sid,
            )
            await con.execute(
                "UPDATE pilot_checks SET selected_summary_job_id=$2 WHERE id=$1",
                cid,
                jid,
            )
    settlements_before = await h.svc.pool.fetchval(
        "SELECT count(*) FROM pilot_fund_ledger WHERE operation='settlement'"
    )
    fresh = Gateway()
    h.svc.transport = fresh
    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    assert await h.run()
    assert len(tasks(await h.check())) == 1
    await finalize(h)
    assert await h.run()
    assert (await h.call("getSummary", check_id=h.check_id, expected=200)).json()[
        "state"
    ] == "succeeded"
    assert len(fresh.calls) == 2 and {c[1] for c in fresh.calls} == {
        "page_check",
        "class_analytics",
    }
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_attempts WHERE job_id=ANY($1::uuid[])", stale
        )
        == 0
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_fund_ledger WHERE operation='settlement'"
        )
        == settlements_before + 2
    )
