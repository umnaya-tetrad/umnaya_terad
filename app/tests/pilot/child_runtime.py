"""Subprocess fixture entrypoint, never imported by production code."""
import asyncio
import json
import os
from pathlib import Path
import sys
from decimal import Decimal

import asyncpg
from config import Settings
from pilot.domain.services import create_services


async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=3)
    svc=create_services(pool,Path(os.environ['PILOT_STORAGE_ROOT']),Settings(pilot_transport='fixture',database_url=os.environ['DATABASE_URL']))
    async def gateway(job,payload):
        from pilot.processing.transport import TransportResult
        await pool.execute('INSERT INTO test_gateway_calls(job_id,kind) VALUES($1,$2)',job['id'],job['kind'])
        if os.environ.get('PILOT_TEST_GATE')=='1':
            while not await pool.fetchval('SELECT dispatch_released FROM test_gateway_control'):
                await asyncio.sleep(.01)
        value=json.loads(Path(os.environ['PILOT_TEST_REPORT']).read_text(encoding='utf-8'))
        return TransportResult('success',payload=value,actual_cost_rub=Decimal('0.01'),provider_request_id='synthetic-child',raw=json.dumps(value))
    svc.transport=gateway
    try:
        if sys.argv[1]=='once':
            from pilot.processing.worker import run_once
            if os.environ.get('PILOT_TEST_BARRIER')=='1':
                await pool.execute('INSERT INTO test_worker_ready(pid) VALUES($1)',os.getpid())
                while not await pool.fetchval('SELECT start_released FROM test_gateway_control'):
                    await asyncio.sleep(.01)
            await run_once(svc)
        elif sys.argv[1]=='health':
            from pilot.processing.worker import heartbeat
            from uuid import uuid4
            await heartbeat(svc,uuid4())
        elif sys.argv[1]=='serve':
            import uvicorn
            from .harness import make_app
            await uvicorn.Server(uvicorn.Config(make_app(svc),host='127.0.0.1',port=int(sys.argv[2]),log_level='error')).serve()
    finally: await pool.close()


if __name__=='__main__': asyncio.run(main())
