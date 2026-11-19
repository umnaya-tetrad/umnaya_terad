"""Closed staff read-only acceptance (REL-C07) on the real local stack."""
from __future__ import annotations

import subprocess
import time

import pytest

from conftest import (
    COMPOSE,
    PHOTO_FIXTURE,
    ROOT,
    Client,
    mutation_key,
    new_check,
    setting,
)

pytestmark = pytest.mark.release


def audit_for(name: str, check_id: str) -> list[str]:
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
         f"select coalesce(actor_id::text,'-') || '|' || role || '|' || coalesce(request_id::text,'-') "
         f"from pilot_audit where name='{name}' and check_id='{check_id}' order by created_at"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def submit_one_bundle(client: Client, check: str) -> tuple[dict, dict]:
    """Upload one synthetic page, submit it, and wait for the fixture checker."""
    current = client.expect("GET", check, 200).body
    notebook = current["notebooks"][0]
    bundle = notebook["bundles"][0]
    draft = bundle["draft"]
    photo = client.expect(
        "POST", f"/input-versions/{draft['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    submitted = client.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload={"input_version_id": draft["id"]},
        revision=photo["check_revision"], key=mutation_key(),
    ).body
    cutoff = time.monotonic() + 60
    while time.monotonic() < cutoff:
        job = client.expect("GET", f"/jobs/{submitted['job']['id']}", 200).body
        if job["state"] == "succeeded":
            return bundle, job
        time.sleep(1)
    raise AssertionError(f"Fixture checker did not finish: {job['state']}")


def test_rel_c07_staff_read_only_and_audited():
    staff = Client()
    assert staff.login("STAFF")["role"] == "staff"
    teacher = Client()
    teacher.login("TEACHER_1")
    other = Client()
    other.login("TEACHER_2")

    check, _revision = new_check(teacher, "REL-C07 поддержка")
    submit_one_bundle(teacher, check)
    check_id = check.rsplit("/", 1)[1]
    teacher_login = setting("PILOT_FIXTURE_TEACHER_1_LOGIN")
    other_login = setting("PILOT_FIXTURE_TEACHER_2_LOGIN")

    listing = staff.expect("GET", "/staff/checks", 200).body
    assert set(listing) == {"items", "next_cursor"}
    assert any(item["check"]["id"] == check_id for item in listing["items"])
    for item in listing["items"]:
        assert set(item) == {"owner", "check"}
        assert set(item["owner"]) == {"user_id", "login"}
        assert item["check"]["phase"] in {"editing", "review", "finalized"}

    filtered = staff.expect("GET", f"/staff/checks?owner_login={teacher_login}", 200).body
    assert filtered["items"]
    assert {item["owner"]["login"] for item in filtered["items"]} == {teacher_login}, (
        "The exact owner filter must not return another teacher"
    )

    foreign = staff.expect("GET", f"/staff/checks?owner_login={other_login}", 200).body
    assert all(item["owner"]["login"] == other_login for item in foreign["items"])
    assert all(item["check"]["id"] != check_id for item in foreign["items"])

    paged = staff.expect("GET", "/staff/checks?limit=1", 200).body
    assert paged["next_cursor"], "With more than one check the cursor must be present"
    seen = {item["check"]["id"] for item in paged["items"]}
    cursor = paged["next_cursor"]
    while cursor:
        page = staff.expect("GET", f"/staff/checks?limit=1&cursor={cursor}", 200).body
        ids = {item["check"]["id"] for item in page["items"]}
        assert not (ids & seen), "Pagination must not repeat an item"
        seen |= ids
        cursor = page["next_cursor"]
    assert check_id in seen

    detail = staff.expect("GET", f"/staff/checks/{check_id}", 200)
    assert detail.body["owner"]["login"] == teacher_login
    assert detail.body["check"]["id"] == check_id
    assert detail.headers["etag"] == f'"{detail.body["check"]["revision"]}"'
    assert detail.headers["cache-control"] == "private, no-store"

    teacher_read = teacher.request("GET", f"/staff/checks/{check_id}")
    assert teacher_read.status == 403

    bundle = detail.body["check"]["notebooks"][0]["bundles"][0]
    history = staff.expect("GET", f"/bundles/{bundle['id']}/history", 200).body
    assert history["bundle_id"] == bundle["id"]
    assert history["versions"], "The fixture must keep the submitted generation"
    run = history["versions"][-1]["runs"][-1]
    assert run["job"]["state"] == "succeeded"
    assert run["result"]["report"]["tasks"], "The history must retain the stored Report"
    assert teacher.request("GET", f"/bundles/{bundle['id']}/history").status == 403

    summary_history = staff.expect("GET", f"{check}/summary/history", 200).body
    assert set(summary_history) == {"items"}
    for item in summary_history["items"]:
        assert {"created_at", "summary"} <= set(item)
    assert teacher.request("GET", f"{check}/summary/history").status == 403

    photo_id = bundle["current_input"]["photos"][0]["id"]
    assert staff.expect("GET", f"/assets/{photo_id}", 200).headers["cache-control"] == "private, no-store"
    assert other.expect("GET", f"/assets/{photo_id}", 404).status == 404

    revision = detail.body["check"]["revision"]
    forbidden_mutations = [
        ("POST", f"{check}/notebooks", {"revision": revision, "key": mutation_key()}),
        ("DELETE", check, {"revision": revision, "key": mutation_key()}),
    ]
    for method, path, kwargs in forbidden_mutations:
        assert staff.request(method, path, **kwargs).status == 403, f"staff reached {method} {path}"

    before = teacher.expect("GET", check, 200).body
    staff.expect("GET", f"/staff/checks/{check_id}", 200)
    after = teacher.expect("GET", check, 200).body
    assert after["revision"] == before["revision"]
    assert after["data_revision"] == before["data_revision"]
    reviews_before = [(task["task_id"], task["review"]) for task in bundle["tasks"]]
    reviews_after = [(task["task_id"], task["review"]) for task in after["notebooks"][0]["bundles"][0]["tasks"]]
    assert reviews_after == reviews_before, "A staff read must not touch reviews"

    reads = audit_for("staff_read_check", check_id)
    assert reads, "Every staff read of a check must be audited"
    assert all(row.split("|")[1] == "staff" for row in reads), reads
    assert all(row.split("|")[2] != "-" for row in reads), "The audit must keep the real request id"

    assert audit_for("staff_read_bundle_history", check_id)
    assert audit_for("staff_read_summary_history", check_id)
    assert audit_for("staff_read_photo", check_id)

    for name in ("create_notebook", "delete_check", "save_review", "finalize_check"):
        rows = audit_for(name, check_id)
        assert all(row.split("|")[1] != "staff" for row in rows), f"staff mutation was audited as {name}"


def test_rel_c07_ui_has_no_review_or_mutation_controls():
    """Static check of the release-owned staff module against the shared copy catalog."""
    from pathlib import Path

    module = Path(ROOT / "src/pilot/staff/StaffScreens.tsx").read_text(encoding="utf-8")
    for forbidden in (
        "ReviewControls", "saveReview", "deleteTask", "skipTask", "retryBundle",
        "finalizeCheck", "refreshSummary", "attach(", "uploadPhoto",
    ):
        assert forbidden not in module, f"Staff UI must not call {forbidden}"
    for required in ("staff.readonly", "staff.review_confirmed", "staff.review_system_error",
                     "staff.review_missing"):
        assert required in module, f"Staff UI must use the shared copy key {required}"
