import json
from decimal import Decimal
from uuid import uuid4
import pytest
from config import Settings
from pilot.domain.services import create_services
from pilot.processing.funds import FundsEvidence,fund_wallet
from pilot.processing.queue import claim
from pilot.processing.attempts import complete
from pilot.processing.transport import TransportResult,MODEL,PROVIDER

@pytest.mark.asyncio
async def test_trusted_pricing_file_factory_to_real_polza_claim(h,tmp_path):
    ids=await h.create()
    await h.submit(ids[2],ids[3],expected=202)
    profile={'verified':True,'profile_id':'synthetic-pricing-v1','model':MODEL,'provider':PROVIDER,'max_input_tokens':1048576,'max_output_tokens':25000,'prompt_rub_per_million':'50','completion_rub_per_million':'250','image_rub_per_million':'50'}
    path=tmp_path/'private-pricing.json';path.write_text(json.dumps(profile),encoding='utf-8')
    settings=Settings(pilot_transport='polza',pilot_pricing_profile_file=str(path),polza_api_key='synthetic-no-network')
    service=create_services(h.svc.pool,h.svc.storage_root,settings)
    assert service.pricing_profile==profile
    await fund_wallet(service,operation='initialize',amount_rub=Decimal(1000),evidence=FundsEvidence('synthetic verified balance','e'*64,'synthetic-pricing-v1'),operator_ref='pytest',request_id=uuid4())
    service.pricing_profile={**profile,'profile_id':'unapproved-v2'}
    assert await claim(service,uuid4()) is None
    service.pricing_profile=profile
    item=await claim(service,uuid4())
    assert item and item['job']['kind']=='page_check'
    await complete(service,item,TransportResult('rejected',actual_cost_rub=Decimal(0)))
    assert await service.pool.fetchval("SELECT held_rub FROM pilot_funds WHERE mode='polza'")==0
    assert await service.pool.fetchval("SELECT balance_rub FROM pilot_funds WHERE mode='fixture'")==0

def test_pricing_file_malformed_fails_closed(tmp_path):
    p=tmp_path/'private-pricing.json';p.write_text('{bad',encoding='utf-8')
    with pytest.raises(ValueError):create_services(None,tmp_path,Settings(pilot_pricing_profile_file=str(p)))
