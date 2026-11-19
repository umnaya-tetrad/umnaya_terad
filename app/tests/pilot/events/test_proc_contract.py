from datetime import datetime, timezone
from uuid import uuid4
import pytest

pytestmark = pytest.mark.asyncio


async def test_proc_c23(h):
    ids = await h.create()
    event = {
        "id": str(uuid4()),
        "session_id": str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "name": "capture_opened",
        "check_id": ids[0],
        "entity_id": ids[2],
    }
    payload = {"events": [event]}
    first = await h.call("ingestEvents", payload=payload, expected=202)
    replay = await h.call("ingestEvents", payload=payload, expected=202)
    assert first.json() == replay.json() and first.json()["accepted_ids"] == [
        event["id"]
    ]
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_events") == 1
    await h.call(
        "ingestEvents",
        payload={"events": [{**event, "name": "result_opened"}]},
        expected=409,
    )
    await h.call(
        "ingestEvents",
        payload={"events": [{**event, "id": str(uuid4()), "check_id": str(uuid4())}]},
        expected=404,
    )
    await h.call(
        "ingestEvents",
        payload={"events": [{**event, "id": str(uuid4()), "role": "staff"}]},
        expected=422,
    )
    await h.call("ingestEvents", payload={"events": [event] * 101}, expected=422)
    await h.call(
        "ingestEvents",
        payload={
            "events": [
                {**event, "id": str(uuid4())},
                {**event, "id": str(uuid4()), "check_id": str(uuid4())},
            ]
        },
        expected=404,
    )
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_events") == 1
