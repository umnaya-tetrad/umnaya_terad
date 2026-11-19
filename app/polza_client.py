import base64
import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from config import Settings
from image_validation import ValidatedImage
from model_catalog import DEFAULT_POLZA_MODEL
from prompts import DEFAULT_PROMPT_VERSION, USER_PROMPT, get_system_prompt
from schemas import AnalysisResponse


class PolzaUnavailableError(RuntimeError):
    pass


class PolzaProviderError(RuntimeError):
    def __init__(self, status_code: int, provider_error_code: str | None = None, validation_hint: str | None = None) -> None:
        self.status_code = status_code
        self.provider_error_code = provider_error_code
        self.validation_hint = validation_hint
        super().__init__(f"Polza AI returned HTTP {status_code}")


class PolzaInvalidResponseError(RuntimeError):
    def __init__(
        self,
        message: str,
        provider_model: str | None = None,
        usage: dict[str, Any] | None = None,
        raw_content: str | None = None,
        contract_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_model = provider_model
        self.usage = usage or {}
        # Не логируется приложением. Benchmark-раннер сохраняет это только в
        # локальный gitignored requests.jsonl для диагностики контракта.
        self.raw_content = raw_content
        self.contract_error = contract_error


@dataclass(frozen=True)
class PolzaAnalysis:
    """Валидированный результат и безопасные метаданные одного вызова Polza."""

    analysis: AnalysisResponse
    provider_model: str | None
    usage: dict[str, Any]


class PolzaClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        model: str = DEFAULT_POLZA_MODEL,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        response_format_type: Literal["json_schema", "json_object"] = "json_schema",
        prompt_version: str = DEFAULT_PROMPT_VERSION,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.model = model
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.response_format_type = response_format_type
        self.prompt_version = prompt_version

    async def analyze(self, image: ValidatedImage) -> AnalysisResponse:
        return (await self.analyze_detailed(image)).analysis

    async def analyze_detailed(self, image: ValidatedImage) -> PolzaAnalysis:
        if not self.settings.polza_api_key:
            raise PolzaUnavailableError("Ключ Polza AI ещё не настроен.")

        encoded_image = base64.b64encode(image.content).decode("ascii")
        response_format: dict[str, Any] = {"type": self.response_format_type}
        if self.response_format_type == "json_schema":
            response_format["json_schema"] = {
                "name": "smart_note_analysis",
                "strict": True,
                "schema": AnalysisResponse.model_json_schema(),
            }

        system_prompt = get_system_prompt(self.prompt_version)
        if self.response_format_type == "json_object":
            # Некоторые vision-модели не принимают JSON Schema. Они всё равно
            # обязаны пройти ту же серверную Pydantic-валидацию после ответа.
            system_prompt = f"{system_prompt}\n\nКонтракт JSON: {json.dumps(AnalysisResponse.model_json_schema(), ensure_ascii=False)}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image.mime_type};base64,{encoded_image}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            "response_format": response_format,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_completion_tokens is not None:
            payload["max_completion_tokens"] = self.max_completion_tokens
        # Verified catalog 2026-10-31: context <= 1,048,576, output <= 4,000.
        # At these ceilings, even a completely full context costs < 100 RUB.
        if self.settings.llm_price_verified:
            payload['provider'] = {
                'only': ['google-ai-studio'], 'allow_fallbacks': False,
                'max_price': {'prompt': 88, 'completion': 440, 'image': 88, 'request': 0},
            }
            payload['reasoning'] = {'effort': 'low'}

        timeout = httpx.Timeout(
            self.settings.polza_timeout_seconds,
            connect=self.settings.polza_connect_timeout_seconds,
        )
        try:
            # Polza AI доступна напрямую. Не наследуем HTTP(S)_PROXY из окружения,
            # чтобы корпоративный/системный прокси не перехватывал этот вызов.
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.post(
                    self.settings.polza_chat_url,
                    headers={"Authorization": f"Bearer {self.settings.polza_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                provider_payload = response.json()
        except httpx.HTTPStatusError as error:
            hint = None
            if error.response.status_code == 400:
                try:
                    candidate = error.response.json().get('error',{}).get('message')
                    # Only fixed diagnostic categories; never log provider text.
                    if isinstance(candidate,str):
                        for field in ('provider.max_price','reasoning','max_completion_tokens','response_format'):
                            if field in candidate:
                                hint = 'invalid_' + field.replace('.','_')
                                break
                except (ValueError,AttributeError):
                    pass
            raise PolzaProviderError(error.response.status_code, _safe_provider_error_code(error.response),hint) from error
        except httpx.HTTPError as error:
            raise PolzaUnavailableError("Сервис проверки временно недоступен.") from error
        except ValueError as error:
            raise PolzaInvalidResponseError("Polza AI вернула некорректный HTTP-ответ.") from error
        finally:
            del encoded_image

        content: str | None = None
        try:
            content = provider_payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Provider content must be a string")
            analysis = AnalysisResponse.model_validate(json.loads(content))
            return PolzaAnalysis(
                analysis=analysis,
                provider_model=_provider_model(provider_payload),
                usage=_safe_usage(provider_payload),
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as error:
            raise PolzaInvalidResponseError(
                "Модель вернула ответ, не прошедший проверку контракта.",
                provider_model=_provider_model(provider_payload),
                usage=_safe_usage(provider_payload),
                raw_content=content,
                contract_error=str(error),
            ) from error


def _provider_model(provider_payload: dict[str, Any]) -> str | None:
    model = provider_payload.get("model")
    return model if isinstance(model, str) and model else None


def _safe_usage(provider_payload: dict[str, Any]) -> dict[str, Any]:
    """Оставляет только счётчики и стоимость, никогда не сохраняя ответ провайдера целиком."""

    usage = provider_payload.get("usage")
    if not isinstance(usage, dict):
        return {}

    safe_usage: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_rub", "cost"):
        value = usage.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            safe_usage[key] = value
    return safe_usage


def _safe_provider_error_code(response: httpx.Response) -> str | None:
    """Сохраняет только код причины отказа, никогда текст/контент провайдера."""

    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    for key in ("code", "type"):
        value = error.get(key)
        if isinstance(value, str) and value and len(value) <= 100:
            return value
    return None
