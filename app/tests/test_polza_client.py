import json

import httpx
import pytest

from config import Settings
from image_validation import ValidatedImage
from polza_client import PolzaClient, PolzaInvalidResponseError, PolzaProviderError


@pytest.mark.anyio
async def test_sends_base64_photo_and_returns_validated_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "schema_version": "1.0",
                                    "status": "needs_clearer_photo",
                                    "overall_confidence": 0.2,
                                    "problem": None,
                                    "result": "not_assessed",
                                    "first_incorrect_step_number": None,
                                    "steps": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = PolzaClient(
        Settings(polza_api_key="test-key", llm_price_verified=True),
        transport=httpx.MockTransport(handler),
        max_completion_tokens=4000,
    )
    result = await client.analyze(ValidatedImage(content=b"image-bytes", mime_type="image/jpeg"))

    image_url = captured["messages"][1]["content"][1]["image_url"]["url"]  # type: ignore[index]
    assert image_url == "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM="
    assert captured["model"] == "google/gemini-3.8-flash"
    assert captured['max_completion_tokens'] == 4000
    assert captured['reasoning'] == {'effort': 'low'}
    assert captured['provider'] == {
        'only': ['google-ai-studio'], 'allow_fallbacks': False,
        'max_price': {'prompt': 88, 'completion': 440, 'image': 88, 'request': 0},
    }
    assert result.status.value == "needs_clearer_photo"


@pytest.mark.anyio
async def test_accepts_a_model_selected_by_the_benchmark() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "schema_version": "1.0",
                                    "status": "not_a_math_solution",
                                    "overall_confidence": 1.0,
                                    "problem": None,
                                    "result": "not_assessed",
                                    "first_incorrect_step_number": None,
                                    "steps": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = PolzaClient(
        Settings(polza_api_key="test-key"),
        transport=httpx.MockTransport(handler),
        model="provider/candidate-vision-model",
    )
    await client.analyze(ValidatedImage(content=b"image-bytes", mime_type="image/jpeg"))

    assert captured["model"] == "provider/candidate-vision-model"


@pytest.mark.anyio
async def test_returns_only_safe_usage_metadata_for_benchmarking() -> None:
    client = PolzaClient(
        Settings(polza_api_key="test-key"),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/canonical-model",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost_rub": 0.15, "unsafe": "omit"},
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "schema_version": "1.0",
                                        "status": "not_a_math_solution",
                                        "overall_confidence": 1.0,
                                        "problem": None,
                                        "result": "not_assessed",
                                        "first_incorrect_step_number": None,
                                        "steps": [],
                                    }
                                )
                            }
                        }
                    ],
                },
            )
        ),
    )

    detailed = await client.analyze_detailed(ValidatedImage(content=b"image-bytes", mime_type="image/jpeg"))

    assert detailed.provider_model == "provider/canonical-model"
    assert detailed.usage == {"prompt_tokens": 10, "completion_tokens": 20, "cost_rub": 0.15}


@pytest.mark.anyio
async def test_exposes_safe_usage_when_provider_response_is_not_a_valid_contract() -> None:
    client = PolzaClient(
        Settings(polza_api_key="test-key"),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/canonical-model",
                    "usage": {"prompt_tokens": 10, "cost_rub": 0.15, "unsafe": "omit"},
                    "choices": [{"message": {"content": "not-json"}}],
                },
            )
        ),
    )

    with pytest.raises(PolzaInvalidResponseError) as raised:
        await client.analyze_detailed(ValidatedImage(content=b"image-bytes", mime_type="image/jpeg"))

    assert raised.value.provider_model == "provider/canonical-model"
    assert raised.value.usage == {"prompt_tokens": 10, "cost_rub": 0.15}
    assert raised.value.raw_content == "not-json"
    assert raised.value.contract_error is not None


@pytest.mark.anyio
async def test_exposes_only_provider_status_for_rejected_request() -> None:
    client = PolzaClient(
        Settings(polza_api_key="test-key"),
        transport=httpx.MockTransport(lambda _request: httpx.Response(400, text="untrusted response")),
    )

    with pytest.raises(PolzaProviderError) as raised:
        await client.analyze(ValidatedImage(content=b"image-bytes", mime_type="image/jpeg"))

    assert raised.value.status_code == 400


@pytest.mark.anyio
async def test_allows_json_object_fallback_and_keeps_the_same_server_validation() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({
                    "schema_version": "1.0", "status": "not_a_math_solution", "overall_confidence": 1.0,
                    "problem": None, "result": "not_assessed", "first_incorrect_step_number": None, "steps": [],
                })}}],
            },
        )

    client = PolzaClient(
        Settings(polza_api_key="test-key"),
        transport=httpx.MockTransport(handler),
        response_format_type="json_object",
    )
    await client.analyze(ValidatedImage(content=b"image-bytes", mime_type="image/jpeg"))

    assert captured["response_format"] == {"type": "json_object"}
