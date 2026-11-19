"""Backup, restore and rollback acceptance (REL-C28) plus persistence (REL-C03/C04)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

from conftest import (
    ACCEPTANCE_PROJECT,
    PHOTO_FIXTURE,
    ROOT,
    Client,
    mutation_key,
    new_check,
    wait_healthy,
)

pytestmark = pytest.mark.release

RESTORE_PROJECT = "smartnote-restore-test"
BACKUP_ENV = {
    "PILOT_ENV_FILE": str(Path.home() / ".config/smartnote/pilot.env"),
    # The scripts default to the working project; acceptance must point them at
    # its own isolated project explicitly.
    "COMPOSE_PROJECT_NAME": ACCEPTANCE_PROJECT,
    "PILOT_BACKUP_PROJECT": ACCEPTANCE_PROJECT,
}


def psql(project: str, sql: str) -> str:
    return _compose(project, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc", sql).stdout.strip()


def _compose(project: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    command = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
    env_file = Path.home() / ".config/smartnote/pilot.env"
    if env_file.is_file():
        command.extend(["--env-file", str(env_file)])
    environment = dict(os.environ)
    environment["COMPOSE_PROJECT_NAME"] = project
    return subprocess.run(
        [*command, *args], cwd=ROOT, capture_output=True, text=True, check=check, env=environment
    )


def run_script(*args: str, expect: int = 0) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.update(BACKUP_ENV)
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False, env=environment
    )
    assert result.returncode == expect, (
        f"{args} exited {result.returncode}, expected {expect}: {result.stdout}{result.stderr}"
    )
    return result


def prepare_source() -> dict:
    """Create a check with a photo so the backup has real material."""
    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C28 бэкап")
    current = client.expect("GET", check, 200).body
    bundle = current["notebooks"][0]["bundles"][0]
    photo = client.expect(
        "POST", f"/input-versions/{bundle['draft']['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    return {"check": check, "photo": photo["entity_id"]}


def test_rel_c28_backup_and_restore_into_separate_project(tmp_path: Path):
    """REL-C28: a consistent private backup restores into a new project only."""
    _compose(RESTORE_PROJECT, "down", "-v", "--remove-orphans", check=False)
    material = prepare_source()

    _compose(ACCEPTANCE_PROJECT, "stop", "backend", "worker")
    try:
        backup_dir = tmp_path / "private-backups"
        result = run_script(
            str(ROOT / "scripts/pilot/backup_local.py"),
            "--destination", str(backup_dir),
            "--project", ACCEPTANCE_PROJECT,
        )
        manifest = json.loads(result.stdout.strip())
        bundle = Path(manifest["bundle"])
        assert bundle.is_dir()
        assert (bundle / "manifest.json").is_file()
        assert Path(manifest["database"]).name == "database.dump"
        assert (bundle / "database.dump").stat().st_size > 0
        assert (bundle / "photos.tar.gz").stat().st_size > 0
        if os.name == "posix":
            assert (bundle.stat().st_mode & 0o077) == 0, "The backup must be private"
        assert str(ROOT) not in str(bundle), "The backup must live outside the repository"
    finally:
        _compose(ACCEPTANCE_PROJECT, "start", "backend", "worker")
        wait_healthy()

    protected = run_script(
        str(ROOT / "scripts/pilot/restore_local.py"),
        "--bundle", str(bundle), "--project", "smartnote-pilot", expect=2,
    )
    assert "separate project" in protected.stderr

    wrong_prefix = run_script(
        str(ROOT / "scripts/pilot/restore_local.py"),
        "--bundle", str(bundle), "--project", "quiet-target", expect=2,
    )
    assert "smartnote-restore-" in wrong_prefix.stderr

    inside_repo = run_script(
        str(ROOT / "scripts/pilot/backup_local.py"),
        "--destination", str(ROOT / "backups"), "--project", ACCEPTANCE_PROJECT, expect=2,
    )
    assert "outside the repository" in inside_repo.stderr
    shutil.rmtree(ROOT / "backups", ignore_errors=True)

    restored = run_script(
        str(ROOT / "scripts/pilot/restore_local.py"),
        "--bundle", str(bundle), "--project", RESTORE_PROJECT,
    )
    report = json.loads(restored.stdout.strip())
    assert report["checks"] >= int(psql(ACCEPTANCE_PROJECT, "select count(*) from pilot_checks"))

    assert psql(RESTORE_PROJECT, "select count(*) from pilot_migrations") == "15"
    assert psql(RESTORE_PROJECT, "select count(*) from users") == "3"
    assert int(psql(RESTORE_PROJECT, "select count(*) from pilot_photo_assets")) >= 1
    assert psql(
        RESTORE_PROJECT,
        "select count(*) from pilot_photo_assets where id='" + material["photo"] + "'",
    ) == "1"

    for path in psql(RESTORE_PROJECT, "select normalized_path from pilot_photo_assets").splitlines():
        if not path.strip():
            continue
        exists = _compose(
            RESTORE_PROJECT, "exec", "-T", "backend", "sh", "-c", f"test -f '{path.strip()}'",
            check=False,
        )
        assert exists.returncode == 0, f"restored photo file missing: {path}"

    # The source project must be untouched by the restore.
    assert int(psql(ACCEPTANCE_PROJECT, "select count(*) from pilot_checks")) >= report["checks"]
    assert psql(
        ACCEPTANCE_PROJECT, "select spend_limit_rub from pilot_processing_budget where mode='fixture'"
    ).startswith("500"), "The source budget must stay intact"

    again = run_script(
        str(ROOT / "scripts/pilot/restore_local.py"),
        "--bundle", str(bundle), "--project", RESTORE_PROJECT, expect=2,
    )
    assert "already contains pilot data" in again.stderr

    _compose(RESTORE_PROJECT, "down", "-v", "--remove-orphans", check=False)


def test_rel_c28_unknown_reserve_survives_backup_and_restore(tmp_path: Path):
    """REL-C28: an unknown attempt keeps its reserve through backup and restore."""
    from conftest import reconcile_fixture_unknown

    client = Client()
    client.login("TEACHER_1")
    check, _ = new_check(client, "REL-C28 неизвестный")
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

    _compose(ACCEPTANCE_PROJECT, "stop", "worker")
    try:
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
        _compose(ACCEPTANCE_PROJECT, "exec", "-T", "backend", "python", "-c", script, check=False)
    finally:
        _compose(ACCEPTANCE_PROJECT, "start", "worker")

    attempt = psql(
        ACCEPTANCE_PROJECT,
        "select a.id from pilot_attempts a join pilot_jobs j on j.id=a.job_id "
        f"where j.id='{submitted['job']['id']}' and a.state='unknown'",
    )
    assert attempt, "The fixture must produce an unknown attempt"
    held_before = psql(
        ACCEPTANCE_PROJECT,
        f"select coalesce(sum(amount_rub),0) from pilot_fund_reservations where attempt_id='{attempt}' and active",
    )

    try:
        _compose(RESTORE_PROJECT, "down", "-v", "--remove-orphans", check=False)
        _compose(ACCEPTANCE_PROJECT, "stop", "backend", "worker")
        try:
            backup = json.loads(run_script(
                str(ROOT / "scripts/pilot/backup_local.py"),
                "--destination", str(tmp_path / "private"), "--project", ACCEPTANCE_PROJECT,
            ).stdout.strip())
        finally:
            _compose(ACCEPTANCE_PROJECT, "start", "backend", "worker")
            wait_healthy()

        run_script(
            str(ROOT / "scripts/pilot/restore_local.py"),
            "--bundle", backup["bundle"], "--project", RESTORE_PROJECT,
        )
        assert psql(
            RESTORE_PROJECT, f"select state from pilot_attempts where id='{attempt}'"
        ) == "unknown", "Restore must not turn an unknown attempt into success or free"
        held_after = psql(
            RESTORE_PROJECT,
            f"select coalesce(sum(amount_rub),0) from pilot_fund_reservations where attempt_id='{attempt}' and active",
        )
        assert held_after == held_before, "The reserve must survive backup and restore"
    finally:
        reconcile_fixture_unknown(attempt)
        _compose(RESTORE_PROJECT, "down", "-v", "--remove-orphans", check=False)


def test_rel_c03_migrations_are_serialized_and_idempotent():
    """REL-C03: two concurrent runners apply nothing twice."""
    before = psql(ACCEPTANCE_PROJECT, "select count(*) from pilot_migrations")
    assert before == "15"
    psql(ACCEPTANCE_PROJECT, "select 1")

    parallel = [
        subprocess.Popen(
            [
                "docker", "compose", "-f", str(ROOT / "compose.yaml"),
                "--env-file", str(Path.home() / ".config/smartnote/pilot.env"),
                "exec", "-T", "backend", "python", "-m", "pilot.domain.migrate",
            ],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "COMPOSE_PROJECT_NAME": ACCEPTANCE_PROJECT},
        )
        for _ in range(2)
    ]
    for process in parallel:
        _, errors = process.communicate(timeout=180)
        assert process.returncode == 0, errors

    after = psql(ACCEPTANCE_PROJECT, "select count(*) from pilot_migrations")
    assert after == before, "A repeated runner must not insert rows"
    checksums = psql(ACCEPTANCE_PROJECT, "select count(distinct sha256) from pilot_migrations")
    assert checksums == before


def test_rel_c03_applied_migration_checksum_is_enforced():
    """REL-C03: an edited applied migration is detected instead of silently rerun."""
    name = psql(ACCEPTANCE_PROJECT, "select name from pilot_migrations order by name limit 1")
    original = psql(ACCEPTANCE_PROJECT, f"select sha256 from pilot_migrations where name='{name}'")
    assert len(original) == 64

    psql(
        ACCEPTANCE_PROJECT,
        f"update pilot_migrations set sha256='{'0' * 64}' where name='{name}'",
    )
    try:
        result = _compose(
            ACCEPTANCE_PROJECT, "exec", "-T", "backend", "python", "-m", "pilot.domain.migrate",
            check=False,
        )
        assert result.returncode != 0, "A changed checksum must fail the runner"
        assert "checksum" in (result.stderr + result.stdout).lower()
    finally:
        psql(
            ACCEPTANCE_PROJECT,
            f"update pilot_migrations set sha256='{original}' where name='{name}'",
        )
    assert psql(ACCEPTANCE_PROJECT, "select count(*) from pilot_migrations") == "15"
