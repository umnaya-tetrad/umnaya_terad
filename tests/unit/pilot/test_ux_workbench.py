"""Safety boundaries and canned UX contracts, without a DB or model request."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))
from pilot.operations import ux_workbench as ux

FIXTURES = ROOT / "dev/ux-workbench"


@pytest.mark.parametrize("mode,key", [("polza", ""), ("fixture", "synthetic-not-empty"), ("fixture", " ")])
def test_guard_refuses_before_any_pool_or_fixture_access(monkeypatch, mode, key):
    def forbidden(*args, **kwargs):
        raise AssertionError("No pool may be opened for refused configuration")

    monkeypatch.setattr(ux.asyncpg, "create_pool", forbidden)
    settings = SimpleNamespace(pilot_transport=mode, polza_api_key=key)
    with pytest.raises(ValueError, match="fixture mode and an empty"):
        asyncio.run(ux.run_worker(settings, Path("missing-fixtures-must-not-be-read")))


@pytest.mark.parametrize("mode,key", [("polza", ""), ("fixture", "synthetic-not-empty")])
def test_api_entrypoint_guard_runs_before_uvicorn_start(monkeypatch, mode, key):
    import uvicorn
    monkeypatch.setattr(sys, "argv", ["ux_workbench", "api"])
    monkeypatch.setattr(ux, "get_settings", lambda: SimpleNamespace(pilot_transport=mode, polza_api_key=key))
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: pytest.fail("Refused API must not start"))
    with pytest.raises(ValueError, match="fixture mode and an empty"):
        ux.main()


class ReadOnlyPool:
    def __init__(self, title="Ручная проверка", jobs=1, hashes=()):
        self.title, self.jobs, self.hashes = title, jobs, hashes

    async def fetchval(self, query, *args):
        if query.startswith("SELECT title"):
            return self.title
        assert query.startswith("SELECT count(*) FROM pilot_jobs")
        return self.jobs

    async def fetch(self, query, *args):
        assert query.startswith("SELECT a.sha256")
        return [{"sha256": value} for value in self.hashes]


def transport(pool):
    return ux.LocalTransport(SimpleNamespace(pool=pool, settings=SimpleNamespace(
        pilot_transport="fixture", polza_api_key="")), FIXTURES, 0)


def job():
    return dict(id=uuid4(), kind="page_check", check_id=uuid4(), bundle_id=uuid4(), input_version_id=uuid4())


@pytest.mark.parametrize("photo_count", [1, 2])
def test_unrecognized_manual_photos_return_explicit_canned_mixed_report(photo_count):
    result = asyncio.run(transport(ReadOnlyPool())(job(), {"images": [Path("not-read")] * photo_count}))
    assert result.outcome == "success" and result.actual_cost_rub == 0
    assert [task["result"] for task in result.payload["tasks"]] == [
        "all_steps_correct", "first_error_found", "all_steps_correct",
    ]
    assert result.payload["tasks"][2]["completeness"] == "incomplete"
    assert result.payload["tasks"][1]["first_error"]["corrected_latex"] == "3x-6=12"
    if photo_count == 2:
        assert result.payload["tasks"][2]["photo_indices"] == [1, 2]


@pytest.mark.parametrize("title", ["[UX 04] Ошибка", "[UX RUN retry] Мой прогон"])
def test_safe_failure_stays_on_first_job_then_manual_new_job_succeeds(title):
    pool = ReadOnlyPool(title=title)
    local = transport(pool)
    first = asyncio.run(local(job(), {"images": [Path("not-read")]}))
    assert first.outcome == "rejected" and first.actual_cost_rub == 0
    assert first.payload is None
    # A second attempt of the same first Job still cannot become fake success.
    assert asyncio.run(local(job(), {"images": [Path("not-read")]})).outcome == "rejected"
    pool.jobs = 2
    assert asyncio.run(local(job(), {"images": [Path("not-read")]})).outcome == "success"


def test_known_unassessed_asset_works_in_arbitrary_manual_check():
    catalog = ux.load_catalog(FIXTURES)
    photo_hash = catalog["asset_sha256"]["assets/unassessed.png"]
    result = asyncio.run(transport(ReadOnlyPool(hashes=[photo_hash]))(job(), {"images": [Path("not-read")]}))
    assert len(result.payload["tasks"]) == 4
    unknown = result.payload["tasks"][-1]
    assert unknown["result"] == "not_assessed" and unknown["completeness"] == "unknown"
    assert unknown["uncheckable_reason"] and unknown["first_error"] is None


def test_retry_photo_set_also_triggers_safe_failure_in_manual_check():
    catalog = ux.load_catalog(FIXTURES)
    pool = ReadOnlyPool(hashes=[catalog["asset_sha256"]["assets/retry.png"]])
    local = transport(pool)
    assert asyncio.run(local(job(), {"images": [Path("not-read")]})).outcome == "rejected"
    pool.jobs = 2
    assert asyncio.run(local(job(), {"images": [Path("not-read")]})).outcome == "success"


def load_seed():
    spec = importlib.util.spec_from_file_location("seed_ux_workbench", ROOT / "scripts/pilot/seed_ux_workbench.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repeat_seed_reuses_owned_examples_without_editing_any_data():
    seed = load_seed()
    catalog = ux.load_catalog(FIXTURES)

    class ExistingClient:
        def call(self, method, path, *args, **kwargs):
            if method == "POST" and path == "/auth/login":
                return {"role": "teacher"}
            assert method == "GET" and path.startswith("/checks?"), "Existing examples must never be mutated"
            return {"items": [{"id": str(index), "title": item["title"]} for index, item in enumerate(catalog["scenarios"])],
                    "next_cursor": None}

    results = seed.seed(ExistingClient(), {"login": "synthetic", "password": "synthetic"}, FIXTURES)
    assert len(results) == 5 and all(item["reused"] for item in results)


def test_seed_refuses_live_environment_before_client_or_credentials(monkeypatch):
    seed = load_seed()
    monkeypatch.setenv("PILOT_TRANSPORT", "polza")
    monkeypatch.setenv("POLZA_API_KEY", "")
    with pytest.raises(ValueError, match="explicit fixture"):
        seed.main()


def test_catalog_assets_are_local_synthetic_files_with_recorded_hashes():
    catalog = ux.load_catalog(FIXTURES)
    assert [item["id"] for item in catalog["scenarios"]] == ["manual", "mixed", "unassessed", "retry", "summary"]
    for path, digest in catalog["asset_sha256"].items():
        asset = (FIXTURES / path).resolve()
        assert FIXTURES.resolve() in asset.parents
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == digest
    for name, count in (("normal", 1), ("continuation", 2), ("unassessed", 1)):
        report = ux.report_for(FIXTURES, "unassessed" if name == "unassessed" else "mixed", count)
        assert report["schema_version"] == "page-check/1.2"
