"""Finalization and analytics lifecycle acceptance (REL-C19..C23)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from conftest import (
    PHOTO_FIXTURE,
    Client,
    compose,
    mutation_key,
    new_check,
    wait_healthy,
)

pytestmark = pytest.mark.release

SHARED = Path(__file__).resolve().parents[3] / "project-context/pilot/planning/shared"
ANALYTICS_FIXTURES = SHARED / "analytics/fixtures"


def psql(sql: str) -> str:
    return compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc", sql
    ).stdout.strip()


def upload(client: Client, check: str) -> tuple[dict, dict]:
    current = client.expect("GET", check, 200).body
    bundle = current["notebooks"][0]["bundles"][0]
    photo = client.expect(
        "POST", f"/input-versions/{bundle['draft']['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    return bundle, photo


def submit(client: Client, check: str) -> dict:
    bundle, photo = upload(client, check)
    return client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload={"input_version_id": bundle["draft"]["id"]},
        revision=photo["check_revision"], key=mutation_key(),
    ).body


def wait_job(client: Client, job_id: str, states: set[str], timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    job = {}
    while time.monotonic() < deadline:
        job = client.expect("GET", f"/jobs/{job_id}", 200).body
        if job["state"] in states:
            return job
        time.sleep(1)
    raise AssertionError(f"Job stayed {job.get('state')!r}")


def wait_summary(client: Client, check: str, state: str, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    value = {}
    while time.monotonic() < deadline:
        value = client.expect("GET", f"{check}/summary", 200).body
        if value["state"] == state:
            return value
        time.sleep(1)
    raise AssertionError(f"Summary stayed {value.get('state')!r}: {value}")


def review_all(client: Client, check: str, state: str = "confirmed") -> dict:
    current = client.expect("GET", check, 200).body
    revision = current["revision"]
    if current["phase"] == "editing":
        revision = client.expect(
            "POST", f"{check}/begin-completion", 200,
            revision=revision, key=mutation_key(),
        ).body["check_revision"]
    for notebook in current["notebooks"]:
        for bundle in notebook["bundles"]:
            for task in bundle["tasks"]:
                if task["analysis"]["result"] == "not_assessed":
                    result = client.expect(
                        "POST", f"/tasks/{task['task_id']}/skip", 200,
                        payload={"analysis_id": task["analysis_id"]},
                        revision=revision, key=mutation_key(),
                    ).body
                else:
                    result = client.expect(
                        "PUT", f"/tasks/{task['task_id']}/review", 200,
                        payload={"analysis_id": task["analysis_id"], "state": state, "comment": ""},
                        revision=revision, key=mutation_key(),
                    ).body
                revision = result["check_revision"]
    return client.expect("GET", check, 200).body


def test_rel_c19_two_steps_block_unresolved_and_create_one_snapshot():
    """REL-C19: begin-completion waits for reviews; finalize creates one snapshot."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C19 финал")
    submit(client, check)
    current = client.expect("GET", check, 200).body
    job = current["notebooks"][0]["bundles"][0]["job"]
    wait_job(client, job["id"], {"succeeded"})

    editing = client.expect("GET", check, 200).body
    assert editing["phase"] == "editing"
    started = client.expect(
        "POST", f"{check}/begin-completion", 200,
        revision=editing["revision"], key=mutation_key(),
    ).body
    after_begin = client.expect("GET", check, 200).body
    assert after_begin["phase"] == "review"
    assert after_begin["summary"]["state"] == "not_started"
    assert psql(
        f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}' and kind='class_analytics'"
    ) == "0"

    blocked = client.request(
        "POST", f"{check}/finalize", revision=started["check_revision"], key=mutation_key()
    )
    assert blocked.status == 409
    assert psql(
        f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}' and kind='class_analytics'"
    ) == "0", "A blocked finalize must not create an AnalyticsJob"

    # Editing stays allowed while the check is in review.
    added = client.expect(
        "POST", f"{check}/notebooks", 201,
        revision=client.expect("GET", check, 200).body["revision"], key=mutation_key(),
    ).body
    assert added["entity_id"]

    ready = review_all(client, check)
    assert ready["completion"]["can_finalize"] is True, ready["completion"]
    key = mutation_key()
    first = client.expect(
        "POST", f"{check}/finalize", 202, revision=ready["revision"], key=key
    ).body
    replay = client.expect(
        "POST", f"{check}/finalize", 202, revision=ready["revision"], key=key
    ).body
    assert replay == first, "A repeated finalize returns the original AnalyticsJob"
    assert psql(
        f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}' and kind='class_analytics'"
    ) == "1"
    assert psql(
        f"select count(*) from pilot_snapshots s join pilot_jobs j on j.snapshot_id=s.id "
        f"where j.check_id='{check.rsplit('/', 1)[1]}'"
    ) == "1"

    summary = wait_summary(client, check, "succeeded")
    assert summary["result"] is not None
    assert summary["job_id"] == first["job"]["id"]
    assert client.expect("GET", check, 200).body["phase"] == "finalized"

    empty_check, _ = new_check(client, "REL-C19 пустая")
    empty_begin = client.expect(
        "POST", f"{empty_check}/begin-completion", 200,
        revision=client.expect("GET", empty_check, 200).body["revision"], key=mutation_key(),
    ).body
    empty_final = client.request(
        "POST", f"{empty_check}/finalize", revision=empty_begin["check_revision"], key=mutation_key()
    )
    assert empty_final.status in {409, 422}, "An empty check must not finalize"


def test_rel_c20_finalized_composition_is_closed_but_reviews_stay_open():
    """REL-C20: after finalize the composition is frozen; review edits remain allowed."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C20 состав")
    submit(client, check)
    job = client.expect("GET", check, 200).body["notebooks"][0]["bundles"][0]["job"]
    wait_job(client, job["id"], {"succeeded"})

    ready = review_all(client, check)
    client.expect(
        "POST", f"{check}/finalize", 202, revision=ready["revision"], key=mutation_key()
    )
    wait_summary(client, check, "succeeded")
    frozen = client.expect("GET", check, 200).body
    revision = frozen["revision"]

    forbidden = [
        ("POST", f"{check}/notebooks", None),
        ("POST", f"/notebooks/{frozen['notebooks'][0]['id']}/bundles", None),
        ("DELETE", f"/notebooks/{frozen['notebooks'][0]['id']}", None),
        ("DELETE", check, None),
    ]
    for method, path, payload in forbidden:
        response = client.request(
            method, path, payload=payload, revision=revision, key=mutation_key()
        )
        if method == "DELETE" and path == check:
            assert response.status == 200, "Deleting the whole check stays available"
            continue
        assert response.status == 409, f"{method} {path} was not blocked ({response.status})"

    # Deleting the check above invalidated it; create a fresh one for the review rules.
    check2, _ = new_check(client, "REL-C20 отзывы")
    submit(client, check2)
    job2 = client.expect("GET", check2, 200).body["notebooks"][0]["bundles"][0]["job"]
    wait_job(client, job2["id"], {"succeeded"})
    ready2 = review_all(client, check2)
    client.expect("POST", f"{check2}/finalize", 202, revision=ready2["revision"], key=mutation_key())
    wait_summary(client, check2, "succeeded")
    frozen2 = client.expect("GET", check2, 200).body
    task = next(
        item for notebook in frozen2["notebooks"] for bundle in notebook["bundles"]
        for item in bundle["tasks"] if item["analysis"]["result"] != "not_assessed"
    )
    changed = client.expect(
        "PUT", f"/tasks/{task['task_id']}/review", 200,
        payload={"analysis_id": task["analysis_id"], "state": "system_error", "comment": "после финала"},
        revision=frozen2["revision"], key=mutation_key(),
    ).body
    assert changed["check_revision"] > frozen2["revision"]
    after = client.expect("GET", f"{check2}/summary", 200).body
    assert after["stale"] is True, "A review change after finalize must stale the summary"


def test_rel_c21_get_summary_never_starts_a_job():
    """REL-C21: reading a summary does not create work or spend money."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C21 чтение")
    submit(client, check)
    job = client.expect("GET", check, 200).body["notebooks"][0]["bundles"][0]["job"]
    wait_job(client, job["id"], {"succeeded"})

    before = int(psql(f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}'"))
    for _ in range(3):
        value = client.expect("GET", f"{check}/summary", 200).body
        assert value["state"] in {"not_started", "queued", "running", "failed", "succeeded"}
    after = int(psql(f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}'"))
    assert after == before, "A summary read must not create a Job"


def test_rel_c21_failed_summary_retries_the_same_snapshot():
    """REL-C21: a safe failed snapshot can be retried without a new snapshot."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C21 retry")
    submit(client, check)
    job = client.expect("GET", check, 200).body["notebooks"][0]["bundles"][0]["job"]
    wait_job(client, job["id"], {"succeeded"})
    ready = review_all(client, check)

    compose("stop", "worker")
    try:
        finalized = client.expect(
            "POST", f"{check}/finalize", 202, revision=ready["revision"], key=mutation_key()
        ).body
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
        services.fixture_scenario = "invalid_response"
        await run_once(services)

asyncio.run(main())
"""
        failed_run = compose("exec", "-T", "backend", "python", "-c", script, check=False)
        assert failed_run.returncode == 0, failed_run.stderr
    finally:
        compose("start", "worker")
        wait_healthy()

    failed = wait_summary(client, check, "failed")
    assert failed["stale"] is False
    assert failed["can_retry"] is True
    assert failed["snapshot_id"]
    revision = client.expect("GET", check, 200).body["revision"]
    retried = client.expect(
        "POST", f"{check}/summary/retry", 202, revision=revision, key=mutation_key()
    ).body
    saved = wait_summary(client, check, "succeeded")
    assert saved["snapshot_id"] == failed["snapshot_id"], "Retry reuses the same snapshot"
    assert saved["job_id"] == retried["job"]["id"] != finalized["job"]["id"]


def test_rel_c22_review_change_makes_summary_stale_and_refresh_snapshots():
    """REL-C22: state change stales; comment-only does not; refresh builds a new snapshot."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C22 stale")
    submit(client, check)
    job = client.expect("GET", check, 200).body["notebooks"][0]["bundles"][0]["job"]
    wait_job(client, job["id"], {"succeeded"})
    ready = review_all(client, check)
    client.expect("POST", f"{check}/finalize", 202, revision=ready["revision"], key=mutation_key())
    original = wait_summary(client, check, "succeeded")

    frozen = client.expect("GET", check, 200).body
    task = next(
        item for notebook in frozen["notebooks"] for bundle in notebook["bundles"]
        for item in bundle["tasks"] if item["analysis"]["result"] != "not_assessed"
    )

    comment = client.expect(
        "PUT", f"/tasks/{task['task_id']}/review", 200,
        payload={"analysis_id": task["analysis_id"], "state": "confirmed", "comment": "только комментарий"},
        revision=frozen["revision"], key=mutation_key(),
    ).body
    unchanged = client.expect("GET", f"{check}/summary", 200).body
    assert unchanged["stale"] is False, "A comment-only change keeps the summary current"
    assert unchanged["snapshot_id"] == original["snapshot_id"]

    changed = client.expect(
        "PUT", f"/tasks/{task['task_id']}/review", 200,
        payload={"analysis_id": task["analysis_id"], "state": "system_error", "comment": "только комментарий"},
        revision=comment["check_revision"], key=mutation_key(),
    ).body
    stale = client.expect("GET", f"{check}/summary", 200).body
    assert stale["stale"] is True
    assert stale["can_refresh"] is True
    assert stale["snapshot_id"] == original["snapshot_id"]

    refreshed = client.expect(
        "POST", f"{check}/summary/refresh", 202, revision=changed["check_revision"], key=mutation_key()
    ).body
    updated = wait_summary(client, check, "succeeded")
    assert updated["snapshot_id"] != original["snapshot_id"], "Refresh creates a new snapshot"
    assert updated["job_id"] == refreshed["job"]["id"]
    assert updated["stale"] is False
    assert client.request(
        "GET", f"{check}/summary/history"
    ).status == 403, "A teacher does not see launch history"


def test_rel_c22_disputed_review_is_excluded_from_confirmed_math():
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C22 смешанный")
    submit(client, check)
    job = client.expect("GET", check, 200).body["notebooks"][0]["bundles"][0]["job"]
    wait_job(client, job["id"], {"succeeded"})

    current = client.expect("GET", check, 200).body
    begin = client.expect(
        "POST", f"{check}/begin-completion", 200,
        revision=current["revision"], key=mutation_key(),
    ).body
    revision = begin["check_revision"]
    tasks = [item for notebook in current["notebooks"] for bundle in notebook["bundles"] for item in bundle["tasks"]]
    assert tasks
    for index, task in enumerate(tasks):
        state = "system_error" if index == 0 else "confirmed"
        payload = (
            {"analysis_id": task["analysis_id"]}
            if task["analysis"]["result"] == "not_assessed"
            else {"analysis_id": task["analysis_id"], "state": state, "comment": ""}
        )
        path = f"/tasks/{task['task_id']}/skip" if task["analysis"]["result"] == "not_assessed" else f"/tasks/{task['task_id']}/review"
        method = "POST" if task["analysis"]["result"] == "not_assessed" else "PUT"
        result = client.expect(method, path, 200, payload=payload, revision=revision, key=mutation_key()).body
        revision = result["check_revision"]

    final = client.expect("POST", f"{check}/finalize", 202, revision=revision, key=mutation_key()).body
    assert final["job"]["kind"] == "class_analytics"
    summary = wait_summary(client, check, "succeeded")
    result = summary["result"]
    assert result["schema_version"] == "class-summary/1"
    assert result["disputed_tasks"] >= 1, "A red review is counted separately"

    expected_top = int(psql(
        f"select count(*) from pilot_task_analyses t "
        f"join pilot_reviews v on v.analysis_id=t.id "
        f"join pilot_jobs j on j.id=t.job_id "
        f"where j.check_id='{check.rsplit('/', 1)[1]}' and v.state='confirmed' and not t.deleted "
        f"and (t.analysis->>'result')='first_error_found'"
    ))
    top_total = sum(len(group["task_ids"]) for group in result["top_errors"])
    assert top_total <= expected_top, "Top groups may reference only confirmed first errors"
    denominator = result["notebooks"]["with_errors"] + result["notebooks"]["without_errors"]
    if denominator == 0:
        assert result["average_errors_per_notebook"] is None, "Zero denominator means no average"
    else:
        assert result["average_errors_per_notebook"] is not None
    assert summary["stale"] is False


@pytest.mark.parametrize("case", [case["id"] for case in json.loads(
    (ANALYTICS_FIXTURES / "manifest.json").read_text(encoding="utf-8"))["cases"]])
def test_rel_c23_contract_fixtures_pass_the_worker_validator(case: str):
    """REL-C23: the four declared analytics pairs pass the real validator."""
    script = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, "/app")
from pilot.analytics.validation import validate_pair
base = Path("/fixtures")
snapshot = json.loads((base / "{case}.input.json").read_text(encoding="utf-8"))
result = json.loads((base / "{case}.result.json").read_text(encoding="utf-8"))
validate_pair(snapshot, result)
print("PASS")
"""
    compose("exec", "-T", "backend", "python", "-c", "import pathlib; print('ok')", check=False)
    compose(
        "cp", "project-context/pilot/planning/shared/analytics/fixtures",
        "backend:/fixtures", check=False,
    )
    outcome = compose("exec", "-T", "backend", "python", "-c", script, check=False)
    assert outcome.returncode == 0, outcome.stderr
    assert "PASS" in outcome.stdout


def test_rel_c23_invalid_result_is_rejected_not_repaired():
    """REL-C23: a wrong count or a foreign task id is refused, never fixed silently."""
    script = """
import json, sys
from pathlib import Path
sys.path.insert(0, "/app")
from pilot.analytics.validation import validate_pair
base = Path("/fixtures")
snapshot = json.loads((base / "oracle.input.json").read_text(encoding="utf-8"))
result = json.loads((base / "oracle.result.json").read_text(encoding="utf-8"))

broken = json.loads(json.dumps(result))
broken["notebooks"]["with_errors"] += 1
try:
    validate_pair(snapshot, broken)
    print("ACCEPTED")
except Exception:
    print("REJECTED")

foreign = json.loads(json.dumps(result))
foreign["top_errors"][0]["task_ids"] = ["00000000-0000-4000-8000-000000000000"]
try:
    validate_pair(snapshot, foreign)
    print("ACCEPTED")
except Exception:
    print("REJECTED")
"""
    compose(
        "cp", "project-context/pilot/planning/shared/analytics/fixtures",
        "backend:/fixtures", check=False,
    )
    outcome = compose("exec", "-T", "backend", "python", "-c", script, check=False)
    assert outcome.returncode == 0, outcome.stderr
    assert outcome.stdout.count("REJECTED") == 2, outcome.stdout


def test_rel_c19_pending_check_is_not_reported_as_done():
    """REL-C19: pending checker work blocks finalize and shows its state."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C19 ожидание")

    compose("stop", "worker")
    try:
        submit(client, check)
        current = client.expect("GET", check, 200).body
        assert current["notebooks"][0]["bundles"][0]["job"]["state"] == "queued"
        begin = client.expect(
            "POST", f"{check}/begin-completion", 200,
            revision=current["revision"], key=mutation_key(),
        ).body
        await_pending = client.expect("GET", check, 200).body
        assert await_pending["completion"]["pending_jobs"] >= 1
        blocked = client.request(
            "POST", f"{check}/finalize", revision=begin["check_revision"], key=mutation_key()
        )
        assert blocked.status == 409
        assert psql(
            f"select count(*) from pilot_jobs where check_id='{check.rsplit('/', 1)[1]}' and kind='class_analytics'"
        ) == "0"
    finally:
        compose("start", "worker")
        wait_healthy()
