"""Events and load acceptance (REL-C24/C25) without paid calls."""
from __future__ import annotations

import time
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from conftest import (
    PHOTO_FIXTURE,
    Client,
    compose,
    mutation_key,
    new_check,
)

pytestmark = pytest.mark.release

EVENT_NAMES = [
    "capture_opened", "photo_selected", "result_opened", "result_closed",
    "app_visible", "app_hidden", "heartbeat",
]


def psql(sql: str) -> str:
    return compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc", sql
    ).stdout.strip()


def check_uuid(check: str) -> str:
    """The API path is /checks/{uuid}; events need the bare uuid."""
    return check.rsplit("/", 1)[1]


def event(name: str, check_id: str | None = None, entity_id: str | None = None) -> dict:
    return {
        "id": str(uuid4()),
        "session_id": str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "name": name,
        "check_id": check_id,
        "entity_id": entity_id,
    }


def submit(client: Client, check: str) -> dict:
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


def test_rel_c25_batch_dedupe_and_bounds():
    """REL-C25: identical replays are accepted once; different payloads conflict."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C25 события")

    batch = {"events": [event(name, check_uuid(check)) for name in EVENT_NAMES]}
    accepted = client.expect("POST", "/events", 202, payload=batch).body
    assert sorted(accepted["accepted_ids"]) == sorted(item["id"] for item in batch["events"])
    assert client.expect("POST", "/events", 202, payload=batch).body == accepted, "A replay must not duplicate"

    stored = int(psql(
        "select count(*) from pilot_events where payload->>'check_id'='" + check.rsplit('/', 1)[1] + "'"
    ))
    assert stored == len(EVENT_NAMES)

    conflicting = {"events": [{**batch["events"][0], "name": "heartbeat"}]}
    conflict = client.request("POST", "/events", payload=conflicting)
    assert conflict.status == 409, conflict.status
    assert conflict.body["error"]["code"] == "idempotency_conflict"

    duplicate_in_one_batch = {"events": [batch["events"][0], {**batch["events"][0], "name": "heartbeat"}]}
    same_batch = client.request("POST", "/events", payload=duplicate_in_one_batch)
    assert same_batch.status == 409


def test_rel_c25_foreign_reference_is_refused_without_partial_accept():
    client = Client()
    client.login("TEACHER_1")
    other = Client()
    other.login("TEACHER_2")

    foreign_check, _ = new_check(client, "REL-C25 чужой")
    own_check, _ = new_check(other, "REL-C25 свой")

    foreign_entity = event("photo_selected", check_uuid(foreign_check), str(uuid4()))
    own_event = event("app_visible", check_uuid(own_check))
    response = other.request("POST", "/events", payload={"events": [own_event, foreign_entity]})
    assert response.status == 404, response.status

    accepted = int(psql(
        "select count(*) from pilot_events where payload->>'check_id'='" + own_check.rsplit('/', 1)[1] + "'"
    ))
    assert accepted == 0, "A rejected batch must not accept any of its events"

    bogus_entity = client.request(
        "POST", "/events",
        payload={"events": [event("photo_selected", check_uuid(foreign_check), str(uuid4()))]},
    )
    assert bogus_entity.status == 404

    attach_entity_without_check = client.request(
        "POST", "/events", payload={"events": [event("photo_selected", None, str(uuid4()))]}
    )
    assert attach_entity_without_check.status == 404


def test_rel_c25_batch_limit_and_server_attribution():
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C25 предел")

    too_many = client.request(
        "POST", "/events",
        payload={"events": [event("heartbeat", check_uuid(check)) for _ in range(101)]},
    )
    assert too_many.status == 422, too_many.status

    hundred = client.expect(
        "POST", "/events", 202,
        payload={"events": [event("heartbeat", check_uuid(check)) for _ in range(100)]},
    ).body
    assert len(hundred["accepted_ids"]) == 100

    rows = psql(
        "select count(distinct role) || '|' || min(role) from pilot_events "
        "where payload->>'check_id'='" + check.rsplit('/', 1)[1] + "'"
    )
    assert rows == "1|teacher", "The server must set actor/role, not the client"

    forged = event("heartbeat", check_uuid(check))
    forged["role"] = "staff"
    forged["actor_id"] = str(uuid4())
    forged["received_at"] = "2000-01-01T00:00:00Z"
    rejected = client.request("POST", "/events", payload={"events": [forged]})
    assert rejected.status == 422, rejected.status


def test_rel_c25_telemetry_failure_does_not_block_the_teacher_path():
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C25 потеря")

    broken = client.request("POST", "/events", payload={"events": [{"name": "app_visible"}]})
    assert broken.status == 422

    submitted = submit(client, check)
    assert submitted["job"]["id"]
    current = client.expect("GET", check, 200).body
    assert current["notebooks"][0]["bundles"][0]["current_input"] is not None


def test_rel_c25_logs_contain_no_material_or_secret():
    """REL-C25: no photo bytes, report text, comment, password or key in the shared journal."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C25 журнал")
    current = client.expect("GET", check, 200).body
    bundle = current["notebooks"][0]["bundles"][0]
    photo = client.expect(
        "POST", f"/input-versions/{bundle['draft']['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    submitted = client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload={"input_version_id": bundle["draft"]["id"]},
        revision=photo["check_revision"], key=mutation_key(),
    ).body
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if client.expect("GET", f"/jobs/{submitted['job']['id']}", 200).body["state"] == "succeeded":
            break
        time.sleep(1)

    check_id = check_uuid(check)
    payloads = psql(
        "select coalesce(string_agg(payload::text, ' '), '') from pilot_events "
        f"where payload->>'check_id'='{check_id}'"
    )
    audits = psql(
        "select coalesce(string_agg(payload::text, ' '), '') from pilot_audit "
        f"where check_id='{check_id}'"
    )
    combined = (payloads + " " + audits).lower()
    for forbidden in ("data:image", "base64", "password", "cookie", "sk-", "prompt",
                      "corrected_latex", "explanation", PHOTO_FIXTURE.read_bytes()[:16].hex()):
        assert forbidden.lower() not in combined, f"{forbidden} leaked into the journal"

    cost_rows = psql(
        "select coalesce(sum((payload->>'cost_known')::int), 0) from pilot_audit "
        f"where check_id='{check_id}' and name='attempt_settled'"
    )
    assert int(cost_rows) >= 0
    funds = psql(
        "select count(*) from pilot_fund_ledger l join pilot_attempts a on a.id=l.attempt_id "
        f"join pilot_jobs j on j.id=a.job_id where j.check_id='{check_id}'"
    )
    assert int(funds) >= 1, "Money lives in the ledger, not in a generic event"


def test_rel_c24_two_teachers_sixty_notebooks_without_mixing(controlled_provider):
    """60 real uploads/Jobs -> 240 Tasks, two overlapping worker POSTs, exact ledger.

    Only the provider HTTP boundary is synthetic. This measures fixture pipeline
    integrity, not Gemini throughput or mathematical recognition quality.
    """
    from decimal import Decimal

    control = controlled_provider
    teachers = [Client(), Client()]
    for client, account in zip(teachers, ("TEACHER_1", "TEACHER_2")):
        client.login(account)
    checks = [new_check(client, f"REL-C24 controlled owner {i}")[0] for i, client in enumerate(teachers)]
    expected = {check: [] for check in checks}
    jobs = []
    spent_before = Decimal(control.sql("SELECT spent_rub FROM pilot_processing_budget WHERE mode='fixture'"))
    for index in range(30):
        for owner, (client, check) in enumerate(zip(teachers, checks)):
            current = client.expect("GET", check, 200).body
            if index == 0:
                bundle = current["notebooks"][0]["bundles"][0]
            else:
                notebook = client.expect("POST", f"{check}/notebooks", 201,
                                         revision=current["revision"], key=mutation_key()).body
                created = client.expect("POST", f"/notebooks/{notebook['entity_id']}/bundles", 201,
                                        revision=notebook["check_revision"], key=mutation_key()).body
                current = client.expect("GET", check, 200).body
                bundle = next(book for book in current["notebooks"] if book["id"] == notebook["entity_id"])["bundles"][0]
                assert created["entity_id"] == bundle["id"]
            photo = client.expect("POST", f"/input-versions/{bundle['draft']['id']}/photos", 201,
                                  revision=current["revision"], key=mutation_key(),
                                  photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes())).body
            submitted = client.expect("POST", f"/bundles/{bundle['id']}/submit", 202,
                                      payload={"input_version_id": bundle["draft"]["id"]},
                                      revision=photo["check_revision"], key=mutation_key()).body
            job = submitted["job"]
            count = 3 + index % 3
            control.register(job, count, released=False, delay_ms=(index % 3) * 15)
            jobs.append(job)
            expected[check].append((bundle["id"], bundle["draft"]["id"], photo["entity_id"], count, job["id"]))
            # History and foreign-ID protection remain available with queued work.
            assert teachers[1 - owner].request("GET", check).status == 404
            assert client.expect("GET", "/checks?limit=100", 200).body["items"]
    assert len(jobs) == 60
    first, second = control.worker(), control.worker()
    control.wait("SELECT count(*) FROM release_test_posts WHERE ended_at IS NULL", 2)
    assert control.sql("SELECT count(*) FROM pilot_slots WHERE attempt_id IS NOT NULL") == "2"
    third = control.worker()
    assert json.loads(control.finish(third))["claimed"] is False
    assert control.sql("SELECT count(*) FROM release_test_posts") == "2"
    # Finish the second submitted job while the first is still blocked inside POST.
    control.sql(f"UPDATE release_test_jobs SET released=true WHERE job_id='{jobs[1]['id']}'")
    control.wait(f"SELECT state FROM pilot_jobs WHERE id='{jobs[1]['id']}'", "succeeded")
    assert control.sql(f"SELECT state FROM pilot_jobs WHERE id='{jobs[0]['id']}'") == "running"
    assert teachers[0].expect("GET", checks[0], 200).body["notebooks"][0]["bundles"][0]["tasks"] == []
    assert teachers[1].expect("GET", checks[1], 200).body["notebooks"][0]["bundles"][0]["tasks"]
    control.sql("UPDATE release_test_jobs SET released=true")
    control.finish(first)
    control.finish(second)
    drains = [control.worker("drain"), control.worker("drain")]
    for process in drains:
        control.finish(process, timeout=180)
    assert control.sql("SELECT count(*) FROM pilot_jobs j JOIN release_test_jobs t ON t.job_id=j.id WHERE j.state='succeeded'") == "60"
    assert control.sql("SELECT count(*) FROM release_test_posts WHERE method='POST' AND http_status=200") == "60"
    assert control.sql("SELECT max(active_slots) FROM release_test_posts") == "2"
    assert control.sql("SELECT EXISTS(SELECT 1 FROM release_test_posts a JOIN release_test_posts b ON a.id<b.id AND a.started_at<b.ended_at AND b.started_at<a.ended_at)") == "t"
    unique_tasks = set()
    for client, stranger, check in zip(teachers, reversed(teachers), checks):
        current = client.expect("GET", check, 200).body
        assert len(current["notebooks"]) == 30
        assert [book["number"] for book in current["notebooks"]] == list(range(1, 31))
        assert sum(len(book["bundles"][0]["tasks"]) for book in current["notebooks"]) == 120
        for book, (bundle_id, input_id, photo_id, count, job_id) in zip(current["notebooks"], expected[check]):
            bundle = book["bundles"][0]
            assert bundle["id"] == bundle_id and bundle["current_input"]["id"] == input_id
            assert bundle["job"]["id"] == job_id and len(bundle["tasks"]) == count
            assert [photo["id"] for photo in bundle["current_input"]["photos"]] == [photo_id]
            for task in bundle["tasks"]:
                assert task["task_id"] not in unique_tasks
                unique_tasks.add(task["task_id"])
            assert stranger.request("GET", f"/jobs/{job_id}").status == 404
            assert stranger.request("GET", f"/assets/{photo_id}").status == 404
            assert client.expect("GET", f"/assets/{photo_id}", 200).content
    assert len(unique_tasks) == 240
    assert control.sql("SELECT count(*) FROM pilot_attempts a JOIN release_test_jobs t ON t.job_id=a.job_id") == "60"
    assert control.sql("SELECT count(*) FROM pilot_fund_ledger l JOIN pilot_attempts a ON a.id=l.attempt_id JOIN release_test_jobs t ON t.job_id=a.job_id WHERE l.operation='settlement'") == "60"
    amount = control.sql("SELECT sum(l.amount_rub) FROM pilot_fund_ledger l JOIN pilot_attempts a ON a.id=l.attempt_id JOIN release_test_jobs t ON t.job_id=a.job_id WHERE l.operation='settlement'")
    assert Decimal(amount) == Decimal("0.60")
    assert Decimal(control.sql("SELECT spent_rub FROM pilot_processing_budget WHERE mode='fixture'")) - spent_before == Decimal("0.60")
    assert control.sql("SELECT count(*) FROM pilot_fund_reservations r JOIN pilot_attempts a ON a.id=r.attempt_id JOIN release_test_jobs t ON t.job_id=a.job_id WHERE r.active") == "0"
    assert control.sql("SELECT count(*) FROM pilot_slots WHERE attempt_id IS NOT NULL") == "0"
