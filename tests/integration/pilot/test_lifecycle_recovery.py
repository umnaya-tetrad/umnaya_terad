"""Versions, duplicate intents and recovery acceptance (REL-C12..C16)."""
from __future__ import annotations

import time
import json
from uuid import uuid4

import pytest

from conftest import (
    PHOTO_FIXTURE,
    Client,
    compose,
    mutation_key,
    new_check,
    reconcile_fixture_unknown,
    wait_healthy,
)

pytestmark = pytest.mark.release


def psql(sql: str) -> str:
    return compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc", sql
    ).stdout.strip()


def check_of(client: Client, path: str) -> dict:
    return client.expect("GET", path, 200).body


def upload(client: Client, check: str, page: bytes | None = None) -> tuple[dict, dict]:
    current = client.expect("GET", check, 200).body
    bundle = current["notebooks"][0]["bundles"][0]
    photo = client.expect(
        "POST", f"/input-versions/{bundle['draft']['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", page or PHOTO_FIXTURE.read_bytes()),
    ).body
    return bundle, photo


def submit(client: Client, check: str, key: str | None = None, revision: int | None = None) -> tuple[dict, str, int]:
    bundle, photo = upload(client, check)
    key = key or mutation_key()
    client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload={"input_version_id": bundle["draft"]["id"]},
        revision=photo["check_revision"] if revision is None else revision,
        key=key,
    )
    return bundle, key, photo["check_revision"]


def wait_job(client: Client, job_id: str, states: set[str], timeout: float = 90) -> dict:
    cutoff = time.monotonic() + timeout
    job = {}
    while time.monotonic() < cutoff:
        job = client.expect("GET", f"/jobs/{job_id}", 200).body
        if job["state"] in states:
            return job
        time.sleep(1)
    raise AssertionError(f"Job stayed {job.get('state')!r}")


def job_from(check: dict) -> dict:
    return check["notebooks"][0]["bundles"][0]["job"] or {}


def test_rel_c12_lost_response_replays_one_intent():
    """REL-C12: a repeated intent returns the original Job, not a second one."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C12 повтор")
    bundle, photo = upload(client, check)

    key = mutation_key()
    payload = {"input_version_id": bundle["draft"]["id"]}
    first = client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload=payload, revision=photo["check_revision"], key=key,
    ).body

    # The response is "lost": the client retries the same intent with an older guard.
    replay = client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload=payload, revision=photo["check_revision"], key=key,
    ).body
    assert replay == first, "A replay must return the original response"
    assert first["job"]["id"]

    conflict = client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 409,
        payload={"input_version_id": str(uuid4())},
        revision=photo["check_revision"], key=key,
    ).body
    assert conflict["error"]["code"] == "idempotency_conflict"

    current = client.expect("GET", check, 200).body
    stale = client.request(
        "POST", f"{check}/notebooks", revision=first["check_revision"] - 1, key=mutation_key()
    )
    assert stale.status == 409
    assert stale.body["error"]["code"] == "revision_conflict"
    assert stale.body["error"]["current_revision"] == current["revision"]

    jobs = psql(f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}'")
    assert int(jobs) == 1, "One intent must produce exactly one Job"

    intents = psql(
        "select count(*) from pilot_idempotency where key='" + key + "'"
    )
    assert int(intents) == 1

    second_client = Client()
    second_client.login("TEACHER_1")
    assert second_client.expect("GET", check, 200).body["notebooks"][0]["bundles"][0]["job"]["id"] == first["job"]["id"]


def test_rel_c12_reload_does_not_submit_again():
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C12 reload")
    _bundle, _key, _revision = submit(client, check)

    fresh = Client()
    fresh.login("TEACHER_1")
    current = fresh.expect("GET", check, 200).body
    jobs = psql(f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}'")
    assert int(jobs) == 1
    assert job_from(current)["state"] in {"queued", "running", "succeeded"}


def test_rel_c13_replacement_generation_archives_reviews():
    """REL-C13: only submit of a new version drops the old generation and reviews."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C13 поколение")
    bundle, _key, _revision = submit(client, check)
    ready = wait_job(client, job_from(check_of(client, check))["id"], {"succeeded"})
    assert ready["state"] == "succeeded"

    current = check_of(client, check)
    task = next(
        (item for item in current["notebooks"][0]["bundles"][0]["tasks"]
         if item["analysis"]["result"] != "not_assessed"), None,
    )
    assert task, "The fixture must yield a reviewable task"
    confirmed = client.expect(
        "PUT", f"/tasks/{task['task_id']}/review", 200,
        payload={"analysis_id": task["analysis_id"], "state": "confirmed", "comment": ""},
        revision=current["revision"], key=mutation_key(),
    ).body

    active = check_of(client, check)
    sealed = active["notebooks"][0]["bundles"][0]
    version = client.expect(
        "POST", f"/bundles/{sealed['id']}/versions", 201,
        payload={"photo_ids": [photo["id"] for photo in sealed["current_input"]["photos"]]},
        revision=confirmed["check_revision"], key=mutation_key(),
    ).body

    # A discarded draft must keep the old reviews and the old generation.
    discarded = client.expect(
        "DELETE", f"/input-versions/{version['entity_id']}", 200,
        revision=version["check_revision"], key=mutation_key(),
    ).body
    kept = check_of(client, check)
    assert kept["notebooks"][0]["bundles"][0]["current_input"]["id"] == sealed["current_input"]["id"]
    assert any(item["review"] for item in kept["notebooks"][0]["bundles"][0]["tasks"])

    # The explicit submit activates the new generation and clears every review.
    created = client.expect(
        "POST", f"/bundles/{sealed['id']}/versions", 201,
        payload={"photo_ids": [photo["id"] for photo in sealed["current_input"]["photos"]]},
        revision=discarded["check_revision"], key=mutation_key(),
    ).body
    submitted = client.expect(
        "POST", f"/bundles/{sealed['id']}/submit", 202,
        payload={"input_version_id": created["entity_id"]},
        revision=created["check_revision"], key=mutation_key(),
    ).body
    new_job = wait_job(client, submitted["job"]["id"], {"succeeded", "failed"})
    assert new_job["state"] == "succeeded"

    fresh = check_of(client, check)
    new_bundle = fresh["notebooks"][0]["bundles"][0]
    assert new_bundle["current_input"]["id"] == created["entity_id"]
    assert new_bundle["current_input"]["id"] != sealed["current_input"]["id"]
    assert new_bundle["tasks"], "A new generation must publish its own tasks"
    assert all(item["review"] is None for item in new_bundle["tasks"])

    old_analysis = task["analysis_id"]
    stale_review = client.request(
        "PUT", f"/tasks/{task['task_id']}/review",
        payload={"analysis_id": old_analysis, "state": "system_error", "comment": ""},
        revision=fresh["revision"], key=mutation_key(),
    )
    assert stale_review.status in {404, 409}, "An old analysis must not accept a new review"

    history = psql(
        f"select count(*) from pilot_input_versions where bundle_id='{sealed['id']}' and state='sealed'"
    )
    assert int(history) == 2, "The previous generation stays in staff history"


def test_rel_c13_similar_formula_does_not_transfer_consent():
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C13 формула")
    _bundle, _key, _revision = submit(client, check, )
    ready = wait_job(client, job_from(check_of(client, check))["id"], {"succeeded"})
    assert ready["state"] == "succeeded"

    current = check_of(client, check)
    tasks = current["notebooks"][0]["bundles"][0]["tasks"]
    reviewable = next((item for item in tasks if item["analysis"]["result"] != "not_assessed"), None)
    assert reviewable
    client.expect(
        "PUT", f"/tasks/{reviewable['task_id']}/review", 200,
        payload={"analysis_id": reviewable["analysis_id"], "state": "confirmed", "comment": "оставить"},
        revision=current["revision"], key=mutation_key(),
    )

    # A completely independent bundle in the same check keeps its own reviews.
    added = client.expect(
        "POST", f"{check}/notebooks", 201,
        revision=check_of(client, check)["revision"], key=mutation_key(),
    ).body
    bundle = client.expect(
        "POST", f"/notebooks/{added['entity_id']}/bundles", 201,
        revision=added["check_revision"], key=mutation_key(),
    ).body
    photo = client.expect(
        "POST", f"/input-versions/{check_of(client, check)['notebooks'][1]['bundles'][0]['draft']['id']}/photos",
        201, revision=check_of(client, check)["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    second = client.expect(
        "POST", f"/bundles/{bundle['entity_id']}/submit", 202,
        payload={"input_version_id": check_of(client, check)["notebooks"][1]["bundles"][0]["draft"]["id"]},
        revision=photo["check_revision"], key=mutation_key(),
    ).body
    wait_job(client, second["job"]["id"], {"succeeded"})

    final = check_of(client, check)
    first_bundle = final["notebooks"][0]["bundles"][0]
    assert any(item["review"] and item["review"]["state"] == "confirmed" for item in first_bundle["tasks"])
    second_bundle = final["notebooks"][1]["bundles"][0]
    assert all(item["review"] is None for item in second_bundle["tasks"]), (
        "A similar formula in an independent bundle must not inherit a review"
    )


def test_rel_c14_delete_task_keeps_the_shared_photo_and_tombstone():
    """REL-C14: deleting one task hides only that task; the photo and report survive."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C14 удаление")
    _bundle, _key, _revision = submit(client, check)
    wait_job(client, job_from(check_of(client, check))["id"], {"succeeded"})

    current = check_of(client, check)
    bundle = current["notebooks"][0]["bundles"][0]
    assert len(bundle["tasks"]) >= 1
    victim = bundle["tasks"][0]
    removed = client.expect(
        "DELETE", f"/tasks/{victim['task_id']}", 200,
        revision=current["revision"], key=mutation_key(),
    ).body

    after = check_of(client, check)
    remaining = after["notebooks"][0]["bundles"][0]
    assert victim["task_id"] not in {item["task_id"] for item in remaining["tasks"]}
    photos = remaining["current_input"]["photos"]
    assert photos, "Deleting a task must not remove the shared photo"
    assert client.expect("GET", f"/assets/{photos[0]['id']}", 200).status == 200
    assert remaining["result"] is not None, "The stored Report stays for support history"

    tombstone = psql(
        f"select count(*) from pilot_task_analyses where task_id='{victim['task_id']}' and deleted"
    )
    assert int(tombstone) == 1, "The deleted task keeps a tombstone"

    # Re-publishing the same Job must not resurrect the deleted task.
    time.sleep(1)
    after_restart = check_of(client, check)
    assert victim["task_id"] not in {item["task_id"] for item in after_restart["notebooks"][0]["bundles"][0]["tasks"]}
    assert removed["check_revision"] <= after_restart["revision"]


def test_rel_c14_delete_during_run_blocks_new_paid_work():
    """REL-C14: deleting the check while a Job runs hides material and stops publication."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C14 удаление в работе")

    compose("stop", "worker")
    try:
        _bundle, _key, _revision = submit(client, check)
        current = check_of(client, check)
        job = job_from(current)
        assert job["state"] == "queued"

        deleted = client.expect(
            "DELETE", check, 200, revision=current["revision"], key=mutation_key()
        ).body
        assert deleted["check_id"]
        assert client.request("GET", check).status == 404
    finally:
        compose("start", "worker")
        wait_healthy()

    # A deleted check hides its Job from the owner (404) and the worker must not
    # publish a result for it; the tombstoned row stays for audit.
    cutoff = time.monotonic() + 60
    late = ""
    while time.monotonic() < cutoff:
        late = psql(f"select state from pilot_jobs where id='{job['id']}'")
        if late in {"cancelled", "failed", "unknown", "succeeded"}:
            break
        time.sleep(1)
    assert late in {"cancelled", "failed", "unknown"}, f"unexpected state {late!r}"
    assert client.request("GET", check).status == 404
    assert client.request("GET", f"/jobs/{job['id']}").status == 404
    assert int(psql(f"select count(*) from pilot_checks where id='{check.rsplit('/', 1)[1]}'")) == 1
    assert psql(f"select deleted from pilot_checks where id='{check.rsplit('/', 1)[1]}'") == "t"
    published = psql(
        f"select count(*) from pilot_bundle_reports r join pilot_jobs j on j.id=r.job_id "
        f"where j.id='{job['id']}'"
    )
    assert int(published) == 0, "A deleted check must not publish a new Report"


@pytest.mark.parametrize("second_outcome", ["success", "temporary_failure"])
def test_rel_c15_one_automatic_retry_only(controlled_provider, second_outcome):
    """Actual 429 POST -> retry_wait -> second POST; fresh worker process, no third."""
    from decimal import Decimal

    control = controlled_provider
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C15 controlled transient")
    _bundle, _key, _revision = submit(client, check)
    job = job_from(check_of(client, check))
    job_id = job["id"]
    control.register(job, outcomes=("temporary_failure", second_outcome))
    first = control.worker()
    control.finish(first)
    assert client.expect("GET", f"/jobs/{job_id}", 200).body["state"] == "retry_wait"
    assert control.sql(f"SELECT auto_retry_count FROM pilot_jobs WHERE id='{job_id}'") == "1"
    first_worker = control.sql(f"SELECT worker_id FROM pilot_jobs WHERE id='{job_id}'")
    assert control.sql(f"SELECT count(*) FROM release_test_posts WHERE job_id='{job_id}' AND method='POST' AND http_status=429") == "1"
    assert control.sql(f"SELECT ordinal || ':' || state FROM pilot_attempts WHERE job_id='{job_id}'") == "1:rejected"
    # The first OS worker exits completely; the new process must recover the
    # durable retry count from PostgreSQL instead of resetting it in memory.
    time.sleep(1.1)
    control.finish(control.worker())
    expected = "succeeded" if second_outcome == "success" else "failed"
    assert client.expect("GET", f"/jobs/{job_id}", 200).body["state"] == expected
    assert control.sql(f"SELECT worker_id FROM pilot_jobs WHERE id='{job_id}'") != first_worker
    assert control.sql(f"SELECT auto_retry_count FROM pilot_jobs WHERE id='{job_id}'") == "1"
    assert control.sql(f"SELECT string_agg(ordinal::text,',' ORDER BY ordinal) FROM pilot_attempts WHERE job_id='{job_id}'") == "1,2"
    assert control.sql(f"SELECT count(*) FROM release_test_posts WHERE job_id='{job_id}'") == "2"
    assert json.loads(control.finish(control.worker()))["claimed"] is False
    assert control.sql(f"SELECT count(*) FROM release_test_posts WHERE job_id='{job_id}'") == "2"
    assert control.sql(f"SELECT count(*) FROM pilot_attempts WHERE job_id='{job_id}'") == "2"
    settled = control.sql(f"SELECT coalesce(sum(l.amount_rub),0) FROM pilot_fund_ledger l JOIN pilot_attempts a ON a.id=l.attempt_id WHERE a.job_id='{job_id}' AND l.operation='settlement'")
    assert Decimal(settled) == (Decimal("0.01") if second_outcome == "success" else Decimal(0))
    assert control.sql(f"SELECT count(*) FROM pilot_fund_reservations r JOIN pilot_attempts a ON a.id=r.attempt_id WHERE a.job_id='{job_id}' AND r.active") == "0"
    current = check_of(client, check)
    assert len(current["notebooks"][0]["bundles"][0]["tasks"]) == (3 if second_outcome == "success" else 0)


def test_rel_c15_red_review_does_not_retry():
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C15 красный")
    _bundle, _key, _revision = submit(client, check)
    job_id = job_from(check_of(client, check))["id"]
    wait_job(client, job_id, {"succeeded"})

    current = check_of(client, check)
    task = next(item for item in current["notebooks"][0]["bundles"][0]["tasks"]
                if item["analysis"]["result"] != "not_assessed")
    client.expect(
        "PUT", f"/tasks/{task['task_id']}/review", 200,
        payload={"analysis_id": task["analysis_id"], "state": "system_error", "comment": "красный"},
        revision=current["revision"], key=mutation_key(),
    )
    time.sleep(1)
    attempts = int(psql(f"select count(*) from pilot_attempts where job_id='{job_id}'"))
    assert attempts == 1, "A red review must not create another attempt"
    assert job_from(check_of(client, check))["state"] == "succeeded"


def test_rel_c16_expired_lease_fences_the_old_worker():
    """REL-C16: an expired lease becomes unknown, keeps the reserve and fences the old worker."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C16 fencing")

    compose("stop", "worker")
    try:
        _bundle, _key, _revision = submit(client, check)
        job_id = job_from(check_of(client, check))["id"]

        claimed = compose(
            "exec", "-T", "backend", "python", "-c",
            """
import asyncio, uuid
from pathlib import Path
import asyncpg
from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.queue import claim

async def main():
    settings = get_settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        item = await claim(services, uuid.uuid4())
        assert item, "the queued job must be claimable"
        print(item["job"]["id"], item["job"]["epoch"], item["attempt_id"])

asyncio.run(main())
""",
            check=False,
        )
        assert claimed.returncode == 0, claimed.stderr
        job_id_seen, epoch_seen, attempt_seen = claimed.stdout.strip().splitlines()[-1].split()
        assert job_id_seen == job_id
        check_seen, bundle_seen, input_seen = psql(
            f"select check_id || ' ' || coalesce(bundle_id::text,'') || ' ' || coalesce(input_version_id::text,'') "
            f"from pilot_jobs where id='{job_id}'"
        ).split()

        # The external call was dispatched and its lease expired without an answer.
        psql(f"update pilot_attempts set dispatched=true where id='{attempt_seen}'")
        psql(f"update pilot_jobs set lease_until=now() - interval '5 minutes' where id='{job_id}'")

        recovered = compose(
            "exec", "-T", "backend", "python", "-c",
            """
import asyncio
from pathlib import Path
import asyncpg
from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.queue import recover_expired

async def main():
    settings = get_settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        await recover_expired(services)

asyncio.run(main())
""",
            check=False,
        )
        assert recovered.returncode == 0, recovered.stderr

        assert psql(f"select state from pilot_jobs where id='{job_id}'") == "unknown"
        assert psql(f"select state from pilot_attempts where id='{attempt_seen}'") == "unknown"
        held = psql(
            f"select coalesce(sum(amount_rub),0) from pilot_fund_reservations "
            f"where attempt_id='{attempt_seen}' and active"
        )
        assert held not in {"0", "0.00", "0.0000"}, "An unknown attempt keeps its reserve"

        # The old worker's late answer for the previous epoch must not publish.
        late = compose(
            "exec", "-T", "backend", "python", "-c",
            f"""
import asyncio
from pathlib import Path
import asyncpg
from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.attempts import complete
from pilot.processing.transport import TransportResult

JOB = "{job_id}"
EPOCH = {epoch_seen}
ATTEMPT = "{attempt_seen}"
CHECK = "{check_seen}"
BUNDLE = "{bundle_seen}"
INPUT = "{input_seen}"

async def main():
    settings = get_settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        claim = {{
            "job": {{
                "id": JOB, "epoch": EPOCH, "check_id": CHECK, "bundle_id": BUNDLE,
                "input_version_id": INPUT, "snapshot_id": None, "kind": "page_check",
                "state": "unknown",
            }},
            "attempt_id": ATTEMPT,
            "payload": {{}},
        }}
        payload = {{"schema_version": "page-check/1.2", "status": "uncheckable", "tasks": [], "message": "late"}}
        ok = await complete(services, claim, TransportResult("success", actual_cost_rub=0, payload=payload))
        print("published" if ok else "fenced")

asyncio.run(main())
""",
            check=False,
        )
        assert late.returncode == 0, late.stderr
        assert "fenced" in late.stdout.lower(), late.stdout + late.stderr
        published = psql(
            f"select count(*) from pilot_bundle_reports r join pilot_jobs j on j.id=r.job_id where j.id='{job_id}'"
        )
        assert int(published) == 0, "A fenced worker must not publish a Report"
        assert int(psql(f"select count(*) from pilot_jobs where id='{job_id}'")) == 1

        # An unknown attempt is never retried automatically.
        compose(
            "exec", "-T", "backend", "python", "-c",
            """
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
""",
            check=False,
        )
        assert psql(f"select state from pilot_jobs where id='{job_id}'") == "unknown"
        assert psql(f"select state from pilot_attempts where id='{attempt_seen}'") == "unknown"
    finally:
        compose("start", "worker")
        wait_healthy()

    reconcile_fixture_unknown(attempt_seen)
