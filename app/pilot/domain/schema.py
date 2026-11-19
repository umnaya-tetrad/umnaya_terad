"""Runtime validation of unchanged closed shared DTOs with local-only refs."""

import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from .errors import DomainError

ROOT = Path(__file__).parent / "assets"
SCHEMA = json.loads((ROOT / "domain.schema.json").read_text(encoding="utf-8"))


# The published schema uses repository-relative file references. Runtime assets
# retain their exact bytes; only their resolution base is mapped to local URNs.
def _local_refs(value):
    if isinstance(value, list):
        return [_local_refs(x) for x in value]
    if not isinstance(value, dict):
        return value
    out = {k: _local_refs(v) for k, v in value.items()}
    if "$ref" in out:
        out["$ref"] = (
            out["$ref"]
            .replace(
                "../../../../ai/response-schema-v1.2.json",
                "urn:smartnote:page-check:1.2",
            )
            .replace(
                "../../analytics/result.schema.json", "urn:smartnote:class-summary:1"
            )
        )
    return out


SCHEMA = _local_refs(SCHEMA)
SCHEMA["$id"] = "urn:smartnote:domain:1"
REGISTRY = Registry()
for alias, name in [
    ("urn:smartnote:page-check:1.2", "checker.schema.json"),
    ("urn:smartnote:class-summary:1", "summary.schema.json"),
]:
    REGISTRY = REGISTRY.with_resource(
        alias,
        Resource.from_contents(
            json.loads((ROOT / name).read_text(encoding="utf-8")),
            default_specification=DRAFT202012,
        ),
    )
REGISTRY = REGISTRY.with_resource(SCHEMA["$id"], Resource.from_contents(SCHEMA))


def validate(value, name):
    try:
        Draft202012Validator(
            {"$ref": SCHEMA["$id"] + "#/$defs/" + name},
            registry=REGISTRY,
            format_checker=FormatChecker(),
        ).validate(value)
    except ValidationError as e:
        raise DomainError(422, "invalid_input", "Некорректные данные запроса.") from e
    return value
