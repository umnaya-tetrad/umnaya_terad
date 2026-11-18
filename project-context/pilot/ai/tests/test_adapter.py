"""Offline contract/transport tests. Every HTTP request uses MockTransport."""

import base64
import copy
import hashlib
import json
from pathlib import Path
import sys

import httpx
from PIL import Image
import pytest


AI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI))
from adapter import AdapterConfig, PolzaAdapter, PROMPT_TEXT_SHA256, load_prompt
from contract import Report, indexed_schema, provider_schema


@pytest.fixture
def photos(tmp_path):
    paths = [tmp_path / "page1.png", tmp_path / "page2.jpg"]
    Image.new("RGB", (64, 80), "white").save(paths[0])
    Image.new("RGB", (70, 80), "gray").save(paths[1])
    return paths


def report():
    return {"schema_version": "page-check/1.2", "status": "ok", "tasks": [{
        "task_id": "task1", "locator": "private handwritten solution", "photo_indices": [1, 2],
        "condition": "x+1=2", "result": "all_steps_correct", "completeness": "complete",
        "detail_level": "sufficient", "omitted_steps_note": "", "completeness_note": "",
        "evidence": [{"photo_index": 1, "latex": "x+1=2"}, {"photo_index": 2, "latex": "x=1"}],
        "first_error": None, "uncheckable_reason": "",
    }], "message": "private model message"}


def envelope(value=None, finish="stop", usage=None):
    return {"id": "generation-test-123", "choices": [{
        "finish_reason": finish, "message": {"content": json.dumps(report() if value is None else value)},
    }], "usage": usage if usage is not None else {
        "prompt_tokens": 50, "completion_tokens": 60, "total_tokens": 110,
        "cost_rub": 0.2, "completion_tokens_details": {"reasoning_tokens": 30},
    }}


def call(photos, body=None, status=200):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=envelope() if body is None else body)
    result = PolzaAdapter(AdapterConfig(api_key="test-key"), transport=httpx.MockTransport(handler)).analyze(photos)
    assert len(seen) == 1
    assert seen[0].method == "POST"
    return result, seen[0]


def test_frozen_prompt_and_schemas():
    assert hashlib.sha256(load_prompt().encode("utf-8")).hexdigest() == PROMPT_TEXT_SHA256
    assert Report.model_json_schema() == json.loads((AI / "response-schema-v1.2.json").read_text(encoding="utf-8"))
    for count in (1, 2):
        expected = json.loads((AI / f"wire-schema-{count}-photo.json").read_text(encoding="utf-8"))
        assert provider_schema(indexed_schema(Report.model_json_schema(), count)) == expected


def test_multipage_one_request_preserves_bytes_and_order(photos):
    result, request = call(photos)
    assert result.status == "ok"
    assert result.report.tasks[0].photo_indices == [1, 2]
    payload = json.loads(request.content)
    assert len(payload["messages"]) == 2
    assert payload["messages"][0] == {"role": "system", "content": load_prompt()}
    content = payload["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": (
        "Проверь все приложенные изображения совместно. Приложено 2 фото. Фото нумеруются С ЕДИНИЦЫ: 1,2. "
        "Нулевого фото нет. Все photo_index и photo_indices используют эти номера."
    )}
    assert len(content) == 3
    for path, part in zip(photos, content[1:], strict=True):
        assert part["image_url"]["detail"] == "high"
        assert base64.b64decode(part["image_url"]["url"].split(",", 1)[1]) == path.read_bytes()
    assert payload["response_format"]["json_schema"]["schema"] == provider_schema(indexed_schema(Report.model_json_schema(), 2))
    assert payload["provider"] == {"only": ["google-ai-studio/flex"], "allow_fallbacks": False,
        "max_price": {"prompt": 50, "completion": 250, "image": 50, "request": 0}}
    assert payload["max_completion_tokens"] == 25000
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["temperature"] == 0
    assert payload["media_resolution"] == "MEDIA_RESOLUTION_HIGH"
    assert request.extensions["timeout"] == {"connect": 15, "read": 300, "write": 300, "pool": 300}
    assert result.cost_rub == 0.2
    assert result.usage["completion_tokens_details"]["reasoning_tokens"] == 30


def test_environment_config_and_secret_repr(monkeypatch):
    monkeypatch.setenv("POLZA_API_KEY", "test-key")
    assert AdapterConfig.from_env().max_completion_tokens == 25000
    assert AdapterConfig.from_env().timeout_seconds == 300
    configured = AdapterConfig.from_env({"POLZA_API_KEY": "test-key", "POLZA_MAX_COMPLETION_TOKENS": "24000",
        "POLZA_TIMEOUT_SECONDS": "180", "POLZA_CONNECT_TIMEOUT_SECONDS": "9"})
    assert configured.max_completion_tokens == 24000
    assert configured.timeout_seconds == 180
    assert configured.connect_timeout_seconds == 9
    assert "test-key" not in repr(configured)


@pytest.mark.parametrize("finish", ["length", "max_tokens", "max_output_tokens"])
def test_truncation_rejected_before_valid_json(photos, finish):
    result, _ = call(photos, envelope(finish=finish))
    assert result.status == "truncated"
    assert result.report is None
    assert result.raw_content is not None
    assert result.cost_rub == 0.2


def test_read_timeout_unknown_cost_and_no_retry(photos):
    attempts = []
    def handler(request):
        attempts.append(request)
        raise httpx.ReadTimeout("private failure text test-key", request=request)
    result = PolzaAdapter(AdapterConfig(api_key="test-key"), transport=httpx.MockTransport(handler)).analyze(photos)
    assert len(attempts) == 1
    assert result.status == "network_error"
    assert result.error_class == "ReadTimeout"
    assert result.cost_rub is None
    assert result.http_status is None
    assert "test-key" not in json.dumps(result.safe_metadata())


def test_pdf_rejected_without_http(tmp_path):
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.7\nnot a photo")
    def handler(request):
        pytest.fail("Invalid image must never trigger HTTP")
    with pytest.raises(ValueError):
        PolzaAdapter(AdapterConfig(api_key="test-key"), transport=httpx.MockTransport(handler)).analyze([path])


@pytest.mark.parametrize("status,expected", [(400, "http_client_error"), (429, "rate_limited"),
    (500, "http_server_error"), (503, "http_server_error"), (307, "http_error")])
def test_http_failures_never_retry_or_follow_redirects(photos, status, expected):
    result, _ = call(photos, {"error": {"message": "private body test-key"}}, status)
    assert result.status == expected
    assert result.http_status == status
    assert result.cost_rub is None
    assert "test-key" not in repr(result)
    assert "private" not in json.dumps(result.safe_metadata())


def test_safe_metadata_and_repr_exclude_model_content(photos):
    body = envelope()
    body["usage"]["private"] = "test-key"
    result, _ = call(photos, body)
    metadata = json.dumps(result.safe_metadata())
    assert "private" not in metadata
    assert "report" not in metadata
    assert "raw_content" not in metadata
    assert "private" not in repr(result)
    assert "test-key" not in repr(result)


@pytest.mark.parametrize("usage,expected", [({"cost": 0.31}, 0.31), ({"cost_rub": True}, None),
    ({"cost_rub": -1}, None), ({"cost_rub": "0.3"}, None), ({"cost_rub": 0}, 0)])
def test_usage_numeric_cost_only(photos, usage, expected):
    result, _ = call(photos, envelope(usage=usage))
    assert result.cost_rub == expected


@pytest.mark.parametrize("mutation", ["index_zero", "index_outside", "evidence_outside", "error_outside", "error_missing", "extra_evidence", "extra_field", "float_index"])
def test_contract_and_photo_references(photos, mutation):
    value = copy.deepcopy(report())
    task = value["tasks"][0]
    if mutation == "index_zero":
        task["photo_indices"] = [0]
    elif mutation == "index_outside":
        task["photo_indices"] = [3]
    elif mutation == "evidence_outside":
        task["photo_indices"] = [1]
    elif mutation == "error_outside":
        task["result"] = "first_error_found"
        task["first_error"] = {"photo_index": 3, "wrong_latex": "x=1", "rule": "rule", "explanation": "explanation", "corrected_latex": "x=2"}
    elif mutation == "error_missing":
        task["result"] = "first_error_found"
    elif mutation == "extra_evidence":
        task["evidence"] *= 3
    elif mutation == "extra_field":
        task["secret"] = "private"
    elif mutation == "float_index":
        task["photo_indices"] = [1.0]
    result, _ = call(photos, envelope(value))
    assert result.status == "schema_error"
    assert result.report is None


def test_uncheckable_is_report_not_transport_failure(photos):
    result, _ = call(photos, envelope({"schema_version": "page-check/1.2", "status": "uncheckable", "tasks": [], "message": "unreadable"}))
    assert result.status == "ok"
    assert result.report.status == "uncheckable"


def test_invalid_json_is_not_repaired(photos):
    body = envelope()
    body["choices"][0]["message"]["content"] = "```json\n{}\n```"
    result, _ = call(photos, body)
    assert result.status == "invalid_json"


def test_no_system_proxy_and_default_transport_retries(photos, monkeypatch):
    # Inspect construction while still routing all traffic through MockTransport.
    import adapter
    real_client = httpx.Client
    calls = []
    def client_factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["verify"] is True
        return real_client(**kwargs)
    def transport_factory(**kwargs):
        calls.append(kwargs)
        return httpx.MockTransport(lambda request: httpx.Response(200, json=envelope()))
    monkeypatch.setattr(adapter.httpx, "Client", client_factory)
    monkeypatch.setattr(adapter.httpx, "HTTPTransport", transport_factory)
    result = PolzaAdapter(AdapterConfig(api_key="test-key")).analyze(photos)
    assert result.status == "ok"
    assert calls == [{"retries": 0, "trust_env": False, "verify": True}]
