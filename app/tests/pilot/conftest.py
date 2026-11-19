import os
import sys
import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch,tmp_path):
    """Fail before any real external HTTP; PG and child ASGI use loopback."""
    original=httpx.AsyncHTTPTransport.handle_async_request
    async def guarded(self,request):
        if request.url.host not in ('127.0.0.1','localhost','test'):
            raise AssertionError('External HTTP is forbidden in processing acceptance tests')
        return await original(self,request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',guarded)
    codec=tmp_path/'codec-temp';codec.mkdir()
    monkeypatch.setattr(tempfile,'tempdir',str(codec))


@pytest_asyncio.fixture
async def db():
    """Never drop, truncate or migrate a database not created by this fixture."""
    supplied = os.environ.get('PILOT_TEST_DATABASE_URL')
    if not supplied:
        raise RuntimeError('Set PILOT_TEST_DATABASE_URL to an isolated pilot_test_* PostgreSQL16 database')
    parsed = urlsplit(supplied)
    if not parsed.path.lstrip('/').startswith('pilot_test_'):
        raise RuntimeError('Unsafe test database name: expected pilot_test_*')
    admin_url = supplied.rsplit('/', 1)[0] + '/postgres'
    admin = await asyncpg.connect(admin_url)
    name = 'pilot_test_' + uuid4().hex
    version = await admin.fetchval('SHOW server_version_num')
    assert 160000 <= int(version) < 170000, version
    await admin.execute(f'CREATE DATABASE "{name}"')
    pool = await asyncpg.create_pool(supplied.rsplit('/', 1)[0] + '/' + name, min_size=1, max_size=12)
    try:
        yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


@pytest_asyncio.fixture
async def svc(db, tmp_path):
    from config import Settings
    from pilot.domain.services import create_services
    from pilot.domain.migrate import migrate
    await migrate(db)
    service = create_services(db, tmp_path / 'private', Settings(pilot_transport='fixture'))
    database = await db.fetchval('SELECT current_database()')
    service.test_database_url = os.environ['PILOT_TEST_DATABASE_URL'].rsplit('/',1)[0] + '/' + database
    yield service


@pytest_asyncio.fixture
async def h(svc,request):
    from .harness import Harness
    harness = Harness(svc)
    await harness.start()
    try:
        yield harness
    finally:
        folder=APP.parent.parent/'.cache/processing-case-reports'
        folder.mkdir(parents=True,exist_ok=True)
        counts={}
        for table in ['pilot_jobs','pilot_attempts','pilot_bundle_reports','pilot_snapshots','pilot_analytics_results','pilot_idempotency','pilot_outbox','pilot_fund_ledger']:
            counts[table]=await svc.pool.fetchval(f'SELECT count(*) FROM {table}')
        report={'node':request.node.nodeid,'transport':svc.mode,'postgres':await svc.pool.fetchval('SELECT version()'),'http':harness.http,'db_counts':counts,'provider_post_count':getattr(svc.transport,'calls',None) and len(svc.transport.calls)}
        (folder/(request.node.name+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        await harness.close()
