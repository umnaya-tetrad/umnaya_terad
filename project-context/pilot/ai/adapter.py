"""Portable reference adapter: one explicit call = at most one HTTP POST.

This is not a durable worker. The caller owns authorization, persistence,
budget accounting, route verification and any separately approved retry policy.
No dotenv is loaded automatically and no process-global network state is changed.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping

import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from contract import Report, indexed_schema, provider_schema, validate_report


ASSETS = Path(__file__).resolve().parent
PROMPT_TEXT_SHA256 = "7a44b3006e88680d88ced741ec65896930fa180c39ba95405200da7aecbf3aec"
MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
TRUNCATED_REASONS = {"length", "max_tokens", "max_output_tokens"}


@dataclass(frozen=True)
class AdapterConfig:
    api_key: str = field(repr=False)
    base_url: str = "https://polza.ai/api/v1"
    model: str = "google/gemini-3.8-flash"
    provider: str = "google-ai-studio/flex"
    # New reference recommendation, NOT the tested benchmark's 12k/24k profile.
    max_completion_tokens: int = 25000
    # HTTPX phase inactivity timeout; not a total wall-clock deadline.
    timeout_seconds: float = 300
    connect_timeout_seconds: float = 15
    # Dated tested routing caps, RUB per million tokens (2026-11-19).
    max_price_prompt: float = 50
    max_price_completion: float = 250
    max_price_image: float = 50

    def __post_init__(self):
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("POLZA_API_KEY is required")
        url = httpx.URL(self.base_url)
        if url.scheme != "https" or not url.host or url.username or url.password or url.query or url.fragment:
            raise ValueError("POLZA_BASE_URL must be an HTTPS URL without credentials/query/fragment")
        if not self.model or not self.provider:
            raise ValueError("Model and provider are required")
        if isinstance(self.max_completion_tokens, bool) or not isinstance(self.max_completion_tokens, int) or self.max_completion_tokens < 1:
            raise ValueError("Completion token limit must be a positive integer")
        for value in (self.timeout_seconds, self.connect_timeout_seconds):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError("Timeouts must be positive finite numbers")
        for value in (self.max_price_prompt, self.max_price_completion, self.max_price_image):
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError("Price caps must be nonnegative finite numbers")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AdapterConfig:
        env = os.environ if environ is None else environ
        return cls(
            api_key=env.get("POLZA_API_KEY", ""),
            base_url=env.get("POLZA_BASE_URL", "https://polza.ai/api/v1"),
            model=env.get("POLZA_MODEL", "google/gemini-3.8-flash"),
            provider=env.get("POLZA_PROVIDER", "google-ai-studio/flex"),
            max_completion_tokens=int(env.get("POLZA_MAX_COMPLETION_TOKENS", "25000")),
            timeout_seconds=float(env.get("POLZA_TIMEOUT_SECONDS", "300")),
            connect_timeout_seconds=float(env.get("POLZA_CONNECT_TIMEOUT_SECONDS", "15")),
            max_price_prompt=float(env.get("POLZA_MAX_PRICE_PROMPT", "50")),
            max_price_completion=float(env.get("POLZA_MAX_PRICE_COMPLETION", "250")),
            max_price_image=float(env.get("POLZA_MAX_PRICE_IMAGE", "50")),
        )


@dataclass
class AnalysisResult:
    # Adapter status is independent of Report.status (ok / uncheckable).
    status: str
    elapsed_seconds: float = 0
    http_status: int | None = None
    provider_id: str | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    cost_rub: float | int | None = None
    error_class: str | None = None
    error_code: str | None = None
    report: Report | None = field(default=None, repr=False)
    raw_content: str | None = field(default=None, repr=False)

    def safe_metadata(self) -> dict[str, Any]:
        """No photo bytes, raw output, report, exception text, headers or key."""
        return {
            "status": self.status, "elapsed_seconds": self.elapsed_seconds,
            "http_status": self.http_status, "provider_id": self.provider_id,
            "finish_reason": self.finish_reason,
            "usage": json.loads(json.dumps(self.usage)), "cost_rub": self.cost_rub,
            "error_class": self.error_class, "error_code": self.error_code,
        }


def load_prompt() -> str:
    # Universal-newline read reproduces the LF system message sent by runner.py.
    prompt = (ASSETS / "checker-v2.txt").read_text(encoding="utf-8")
    if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != PROMPT_TEXT_SHA256:
        raise ValueError("Frozen prompt text checksum mismatch")
    return prompt


def _image(path: Path) -> tuple[bytes, str]:
    with path.open("rb") as stream:
        content = stream.read(8_000_001)
    if not content or len(content) > 8_000_000:
        raise ValueError("Image is empty or exceeds 8 MB")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in MIME_BY_FORMAT:
                raise ValueError("Only JPEG, PNG and WebP are supported")
            if image.width * image.height > 36_000_000 or min(image.size) < 32:
                raise ValueError("Image dimensions outside supported bounds")
            mime = MIME_BY_FORMAT[image.format]
            image.verify()
        with Image.open(BytesIO(content)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Image failed decoding validation") from error
    return content, mime


def _number(value: Any) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool) and value >= 0) or (
        isinstance(value, float) and math.isfinite(value) and value >= 0
    )


def _usage(payload: dict) -> dict[str, Any]:
    source = payload.get("usage")
    if not isinstance(source, dict):
        return {}
    result = {key: source[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_rub", "cost") if _number(source.get(key))}
    details = source.get("completion_tokens_details")
    if isinstance(details, dict) and _number(details.get("reasoning_tokens")):
        result["completion_tokens_details"] = {"reasoning_tokens": details["reasoning_tokens"]}
    return result


def _reject_constant(value: str):
    raise ValueError("Non-JSON numeric constant")


class PolzaAdapter:
    def __init__(self, config: AdapterConfig, *, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.transport = transport

    def analyze(self, images: list[Path]) -> AnalysisResult:
        """Send an ordered, nonempty packet. Input errors raise before HTTP.

        Never retries, repairs JSON, crops/reencodes photos or persists content.
        Unknown billing (e.g. ReadTimeout) remains None for caller reconciliation.
        """
        if not isinstance(images, list) or not images or any(not isinstance(path, Path) for path in images):
            raise ValueError("images must be a nonempty ordered list of Path objects")
        user_text = (
            "Проверь все приложенные изображения совместно."
            + f" Приложено {len(images)} фото. Фото нумеруются С ЕДИНИЦЫ: "
            + ",".join(str(index) for index in range(1, len(images) + 1))
            + ". Нулевого фото нет. Все photo_index и photo_indices используют эти номера."
        )
        content = [{"type": "text", "text": user_text}]
        for path in images:
            data, mime = _image(path)
            content.append({"type": "image_url", "image_url": {
                "url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", "detail": "high",
            }})
        payload = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": load_prompt()}, {"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "SmartNotePage", "strict": True,
                "schema": provider_schema(indexed_schema(Report.model_json_schema(), len(images))),
            }},
            "temperature": 0,
            "max_completion_tokens": self.config.max_completion_tokens,
            "provider": {"only": [self.config.provider], "allow_fallbacks": False, "max_price": {
                "prompt": self.config.max_price_prompt, "completion": self.config.max_price_completion,
                "image": self.config.max_price_image, "request": 0,
            }},
            "reasoning": {"effort": "medium"},
            "media_resolution": "MEDIA_RESOLUTION_HIGH",
        }
        result = AnalysisResult(status="network_error")
        started = time.perf_counter()
        try:
            transport = self.transport if self.transport is not None else httpx.HTTPTransport(retries=0, trust_env=False, verify=True)
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, verify=True,
                              timeout=httpx.Timeout(self.config.timeout_seconds, connect=self.config.connect_timeout_seconds)) as client:
                response = client.post(self.config.base_url.rstrip("/") + "/chat/completions",
                                       headers={"Authorization": f"Bearer {self.config.api_key}"}, json=payload)
            result.http_status = response.status_code
        except httpx.RequestError as error:
            # Exception text may contain URLs/credentials; never return or log it.
            result.error_class = type(error).__name__ if type(error).__module__.startswith("httpx") else "RequestError"
            result.error_code = "transport_failure"
            return result
        finally:
            result.elapsed_seconds = time.perf_counter() - started
        try:
            body = json.loads(response.content, parse_constant=_reject_constant)
        except (ValueError, UnicodeError):
            body = None
        if isinstance(body, dict):
            result.usage = _usage(body)
            # Polza's tested `cost` alias is RUB; this is not a generic OpenAI convention.
            result.cost_rub = result.usage.get("cost_rub", result.usage.get("cost"))
            provider_id = body.get("id")
            if isinstance(provider_id, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", provider_id) and self.config.api_key not in provider_id:
                result.provider_id = provider_id
        if response.status_code < 200 or response.status_code >= 300:
            result.status = ("rate_limited" if response.status_code == 429 else "http_client_error" if 400 <= response.status_code < 500
                             else "http_server_error" if response.status_code >= 500 else "http_error")
            result.error_class, result.error_code = "HTTPError", f"http_{response.status_code}"
            return result
        if not isinstance(body, dict):
            result.status, result.error_class, result.error_code = "invalid_response", "ResponseError", "invalid_envelope"
            return result
        try:
            choice = body["choices"][0]
            finish = choice.get("finish_reason")
            # Fixed vocabulary only: provider-controlled text is never safe metadata.
            result.finish_reason = finish if isinstance(finish, str) and finish in {"stop", "length", "max_tokens", "max_output_tokens", "content_filter", "tool_calls"} else None
            raw = choice.get("message", {}).get("content")
            result.raw_content = raw if isinstance(raw, str) else None
        except (KeyError, IndexError, TypeError, AttributeError):
            result.status, result.error_class, result.error_code = "invalid_response", "ResponseError", "missing_choice"
            return result
        if result.finish_reason in TRUNCATED_REASONS:
            result.status, result.error_class, result.error_code = "truncated", "OutputLimitError", "output_limit"
            return result
        if result.finish_reason != "stop" or result.raw_content is None:
            result.status, result.error_class, result.error_code = "invalid_response", "ResponseError", "incomplete_response"
            return result
        try:
            parsed = json.loads(result.raw_content, parse_constant=_reject_constant)
        except ValueError:
            result.status, result.error_class, result.error_code = "invalid_json", "JSONDecodeError", "invalid_json"
            return result
        try:
            result.report = validate_report(parsed, len(images))
        except (ValidationError, ValueError):
            result.status, result.error_class, result.error_code = "schema_error", "ContractError", "invalid_report"
            return result
        result.status = "ok"
        return result
