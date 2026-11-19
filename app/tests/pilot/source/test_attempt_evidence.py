import asyncio
import json
import os
import sys
from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from pilot.processing.queue import claim, recover_expired
from pilot.processing.providers import run_job
from pilot.processing.attempts import complete
from pilot.processing.worker import run_once
from pilot.processing.transport import TransportResult
from pilot.processing.reconciliation import reconcile_attempt, ReconciliationEvidence
from ..scenarios import ready, wallet, finalize, Gateway


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["page_check", "class_analytics"])
async def test_old_epoch_retains_hold_until_trusted_reconciliation(h, kind):
    if kind == "page_check":
        await wallet(h.svc)
        h.svc.transport = Gateway()
        ids = await h.create()
        await h.submit(ids[2], ids[3], expected=202)
    else:
        ids, _, _ = await ready(h)
        await finalize(h)
    item = await claim(h.svc, uuid4())
    result = await run_job(h.svc, item["job"], item["payload"])
    assert result.outcome == "success"
    await h.svc.pool.execute(
        "UPDATE pilot_jobs SET lease_until=now()-interval '1 second' WHERE id=$1",
        item["job"]["id"],
    )
    await recover_expired(h.svc)
    hold = await h.svc.pool.fetchval(
        "SELECT held_rub FROM pilot_processing_budget WHERE mode='fixture'"
    )
    assert hold > 0
    assert not await complete(h.svc, item, result)
    attempt = await h.svc.pool.fetchrow(
        "SELECT * FROM pilot_attempts WHERE id=$1", item["attempt_id"]
    )
    assert attempt["state"] == "unknown" and attempt["actual_cost_rub"] is None
    assert (
        await h.svc.pool.fetchval(
            "SELECT held_rub FROM pilot_processing_budget WHERE mode='fixture'"
        )
        == hold
    )
    assert json.loads(attempt["diagnostics"])["actual_cost_rub"] == str(
        result.actual_cost_rub
    )
    evidence = ReconciliationEvidence(
        "synthetic provider check",
        "a" * 64,
        result.actual_cost_rub,
        "synthetic-provider",
    )
    req = uuid4()
    first = await reconcile_attempt(
        h.svc,
        attempt_id=item["attempt_id"],
        outcome="settled",
        evidence=evidence,
        operator_ref="pytest",
        request_id=req,
    )
    again = await reconcile_attempt(
        h.svc,
        attempt_id=item["attempt_id"],
        outcome="settled",
        evidence=evidence,
        operator_ref="pytest",
        request_id=req,
    )
    assert first.changed and not again.changed
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_fund_ledger WHERE attempt_id=$1 AND operation='settlement'",
            item["attempt_id"],
        )
        == 1
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT held_rub FROM pilot_processing_budget WHERE mode='fixture'"
        )
        == 0
    )
    if kind == "page_check":
        await h.call(
            "retryBundle",
            bundle_id=ids[2],
            payload={"input_version_id": ids[3]},
            expected=202,
        )
    else:
        summary = (await h.call("getSummary", check_id=ids[0], expected=200)).json()
        assert summary["state"] == "failed" and summary["can_retry"]
        await h.call("retrySummary", check_id=ids[0], expected=202)


@pytest.mark.asyncio
async def test_unknown_diagnostics_safe_allowlist_survives_reader_process_restart(
    h, tmp_path, caplog
):
    await wallet(h.svc)
    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    marker = "PRIVATE-RAW-COMMENT-COOKIE-PASSWORD-KEY-BASE64-MARKER"

    async def provider(job, payload):
        return TransportResult(
            "unknown",
            raw=None,
            http_status=None,
            elapsed_seconds=300.125,
            error_code="ReadTimeout",
            usage={
                "prompt_tokens": 42,
                "completion_tokens": 7,
                "total_tokens": 49,
                "reasoning_tokens": 3,
                "password": marker,
                "arbitrary": marker,
            },
        )

    h.svc.transport = provider
    await run_once(h.svc)
    a = await h.svc.pool.fetchrow("SELECT * FROM pilot_attempts")
    assert a["ended_at"] is not None and a["raw_response"] is None
    env = {
        **os.environ,
        "PILOT_TEST_DATABASE_URL": h.svc.test_database_url,
        "PILOT_TEST_ATTEMPT_ID": str(a["id"]),
    }
    code = "import asyncio,asyncpg,os;from uuid import UUID\nasync def main():\n c=await asyncpg.connect(os.environ['PILOT_TEST_DATABASE_URL']);v=await c.fetchval('SELECT diagnostics FROM pilot_attempts WHERE id=$1',UUID(os.environ['PILOT_TEST_ATTEMPT_ID']));print(v);await c.close()\nasyncio.run(main())"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await process.communicate()
    assert process.returncode == 0, err.decode()
    diagnostics = json.loads(out)
    assert (
        diagnostics["error_code"] == "ReadTimeout"
        and diagnostics["elapsed_seconds"] == 300.125
    )
    assert diagnostics["usage"] == {
        "prompt_tokens": 42,
        "completion_tokens": 7,
        "total_tokens": 49,
        "reasoning_tokens": 3,
    }
    assert (
        diagnostics["actual_cost_rub"] is None
        and marker not in out.decode()
        and marker not in caplog.text
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["page_check", "class_analytics"])
async def test_current_unknown_with_known_cost_retains_hold_until_trusted_reconciliation(
    h, kind
):
    if kind == "page_check":
        await wallet(h.svc)
        ids = await h.create()
        await h.submit(ids[2], ids[3], expected=202)
    else:
        ids, _, _ = await ready(h)
        await finalize(h)

    async def unknown_cost(job, payload):
        return TransportResult(
            "unknown",
            actual_cost_rub=Decimal(".3"),
            http_status=500,
            error_code="http_500",
        )

    h.svc.transport = unknown_cost
    await run_once(h.svc)
    row = await h.svc.pool.fetchrow(
        "SELECT a.* FROM pilot_attempts a JOIN pilot_jobs j ON a.job_id=j.id WHERE j.kind=$1 ORDER BY a.created_at DESC LIMIT 1",
        kind,
    )
    assert row["state"] == "unknown" and row["actual_cost_rub"] is None
    assert json.loads(row["diagnostics"])["actual_cost_rub"] == "0.3"
    held = await h.svc.pool.fetchval(
        "SELECT active FROM pilot_fund_reservations WHERE attempt_id=$1", row["id"]
    )
    assert held
    evidence = ReconciliationEvidence(
        "synthetic outcome check", "b" * 64, Decimal(".3"), "synthetic-500"
    )
    result = await reconcile_attempt(
        h.svc,
        attempt_id=row["id"],
        outcome="settled",
        evidence=evidence,
        operator_ref="pytest",
        request_id=uuid4(),
    )
    assert result.changed and result.held_rub == 0
    if kind == "page_check":
        await h.call(
            "retryBundle",
            bundle_id=ids[2],
            payload={"input_version_id": ids[3]},
            expected=202,
        )
    else:
        await h.call("retrySummary", check_id=ids[0], expected=202)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["page_check", "class_analytics"])
@pytest.mark.parametrize("late", [False, True], ids=["current", "late"])
async def test_unknown_overbound_observation_extends_hold_without_auto_pause(
    h, kind, late
):
    if kind == "page_check":
        await wallet(h.svc)
        ids = await h.create()
        await h.submit(ids[2], ids[3], expected=202)
    else:
        ids, _, _ = await ready(h)
        await finalize(h)
    item = await claim(h.svc, uuid4())
    if late:
        await h.svc.pool.execute(
            "UPDATE pilot_jobs SET lease_until=now()-interval '1 second' WHERE id=$1",
            item["job"]["id"],
        )
        await recover_expired(h.svc)
    result = TransportResult(
        "unknown", actual_cost_rub=Decimal(2), http_status=500, error_code="http_500"
    )
    await complete(h.svc, item, result)
    state = await h.svc.pool.fetchrow(
        "SELECT * FROM pilot_processing_budget WHERE mode='fixture'"
    )
    assert (
        not state["paused"]
        and state["held_rub"] == 2
        and state["spent_rub"]
        == (Decimal(0) if kind == "page_check" else Decimal(".01"))
    )
    attempt = await h.svc.pool.fetchrow(
        "SELECT * FROM pilot_attempts WHERE id=$1", item["attempt_id"]
    )
    assert attempt["state"] == "unknown" and attempt["actual_cost_rub"] is None
    assert json.loads(attempt["diagnostics"])["actual_cost_rub"] == "2"
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_audit WHERE name='cost_bound_observation'"
        )
        == 1
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_fund_ledger WHERE operation='settlement' AND attempt_id=$1",
            item["attempt_id"],
        )
        == 0
    )


@pytest.mark.asyncio
async def test_reconciliation_request_id_collision_is_domain_conflict(h):
    from pilot.processing.funds import fund_wallet, FundsEvidence
    from pilot.domain.errors import DomainError

    req = uuid4()
    await fund_wallet(
        h.svc,
        operation="initialize",
        amount_rub=Decimal(10),
        evidence=FundsEvidence("synthetic", "c" * 64, "fixture"),
        operator_ref="pytest",
        request_id=req,
    )
    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    h.svc.transport = Gateway("unknown")
    await h.run()
    attempt = await h.svc.pool.fetchval(
        "SELECT id FROM pilot_attempts WHERE state='unknown'"
    )
    with pytest.raises(DomainError) as error:
        await reconcile_attempt(
            h.svc,
            attempt_id=attempt,
            outcome="settled",
            evidence=ReconciliationEvidence("synthetic check", "d" * 64, Decimal(".2")),
            operator_ref="pytest",
            request_id=req,
        )
    assert error.value.http_status == 409 and error.value.code == "idempotency_conflict"
    assert (
        await h.svc.pool.fetchval(
            "SELECT held_rub FROM pilot_processing_budget WHERE mode='fixture'"
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["page_check", "class_analytics"])
async def test_valid_response_with_unknown_cost_publishes_and_retains_billing_only_hold(
    h, kind
):
    if kind == "page_check":
        ids = await h.create()
        await h.submit(ids[2], ids[3], expected=202)
    else:
        ids, _, _ = await ready(h)
        await finalize(h)
    gateway = Gateway()

    async def provider(job, payload):
        result = await gateway(job, payload)
        result.actual_cost_rub = None
        return result

    h.svc.transport = provider
    await h.run()
    job = await h.svc.pool.fetchrow(
        "SELECT * FROM pilot_jobs WHERE kind=$1 ORDER BY created_at DESC LIMIT 1", kind
    )
    a = await h.svc.pool.fetchrow(
        "SELECT * FROM pilot_attempts WHERE job_id=$1", job["id"]
    )
    assert (
        job["state"] == "succeeded"
        and a["state"] == "settled"
        and a["billing_state"] == "unknown"
        and a["actual_cost_rub"] is None
    )
    assert await h.svc.pool.fetchval(
        "SELECT active FROM pilot_fund_reservations WHERE attempt_id=$1", a["id"]
    )
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_slots WHERE attempt_id=$1", a["id"]
        )
        == 0
    )
    if kind == "class_analytics":
        task = (await h.check())["notebooks"][0]["bundles"][0]["tasks"][0]
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
        summary = (await h.call("getSummary", check_id=ids[0], expected=200)).json()
        assert summary["stale"] and summary["can_refresh"]
        await h.call("refreshSummary", check_id=ids[0], expected=202)
    result = await reconcile_attempt(
        h.svc,
        attempt_id=a["id"],
        outcome="settled",
        evidence=ReconciliationEvidence(
            "synthetic cost check", "e" * 64, Decimal(".02")
        ),
        operator_ref="pytest",
        request_id=uuid4(),
    )
    assert result.changed and result.held_rub == 0
    assert (
        await h.svc.pool.fetchval("SELECT state FROM pilot_jobs WHERE id=$1", job["id"])
        == "succeeded"
    )


@pytest.mark.asyncio
async def test_late_nonselected_analytics_result_is_typed_history_and_never_selected(h):
    ids, _, _ = await ready(h)
    await finalize(h)
    item = await claim(h.svc, uuid4())
    result = await run_job(h.svc, item["job"], item["payload"])
    await h.svc.pool.execute(
        "UPDATE pilot_jobs SET lease_until=now()-interval '1 second' WHERE id=$1",
        item["job"]["id"],
    )
    await recover_expired(h.svc)
    await reconcile_attempt(
        h.svc,
        attempt_id=item["attempt_id"],
        outcome="rejected",
        evidence=ReconciliationEvidence("synthetic request rejected", "f" * 64),
        operator_ref="pytest",
        request_id=uuid4(),
    )
    newer = (await h.call("retrySummary", check_id=ids[0], expected=202)).json()["job"][
        "id"
    ]
    before = (await h.check())["revision"]
    assert not await complete(h.svc, item, result)
    assert not await complete(h.svc, item, result)
    current = (await h.call("getSummary", check_id=ids[0], expected=200)).json()
    assert current["job_id"] == newer and current["result"] is None
    assert (await h.check())["revision"] == before
    history = (
        await h.call("getSummaryHistory", actor="staff", check_id=ids[0], expected=200)
    ).json()
    old = next(
        x["summary"]
        for x in history["items"]
        if x["summary"]["job_id"] == str(item["job"]["id"])
    )
    assert old["result"] == result.payload
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_analytics_results WHERE job_id=$1",
            item["job"]["id"],
        )
        == 1
    )


@pytest.mark.asyncio
async def test_reconciliation_replays_earlier_null_cost_intent_after_known_cost_enrichment(
    h,
):
    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    h.svc.transport = Gateway("unknown")
    await h.run()
    aid = await h.svc.pool.fetchval(
        "SELECT id FROM pilot_attempts WHERE state='unknown'"
    )
    one = ReconciliationEvidence(
        "synthetic terminal outcome, billing pending", "1" * 64
    )
    two = ReconciliationEvidence(
        "synthetic provider billing proof", "2" * 64, Decimal(".2")
    )
    k1, k2 = uuid4(), uuid4()
    result = await reconcile_attempt(
        h.svc,
        attempt_id=aid,
        outcome="settled",
        evidence=one,
        operator_ref="pytest",
        request_id=k1,
    )
    assert result.changed and result.held_rub == 1
    result = await reconcile_attempt(
        h.svc,
        attempt_id=aid,
        outcome="settled",
        evidence=two,
        operator_ref="pytest",
        request_id=k2,
    )
    assert result.changed and result.held_rub == 0
    result = await reconcile_attempt(
        h.svc,
        attempt_id=aid,
        outcome="settled",
        evidence=one,
        operator_ref="pytest",
        request_id=k1,
    )
    assert not result.changed and result.held_rub == 0
    assert await h.svc.pool.fetchval(
        "SELECT spent_rub FROM pilot_processing_budget WHERE mode='fixture'"
    ) == Decimal(".2")
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_fund_ledger WHERE attempt_id=$1 AND operation='settlement'",
            aid,
        )
        == 1
    )
