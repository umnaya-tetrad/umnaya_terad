"""One POST per attempt. Unknown billing is never represented as zero.

Payloads/raw content are private artifacts. Only safe_metadata may be logged.
The durable caller owns dispatch guards, reservations, publication and retries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
import math
import re
import time
from typing import Any, Mapping

import httpx

MODEL = "google/gemini-3.8-flash"
PROVIDER = "google-ai-studio/flex"


def strict_json(value: str | bytes) -> Any:
    def reject_constant(value):
        raise ValueError("Non-JSON numeric constant")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique_object)


@dataclass(frozen=True)
class ProviderConfig:
    api_key: str = field(repr=False)
    base_url: str = "https://polza.ai/api/v1"
    model: str = MODEL
    provider: str = PROVIDER
    max_completion_tokens: int = 25000
    timeout_seconds: float = 300
    connect_timeout_seconds: float = 15
    max_price_prompt: float = 50
    max_price_completion: float = 250
    max_price_image: float = 50

    def __post_init__(self):
        if not self.api_key or not self.api_key.strip():
            raise ValueError("POLZA_API_KEY is required")
        url = httpx.URL(self.base_url)
        if url.scheme != "https" or not url.host or url.username or url.password or url.query or url.fragment:
            raise ValueError("Invalid Polza HTTPS endpoint")
        if self.model != MODEL or self.provider != PROVIDER:
            raise ValueError("Unverified model/provider profile")
        if type(self.max_completion_tokens) is not int or not 1 <= self.max_completion_tokens <= 25000:
            raise ValueError("Invalid completion cap")
        for value in (self.timeout_seconds, self.connect_timeout_seconds):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid phase timeout")
        for value in (self.max_price_prompt, self.max_price_completion, self.max_price_image):
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid route price cap")

    @classmethod
    def from_settings(cls, settings):
        def get(name, default):
            return settings.get(name, default) if isinstance(settings, Mapping) else getattr(settings, name, default)
        return cls(**{name: get("polza_" + name, "" if name == "api_key" else f.default) for name, f in cls.__dataclass_fields__.items()})


@dataclass
class TransportResult:
    outcome: str
    payload: dict | None = field(default=None, repr=False)
    actual_cost_rub: Decimal | None = None
    provider_request_id: str | None = None
    raw: str | None = field(default=None, repr=False)
    http_status: int | None = None
    elapsed_seconds: float = 0
    finish_reason: str | None = None
    error_code: str | None = None
    usage: dict = field(default_factory=dict)
    # The full envelope is private: it can include provider-controlled content.
    raw_envelope: str | None = field(default=None, repr=False)

    def safe_metadata(self):
        return dict(outcome=self.outcome, actual_cost_rub=str(self.actual_cost_rub) if self.actual_cost_rub is not None else None,
                    provider_request_id=self.provider_request_id, http_status=self.http_status,
                    elapsed_seconds=self.elapsed_seconds, finish_reason=self.finish_reason,
                    error_code=self.error_code, usage=self.usage.copy())


def request_base(config: ProviderConfig) -> dict:
    return {
        "model": config.model, "temperature": 0,
        "max_completion_tokens": config.max_completion_tokens,
        "provider": {"only": [config.provider], "allow_fallbacks": False, "max_price": {
            "prompt": config.max_price_prompt, "completion": config.max_price_completion,
            "image": config.max_price_image, "request": 0,
        }},
        "reasoning": {"effort": "medium"},
        "media_resolution": "MEDIA_RESOLUTION_HIGH",
    }


def _decimal(value) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def parse_response(response: httpx.Response, config: ProviderConfig, elapsed: float) -> TransportResult:
    result = TransportResult("invalid_response", http_status=response.status_code, elapsed_seconds=elapsed)
    result.raw_envelope = response.text
    try:
        body = strict_json(response.content)
    except (ValueError, UnicodeError):
        body = None
    if isinstance(body, dict):
        usage = body.get("usage")
        if isinstance(usage, dict):
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key)
                if type(value) is int and value >= 0:
                    result.usage[key] = value
            details = usage.get("completion_tokens_details")
            if isinstance(details, dict) and type(details.get("reasoning_tokens")) is int and details["reasoning_tokens"] >= 0:
                result.usage["reasoning_tokens"] = details["reasoning_tokens"]
            result.actual_cost_rub = _decimal(usage.get("cost_rub", usage.get("cost")))
        identity = body.get("id")
        if isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", identity) and config.api_key not in identity:
            result.provider_request_id = identity
    if not 200 <= response.status_code < 300:
        # An explicit pre-inference rejection is safe. A 5xx/garbled body may
        # have followed inference; HTTP status alone cannot release its hold.
        rejection = (400 <= response.status_code < 500 and isinstance(body, dict)
                     and isinstance(body.get("error"), (dict, str)) and not body.get("choices")
                     and not body.get("usage"))
        result.outcome = "temporary_failure" if rejection and response.status_code == 429 else "rejected" if rejection else "unknown"
        if rejection:
            result.actual_cost_rub = Decimal(0)
        result.error_code = f"http_{response.status_code}"
        return result
    if not isinstance(body, dict):
        result.error_code = "invalid_envelope"
        return result
    try:
        choice = body["choices"][0]
        finish = choice.get("finish_reason")
        result.finish_reason = finish if finish in {"stop", "length", "max_tokens", "max_output_tokens", "content_filter", "tool_calls"} else None
        raw = choice["message"]["content"]
        result.raw = raw if isinstance(raw, str) else None
    except (KeyError, IndexError, TypeError, AttributeError):
        result.error_code = "missing_choice"
        return result
    if result.finish_reason in {"length", "max_tokens", "max_output_tokens"}:
        result.error_code = "output_limit"
        return result
    if result.finish_reason != "stop" or result.raw is None:
        result.error_code = "incomplete_response"
        return result
    try:
        parsed = strict_json(result.raw)
        if not isinstance(parsed, dict):
            raise ValueError("Expected object")
        result.payload = parsed
    except ValueError:
        result.error_code = "invalid_json"
        return result
    result.outcome = "success"
    return result


async def send_once(request: dict, attempt_context=None, *, config: ProviderConfig,
                    transport: httpx.AsyncBaseTransport | None = None) -> TransportResult:
    """Never retries. trust_env=False disables env proxies, not a system TUN."""
    started = time.perf_counter()
    try:
        actual_transport = transport if transport is not None else httpx.AsyncHTTPTransport(retries=0, trust_env=False, verify=True)
        async with httpx.AsyncClient(transport=actual_transport, trust_env=False, follow_redirects=False,
                                    verify=True, timeout=httpx.Timeout(config.timeout_seconds, connect=config.connect_timeout_seconds)) as client:
            response = await client.post(config.base_url.rstrip("/") + "/chat/completions",
                                         headers={"Authorization": "Bearer " + config.api_key}, json=request)
        return parse_response(response, config, time.perf_counter() - started)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
        return TransportResult("temporary_failure", actual_cost_rub=Decimal(0), elapsed_seconds=time.perf_counter() - started,
                               error_code=type(error).__name__)
    except httpx.RequestError as error:
        # Read/write/protocol failures may follow a paid accepted request.
        return TransportResult("unknown", elapsed_seconds=time.perf_counter() - started,
                               error_code=type(error).__name__ if type(error).__module__.startswith("httpx") else "RequestError")
