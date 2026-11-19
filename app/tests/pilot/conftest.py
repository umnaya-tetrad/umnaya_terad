import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))


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
async def db(pg_factory, request):
    pool = await pg_factory()
    yield pool
    if request.node.name == "test_proc_c01":
        folder = APP.parent.parent / ".cache/processing-case-reports"
        folder.mkdir(parents=True, exist_ok=True)
        outcome = getattr(request.node, "rep_call", None)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=APP.parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        report = {
            "node": request.node.nodeid,
            "commit": commit,
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
async def h(svc, request, monkeypatch):
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
        folder = APP.parent.parent / ".cache/processing-case-reports"
        folder.mkdir(parents=True, exist_ok=True)
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
            "wallet_nonnegative_holds_and_protected_balance": await svc.pool.fetchval(
                "SELECT bool_and(held_rub>=0 AND balance_rub>=held_rub AND outstanding_debt_rub>=0) FROM pilot_funds"
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
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=APP.parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        outcome = getattr(request.node, "rep_call", None)
        report = {
            "node": request.node.nodeid,
            "commit": commit,
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
