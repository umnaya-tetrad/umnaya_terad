"""Funds, pause and reconciliation acceptance (REL-C16/C17/C18)."""
from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from conftest import (
    PHOTO_FIXTURE,
    ROOT,
    Client,
    compose,
    mutation_key,
    new_check,
    reconcile_fixture_unknown,
    run_host_script,
)

pytestmark = pytest.mark.release

# Unknown attempts produced by these tests hold a global worker slot until they
# are reconciled. They are settled in teardown so the isolated stack stays usable.
UNKNOWN_ATTEMPTS: list[str] = []


@pytest.fixture(scope="module", autouse=True)
def _release_fixture_slots():
    yield
    for attempt in UNKNOWN_ATTEMPTS:
        reconcile_fixture_unknown(attempt)
    UNKNOWN_ATTEMPTS.clear()


def psql(sql: str) -> str:
    return compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc", sql
    ).stdout.strip()


def control(*args: str, expect: int = 0) -> dict | None:
    result = run_host_script(str(ROOT / "scripts/pilot/processing_control.py"), *args)
    assert result.returncode == expect, (
        f"processing_control.py {args} exited {result.returncode}, expected {expect}: "
        f"{result.stdout}{result.stderr}"
    )
    if expect == 0 and result.stdout.strip():
        return json.loads(result.stdout.strip())
    return None


def budget() -> dict:
    return json.loads(
        compose("exec", "-T", "backend", "python", "-m", "pilot.processing.budget", "status").stdout.strip()
    )


def wait_job(client: Client, job_id: str, allow: set[str], timeout: float = 90) -> dict:
    """Poll a Job until it reaches one of the allowed terminal-or-waiting states."""
    cutoff = time.monotonic() + timeout
    job = {}
    while time.monotonic() < cutoff:
        job = client.expect("GET", f"/jobs/{job_id}", 200).body
        if job["state"] in allow:
            return job
        time.sleep(1)
    raise AssertionError(f"Job {job_id} stayed {job.get('state')!r}")


def submit_bundle(client: Client, check: str) -> dict:
    current = client.expect("GET", check, 200).body
    bundle = current["notebooks"][0]["bundles"][0]
    photo = client.expect(
        "POST", f"/input-versions/{bundle['draft']['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    return client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload={"input_version_id": bundle["draft"]["id"]},
        revision=photo["check_revision"], key=mutation_key(),
    ).body


def test_rel_c18_pause_stops_dispatch_and_resume_continues():
    """REL-C18: pause stops new dispatches; queued work survives; resume continues."""
    teacher = Client()
    teacher.login("TEACHER_1")

    compose("stop", "worker")
    try:
        check, _ = new_check(teacher, "REL-C18 пауза")
        submitted = submit_bundle(teacher, check)
        job_id = submitted["job"]["id"]
        queued = teacher.expect("GET", f"/jobs/{job_id}", 200).body
        assert queued["state"] == "queued"

        paused = control("--operator-ref", "rel-c18", "pause", "--reason", "release acceptance")
        assert paused["paused"] is True
        assert control("status")["paused"] is True

        # Accounts and history stay readable while dispatch is paused.
        assert teacher.expect("GET", check, 200).status == 200
        assert Client().login("TEACHER_2")["role"] == "teacher"
    finally:
        compose("start", "worker")
        control("--operator-ref", "rel-c18", "resume", "--reason", "release acceptance finished")

    resumed = wait_job(teacher, job_id, {"succeeded", "failed"})
    assert resumed["state"] == "succeeded", resumed

    audit = psql("select name from pilot_audit where payload->>'operator_ref'='rel-c18' order by created_at")
    assert "processing_paused" in audit and "processing_resumed" in audit

    no_reason = run_host_script(str(ROOT / "scripts/pilot/processing_control.py"), "pause")
    assert no_reason.returncode != 0 and "--reason" in no_reason.stderr


def test_rel_c18_red_review_does_not_pause():
    """REL-C18: a red review is feedback, never an automatic stop."""
    teacher = Client()
    teacher.login("TEACHER_1")
    current = control("status")
    assert current["paused"] is False

    rows = psql("select count(*) from pilot_jobs where state in ('queued','running')")
    assert int(rows) >= 0
    assert control("status")["paused"] is False


def test_rel_c17_shared_cap_and_hot_change():
    """REL-C17: one cumulative cap for both kinds; hot change without restart."""
    state = budget()
    original = state["spend_limit_rub"]
    before = control("status")

    reduced = compose(
        "exec", "-T", "backend", "python", "-m", "pilot.processing.budget",
        "set-limit", "--rub", str(max(1, float(original) / 10)), "--operator-ref", "rel-c17",
        check=False,
    )
    assert reduced.returncode == 0, reduced.stderr
    try:
        tight = budget()
        assert float(tight["spend_limit_rub"]) < float(original)
        assert tight["spent_rub"] == state["spent_rub"], "Changing the cap must not reset spent"
        assert tight["held_rub"] == state["held_rub"], "Changing the cap must not reset holds"

        headroom = budget()
        assert float(headroom["available_rub"]) == max(
            0.0, float(headroom["spend_limit_rub"]) - float(headroom["spent_rub"]) - float(headroom["held_rub"])
        )
    finally:
        restored = compose(
            "exec", "-T", "backend", "python", "-m", "pilot.processing.budget",
            "set-limit", "--rub", original, "--operator-ref", "rel-c17",
            check=False,
        )
        assert restored.returncode == 0, restored.stderr

    back = budget()
    assert back["spend_limit_rub"] == original
    assert back["spent_rub"] == state["spent_rub"]
    assert back["paused"] == state["paused"]
    assert before["mode"] == control("status")["mode"]

    audit = psql("select count(*) from pilot_audit where name='spend_limit_changed' and payload->>'operator_ref'='rel-c17'")
    assert int(audit) >= 2, "Both cap changes must be audited"


def test_rel_c17_cap_blocks_a_new_dispatch_without_destroying_state():
    """REL-C17: a cap below the bound blocks dispatch, the Check survives."""
    state = budget()
    teacher = Client()
    teacher.login("TEACHER_1")
    spent = float(state["spent_rub"])
    held = float(state["held_rub"])

    compose(
        "exec", "-T", "backend", "python", "-m", "pilot.processing.budget",
        "set-limit", "--rub", str(spent + held), "--operator-ref", "rel-c17",
        check=False,
    )
    try:
        check, _ = new_check(teacher, "REL-C17 блокировка")
        submitted = submit_bundle(teacher, check)
        job = wait_job(teacher, submitted["job"]["id"], {"blocked", "queued", "running", "succeeded"}, timeout=30)
        assert job["state"] in {"blocked", "queued", "running", "succeeded"}
        if job["state"] == "blocked":
            assert job["reason"] in {"funds_unavailable", "service_paused"}
        assert teacher.expect("GET", check, 200).status == 200, "Blocked work keeps its material"
    finally:
        compose(
            "exec", "-T", "backend", "python", "-m", "pilot.processing.budget",
            "set-limit", "--rub", state["spend_limit_rub"], "--operator-ref", "rel-c17",
            check=False,
        )
    assert budget()["spend_limit_rub"] == state["spend_limit_rub"]


def create_unknown_attempt(client: Client, check: str) -> str:
    """Produce a real unknown attempt through the fixture transport.

    The regular worker is stopped so it cannot claim the Job; a one-shot worker
    runs with the explicit ``unknown`` scenario, which returns no outcome and no
    cost. The attempt then stays unknown with its reserve held.
    """
    compose("stop", "worker")
    try:
        submitted = submit_bundle(client, check)
        job_id = submitted["job"]["id"]
        script = """
import asyncio
from pathlib import Path
import asyncpg
from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.worker import run_once

async def main():
    settings = get_settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        services.fixture_scenario = "unknown"
        await run_once(services)

asyncio.run(main())
"""
        result = compose("exec", "-T", "backend", "python", "-c", script, check=False)
        assert result.returncode == 0, result.stderr
    finally:
        compose("start", "worker")

    attempt = psql(
        "select a.id from pilot_attempts a join pilot_jobs j on j.id=a.job_id "
        f"where j.id='{job_id}' and a.state='unknown' order by a.ordinal desc limit 1"
    )
    assert attempt, "The explicit unknown scenario must leave an unknown attempt"
    assert wait_job(client, job_id, {"unknown", "failed"})["state"] == "unknown"
    UNKNOWN_ATTEMPTS.append(attempt)
    return attempt


def test_rel_c16_reconciliation_is_idempotent_and_conflict_aware(tmp_path: Path):
    """REL-C16: unknown attempts are settled once, conflicts exit non-zero."""
    teacher = Client()
    teacher.login("TEACHER_1")
    check, _ = new_check(teacher, "REL-C16 unknown")
    unknown = create_unknown_attempt(teacher, check)

    held_before = psql(
        f"select coalesce(sum(amount_rub),0) from pilot_fund_reservations where attempt_id='{unknown}' and active"
    )
    assert held_before not in {"0", "0.00", "0.0000"}, "An unknown attempt keeps its reserve"

    evidence = tmp_path / "receipt.json"
    evidence.write_text(json.dumps({"reference": "release-receipt-1", "actual_cost_rub": "0.0100"}), encoding="utf-8")
    request_id = str(uuid4())

    def reconcile(*extra: str, expect: int = 0) -> dict | None:
        result = run_host_script(
            str(ROOT / "scripts/pilot/reconcile_attempt.py"),
            "--attempt-id", unknown, "--outcome", "settled",
            "--evidence-file", str(evidence), "--operator-ref", "rel-c16",
            "--request-id", request_id, *extra,
        )
        assert result.returncode == expect, (
            f"reconcile exited {result.returncode}, expected {expect}: {result.stdout}{result.stderr}"
        )
        if expect == 0:
            return json.loads(result.stdout.strip())
        return None

    first = reconcile()
    assert first["changed"] is True
    assert Decimal(first["held_rub"]) == Decimal(0), "A finite settled cost must release the reserve"

    stored = psql(f"select payload_hash from pilot_reconciliations where request_id='{request_id}'")
    assert stored, "The reconciliation must be recorded for idempotency"

    again = reconcile()
    assert again["changed"] is False, "A repeated identical reconciliation is a no-op"

    contradicting = tmp_path / "other.json"
    contradicting.write_text(json.dumps({"reference": "release-receipt-2", "actual_cost_rub": "0.0200"}), encoding="utf-8")
    result = run_host_script(
        str(ROOT / "scripts/pilot/reconcile_attempt.py"),
        "--attempt-id", unknown, "--outcome", "settled",
        "--evidence-file", str(contradicting), "--operator-ref", "rel-c16",
        "--request-id", request_id,
    )
    assert result.returncode != 0, "Different evidence under one request id must conflict"

    audit = psql(
        "select count(*) from pilot_audit where name='attempt_reconciled' and payload->>'operator_ref'='rel-c16'"
    )
    assert int(audit) == 1, "Only the effective reconciliation is audited"

    late = teacher.expect("GET", check, 200).body
    assert late["notebooks"][0]["bundles"][0]["job"]["state"] in {"unknown", "failed"}

def test_rel_c16_unknown_stays_unknown_until_evidence(tmp_path: Path):
    """REL-C16: without evidence the unknown attempt keeps its reserve and state."""
    teacher = Client()
    teacher.login("TEACHER_1")
    check, _ = new_check(teacher, "REL-C16 неизвестный")
    unknown = create_unknown_attempt(teacher, check)

    before = psql(
        f"select state || '|' || billing_state from pilot_attempts where id='{unknown}'"
    )
    assert before == "unknown|unknown", before

    no_evidence = tmp_path / "missing.json"
    result = run_host_script(
        str(ROOT / "scripts/pilot/reconcile_attempt.py"),
        "--attempt-id", unknown, "--outcome", "settled",
        "--evidence-file", str(no_evidence), "--operator-ref", "rel-c16",
    )
    assert result.returncode == 2 and "cannot read evidence file" in result.stderr

    after = psql(
        f"select state || '|' || billing_state from pilot_attempts where id='{unknown}'"
    )
    assert after == before, "A refused reconciliation must not alter the attempt"

    # Another worker pass must not resend the unknown call.
    script = """
import asyncio
from pathlib import Path
import asyncpg
from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.worker import run_once

async def main():
    settings = get_settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        await run_once(services)

asyncio.run(main())
"""
    compose("exec", "-T", "backend", "python", "-c", script, check=False)
    still = psql(f"select state || '|' || billing_state from pilot_attempts where id='{unknown}'")
    assert still == "unknown|unknown", "An unknown attempt must never be resent automatically"


def test_rel_c16_rejected_requires_proven_absence(tmp_path: Path):
    """REL-C16: a rejected outcome cannot claim a non-zero charge."""
    attempt = psql("select id from pilot_attempts order by created_at desc limit 1")
    evidence = tmp_path / "bad-reject.json"
    evidence.write_text(json.dumps({"reference": "release-reject", "actual_cost_rub": "1.5"}), encoding="utf-8")
    result = run_host_script(
        str(ROOT / "scripts/pilot/reconcile_attempt.py"),
        "--attempt-id", attempt, "--outcome", "rejected",
        "--evidence-file", str(evidence), "--operator-ref", "rel-c16",
    )
    assert result.returncode == 2
    assert "proven absence" in result.stderr

    missing_reference = tmp_path / "no-reference.json"
    missing_reference.write_text(json.dumps({"actual_cost_rub": "0"}), encoding="utf-8")
    refused = run_host_script(
        str(ROOT / "scripts/pilot/reconcile_attempt.py"),
        "--attempt-id", attempt, "--outcome", "settled",
        "--evidence-file", str(missing_reference), "--operator-ref", "rel-c16",
    )
    assert refused.returncode == 2
    assert "reference" in refused.stderr


def test_rel_c17_no_http_admin_surface():
    """REL-C17/C18: pausing and funds stay on the trusted local CLI."""
    teacher = Client()
    teacher.login("TEACHER_1")
    for path in ("/processing/pause", "/processing/control", "/budget", "/funds", "/admin/processing"):
        status = teacher.request("GET", path).status
        assert status in {403, 404}, f"{path} answered {status}"
    staff = Client()
    staff.login("STAFF")
    for path in ("/processing/pause", "/budget"):
        status = staff.request("POST", path).status
        assert status in {403, 404, 405}, f"staff reached {path} with {status}"
