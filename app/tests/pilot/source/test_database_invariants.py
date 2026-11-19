from decimal import Decimal
from uuid import UUID, uuid4
import asyncpg
import pytest
from pilot.processing.funds import fund_wallet, FundsEvidence


@pytest.mark.asyncio
async def test_cross_check_and_bundle_lineage_is_rejected_by_postgres(h):
    first = await h.create(photos=1)
    photo = (await h.check())["notebooks"][0]["bundles"][0]["draft"]["photos"][0]["id"]
    second = await h.create(actor="t2", photos=0)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await h.svc.pool.execute(
            "UPDATE pilot_bundles SET check_id=$2 WHERE id=$1",
            UUID(first[2]),
            UUID(second[0]),
        )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await h.svc.pool.execute(
            "INSERT INTO pilot_version_photos(version_id,photo_id,position) VALUES($1,$2,1)",
            UUID(second[3]),
            UUID(photo),
        )
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_version_photos WHERE version_id=$1",
            UUID(second[3]),
        )
        == 0
    )


@pytest.mark.asyncio
async def test_fund_ledger_is_immutable_in_postgres(h):
    await fund_wallet(
        h.svc,
        operation="initialize",
        amount_rub=Decimal(10),
        evidence=FundsEvidence("synthetic", "f" * 64, "fixture"),
        operator_ref="pytest",
        request_id=uuid4(),
    )
    with pytest.raises(asyncpg.RaiseError):
        await h.svc.pool.execute("UPDATE pilot_fund_ledger SET amount_rub=999")
    assert await h.svc.pool.fetchval("SELECT amount_rub FROM pilot_fund_ledger") == 10


@pytest.mark.asyncio
async def test_delete_photo_intent_is_scoped_to_full_canonical_path(h):
    ids = await h.create(photos=2)
    photos = (await h.check())["notebooks"][0]["bundles"][0]["draft"]["photos"]
    key = uuid4()
    for photo in photos:
        await h.call(
            "deleteDraftPhoto",
            input_version_id=ids[3],
            photo_id=photo["id"],
            key=key,
            expected=200,
        )
    assert (await h.check())["notebooks"][0]["bundles"][0]["draft"]["photos"] == []
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_idempotency WHERE key=$1", key
        )
        == 2
    )


@pytest.mark.asyncio
async def test_selected_summary_is_same_check_analytics_only(h):
    from ..scenarios import ready, finalize

    ids, _, page = await ready(h)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await h.svc.pool.execute(
            "UPDATE pilot_checks SET selected_summary_job_id=$2 WHERE id=$1",
            UUID(ids[0]),
            UUID(page),
        )
    await finalize(h)
    summary = await h.svc.pool.fetchval(
        "SELECT selected_summary_job_id FROM pilot_checks WHERE id=$1", UUID(ids[0])
    )
    other = await h.create(actor="t2", photos=0)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await h.svc.pool.execute(
            "UPDATE pilot_checks SET selected_summary_job_id=$2 WHERE id=$1",
            UUID(other[0]),
            summary,
        )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await h.svc.pool.execute(
            "UPDATE pilot_checks SET selected_summary_job_id=$2 WHERE id=$1",
            UUID(other[0]),
            uuid4(),
        )
