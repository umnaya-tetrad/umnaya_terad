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
    profile = None
    if settings.pilot_pricing_profile_file:
        path = Path(settings.pilot_pricing_profile_file)
        # Trusted local operator input only. Malformed configuration fails closed.
        from ..processing.transport import strict_json

        profile = strict_json(path.read_text(encoding="utf-8"))
        if not isinstance(profile, dict):
            raise ValueError("Pricing profile must be an object")
    service = Services(pool, Path(storage_root), settings, pricing_profile=profile)
    from . import auth

    service.auth = auth
    return service
