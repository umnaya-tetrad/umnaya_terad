"""Recovery must prove absence of target data before any destructive command."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "smartnote-restore-unit-guard"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/pilot" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bundle(tmp_path):
    folder = tmp_path / "bundle"
    folder.mkdir()
    (folder / "database.dump").write_bytes(b"synthetic-dump")
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "one.png").write_bytes(b"synthetic-photo")
    with tarfile.open(folder / "photos.tar.gz", "w:gz") as archive:
        archive.add(photos, arcname="photos")
    (folder / "manifest.json").write_text(json.dumps({
        "project": "unit-source", "database": "database.dump",
        "photos": "photos.tar.gz", "created_at": "unit-test",
    }))
    return folder


def successful_result(argv, stdout="", returncode=0):
    # Deliberately sensitive-looking synthetic output must never reach an error.
    return subprocess.CompletedProcess(argv, returncode, stdout, "SYNTHETIC_SECRET_DO_NOT_LOG")


def compose_config():
    return json.dumps({"volumes": {
        key: {"name": f"{PROJECT}_{key}"} for key in ("postgres_data", "pilot_photos")
    }})


@pytest.mark.parametrize("probe_index", range(5))
@pytest.mark.parametrize("failure", [False, True], ids=["existing-resource", "probe-error"])
def test_restore_refuses_existing_or_unverifiable_target_before_mutation(
    monkeypatch, bundle, capsys, probe_index, failure,
):
    restore = load_script("restore_local")
    calls = []
    inventories = []

    def docker(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "compose":
            assert "config" in argv, "No up/cp/exec/migration may precede a clean inventory"
            return successful_result(argv, compose_config())
        index = len(inventories)
        inventories.append(argv)
        if index == probe_index:
            return successful_result(argv, "" if failure else "protected-resource", 1 if failure else 0)
        return successful_result(argv)

    monkeypatch.setattr(restore.subprocess, "run", docker)
    assert restore.main(["--bundle", str(bundle), "--project", PROJECT]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "SYNTHETIC_SECRET" not in output.err
    assert all("--all" in argv for argv in inventories if argv[1] == "ps")


@pytest.mark.parametrize("volume", [
    {"name": "source_pilot_photos"},
    {"name": f"{PROJECT}_pilot_photos", "external": True},
])
def test_restore_refuses_shared_volume_configuration(monkeypatch, bundle, volume):
    restore = load_script("restore_local")
    calls = []

    def docker(argv, **kwargs):
        calls.append(argv)
        assert "config" in argv
        return successful_result(argv, json.dumps({"volumes": {"pilot_photos": volume}}))

    monkeypatch.setattr(restore.subprocess, "run", docker)
    assert restore.main(["--bundle", str(bundle), "--project", PROJECT]) == 2
    assert len(calls) == 1


@pytest.mark.parametrize("failed_step", range(10))
def test_restore_any_failed_operation_stops_and_never_reports_success(
    monkeypatch, bundle, capsys, failed_step,
):
    restore = load_script("restore_local")
    operations = []

    def docker(argv, **kwargs):
        if argv[1] != "compose":
            return successful_result(argv)
        assert argv[argv.index("-p") + 1] == PROJECT
        assert kwargs["env"]["COMPOSE_PROJECT_NAME"] == PROJECT
        if "config" in argv:
            return successful_result(argv, compose_config())
        index = len(operations)
        operations.append(argv)
        return successful_result(argv, "1", 17 if index == failed_step else 0)

    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "unrelated-working-project")
    monkeypatch.setattr(restore.subprocess, "run", docker)
    assert restore.main(["--bundle", str(bundle), "--project", PROJECT]) == 2
    assert len(operations) == failed_step + 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "exit 17" in output.err
    assert "SYNTHETIC_SECRET" not in output.err


def test_restore_new_project_completes_with_verified_counts(monkeypatch, bundle, capsys):
    restore = load_script("restore_local")
    calls = []

    def docker(argv, **kwargs):
        calls.append(argv)
        if "config" in argv:
            return successful_result(argv, compose_config())
        return successful_result(argv, "1" if "psql" in argv else "")

    monkeypatch.setattr(restore.subprocess, "run", docker)
    assert restore.main(["--bundle", str(bundle), "--project", PROJECT]) == 0
    assert json.loads(capsys.readouterr().out)["checks"] == 1
    assert all("--exit-on-error" in argv for argv in calls if "pg_restore" in argv)


def test_backup_project_flag_controls_writers_dump_photos_and_manifest(monkeypatch, tmp_path, capsys):
    backup = load_script("backup_local")
    project = "unit-requested-backup"
    calls = []
    override = tmp_path / "override.yaml"
    override.write_text("services: {}\n")

    def docker(argv, **kwargs):
        calls.append(argv)
        assert argv[argv.index("-p") + 1] == project
        assert kwargs["env"]["COMPOSE_PROJECT_NAME"] == project
        assert argv.count("-f") == 2
        assert str(override) in argv
        if "pg_dump" in argv:
            kwargs["stdout"].write(b"synthetic-database")
        if "cp" in argv:
            photos = Path(argv[-1])
            photos.mkdir()
            (photos / "one.png").write_bytes(b"synthetic-photo")
        return successful_result(argv, "fixture" if "printenv" in argv else "")

    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "other-project")
    monkeypatch.setenv("PILOT_BACKUP_PROJECT", "third-project")
    monkeypatch.setenv("PILOT_COMPOSE_OVERRIDES", str(override))
    monkeypatch.setattr(backup.subprocess, "run", docker)
    assert backup.main(["--destination", str(tmp_path / "private"), "--project", project]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["project"] == project
    manifest = json.loads((Path(report["bundle"]) / "manifest.json").read_text())
    assert manifest["project"] == project
    assert len(calls) == 4


def test_backup_running_writers_fail_before_dump(monkeypatch, tmp_path, capsys):
    backup = load_script("backup_local")

    def docker(argv, **kwargs):
        assert "ps" in argv
        return successful_result(argv, json.dumps({"Service": "worker", "State": "running"}))

    monkeypatch.setattr(backup.subprocess, "run", docker)
    assert backup.main(["--destination", str(tmp_path / "private")]) == 2
    assert capsys.readouterr().out == ""
