"""Accounts, ACL and Origin acceptance (REL-C05/C06)."""
from __future__ import annotations

import subprocess
from uuid import uuid4

import pytest

from conftest import (
    COMPOSE,
    PHOTO_FIXTURE,
    ROOT,
    Client,
    credentials,
    mutation_key,
    new_check,
    setting,
)

pytestmark = pytest.mark.release

NEW_PASSWORD = "ReleaseReset2026pass"


def cli(*args: str, password: str | None = None, expect: int = 0) -> subprocess.CompletedProcess:
    command = [*COMPOSE, "exec", "-T"]
    if password is not None:
        command.extend(["-e", f"PILOT_ACCOUNT_PASSWORD={password}"])
    command.extend(["backend", "python", "-m", "pilot.operations.manage_accounts", *args])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == expect, f"CLI exited {result.returncode}, expected {expect}: {result.stdout}{result.stderr}"
    return result


def restore_teacher_password() -> None:
    cli(
        "reset", "--login", setting("PILOT_FIXTURE_TEACHER_1_LOGIN"),
        password=setting("PILOT_FIXTURE_TEACHER_1_PASSWORD"),
    )


def test_rel_c05_seed_roles_login_and_reset():
    """REL-C05: exactly three fixture accounts, working login, safe reset."""
    counts = subprocess.run(
        [*COMPOSE, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
         "select role || '=' || count(*) from users group by role order by role"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert counts == ["staff=1", "teacher=2"], counts

    seeded = cli("seed")
    assert seeded.stdout.count("seeded:") == 3
    again = cli("seed")
    assert again.stdout.count("seeded:") == 3

    sessions = {}
    for account in ("TEACHER_1", "TEACHER_2", "STAFF"):
        client = Client()
        session = client.login(account)
        sessions[account] = (client, session)
        assert session["role"] == ("staff" if account == "STAFF" else "teacher")
        assert client.expect("GET", "/auth/session", 200).body["user_id"] == session["user_id"]

    teacher, teacher_session = sessions["TEACHER_1"]
    teacher.expect("POST", "/auth/logout", 204)
    assert teacher.request("GET", "/auth/session").status == 401, "Logout must revoke the cookie"

    teacher = Client()
    teacher.login("TEACHER_1")
    check, revision = new_check(teacher, "REL-C05 данные учителя")
    second = sessions["TEACHER_2"][0]
    staff = sessions["STAFF"][0]

    try:
        reset = cli(
            "reset", "--login", setting("PILOT_FIXTURE_TEACHER_1_LOGIN"), password=NEW_PASSWORD
        )
        assert "reset:" in reset.stdout
        assert NEW_PASSWORD not in reset.stdout and NEW_PASSWORD not in reset.stderr

        assert teacher.request("GET", check).status == 401, "Reset must revoke existing sessions"
        assert teacher.request("GET", "/auth/session").status == 401

        fresh = Client()
        rejected = fresh.request("POST", "/auth/login", payload=credentials("TEACHER_1"))
        assert rejected.status == 401, "The old password must stop working"

        relogin = fresh.request(
            "POST", "/auth/login",
            payload={"login": setting("PILOT_FIXTURE_TEACHER_1_LOGIN"), "password": NEW_PASSWORD},
        )
        assert relogin.status == 200 and relogin.body["role"] == "teacher"
        restored = fresh.expect("GET", check, 200).body
        assert restored["title"] == "REL-C05 данные учителя"

        assert second.expect("GET", "/auth/session", 200).body["role"] == "teacher"
        assert staff.expect("GET", "/auth/session", 200).body["role"] == "staff"
        assert second.expect("GET", check, 404).status == 404
    finally:
        restore_teacher_password()

    check_still_there = Client()
    check_still_there.login("TEACHER_1")
    assert check_still_there.expect("GET", check, 200).body["title"] == "REL-C05 данные учителя"


def test_rel_c05_cli_rejects_unsafe_input():
    """REL-C05: no argv password, no silent role change, no unknown account."""
    username = setting("PILOT_FIXTURE_TEACHER_1_LOGIN")

    mismatch = cli("create", "--login", username, "--role", "staff", password=NEW_PASSWORD, expect=1)
    assert "invalid_state" in mismatch.stderr

    missing = cli("reset", "--login", "release-missing-account", password=NEW_PASSWORD, expect=1)
    assert "not_found" in missing.stderr

    no_password = subprocess.run(
        [*COMPOSE, "exec", "-T", "backend", "python", "-m", "pilot.operations.manage_accounts",
         "reset", "--login", username, "--password", NEW_PASSWORD],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert no_password.returncode != 0, "The CLI must not accept a password as a flag"
    assert "unrecognized arguments" in no_password.stderr, no_password.stderr

    unchanged = Client()
    unchanged.login("TEACHER_1")
    assert unchanged.expect("GET", "/auth/session", 200).body["role"] == "teacher"


def test_rel_c06_acl_and_origin_on_real_http():
    """REL-C06: foreign IDs are hidden, staff is read-only, writes need exact Origin."""
    owner = Client()
    owner.login("TEACHER_1")
    other = Client()
    other.login("TEACHER_2")
    staff = Client()
    staff.login("STAFF")

    check, revision = new_check(owner, "REL-C06 доступ")
    current = owner.expect("GET", check, 200).body
    draft = current["notebooks"][0]["bundles"][0]["draft"]
    photo = owner.expect(
        "POST", f"/input-versions/{draft['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    bundle_id = current["notebooks"][0]["bundles"][0]["id"]
    task_id = str(uuid4())
    analysis_id = str(uuid4())

    hidden = [
        ("GET", check, None),
        ("GET", f"/assets/{photo['entity_id']}", None),
        ("DELETE", check, revision),
        ("POST", f"{check}/notebooks", owner.expect("GET", check, 200).body["revision"]),
        ("PUT", f"/tasks/{task_id}/review", 1),
        ("DELETE", f"/tasks/{task_id}", 1),
    ]
    for method, path, rev in hidden:
        kwargs = {"key": mutation_key()} if method in {"POST", "PUT", "DELETE", "PATCH"} else {}
        if rev is not None:
            kwargs["revision"] = rev
        if method == "PUT":
            kwargs["payload"] = {"analysis_id": analysis_id, "state": "confirmed", "comment": ""}
        response = other.request(method, path, **kwargs)
        assert response.status == 404, f"{method} {path} leaked {response.status}"

    # Staff-only history endpoints answer 403 for a teacher and hide content.
    for path in (f"/bundles/{bundle_id}/history", f"{check}/summary/history"):
        assert other.request("GET", path).status == 403, f"{path} must not leak to a teacher"
        assert owner.request("GET", path).status == 403

    assert other.expect("GET", f"/assets/{photo['entity_id']}", 404).status == 404
    assert staff.expect("GET", f"/assets/{photo['entity_id']}", 200).status == 200

    # REL-04 mounts the real staff surface: staff reads its own list, a teacher is refused.
    staff_list = staff.expect("GET", "/staff/checks", 200).body
    assert staff_list["items"], "The staff list must show material created for acceptance"
    assert all("login" in item["owner"] for item in staff_list["items"])
    assert owner.request("GET", "/staff/checks").status == 403
    assert other.request("GET", "/staff/checks").status == 403

    current_revision = owner.expect("GET", check, 200).body["revision"]
    staff_write = staff.request(
        "POST", f"{check}/notebooks", revision=current_revision, key=mutation_key()
    )
    assert staff_write.status == 403
    staff_review = staff.request(
        "PUT", f"/tasks/{task_id}/review",
        payload={"analysis_id": analysis_id, "state": "confirmed", "comment": ""},
        revision=current_revision, key=mutation_key(),
    )
    assert staff_review.status == 403

    anonymous = Client()
    assert anonymous.request("GET", check).status == 401
    assert anonymous.request("GET", f"/assets/{photo['entity_id']}").status == 401
    assert anonymous.request(
        "POST", f"{check}/notebooks", revision=current_revision, key=mutation_key()
    ).status == 401

    for origin_value, send in (("", True), ("https://evil.example", True), (None, False)):
        kwargs = {"revision": current_revision, "key": mutation_key()}
        if send:
            kwargs["origin_override"] = origin_value
        else:
            kwargs["send_origin"] = False
        denied = owner.request("POST", f"{check}/notebooks", **kwargs)
        assert denied.status == 403, f"Origin {origin_value!r} (send={send}) was not rejected"

    fresh_revision = owner.expect("GET", check, 200).body["revision"]
    assert fresh_revision == current_revision, "Rejected writes must not change the check"

    asset = owner.expect("GET", f"/assets/{photo['entity_id']}", 200)
    assert asset.headers["cache-control"] == "private, no-store"
    assert asset.headers.get("x-content-type-options") == "nosniff"
    assert asset.content == PHOTO_FIXTURE.read_bytes()

    denied_logout = Client()
    denied_logout.login("TEACHER_1")
    assert denied_logout.request("POST", "/auth/logout", send_origin=False).status == 403
    assert denied_logout.expect("GET", "/auth/session", 200).status == 200
