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
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from decimal import Decimal, InvalidOperation

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
    command = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yaml")]
    for override in os.getenv("PILOT_COMPOSE_OVERRIDES", "").split(os.pathsep):
        if override:
            path = Path(override)
            if not path.is_absolute() or not path.is_file():
                raise RestoreError("Compose overrides must be existing absolute file paths.")
            command.extend(["-f", str(path)])
    if env_file() is not None:
        command.extend(["--env-file", str(env_file())])
    environment = dict(os.environ)
    environment["COMPOSE_PROJECT_NAME"] = project
    result = subprocess.run(
        [*command, *args], cwd=ROOT, capture_output=True, text=True, check=False, env=environment
    )
    if result.returncode != 0:
        # Do not print command output: Compose errors may include interpolated secrets.
        raise RestoreError(f"Restore operation {args[0]!r} failed (exit {result.returncode}).")
    return result


def check_target(project: str) -> None:
    if not project or project in FORBIDDEN_TARGETS:
        raise RestoreError(
            "Restore needs a separate project name; the working project must never be overwritten."
        )
    if not re.fullmatch(r"smartnote-restore-[a-z0-9][a-z0-9_-]*", project):
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
    """Detect any pre-existing target resources, including stopped containers.

    Absence of a reachable SQL server is never evidence of an empty target.
    Check ownership labels and conventional names, so detached volumes left by
    ``compose down`` (or an unlabelled volume with a colliding name) are protected.
    A failed inventory is an error, never permission to create or overwrite.
    """
    config = json.loads(compose(project, "config", "--format", "json", check=False).stdout)
    for name, volume in config.get("volumes", {}).items():
        if volume.get("external") or volume.get("name") != f"{project}_{name}":
            raise RestoreError("Restore requires new project-scoped volumes; shared volumes refused.")
    label = f"label=com.docker.compose.project={project}"
    probes = (
        ["ps", "--all", "--filter", label, "--format", "{{.ID}}"],
        ["ps", "--all", "--filter", f"name=^{project}-", "--format", "{{.ID}}"],
        ["volume", "ls", "--filter", label, "--format", "{{.Name}}"],
        ["volume", "ls", "--filter", f"name=^{project}_", "--format", "{{.Name}}"],
        ["network", "ls", "--filter", label, "--format", "{{.ID}}"],
    )
    for args in probes:
        result = subprocess.run(
            ["docker", *args], cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RestoreError("Cannot verify that the restore target is new; no changes made.")
        if result.stdout.strip():
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore a pilot backup into a separate project.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--target-photos-volume", default=None,
                        help="Legacy option; custom volumes are refused for safe restoration.")
    options = parser.parse_args(argv)

    try:
        check_target(options.project)
        bundle = options.bundle.expanduser().resolve()
        if not bundle.is_dir():
            raise RestoreError(f"{bundle} is not a directory.")
        manifest = read_manifest(bundle)
        if manifest.get("project") == options.project:
            raise RestoreError("The backup source cannot also be the restore target.")
        if options.target_photos_volume is not None:
            raise RestoreError("Restore uses new project-scoped volumes; custom volumes are not allowed.")
        database = bundle / manifest["database"]
        photos = bundle / manifest["photos"]
        if not database.is_file() or not photos.is_file():
            raise RestoreError("The backup directory lacks its database or photo archive.")
        if target_has_data(options.project):
            raise RestoreError(
                f"Project {options.project!r} already contains pilot data or existing resources. "
                "Use a new project name; existing resources are never overwritten."
            )

        compose(options.project, "up", "-d", "--wait", "postgres", check=False)

        with tempfile.TemporaryDirectory(prefix="pilot-restore-") as scratch:
            target_dump = Path(scratch) / "database.dump"
            target_dump.write_bytes(database.read_bytes())
            compose(
                options.project, "cp", str(target_dump), "postgres:/tmp/database.dump", check=False
            )
            compose(
                options.project, "exec", "-T", "postgres", "pg_restore", "-U", "pilot",
                "-d", "pilot", "--exit-on-error", "--clean", "--if-exists", "/tmp/database.dump", check=False,
            )

        # The dump already carries the applied migration registry, so the
        # regular runner only verifies checksums instead of recreating schema.
        compose(options.project, "run", "--rm", "migrate", check=False)

        with tempfile.TemporaryDirectory(prefix="pilot-restore-photos-") as scratch:
            with tarfile.open(photos, "r:gz") as archive:
                _safe_extract(archive, Path(scratch))
            compose(options.project, "up", "-d", "--wait", "backend", check=False)
            # Copy the archive contents, not the directory itself, so the
            # restored volume keeps the original flat layout.
            compose(
                options.project, "cp", f"{Path(scratch) / 'photos'}/.",
                "backend:/var/lib/smartnote/photos", check=False,
            )

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
        checks_count = int(checks)
        unknown_count = int(unknown)
        held_amount = Decimal(held)
        if checks_count < 0 or unknown_count < 0 or not held_amount.is_finite() or held_amount < 0:
            raise RestoreError("Restored database returned invalid verification counters.")
    except (RestoreError, OSError, ValueError, InvalidOperation, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "project": options.project,
        "bundle": str(bundle),
        "checks": checks_count,
        "unknown_attempts": unknown_count,
        "active_reserves_rub": held,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
