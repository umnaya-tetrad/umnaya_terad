"""Run one paid text request and reject invalid output without repairing it."""
from jsonschema.exceptions import ValidationError

from ..processing.transport import ProviderConfig, send_once
from .builder import build_request
from .validation import validate_pair


async def run(snapshot: dict, config: ProviderConfig, *, transport=None):
    request = build_request(snapshot, config)
    result = await send_once(request, config=config, transport=transport)
    if result.outcome == "success":
        try:
            validate_pair(snapshot, result.payload)
        except (ValidationError, ValueError, TypeError):
            result.outcome, result.error_code, result.payload = "invalid_response", "invalid_summary", None
    return result
