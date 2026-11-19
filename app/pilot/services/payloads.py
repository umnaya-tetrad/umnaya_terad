"""Validate raw HTTP bodies with the frozen wire schema before FastAPI coerces them."""
import json
from functools import cache
from pathlib import Path
from typing import Annotated

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BeforeValidator

from pilot.contracts import Login, PhotoOrder, ReviewWrite, Title, VersionCreate

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "project-context/pilot/planning/shared/api/schemas/domain.schema.json"
)


@cache
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema["$ref"] = f"#/$defs/{name}"
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate(name: str):
    def validate(payload):
        if not _validator(name).is_valid(payload):
            raise ValueError("Invalid request body")
        return payload
    return BeforeValidator(validate)


LoginBody = Annotated[Login, _validate("Login")]
TitleBody = Annotated[Title, _validate("Title")]
PhotoOrderBody = Annotated[PhotoOrder, _validate("PhotoOrder")]
VersionCreateBody = Annotated[VersionCreate, _validate("VersionCreate")]
ReviewBody = Annotated[ReviewWrite, _validate("ReviewWrite")]
