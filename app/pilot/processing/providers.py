"""Mode selection, exact request bounds, and shared one-attempt transport."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING
import inspect
import json

from jsonschema.exceptions import ValidationError
from pydantic import ValidationError as PydanticValidationError

from .transport import ProviderConfig, TransportResult, MODEL, PROVIDER, send_once


def _mode(svc):
    settings = svc.settings
    mode = settings.get("pilot_transport", "polza") if isinstance(settings, dict) else getattr(settings, "pilot_transport", "polza")
    if mode not in {"fixture", "polza"}:
        raise ValueError("PILOT_TRANSPORT must be polza or fixture")
    return mode


def build_request(svc, job: dict, input_payload: dict):
    config = ProviderConfig.from_settings(svc.settings)
    if job["kind"] == "page_check":
        from .checker import build_request as build_checker
        request = build_checker(input_payload["images"], config)
    elif job["kind"] == "class_analytics":
        from ..analytics.builder import build_request as build_analytics
        request = build_analytics(input_payload, config)
    else:
        raise ValueError("Unknown job kind")
    return request, config


def bound_for_request(svc, job: dict, input_payload: dict) -> Decimal | None:
    """Reserve at verified ceilings, never an empirical mean cost.

    A verified profile must match the selected model/route and explicitly
    specify token and tariff ceilings. For text the UTF-8 wire byte count plus
    framing margin upper-bounds tokenized input. For images the verified model
    input/context ceiling is reserved, since byte size does not bound patches.
    This is internal trusted configuration, not browser input.
    """
    if _mode(svc) == "fixture":
        return Decimal(str(getattr(svc, "fixture_request_bound", "1")))
    profile = getattr(svc, "pricing_profile", None)
    if not isinstance(profile, dict) or profile.get("verified") is not True:
        return None
    if profile.get("model") != MODEL or profile.get("provider") != PROVIDER or not profile.get("profile_id"):
        return None
    try:
        request, config = build_request(svc, job, input_payload)
        max_input = profile["max_input_tokens"]
        max_output = profile["max_output_tokens"]
        if type(max_input) is not int or type(max_output) is not int or min(max_input, max_output) < 1 or config.max_completion_tokens > max_output:
            return None
        text_bound = len(json.dumps(request, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")) + 8192
        input_bound = max_input if job["kind"] == "page_check" else min(text_bound, max_input)
        prompt = Decimal(str(profile["prompt_rub_per_million"]))
        completion = Decimal(str(profile["completion_rub_per_million"]))
        image = Decimal(str(profile.get("image_rub_per_million", profile["prompt_rub_per_million"])))
        request_price = Decimal(str(profile.get("request_rub", 0)))
        prices = (prompt, completion, image, request_price)
        if any(not x.is_finite() or x < 0 for x in prices):
            return None
        if prompt < Decimal(str(config.max_price_prompt)) or completion < Decimal(str(config.max_price_completion)) or image < Decimal(str(config.max_price_image)):
            return None
        # Images and text may be billed at different input rates; reserving the
        # greater rate over the entire verified token ceiling is conservative.
        input_rate = max(prompt, image) if job["kind"] == "page_check" else prompt
        return ((input_bound * input_rate + config.max_completion_tokens * completion) / Decimal(1_000_000) + request_price).quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


async def run_job(svc, job: dict, input_payload: dict) -> TransportResult:
    override = getattr(svc, "transport", None)
    if override is not None:
        result = override(job, input_payload)
        result = await result if inspect.isawaitable(result) else result
    elif _mode(svc) == "fixture":
        from .fixture_transport import run_fixture
        result = await run_fixture(job, input_payload, scenario=getattr(svc, "fixture_scenario", "default"))
    else:
        try:
            request, config = build_request(svc, job, input_payload)
        except (ValueError, KeyError, TypeError, ValidationError):
            return TransportResult("rejected", actual_cost_rub=Decimal(0), error_code="invalid_request_configuration")
        result = await send_once(request, config=config, transport=getattr(svc, "http_transport", None))
    if result.outcome == "success":
        try:
            if job["kind"] == "class_analytics":
                from ..analytics.validation import validate_pair
                validate_pair(input_payload, result.payload)
            else:
                from .checker import validate_result
                validate_result(result.payload, len(input_payload["images"]))
        except (ValueError, TypeError, KeyError, ValidationError, PydanticValidationError):
            result.outcome, result.error_code, result.payload = "invalid_response", "invalid_analysis", None
    return result
