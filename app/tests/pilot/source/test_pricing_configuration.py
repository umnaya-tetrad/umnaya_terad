"""The final hot-cap decision supersedes mandatory wallet/profile-file setup."""

from decimal import Decimal
from uuid import uuid4
import pytest
from config import Settings
from pilot.domain.services import create_services
from pilot.processing.budget import get_budget, set_spend_limit
from pilot.processing.queue import claim
from pilot.processing.attempts import complete
from pilot.processing.transport import TransportResult, MODEL, PROVIDER


@pytest.mark.asyncio
async def test_default_polza_cap_and_verified_bound_need_no_wallet_or_profile_file(h):
    ids = await h.create()
    await h.submit(ids[2], ids[3], expected=202)
    service = create_services(
        h.svc.pool,
        h.svc.storage_root,
        Settings(pilot_transport="polza", polza_api_key="synthetic-no-network"),
    )
    profile = service.pricing_profile
    assert profile["model"] == MODEL and profile["provider"] == PROVIDER
    assert (
        profile["max_input_tokens"] == 1048576 and profile["max_output_tokens"] == 25000
    )
    assert (await get_budget(service)).spend_limit_rub == 500
    assert not await service.pool.fetchval(
        "SELECT initialized FROM pilot_funds WHERE mode='polza'"
    )
    item = await claim(service, uuid4())
    assert item and item["job"]["kind"] == "page_check"
    await complete(
        service, item, TransportResult("rejected", actual_cost_rub=Decimal(0))
    )
    assert (await get_budget(service)).held_rub == 0
    assert (await get_budget(service)).spent_rub == 0


@pytest.mark.asyncio
async def test_cap_can_be_lower_than_spent_and_holds_without_reset(h):
    state = await set_spend_limit(
        h.svc, spend_limit_rub=Decimal(0), operator_ref="pytest", request_id=uuid4()
    )
    assert state.spend_limit_rub == 0 and state.available_rub == 0
    state = await set_spend_limit(
        h.svc, spend_limit_rub=Decimal(700), operator_ref="pytest", request_id=uuid4()
    )
    assert state.spend_limit_rub == 700 and state.spent_rub == 0


@pytest.mark.asyncio
async def test_hot_limit_prior_intent_replay_preserves_latest_limit_and_audit(h):
    k1, k2 = uuid4(), uuid4()
    await set_spend_limit(
        h.svc, spend_limit_rub=500, operator_ref="pytest", request_id=k1
    )
    await set_spend_limit(
        h.svc, spend_limit_rub=600, operator_ref="pytest", request_id=k2
    )
    state = await set_spend_limit(
        h.svc, spend_limit_rub=500, operator_ref="pytest", request_id=k1
    )
    assert state.spend_limit_rub == 600
    assert (
        await h.svc.pool.fetchval(
            "SELECT count(*) FROM pilot_audit WHERE name='spend_limit_changed'"
        )
        == 2
    )
