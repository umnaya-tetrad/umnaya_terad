"""Offline/worker validator for LLM analytics. Does not generate a summary."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent / "assets"
CHECKER = HERE.parent.parent / "processing" / "assets" / "response-schema-v1.2.json"


def load(path: Path) -> dict:
    def reject_constant(value):
        raise ValueError("Non-JSON numeric constant: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def _validator(filename: str) -> Draft202012Validator:
    input_schema = load(HERE / "input.schema.json")
    output_schema = load(HERE / "result.schema.json")
    checker_schema = load(CHECKER)
    base = (HERE / "input.schema.json").as_uri()
    # No network retrieval: all references are registered local resources.
    registry = Registry().with_resources([
        (input_schema["$id"], Resource.from_contents(input_schema)),
        (base, Resource.from_contents(input_schema)),
        (output_schema["$id"], Resource.from_contents(output_schema)),
        ((HERE / "result.schema.json").as_uri(), Resource.from_contents(output_schema)),
        (CHECKER.as_uri(), Resource.from_contents({"$schema": "https://json-schema.org/draft/2020-12/schema", **checker_schema})),
        ("urn:smartnote:page-check:1.2", Resource.from_contents({"$schema": "https://json-schema.org/draft/2020-12/schema", **checker_schema})),
    ])
    schema = input_schema if filename == "input.schema.json" else output_schema
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def validate_input(snapshot: dict) -> None:
    _validator("input.schema.json").validate(snapshot)
    notebook_ids: set[str] = set()
    task_ids: set[str] = set()
    analysis_ids: set[str] = set()
    for notebook in snapshot["notebooks"]:
        if notebook["notebook_id"] in notebook_ids:
            raise ValueError("Duplicate notebook ID")
        notebook_ids.add(notebook["notebook_id"])
        for item in notebook["tasks"]:
            if item["task_id"] in task_ids or item["analysis_id"] in analysis_ids:
                raise ValueError("Duplicate task/analysis ID")
            task_ids.add(item["task_id"])
            analysis_ids.add(item["analysis_id"])
            analysis = item["analysis"]
            if (analysis["result"] == "first_error_found") != (analysis["first_error"] is not None):
                raise ValueError("Checker error/result mismatch")
            if len(set(analysis["photo_indices"])) != len(analysis["photo_indices"]):
                raise ValueError("Duplicate photo index")
            indices = analysis["photo_indices"]
            if any(e["photo_index"] not in indices for e in analysis["evidence"]):
                raise ValueError("Evidence photo outside task")
            if analysis["first_error"] and analysis["first_error"]["photo_index"] not in indices:
                raise ValueError("Error photo outside task")


def validate_pair(snapshot: dict, result: dict) -> None:
    """Reject structural/arithmetic/reference errors; never repair model output.

    Mathematical-rule grouping still requires semantic quality assessment.
    This computes only invariants to check an LLM result, not a replacement
    analytics implementation or deterministic rule classifier.
    """
    validate_input(snapshot)
    _validator("result.schema.json").validate(result)
    counts = dict(total=len(snapshot["notebooks"]), with_errors=0, without_errors=0, partial=0, empty=0)
    numerator = 0
    incomplete = disputed = unassessed = 0
    eligible_errors: set[str] = set()
    for notebook in snapshot["notebooks"]:
        tasks = notebook["tasks"]
        confirmed = [t for t in tasks if t["review_state"] == "confirmed" and t["analysis"]["result"] != "not_assessed"]
        errors = [t for t in confirmed if t["analysis"]["result"] == "first_error_found"]
        eligible_errors.update(t["task_id"] for t in errors)
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
    if result["notebooks"] != counts:
        raise ValueError("Notebook counts do not match snapshot")
    denominator = counts["with_errors"] + counts["without_errors"]
    average = result["average_errors_per_notebook"]
    if denominator == 0:
        if average is not None:
            raise ValueError("Undefined average must be null")
    elif average is None or not 0 <= average <= numerator or not math.isfinite(average) or not math.isclose(average, numerator / denominator, rel_tol=0, abs_tol=1e-6):
        raise ValueError("Wrong average denominator or numerator")
    for key, expected in (("incomplete_tasks", incomplete), ("disputed_tasks", disputed), ("unassessed_tasks", unassessed)):
        if result[key] != expected:
            raise ValueError(f"Wrong {key}")
    seen: set[str] = set()
    previous_size = math.inf
    for group in result["top_errors"]:
        ids = set(group["task_ids"])
        if not ids <= eligible_errors or ids & seen:
            raise ValueError("Invalid or duplicate top-error task reference")
        if len(ids) > previous_size:
            raise ValueError("Top errors are not ordered by frequency")
        previous_size = len(ids)
        seen.update(ids)
    if bool(eligible_errors) != bool(result["top_errors"]):
        raise ValueError("Top must be empty exactly when no confirmed errors exist")
    if len(eligible_errors) <= 3 and seen != eligible_errors:
        raise ValueError("Small error set must be fully represented")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate saved class-summary fixtures offline")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if bool(args.snapshot) != bool(args.result):
        parser.error("--snapshot and --result must be supplied together")
    if args.snapshot:
        validate_pair(load(args.snapshot), load(args.result))
        print("PASS analytics snapshot/result")
    else:
        manifest = load(HERE / "fixtures" / "manifest.json")
        for case in manifest["cases"]:
            validate_pair(load(HERE / "fixtures" / case["input"]), load(HERE / "fixtures" / case["result"]))
        print(f"PASS {len(manifest['cases'])} analytics fixture pairs; no API calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
