"""Offline runtime checks: request separation, billing ambiguity and invariants."""
import asyncio
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from PIL import Image
import pytest
from jsonschema.exceptions import ValidationError

from pilot.analytics.builder import build_request, load_prompt
from pilot.analytics.validation import validate_pair, HERE
from pilot.processing.checker import build_request as build_checker, PROMPT_SHA256
from pilot.processing.providers import run_job, bound_for_request
from pilot.processing.transport import ProviderConfig, TransportResult, send_once, strict_json


def pair(name="oracle"):
    return tuple(json.loads((HERE / "fixtures" / f"{name}.{suffix}.json").read_text(encoding="utf-8")) for suffix in ("input", "result"))


def config():
    return ProviderConfig(api_key="test-secret")


def envelope(payload, *, finish="stop", cost="0.125"):
    return {"id": "req_1", "choices": [{"message": {"content": json.dumps(payload)}, "finish_reason": finish}],
            "usage": {"cost_rub": cost, "prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}}


@pytest.mark.parametrize("name", ["oracle", "mixed", "synonyms", "zero-denominator"])
def test_frozen_analytics_pairs(name):
    validate_pair(*pair(name))


def test_builders_are_separate_and_checker_frozen(tmp_path):
    cfg = config()
    snapshot, _ = pair()
    request = build_request(snapshot, cfg)
    assert request["messages"][0]["content"] == load_prompt()
    assert strict_json(request["messages"][1]["content"]) == snapshot
    assert request["response_format"]["json_schema"]["name"] == "SmartNoteClassSummary"
    assert not any(isinstance(m["content"], list) for m in request["messages"])
    images = [tmp_path / "1.png", tmp_path / "2.png"]
    for path, color in zip(images, ("white", "black")):
        Image.new("RGB", (64, 64), color).save(path)
    checker = build_checker(images, cfg)
    assert hashlib.sha256(checker["messages"][0]["content"].encode()).hexdigest() == PROMPT_SHA256
    parts = checker["messages"][1]["content"]
    assert len(parts) == 3
    assert all(p["image_url"]["detail"] == "high" for p in parts[1:])
    assert parts[1] != parts[2]
    assert checker["response_format"]["json_schema"]["schema"]["$defs"]["Evidence"]["properties"]["photo_index"]["enum"] == [1, 2]
    for req in (request, checker):
        assert req["max_completion_tokens"] == 25000
        assert req["provider"]["only"] == ["google-ai-studio/flex"]
        assert req["provider"]["allow_fallbacks"] is False
        assert req["reasoning"] == {"effort": "medium"}
        assert req["media_resolution"] == "MEDIA_RESOLUTION_HIGH"


@pytest.mark.parametrize("reason,outcome,cost", [
    (httpx.ConnectTimeout, "temporary_failure", Decimal(0)),
    (httpx.ReadTimeout, "unknown", None),
    (httpx.WriteError, "unknown", None),
    (httpx.DecodingError, "unknown", None),
])
def test_one_post_and_ambiguous_failures(reason, outcome, cost):
    seen = []
    def handler(request):
        seen.append(request)
        raise reason("do not log sensitive exception text", request=request)
    result = asyncio.run(send_once({}, config=config(), transport=httpx.MockTransport(handler)))
    assert len(seen) == 1
    assert result.outcome == outcome
    assert result.actual_cost_rub == cost
    assert "sensitive" not in str(result.safe_metadata())


@pytest.mark.parametrize("status,body,outcome,cost", [
    (429, {"error": {"message": "rate limited"}}, "temporary_failure", Decimal(0)),
    (401, {"error": {"message": "denied"}}, "rejected", Decimal(0)),
    (503, {"error": {"message": "uncertain"}}, "unknown", None),
    (500, {"usage": {"cost": "0.3"}}, "unknown", Decimal("0.3")),
])
def test_rejection_is_not_any_http_failure(status, body, outcome, cost):
    result = asyncio.run(send_once({}, config=config(), transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))))
    assert (result.outcome, result.actual_cost_rub) == (outcome, cost)


@pytest.mark.parametrize("mutation", ["average", "red_ref", "duplicate", "groups", "null"])
def test_invalid_summary_never_repaired(mutation):
    snapshot, result = pair("zero-denominator" if mutation == "null" else "oracle")
    if mutation == "average": result["average_errors_per_notebook"] = 99
    elif mutation == "red_ref": result["top_errors"][0]["task_ids"] = [next(t["task_id"] for n in snapshot["notebooks"] for t in n["tasks"] if t["review_state"] == "system_error")]
    elif mutation == "duplicate": result["top_errors"].append(copy.deepcopy(result["top_errors"][0]))
    elif mutation == "groups": result["top_errors"] *= 4
    else: result["average_errors_per_notebook"] = 0
    async def override(job, payload):
        return TransportResult("success", payload=result, actual_cost_rub=Decimal("0.1"))
    svc = SimpleNamespace(transport=override)
    outcome = asyncio.run(run_job(svc, {"kind": "class_analytics"}, snapshot))
    assert outcome.outcome == "invalid_response"
    assert outcome.payload is None
    assert outcome.actual_cost_rub == Decimal("0.1")


def test_default_polza_missing_key_never_falls_back():
    svc = SimpleNamespace(settings=SimpleNamespace(), transport=None)
    result = asyncio.run(run_job(svc, {"kind": "class_analytics"}, pair()[0]))
    assert result.outcome == "rejected" and result.error_code == "invalid_request_configuration"
    svc.settings = SimpleNamespace(pilot_transport="fixture")
    result = asyncio.run(run_job(svc, {"kind": "class_analytics"}, pair()[0]))
    assert result.outcome == "success"


def test_reservation_requires_verified_model_and_caps():
    svc = SimpleNamespace(settings={"polza_api_key": "test-secret"}, pricing_profile=None)
    snapshot, _ = pair()
    job = {"kind": "class_analytics"}
    assert bound_for_request(svc, job, snapshot) is None
    svc.pricing_profile = {"verified": True, "profile_id": "verified-dev", "model": config().model, "provider": config().provider,
                           "max_input_tokens": 1048576, "max_output_tokens": 25000,
                           "prompt_rub_per_million": 50, "completion_rub_per_million": 250, "image_rub_per_million": 50}
    bound = bound_for_request(svc, job, snapshot)
    assert Decimal("6.25") < bound < Decimal("60")
    svc.pricing_profile["completion_rub_per_million"] = 1
    assert bound_for_request(svc, job, snapshot) is None


def test_safe_metadata_and_strict_json():
    snapshot, summary = pair()
    wire = envelope(summary)
    result = asyncio.run(send_once({}, config=config(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=wire))))
    assert result.actual_cost_rub == Decimal("0.125")
    assert result.payload == summary
    metadata = str(result.safe_metadata())
    assert "test-secret" not in metadata and "top_errors" not in metadata and "Authorization" not in metadata
    for content in ('{"x":NaN}', '{"x":1,"x":2}'):
        with pytest.raises(ValueError): strict_json(content)


def test_length_is_invalid_and_known_cost_preserved():
    result = asyncio.run(send_once({}, config=config(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=envelope({}, finish="length")))))
    assert result.outcome == "invalid_response" and result.error_code == "output_limit"
    assert result.actual_cost_rub == Decimal("0.125")


def test_fixture_and_override_do_not_bypass_image_validation(tmp_path):
    calls = []
    async def override(job, payload):
        calls.append(1)
        return TransportResult("success", payload={})
    svc = SimpleNamespace(transport=override)
    path = tmp_path / "too-small.png"
    Image.new("RGB", (31, 64)).save(path)
    result = asyncio.run(run_job(svc, {"kind": "page_check"}, {"images": [path]}))
    assert result.outcome == "rejected" and result.actual_cost_rub == 0
    assert calls == []


@pytest.mark.parametrize("case", ["oracle", "mixed", "synonyms", "zero-denominator"])
def test_default_fixture_mock_arithmetic_for_arbitrary_snapshot(case):
    snapshot, expected = pair(case)
    svc = SimpleNamespace(settings=SimpleNamespace(pilot_transport="fixture"), transport=None)
    result = asyncio.run(run_job(svc, {"kind": "class_analytics"}, snapshot))
    assert result.outcome == "success"
    validate_pair(snapshot, result.payload)
    for field in ("notebooks", "average_errors_per_notebook", "incomplete_tasks", "disputed_tasks", "unassessed_tasks"):
        assert result.payload[field] == expected[field]


def test_default_fixture_supports_thirty_notebooks_with_new_wrapper_ids():
    snapshot, _ = pair()
    original = snapshot["notebooks"][0]
    snapshot["notebooks"] = []
    for _ in range(30):
        notebook = copy.deepcopy(original)
        notebook["notebook_id"] = str(uuid4())
        for task in notebook["tasks"]:
            task["task_id"], task["analysis_id"] = str(uuid4()), str(uuid4())
        snapshot["notebooks"].append(notebook)
    svc = SimpleNamespace(settings=SimpleNamespace(pilot_transport="fixture"), transport=None)
    result = asyncio.run(run_job(svc, {"kind": "class_analytics"}, snapshot))
    assert result.outcome == "success"
    assert result.payload["notebooks"] == dict(total=30, with_errors=30, without_errors=0, partial=0, empty=0)
    assert result.payload["average_errors_per_notebook"] == 1
    assert len(result.payload["top_errors"][0]["task_ids"]) == 30
    validate_pair(snapshot, result.payload)


def test_named_fixed_fixture_rejects_mismatched_snapshot():
    snapshot, _ = pair("zero-denominator")
    svc = SimpleNamespace(settings=SimpleNamespace(pilot_transport="fixture"), transport=None, fixture_scenario="oracle")
    result = asyncio.run(run_job(svc, {"kind": "class_analytics"}, snapshot))
    assert result.outcome == "invalid_response" and result.payload is None
