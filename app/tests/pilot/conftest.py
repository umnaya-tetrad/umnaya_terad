import os
import sys
import json
import tempfile
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))


def _git(*arguments):
    return subprocess.run(
        ["git", *arguments], cwd=APP.parent, capture_output=True, text=True, check=True
    ).stdout.strip()


def pytest_configure(config):
    """Bind evidence to the code that started this session, before collection."""
    run_id = uuid4().hex
    folder = APP.parent.parent / ".cache/processing-runs" / run_id
    (folder / "cases").mkdir(parents=True)
    info = {
        "run_id": run_id,
        "commit": _git("rev-parse", "HEAD"),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "working_tree_clean_at_start": not bool(_git("status", "--porcelain")),
        "folder": str(folder),
    }
    config._processing_run_info = info
    (folder / "run.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pytest_runtest_call(item):
    info = item.config._processing_run_info
    (Path(info["folder"]) / "current-test.json").write_text(
        json.dumps(
            {
                "node": item.nodeid,
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def pytest_sessionfinish(session, exitstatus):
    info = session.config._processing_run_info
    info.update(
        finished_at_utc=datetime.now(timezone.utc).isoformat(),
        exit_status=int(exitstatus),
        commit_at_end=_git("rev-parse", "HEAD"),
        working_tree_clean_at_end=not bool(_git("status", "--porcelain")),
    )
    (Path(info["folder"]) / "run.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(
        "Processing evidence: " + terminalreporter.config._processing_run_info["folder"]
    )


@pytest.fixture(scope="session")
def run_info(pytestconfig):
    return pytestconfig._processing_run_info


@pytest.fixture(scope="session", autouse=True)
def record_run_provenance(run_info, record_testsuite_property):
    record_testsuite_property("processing_run_id", run_info["run_id"])
    record_testsuite_property("processing_commit", run_info["commit"])
    record_testsuite_property("processing_evidence_folder", run_info["folder"])


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    setattr(item, "rep_" + report.when, report)


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch, tmp_path):
    """Fail before any real external HTTP; PG and child ASGI use loopback."""
    original = httpx.AsyncHTTPTransport.handle_async_request

    async def guarded(self, request):
        if request.url.host not in ("127.0.0.1", "localhost", "test"):
            raise AssertionError(
                "External HTTP is forbidden in processing acceptance tests"
            )
        return await original(self, request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", guarded)
    codec = tmp_path / "codec-temp"
    codec.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(codec))


@pytest_asyncio.fixture
async def pg_factory():
    """Never drop, truncate or migrate a database not created by this fixture."""
    supplied = os.environ.get("PILOT_TEST_DATABASE_URL")
    if not supplied:
        raise RuntimeError(
            "Set PILOT_TEST_DATABASE_URL to an isolated pilot_test_* PostgreSQL16 database"
        )
    parsed = urlsplit(supplied)
    if not parsed.path.lstrip("/").startswith("pilot_test_"):
        raise RuntimeError("Unsafe test database name: expected pilot_test_*")
    admin_url = supplied.rsplit("/", 1)[0] + "/postgres"
    admin = await asyncpg.connect(admin_url)
    version = await admin.fetchval("SHOW server_version_num")
    assert 160000 <= int(version) < 170000, version
    owned = []

    async def create():
        name = "pilot_test_" + uuid4().hex
        await admin.execute(f'CREATE DATABASE "{name}"')
        pool = await asyncpg.create_pool(
            supplied.rsplit("/", 1)[0] + "/" + name, min_size=1, max_size=12
        )
        owned.append((name, pool))
        return pool

    try:
        yield create
    finally:
        for name, pool in owned:
            await pool.close()
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


@pytest_asyncio.fixture
async def db(pg_factory, request, run_info):
    pool = await pg_factory()
    yield pool
    if request.node.name == "test_proc_c01":
        folder = Path(run_info["folder"]) / "cases"
        outcome = getattr(request.node, "rep_call", None)
        report = {
            "node": request.node.nodeid,
            "commit": run_info["commit"],
            "run_id": run_info["run_id"],
            "transport": "fixture",
            "outcome": outcome.outcome if outcome else "setup_failed",
            "postgres": await pool.fetchval("SELECT version()"),
            "http": [],
            "provider_post_count": 0,
            "db_counts": {
                "migrations": await pool.fetchval(
                    "SELECT count(*) FROM pilot_migrations"
                )
            },
            "db_assertions": {
                "checksummed_upgrade_and_clean_schema": bool(outcome and outcome.passed)
            },
        }
        (folder / "test_proc_c01.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


@pytest_asyncio.fixture
async def svc(db, tmp_path):
    from config import Settings
    from pilot.domain.services import create_services
    from pilot.domain.migrate import migrate

    await migrate(db)
    service = create_services(
        db, tmp_path / "private", Settings(pilot_transport="fixture")
    )
    database = await db.fetchval("SELECT current_database()")
    service.test_database_url = (
        os.environ["PILOT_TEST_DATABASE_URL"].rsplit("/", 1)[0] + "/" + database
    )
    yield service


@pytest_asyncio.fixture
async def h(svc, request, monkeypatch, run_info):
    from .harness import Harness

    harness = Harness(svc)
    from pilot.processing import worker, providers

    async def observed(job_svc, job, payload):
        harness.provider_posts += 1
        return await providers.run_job(job_svc, job, payload)

    monkeypatch.setattr(worker, "run_job", observed)
    await harness.start()
    try:
        yield harness
    finally:
        folder = Path(run_info["folder"]) / "cases"
        counts = {}
        for table in [
            "pilot_jobs",
            "pilot_attempts",
            "pilot_bundle_reports",
            "pilot_snapshots",
            "pilot_analytics_results",
            "pilot_idempotency",
            "pilot_outbox",
            "pilot_fund_ledger",
        ]:
            counts[table] = await svc.pool.fetchval(f"SELECT count(*) FROM {table}")
        checks = {
            "budget_nonnegative_and_spend_matches_immutable_cost_ledger": await svc.pool.fetchval(
                "SELECT bool_and(b.spend_limit_rub>=0 AND b.spent_rub>=0 AND b.held_rub>=0 AND b.spent_rub=COALESCE((SELECT sum(l.amount_rub) FROM pilot_fund_ledger l WHERE l.mode=b.mode AND l.operation='settlement'),0)) FROM pilot_processing_budget b"
            ),
            "global_active_slots_at_most_two": await svc.pool.fetchval(
                "SELECT count(*)<=2 FROM pilot_slots WHERE attempt_id IS NOT NULL"
            ),
            "at_most_one_settlement_per_attempt": await svc.pool.fetchval(
                "SELECT NOT EXISTS(SELECT 1 FROM pilot_fund_ledger WHERE operation='settlement' GROUP BY attempt_id HAVING count(*)>1)"
            ),
        }
        has_child_calls = await svc.pool.fetchval(
            "SELECT to_regclass('test_gateway_calls') IS NOT NULL"
        )
        child_posts = (
            await svc.pool.fetchval("SELECT count(*) FROM test_gateway_calls")
            if has_child_calls
            else 0
        )
        outcome = getattr(request.node, "rep_call", None)
        report = {
            "node": request.node.nodeid,
            "commit": run_info["commit"],
            "run_id": run_info["run_id"],
            "transport": svc.mode,
            "outcome": outcome.outcome if outcome else "setup_failed",
            "postgres": await svc.pool.fetchval("SELECT version()"),
            "http": harness.http,
            "db_counts": counts,
            "db_assertions": checks,
            "provider_post_count": int(harness.provider_posts + child_posts),
        }
        (folder / (request.node.name + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await harness.close()
        assert all(checks.values()), checks
