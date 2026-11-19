"""Compose, migration and persistence acceptance (REL-C02/C03/C04)."""
from __future__ import annotations

import json

import pytest

from conftest import (
    PHOTO_FIXTURE,
    Client,
    backend_health,
    compose,
    compose_json,
    credentials,
    fixture_backend,
    mutation_key,
    new_check,
    wait_healthy,
)

pytestmark = pytest.mark.release


def test_rel_c02_clean_compose_and_fail_closed(tmp_path):
    """REL-C02: one transport source, healthy services, fail-closed polza."""
    fixture_backend()
    configuration = compose_json()

    transport = configuration["services"]["backend"]["environment"]["PILOT_TRANSPORT"]
    frontend_transport = configuration["services"]["frontend"]["environment"]["VITE_PILOT_TRANSPORT"]
    assert transport == "fixture"
    assert frontend_transport == transport, "Compose must pass one transport source to the frontend"

    for service in ("postgres", "backend", "worker", "frontend"):
        assert service in configuration["services"], service
    assert configuration["services"]["migrate"], "A one-shot migrate service is required"

    assert configuration["services"]["backend"].get("ports") in (None, []), "Backend must stay on the private network"
    assert configuration["services"]["worker"].get("ports") in (None, []), "Worker must stay on the private network"

    volumes = configuration["volumes"]
    backend_volumes = json.dumps(configuration["services"]["backend"].get("volumes", []))
    worker_volumes = json.dumps(configuration["services"]["worker"].get("volumes", []))
    assert "pilot_photos" in backend_volumes and "pilot_photos" in worker_volumes
    assert "postgres_data" in volumes and "pilot_photos" in volumes
    assert "pilot_photos" not in json.dumps(configuration["services"]["frontend"].get("volumes", [])), (
        "The private photo volume must not be mounted into the frontend container"
    )

    status = compose("ps", "--format", "json").stdout
    services = [json.loads(line) for line in status.splitlines() if line.strip()]
    health = {item["Service"]: item["Health"] for item in services if item.get("Health")}
    for name in ("postgres", "backend", "worker", "frontend"):
        assert health.get(name) == "healthy", f"{name} is not healthy: {health}"

    health_response = backend_health()
    assert health_response == "ok"

    denied = compose(
        "run", "--rm", "--no-deps", "-e", "PILOT_TRANSPORT=polza", "-e", "POLZA_API_KEY=",
        "backend", "python", "-c",
        "import asyncio, main\n"
        "async def run():\n"
        "    try:\n"
        "        async with main.lifespan(main.app):\n"
        "            pass\n"
        "    except RuntimeError as exc:\n"
        "        print('REFUSED', exc)\n"
        "        return\n"
        "    print('STARTED')\n"
        "asyncio.run(run())\n",
        check=False,
    )
    assert "REFUSED" in denied.stdout, denied.stdout + denied.stderr
    assert "POLZA_API_KEY" in denied.stdout


def test_rel_c03_migration_chain_is_idempotent_and_serialized():
    """REL-C03: a repeated runner applies nothing twice; two runners serialize."""
    applied = compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
        "select count(*) from pilot_migrations",
    ).stdout.strip()
    names = compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
        "select name from pilot_migrations order by name",
    ).stdout.split()
    assert int(applied) == 15
    assert names[0] == "001_daily_quota.sql" and names[-1] == "015_pilot_pause_upgrade.sql"
    assert len(set(names)) == 15, "A migration name was applied twice"

    compose("run", "--rm", "migrate")
    again = compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
        "select count(*) from pilot_migrations",
    ).stdout.strip()
    assert again == applied, "A repeated migrate must not insert rows"

    first = compose("run", "--rm", "migrate", check=False)
    second = compose("run", "--rm", "migrate", check=False)
    assert first.returncode == 0 and second.returncode == 0, (first.stderr, second.stderr)
    final = compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
        "select count(*) from pilot_migrations",
    ).stdout.strip()
    assert final == applied

    checksums = compose(
        "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
        "select count(distinct sha256) from pilot_migrations",
    ).stdout.strip()
    assert checksums == applied, "Recorded checksums must stay unique per file"


def test_rel_c04_state_survives_restart():
    """REL-C04: accepted work, reviews and summary survive a restart."""
    teacher = Client()
    teacher.login("TEACHER_1")
    other = Client()
    other.login("TEACHER_2")

    check, revision = new_check(teacher, "REL-C04 сохранение")
    current = teacher.expect("GET", check, 200).body
    notebook = current["notebooks"][0]
    bundle = notebook["bundles"][0]
    draft = bundle["draft"]
    photo = teacher.expect(
        "POST", f"/input-versions/{draft['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    photo_id = photo["entity_id"]
    original_bytes = teacher.expect("GET", f"/assets/{photo_id}", 200).content

    submitted = teacher.expect(
        "POST", f"/bundles/{bundle['id']}/submit", 202,
        payload={"input_version_id": draft["id"]},
        revision=photo["check_revision"], key=mutation_key(),
    ).body
    job_id = submitted["job"]["id"]

    assert other.expect("GET", check, 404).status == 404
    assert other.expect("GET", f"/assets/{photo_id}", 404).status == 404
    assert other.expect("GET", f"/jobs/{job_id}", 404).status == 404

    compose("restart", "backend", "worker")
    wait_healthy()

    again = Client()
    session = again.login("TEACHER_1")
    assert session["role"] == "teacher"
    restored = again.expect("GET", check, 200).body
    assert restored["id"] == check.rsplit("/", 1)[1]
    restored_photo = again.expect("GET", f"/assets/{photo_id}", 200)
    assert restored_photo.content == original_bytes, "Normalized bytes changed across a restart"
    assert restored_photo.headers.get("Cache-Control") == "private, no-store"
    job = again.expect("GET", f"/jobs/{job_id}", 200).body
    assert job["state"] in {"queued", "running", "succeeded"}, job["state"]

    stranger = Client()
    stranger.login("TEACHER_2")
    assert stranger.expect("GET", check, 404).status == 404
    assert stranger.expect("GET", f"/assets/{photo_id}", 404).status == 404


def test_rel_c26_removed_surfaces_are_absent():
    """REL-C26: no registration, anonymous analysis or HTTP control endpoints."""
    anonymous = Client()
    for path in ("/auth/register", "/analyze", "/api/analyze"):
        status = anonymous.request("POST", path, payload={"login": "x", "password": "y"}).status
        assert status in {404, 405}, f"{path} unexpectedly answered {status}"

    teacher = Client()
    teacher.login("TEACHER_1")
    for path in (
        "/processing/pause",
        "/processing/control",
        "/budget",
        "/admin/control",
        "/staff/checks",
    ):
        status = teacher.request("GET", path).status
        assert status in {403, 404}, f"teacher unexpectedly reached {path} with {status}"

    created = teacher.expect("POST", "/checks", 201, payload={"title": "REL-C26"}, key=mutation_key()).body
    check = f"/checks/{created['check_id']}"
    rejected = teacher.request(
        "PATCH", check, payload={"title": "renamed"}, revision=created["check_revision"], key=mutation_key()
    )
    assert rejected.status in {404, 405}, "The check title must not be editable"


def test_rel_c02_frontend_is_not_a_public_photo_host():
    """REL-C02: origin/cookie rules and no static photo route."""
    anonymous = Client()
    login_without_origin = anonymous.request("POST", "/auth/login", payload=credentials("TEACHER_1"), send_origin=False)
    assert login_without_origin.status == 403

    foreign = Client()
    assert foreign.request(
        "POST", "/auth/login", payload=credentials("TEACHER_1"), origin_override="https://evil.example"
    ).status == 403

    teacher = Client()
    teacher.login("TEACHER_1")
    cookie = teacher.expect("POST", "/auth/login", 200, payload=credentials("TEACHER_1"))
    set_cookie = cookie.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()

    check, revision = new_check(teacher, "REL-C02 приватность")
    current = teacher.expect("GET", check, 200).body
    draft = current["notebooks"][0]["bundles"][0]["draft"]
    photo = teacher.expect(
        "POST", f"/input-versions/{draft['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body

    direct = teacher.request("GET", f"/photos/{photo['entity_id']}")
    assert direct.status == 404, "A photo must not be served from a static path"
    assert teacher.expect("GET", f"/assets/{photo['entity_id']}", 200).headers["Cache-Control"] == "private, no-store"

    foreign_write = teacher.request(
        "POST", f"{check}/notebooks", revision=photo["check_revision"], key=mutation_key(),
        origin_override="https://evil.example",
    )
    assert foreign_write.status == 403
    missing_origin = teacher.request(
        "POST", f"{check}/notebooks", revision=photo["check_revision"], key=mutation_key(), send_origin=False
    )
    assert missing_origin.status == 403
