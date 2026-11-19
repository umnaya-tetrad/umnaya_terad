"""Модели для приложения и офлайн-бенчмарков.

Это намеренно не переменные окружения: ключ остаётся секретом в .env,
а набор кандидатов для воспроизводимого сравнения хранится в коде.
"""

from dataclasses import dataclass
from typing import Literal

DEFAULT_POLZA_MODEL = "google/gemini-3.8-flash"

# Единственная модель текущего MVP и регрессионного smoke-прогона.
BENCHMARK_MODELS = (
    "google/gemini-3.8-flash",
)

# Gemini 3.7 Flash вызывается в json_object-режиме, после чего результат
# по-прежнему строго валидируется серверным контрактом.
BENCHMARK_RESPONSE_FORMATS = {
    "google/gemini-3.8-flash": "json_object",
    "google/gemini-3.7-flash": "json_object",
}


@dataclass(frozen=True)
class ModelRequestOptions:
    """Проверенные параметры вызова, не содержащие секретов."""

    response_format_type: Literal["json_schema", "json_object"]
    temperature: float
    max_completion_tokens: int


# Последний успешный smoke-прогон 2026-09-15: 11/11 валидных контрактов для
# Gemini 3.7 Flash с linkage_v2, json_object и лимитом 4 000 completion tokens.
# `json_schema` эта модель через Polza отклоняет с HTTP 400.
APPLICATION_MODEL_OPTIONS = {
    "google/gemini-3.8-flash": ModelRequestOptions(
        response_format_type="json_object",
        temperature=0,
        max_completion_tokens=4000,
    ),
    "google/gemini-3.7-flash": ModelRequestOptions(
        response_format_type="json_object",
        temperature=0,
        max_completion_tokens=4000,
    ),
}


def get_application_model_options(model: str = DEFAULT_POLZA_MODEL) -> ModelRequestOptions:
    try:
        return APPLICATION_MODEL_OPTIONS[model]
    except KeyError as error:
        raise ValueError(f"Для модели {model!r} не заданы проверенные параметры запроса.") from error
