from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass
class Services:
    pool: Any
    storage_root: Path
    settings: Any
    transport: Any = None
    http_transport: Any = None
    fixture_scenario: str = "default"
    pricing_profile: dict | None = None
    clock: Any = None
    auth: Any = None

    @property
    def mode(self):
        return self.settings.pilot_transport


def create_services(pool, storage_root, settings):
    if settings.pilot_transport not in ("fixture", "polza"):
        raise ValueError("PILOT_TRANSPORT must be fixture or polza")
    from ..processing.pricing import default_pricing_profile

    profile = default_pricing_profile()
    service = Services(pool, Path(storage_root), settings, pricing_profile=profile)
    from . import auth

    service.auth = auth
    return service
