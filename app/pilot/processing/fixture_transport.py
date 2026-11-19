"""Explicit offline teaching profile. Never interprets arbitrary photographs."""
from __future__ import annotations

import json
from pathlib import Path
from decimal import Decimal
from jsonschema.exceptions import ValidationError

from .transport import TransportResult

FIXTURES = Path(__file__).resolve().parents[1] / "analytics" / "assets" / "fixtures"


async def run_fixture(job: dict, input_payload: dict, *, scenario="default") -> TransportResult:
    if scenario in {"temporary_failure", "rejected", "unknown", "invalid_response"}:
        return TransportResult(scenario, actual_cost_rub=None if scenario == "unknown" else Decimal(0), error_code="fixture_" + scenario)
    if job["kind"] == "class_analytics":
        # A fixed LLM response belongs to a particular declared snapshot. It
        # is never an alternate deterministic summary generator.
        from ..analytics.validation import validate_pair
        name = scenario if scenario in {"oracle", "mixed", "synonyms", "zero-denominator"} else "oracle"
        snapshot = json.loads((FIXTURES / f"{name}.input.json").read_text(encoding="utf-8"))
        result = json.loads((FIXTURES / f"{name}.result.json").read_text(encoding="utf-8"))
        # Permit new DB wrapper UUIDs for the same fixed task scenario.
        old = [t["task_id"] for n in snapshot["notebooks"] for t in n["tasks"]]
        new = [t["task_id"] for n in input_payload["notebooks"] for t in n["tasks"]]
        if len(old) == len(new):
            mapping = dict(zip(old, new))
            for group in result["top_errors"]:
                group["task_ids"] = [mapping[x] for x in group["task_ids"]]
        try:
            validate_pair(input_payload, result)
        except (ValueError, ValidationError):
            # Catch schema-validation errors too; fixtures never call a model.
            return TransportResult("invalid_response", actual_cost_rub=Decimal(0), error_code="fixture_snapshot_mismatch")
    elif job["kind"] == "page_check":
        # Fixed, conspicuously synthetic 3-task report used by teaching smoke.
        template = json.loads((FIXTURES / "oracle.input.json").read_text(encoding="utf-8"))
        analyses = [t["analysis"] for n in template["notebooks"] for t in n["tasks"]]
        result = {"schema_version": "page-check/1.2", "status": "ok", "message": "Учебный пример", "tasks": analyses[:3]}
        for index, task in enumerate(result["tasks"], 1):
            task["task_id"] = f"fixture_{index}"
            task["photo_indices"] = [1]
            for evidence in task["evidence"]:
                evidence["photo_index"] = 1
            if task["first_error"]:
                task["first_error"]["photo_index"] = 1
    else:
        raise ValueError("Unknown job kind")
    return TransportResult("success", payload=result, actual_cost_rub=Decimal("0.01"), provider_request_id="fixture",
                           raw=json.dumps(result, ensure_ascii=False))
