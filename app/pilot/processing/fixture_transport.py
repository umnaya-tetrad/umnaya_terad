"""Explicit offline mock profile. Never interprets arbitrary photographs.

Default summaries are MOCK responses for synthetic API-only development. Their
arithmetic and literal-rule grouping are not evidence of LLM semantic quality.
This module is never selected as a fallback after a Polza failure.
"""
from __future__ import annotations

import json
from pathlib import Path
from decimal import Decimal
from jsonschema.exceptions import ValidationError

from .transport import TransportResult

FIXTURES = Path(__file__).resolve().parents[1] / "analytics" / "assets" / "fixtures"


def _mock_summary(snapshot: dict) -> dict:
    """Generate only an explicit fixture-mode response, never a real summary."""
    from ..analytics.validation import validate_input
    validate_input(snapshot)
    counts = dict(total=len(snapshot["notebooks"]), with_errors=0, without_errors=0, partial=0, empty=0)
    numerator = incomplete = disputed = unassessed = 0
    groups = {}
    for notebook in snapshot["notebooks"]:
        tasks = notebook["tasks"]
        confirmed = [t for t in tasks if t["review_state"] == "confirmed" and t["analysis"]["result"] != "not_assessed"]
        errors = [t for t in confirmed if t["analysis"]["result"] == "first_error_found"]
        incomplete += sum(t["analysis"]["completeness"] == "incomplete" for t in confirmed)
        disputed += sum(t["review_state"] == "system_error" for t in tasks)
        unassessed += sum(t["analysis"]["result"] == "not_assessed" for t in tasks)
        if not tasks and notebook["unresolved_bundles"] == 0:
            counts["empty"] += 1
        elif tasks and len(confirmed) == len(tasks) and notebook["unresolved_bundles"] == 0:
            counts["with_errors" if errors else "without_errors"] += 1
            numerator += len(errors)
        else:
            counts["partial"] += 1
        for task in errors:
            # Intentionally literal grouping in a mock. Synonym quality is
            # tested separately with saved fixed fixtures and real Polza.
            rule = task["analysis"]["first_error"]["rule"].strip() or "Правило из учебного примера"
            groups.setdefault(rule, []).append(task["task_id"])
    denominator = counts["with_errors"] + counts["without_errors"]
    top = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:3]
    return dict(schema_version="class-summary/1", notebooks=counts,
                average_errors_per_notebook=numerator / denominator if denominator else None,
                incomplete_tasks=incomplete, disputed_tasks=disputed, unassessed_tasks=unassessed,
                top_errors=[dict(rule=rule[:120], task_ids=ids) for rule, ids in top])


async def run_fixture(job: dict, input_payload: dict, *, scenario="default") -> TransportResult:
    if scenario in {"temporary_failure", "rejected", "unknown", "invalid_response"}:
        return TransportResult(scenario, actual_cost_rub=None if scenario == "unknown" else Decimal(0), error_code="fixture_" + scenario)
    if job["kind"] == "class_analytics" and scenario == "default":
        result = _mock_summary(input_payload)
    elif job["kind"] == "class_analytics":
        # A fixed LLM response belongs to a particular declared snapshot. It
        # is never an alternate deterministic summary generator.
        from ..analytics.validation import validate_pair
        if scenario not in {"oracle", "mixed", "synonyms", "zero-denominator"}:
            raise ValueError("Unknown explicit fixture scenario")
        name = scenario
        snapshot = json.loads((FIXTURES / f"{name}.input.json").read_text(encoding="utf-8"))
        result = json.loads((FIXTURES / f"{name}.result.json").read_text(encoding="utf-8"))
        def content(value):
            return [(n["unresolved_bundles"], [(t["review_state"], t["analysis"]) for t in n["tasks"]])
                    for n in value["notebooks"]]
        if content(snapshot) != content(input_payload):
            return TransportResult("invalid_response", actual_cost_rub=Decimal(0), error_code="fixture_snapshot_mismatch")
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
