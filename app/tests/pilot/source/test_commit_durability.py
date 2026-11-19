import io
from uuid import UUID,uuid4
import pytest
from pilot.domain.access import Actor
from pilot.domain.revision import MutationContext
from pilot.domain.services import create_services
from pilot.domain.storage import prepare_photo
from pilot.domain import mutations,queries
from ..harness import png

class CommitResponseLostPool:
    def __init__(self,pool):self.pool=pool
    def acquire(self):return LostAcquire(self.pool)
class LostAcquire:
    def __init__(self,pool):self.pool=pool
    async def __aenter__(self):
        self.con=await self.pool.acquire()
        return LostConnection(self.con)
    async def __aexit__(self,*args):await self.pool.release(self.con)
class LostConnection:
    def __init__(self,con):self.con=con
    def __getattr__(self,name):return getattr(self.con,name)
    def transaction(self,*args,**kwargs):return LostTransaction(self.con.transaction(*args,**kwargs))
class LostTransaction:
    def __init__(self,transaction):self.transaction=transaction
    async def __aenter__(self):return await self.transaction.__aenter__()
    async def __aexit__(self,kind,value,trace):
        result=await self.transaction.__aexit__(kind,value,trace)
        if kind is None:raise ConnectionError('Synthetic lost COMMIT response after real PG commit')
        return result

@pytest.mark.asyncio
async def test_committed_photo_survives_lost_commit_response_and_replay(h):
    ids=await h.create(photos=0)
    before=(await h.check())['revision']
    actor=Actor(UUID(h.ids['t1']),'teacher')
    ctx=MutationContext(actor,before,uuid4(),uuid4())
    faulty=create_services(CommitResponseLostPool(h.svc.pool),h.svc.storage_root,h.svc.settings)
    raw=png()
    with pytest.raises(ConnectionError):
        await mutations.upload_photo(faulty,ctx,UUID(ids[3]),prepare_photo(io.BytesIO(raw),'image/png'))
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_photo_assets')==1
    row=await h.svc.pool.fetchrow('SELECT * FROM pilot_photo_assets')
    from pathlib import Path
    assert Path(row['original_path']).is_file() and Path(row['normalized_path']).is_file()
    replay=await mutations.upload_photo(h.svc,ctx,UUID(ids[3]),prepare_photo(io.BytesIO(raw),'image/png'))
    assert replay['entity_id']==str(row['id']) and replay['check_revision']==before+1
    photo=await queries.open_photo(h.svc,actor,row['id'],request_id=uuid4())
    assert photo.path.read_bytes()==raw
    assert await h.svc.pool.fetchval('SELECT count(*) FROM pilot_idempotency WHERE key=$1',ctx.idempotency_key)==1

@pytest.mark.asyncio
async def test_finalize_from_editing_has_exact_invalid_state(h):
    ids=await h.create(photos=0)
    result=await h.call('finalizeCheck',check_id=ids[0],expected=409)
    assert result.json()['error']['code']=='invalid_state'
