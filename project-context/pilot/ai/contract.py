"""Frozen page-check/1.2 contract; validation bounds stay local."""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Strict):
    photo_index: int = Field(ge=1)
    latex: str


class Error(Strict):
    photo_index: int = Field(ge=1)
    wrong_latex: str
    rule: str
    explanation: str
    corrected_latex: str


class Task(Strict):
    task_id: str
    locator: str
    photo_indices: list[int] = Field(min_length=1)
    condition: str
    result: Literal["all_steps_correct", "first_error_found", "not_assessed"]
    completeness: Literal["complete", "incomplete", "unknown"]
    detail_level: Literal["sufficient", "omitted_steps", "partial", "unknown"]
    omitted_steps_note: str
    completeness_note: str
    evidence: list[Evidence] = Field(max_length=4)
    first_error: Error | None
    uncheckable_reason: str

    @model_validator(mode="after")
    def consistent(self):
        if (self.result == "first_error_found") != (self.first_error is not None):
            raise ValueError("First error/result mismatch")
        return self


class Report(Strict):
    schema_version: Literal["page-check/1.2"]
    status: Literal["ok", "uncheckable"]
    tasks: list[Task]
    message: str


def indexed_schema(schema: dict, images: int) -> dict:
    """Use the request's 1-based photo numbers, exactly as in the benchmark."""
    if isinstance(images, bool) or not isinstance(images, int) or images < 1:
        raise ValueError("At least one photo is required")
    result = copy.deepcopy(schema)

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if "const" in value:
                value["enum"] = [value.pop("const")]
            properties = value.get("properties", {})
            if "photo_index" in properties:
                properties["photo_index"]["enum"] = list(range(1, images + 1))
            if "photo_indices" in properties:
                properties["photo_indices"]["items"]["enum"] = list(range(1, images + 1))
            for item in value.values():
                visit(item)

    visit(result)
    return result


def provider_schema(schema: Any) -> Any:
    """Wire superset: keep shape/enums, validate lengths/numbers locally."""
    omitted = {
        "title", "description", "default", "minLength", "maxLength", "pattern",
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        "minItems", "maxItems", "format",
    }
    if isinstance(schema, list):
        return [provider_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    return {key: provider_schema(value) for key, value in schema.items() if key not in omitted}


def validate_report(value: Any, image_count: int) -> Report:
    report = Report.model_validate(value, strict=True)
    for task in report.tasks:
        if any(index < 1 or index > image_count for index in task.photo_indices):
            raise ValueError("Invalid photo index")
        if any(item.photo_index not in task.photo_indices for item in task.evidence):
            raise ValueError("Evidence photo outside task")
        if task.first_error and task.first_error.photo_index not in task.photo_indices:
            raise ValueError("Error photo outside task")
    return report
