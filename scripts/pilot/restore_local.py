"""Restore a private local backup into a separate Compose project.

Safety rules (REL-11/REL-C28):

* the restore target must be a **new** project name, never the working one;
* the target must not already hold a database with pilot data;
* the source backup directory is read-only for this script;
* unknown attempts and their reserves are restored as-is: they must not become
  "free" or be retried automatically.

The script never prints secrets and never touches the source project.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_TARGETS = {"smartnote-pilot"}


class RestoreError(Exception):
    """A safe, user-facing failure."""


def env_file() -> Path | None:
    explicit = os.getenv("PILOT_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()
    candidate = Path.home() / ".config/smartnote/pilot.env"
    return candidate if candidate.is_file() else None


def compose(project: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    command = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
    if env_file() is not None:
        command.extend(["--env-file", str(env_file())])
    environment = dict(os.environ)
    environment["COMPOSE_PROJECT_NAME"] = project
    return subprocess.run(
        [*command, *args], cwd=ROOT, capture_output=True, text=True, check=check, env=environment
    )


def check_target(project: str) -> None:
    if not project or project in FORBIDDEN_TARGETS:
        raise RestoreError(
            "Restore needs a separate project name; the working project must never be overwritten."
        )
    if not project.startswith("smartnote-restore-"):
        raise RestoreError(
            "Use an explicit restore project, e.g. smartnote-restore-test, so the target is unmistakable."
        )


def read_manifest(bundle: Path) -> dict:
    manifest = bundle / "manifest.json"
    if not manifest.is_file():
        raise RestoreError(f"{bundle} is not a pilot backup: manifest.json is missing.")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise RestoreError("manifest.json is not valid JSON.") from None
    for key in ("database", "photos", "created_at"):
        if not data.get(key):
            raise RestoreError(f"manifest.json lacks {key}.")
    return data


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    """Extract a backup archive without allowing path traversal."""
    root = destination.resolve()
    members = []
    for member in archive.getmembers():
        target = (root / member.name).resolve()
        if root != target and root not in target.parents:
            raise RestoreError(f"unsafe path in the photo archive: {member.name}")
        if member.issym() or member.islnk():
            raise RestoreError(f"links are not allowed in the photo archive: {member.name}")
        members.append(member)
    archive.extractall(path=root, members=members)


def target_has_data(project: str) -> bool:
    """Refuse to restore over an existing pilot database."""
    status = compose(project, "ps", "--format", "json", check=False)
    services = [json.loads(line) for line in status.stdout.splitlines() if line.strip()]
    if not any(item.get("Service") == "postgres" for item in services):
        return False
    probe = compose(
        project, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
        "select count(*) from information_schema.tables where table_name='pilot_checks'",
        check=False,
    )
    if probe.returncode != 0:
        return False
    return probe.stdout.strip() == "1" and int(
        compose(
            project, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc",
            "select count(*) from pilot_migrations", check=False,
        ).stdout.strip() or 0
    ) > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore a pilot backup into a separate project.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--target-photos-volume", default=None,
                        help="Optional explicit volume name for the restored photos.")
    options = parser.parse_args(argv)

    try:
        check_target(options.project)
        bundle = options.bundle.expanduser().resolve()
        if not bundle.is_dir():
            raise RestoreError(f"{bundle} is not a directory.")
        manifest = read_manifest(bundle)
        database = bundle / manifest["database"]
        photos = bundle / manifest["photos"]
        if not database.is_file() or not photos.is_file():
            raise RestoreError("The backup directory lacks its database or photo archive.")
        if target_has_data(options.project):
            raise RestoreError(
                f"Project {options.project!r} already contains pilot data. "
                "Use a new project or remove that test project first."
            )

        compose(options.project, "up", "-d", "--wait", "postgres", check=False)

        with tempfile.TemporaryDirectory(prefix="pilot-restore-") as scratch:
            target_dump = Path(scratch) / "database.dump"
            target_dump.write_bytes(database.read_bytes())
            copied = compose(
                options.project, "cp", str(target_dump), "postgres:/tmp/database.dump", check=False
            )
            if copied.returncode != 0:
                raise RestoreError(f"copying the dump into the target failed: {copied.stderr[:200]}")
            restored_db = compose(
                options.project, "exec", "-T", "postgres", "pg_restore", "-U", "pilot",
                "-d", "pilot", "--clean", "--if-exists", "/tmp/database.dump", check=False,
            )
            if restored_db.returncode != 0:
                raise RestoreError(f"pg_restore failed: {restored_db.stderr[:300]}")

        # The dump already carries the applied migration registry, so the
        # regular runner only verifies checksums instead of recreating schema.
        compose(options.project, "run", "--rm", "migrate", check=False)

        with tempfile.TemporaryDirectory(prefix="pilot-restore-photos-") as scratch:
            with tarfile.open(photos, "r:gz") as archive:
                _safe_extract(archive, Path(scratch))
            compose(options.project, "up", "-d", "--wait", "backend", check=False)
            # Copy the archive contents, not the directory itself, so the
            # restored volume keeps the original flat layout.
            copied_photos = compose(
                options.project, "cp", f"{Path(scratch) / 'photos'}/.",
                "backend:/var/lib/smartnote/photos", check=False,
            )
            if copied_photos.returncode != 0:
                raise RestoreError(f"restoring photos failed: {copied_photos.stderr[:300]}")

        # Frontend is not started here: a second frontend would need another
        # host port, and the RESTORE is verified through the database/worker.
        compose(options.project, "up", "-d", "--wait", "postgres", "backend", "worker", check=False)
        checks = compose(
            options.project, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot",
            "-tAc", "select count(*) from pilot_checks", check=False,
        ).stdout.strip()
        unknown = compose(
            options.project, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot",
            "-tAc", "select count(*) from pilot_attempts where state='unknown'", check=False,
        ).stdout.strip()
        held = compose(
            options.project, "exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot",
            "-tAc", "select coalesce(sum(amount_rub),0) from pilot_fund_reservations where active",
            check=False,
        ).stdout.strip()
    except RestoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "project": options.project,
        "bundle": str(bundle),
        "checks": int(checks or 0),
        "unknown_attempts": int(unknown or 0),
        "active_reserves_rub": held or "0",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
