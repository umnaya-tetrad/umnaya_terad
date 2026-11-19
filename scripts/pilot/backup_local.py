"""Private, consistent backup of the local pilot database and photo volume.

Design constraints (R26/R28/R55/R56, REL-11):

* backups live **outside** Git and outside the repository working tree;
* only one writer may be active, so the caller pauses dispatch and stops the
  backend/worker first (the script refuses to run while they are up);
* the database dump and the photo archive belong to one point in time, so both
  are taken into the same timestamped directory;
* unknown attempts keep their reserves: nothing here settles, retries or
  rewrites money.

The script never prints secret values and never copies `.env`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = "smartnote-pilot"
WRITERS = ("backend", "worker")


class BackupError(Exception):
    """A safe, user-facing failure."""


def env_file() -> Path | None:
    explicit = os.getenv("PILOT_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()
    candidate = Path.home() / ".config/smartnote/pilot.env"
    return candidate if candidate.is_file() else None


def _compose_argv(*args: str) -> list[str]:
    command = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
    if env_file() is not None:
        command.extend(["--env-file", str(env_file())])
    return [*command, *args]


def _compose_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.setdefault("COMPOSE_PROJECT_NAME", os.getenv("PILOT_BACKUP_PROJECT", DEFAULT_PROJECT))
    return environment


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        _compose_argv(*args), cwd=ROOT, capture_output=True, text=True,
        check=check, env=_compose_environment(),
    )


def dump_database(destination: Path) -> Path:
    """Stream the binary custom-format dump straight into the target file."""
    target = destination / "database.dump"
    with target.open("wb") as handle:
        result = subprocess.run(
            _compose_argv("exec", "-T", "postgres", "pg_dump", "-U", "pilot", "-d", "pilot", "-Fc"),
            cwd=ROOT, stdout=handle, stderr=subprocess.PIPE, check=False, env=_compose_environment(),
        )
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupError(
            "pg_dump failed: " + result.stderr.decode("utf-8", "replace").strip()[:300]
        )
    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise BackupError("pg_dump produced an empty file.")
    return target


def running_writers(project: str) -> list[str]:
    status = compose("ps", "--format", "json", check=False)
    if status.returncode != 0:
        raise BackupError(
            f"Compose project {project!r} is not reachable: {status.stderr.strip()[:200]}"
        )
    services = [json.loads(line) for line in status.stdout.splitlines() if line.strip()]
    return [
        item["Service"] for item in services
        if item.get("Service") in WRITERS and item.get("State") == "running"
    ]


def check_destination(target: Path) -> Path:
    resolved = target.expanduser().resolve()
    repo = ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        raise BackupError(
            "Backups must live outside the repository; choose a private directory elsewhere."
        )
    resolved.mkdir(parents=True, exist_ok=True)
    mode = resolved.stat().st_mode & 0o777
    if mode & 0o077:
        resolved.chmod(0o700)
    return resolved


def archive_photos(destination: Path) -> Path:
    target = destination / "photos.tar.gz"
    with tempfile.TemporaryDirectory(prefix="pilot-backup-") as scratch:
        copied = compose(
            "cp", "backend:/var/lib/smartnote/photos", f"{scratch}/photos", check=False
        )
        if copied.returncode != 0:
            raise BackupError(f"copying the private photo volume failed: {copied.stderr.strip()[:300]}")
        with tarfile.open(target, "w:gz") as archive:
            archive.add(Path(scratch) / "photos", arcname="photos")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private consistent local pilot backup.")
    parser.add_argument("--destination", type=Path, required=True,
                        help="Private directory outside the repository.")
    parser.add_argument("--project", default=os.getenv("PILOT_BACKUP_PROJECT", DEFAULT_PROJECT))
    options = parser.parse_args(argv)

    try:
        target = check_destination(options.destination)
        writers = running_writers(options.project)
        if writers:
            raise BackupError(
                "Stop the writers before a consistent backup: "
                + ", ".join(f"docker compose stop {name}" for name in writers)
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle = target / f"pilot-backup-{stamp}"
        bundle.mkdir(parents=True, exist_ok=False)
        bundle.chmod(0o700)
        database = dump_database(bundle)
        photos = archive_photos(bundle)
        manifest = {
            "created_at": stamp,
            "project": options.project,
            "database": database.name,
            "database_bytes": database.stat().st_size,
            "photos": photos.name,
            "photos_bytes": photos.stat().st_size,
            "transport": compose("exec", "-T", "backend", "printenv", "PILOT_TRANSPORT", check=False).stdout.strip()
            or "unknown-service-stopped",
        }
        (bundle / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (bundle / "manifest.json").chmod(0o600)
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"bundle": str(bundle), **manifest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
