"""Checksummed, serialized PostgreSQL migration runner. No startup resets."""
from pathlib import Path
import asyncio
import hashlib
import asyncpg
from config import get_settings

MIGRATIONS = Path(__file__).resolve().parents[2] / 'migrations'
async def migrate(pool, *, migrations_path=MIGRATIONS):
    async with pool.acquire() as con:
        await con.execute('SELECT pg_advisory_lock(718249130)')
        try:
            await con.execute('CREATE TABLE IF NOT EXISTS pilot_migrations(name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
            for path in sorted(Path(migrations_path).glob('*.sql')):
                raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
                old=await con.fetchval('SELECT sha256 FROM pilot_migrations WHERE name=$1',path.name)
                if old is not None:
                    if old!=digest: raise RuntimeError('Applied migration checksum differs: '+path.name)
                    continue
                async with con.transaction():
                    await con.execute(raw.decode('utf-8-sig'))
                    await con.execute('INSERT INTO pilot_migrations(name,sha256) VALUES($1,$2)',path.name,digest)
        finally:
            await con.execute('SELECT pg_advisory_unlock(718249130)')
async def main():
    pool=await asyncpg.create_pool(get_settings().database_url)
    try: await migrate(pool)
    finally: await pool.close()
if __name__=='__main__': asyncio.run(main())
