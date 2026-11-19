"""Independent durable worker; health is PostgreSQL heartbeat, never an LLM call."""
import asyncio,argparse,os,socket
from uuid import uuid4
from pathlib import Path
import asyncpg
from config import get_settings
from ..domain.services import create_services
from .queue import claim,renew,recover_expired,now,HEARTBEAT_SECONDS,HEALTH_STALE_SECONDS
from .providers import run_job
from .attempts import complete
from .transport import TransportResult
async def heartbeat(svc,worker_id):
    await svc.pool.execute('INSERT INTO pilot_workers(id,identity,heartbeat_at) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET heartbeat_at=excluded.heartbeat_at',worker_id,f'{socket.gethostname()}:{os.getpid()}',now(svc))
async def healthcheck(svc):
    latest=await svc.pool.fetchval('SELECT max(heartbeat_at) FROM pilot_workers')
    return latest is not None and (now(svc)-latest).total_seconds()<=HEALTH_STALE_SECONDS
async def run_once(svc,worker_id=None):
    wid=worker_id or uuid4();await heartbeat(svc,wid);await recover_expired(svc)
    item=await claim(svc,wid)
    if not item:return False
    async def keepalive():
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS);await heartbeat(svc,wid)
            if not await renew(svc,item['job'],wid):return
    pulse=asyncio.create_task(keepalive())
    try:
        try:result=await run_job(svc,item['job'],item['payload'])
        except Exception:
            # Unexpected post-dispatch exceptions are unknown, never a free resend.
            result=TransportResult('unknown',error_code='worker_exception')
        return await complete(svc,item,result)
    finally:
        pulse.cancel()
        try:await pulse
        except asyncio.CancelledError:pass
async def run_forever(svc):
    wid=uuid4()
    while True:
        if not await run_once(svc,wid):await asyncio.sleep(1)
async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--healthcheck',action='store_true');args=parser.parse_args()
    settings=get_settings();pool=await asyncpg.create_pool(settings.database_url)
    svc=create_services(pool,Path(settings.pilot_storage_root),settings)
    try:
        if args.healthcheck:
            if not await healthcheck(svc):raise SystemExit(1)
        else:await run_forever(svc)
    finally:await pool.close()
if __name__=='__main__':asyncio.run(main())
