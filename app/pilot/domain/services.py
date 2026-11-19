from dataclasses import dataclass,field
from pathlib import Path
from typing import Any
@dataclass
class Services:
    pool:Any
    storage_root:Path
    settings:Any
    transport:Any=None
    http_transport:Any=None
    fixture_scenario:str='default'
    pricing_profile:dict|None=None
    clock:Any=None
    auth:Any=None
    @property
    def mode(self): return self.settings.pilot_transport

def create_services(pool,storage_root,settings):
    if settings.pilot_transport not in ('fixture','polza'): raise ValueError('PILOT_TRANSPORT must be fixture or polza')
    return Services(pool,Path(storage_root),settings)
