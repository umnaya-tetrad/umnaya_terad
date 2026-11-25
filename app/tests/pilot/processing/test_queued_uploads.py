"""Real PG/HTTP coverage for revision-independent, idempotent upload commands."""
from uuid import uuid4

import pytest

from ..harness import png

pytestmark = pytest.mark.asyncio


def mount(h):
    from pilot.routes.application import router
    h.app.state.pilot_origins = frozenset({"http://localhost:5173"})
    h.app.include_router(router, prefix="/api")


async def upload(h, version, key, *, actor="t1", image=None, origin=None):
    headers = {"Idempotency-Key": str(key)}
    if origin:
        headers["Origin"] = origin
    return await h.clients[actor].post(
        f"/api/input-versions/{version}/queued-photos", headers=headers,
        files={"file": ("page.png", image or png(), "image/png")},
    )


async def test_append_survives_unrelated_revision_and_replays_after_seal(h):
    mount(h)
    check, _, bundle, version = await h.create(photos=0)
    await h.call("createNotebook", check_id=check, expected=201)
    key = uuid4()
    photo = await upload(h, version, key)
    assert photo.status_code == 201
    photo_id = photo.json()["entity_id"]
    second = await upload(h, version, uuid4(), image=png((65, 64)))
    assert second.status_code == 201
    photo_ids = [photo_id, second.json()["entity_id"]]
    path = f"/api/bundles/{bundle}/queued-submit"
    submit_key = uuid4()
    for wrong in [photo_ids[::-1], photo_ids[:1], photo_ids + [str(uuid4())]]:
        response = await h.clients["t1"].post(path, headers={"Idempotency-Key": str(uuid4())}, json={"input_version_id": version, "photo_ids": wrong})
        assert response.status_code == 409
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_jobs") == 0
    payload = {"input_version_id": version, "photo_ids": photo_ids}
    accepted = await h.clients["t1"].post(path, headers={"Idempotency-Key": str(submit_key)}, json=payload)
    assert accepted.status_code == 202, accepted.text
    replay = await h.clients["t1"].post(path, headers={"Idempotency-Key": str(submit_key)}, json=payload)
    assert replay.json() == accepted.json()
    repeated_photo = await upload(h, version, key)
    assert repeated_photo.json() == photo.json()
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_jobs") == 1
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_photo_assets") == 2
    conflict = await upload(h, version, key, image=png((66, 64)))
    assert conflict.status_code == 409
    late_new = await upload(h, version, uuid4())
    assert late_new.status_code == 409


async def test_queued_upload_is_owner_only_origin_checked_and_draft_fenced(h):
    mount(h)
    _, _, _, version = await h.create(photos=0)
    assert (await upload(h, version, uuid4(), actor="t2")).status_code in (403, 404)
    assert (await upload(h, version, uuid4(), actor="staff")).status_code == 403
    assert (await upload(h, version, uuid4(), origin="https://attacker.invalid")).status_code == 403
    assert (await upload(h, version, uuid4(), actor="anon")).status_code == 401
    await h.call("discardDraft", input_version_id=version, expected=200)
    assert (await upload(h, version, uuid4())).status_code in (404, 409)
    assert await h.svc.pool.fetchval("SELECT count(*) FROM pilot_photo_assets") == 0
