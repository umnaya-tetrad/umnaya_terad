"""A separate text-only request; never calls the photo checker builder."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..processing.checker_contract import provider_schema
from ..processing.transport import ProviderConfig, request_base
from .validation import validate_input

ASSETS = Path(__file__).resolve().parent / "assets"
PROMPT_VERSION = "class-summary-prompt/1"


def load_prompt() -> str:
    return (ASSETS / "prompt-v1.txt").read_text(encoding="utf-8")


def prompt_hash() -> str:
    return hashlib.sha256(load_prompt().encode("utf-8")).hexdigest()


def build_request(snapshot: dict, config: ProviderConfig) -> dict:
    validate_input(snapshot)
    schema = json.loads((ASSETS / "result.schema.json").read_text(encoding="utf-8"))
    # Provider dialect uses enum instead of const, as the frozen checker does.
    def wire(value):
        if isinstance(value, list):
            return [wire(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {("enum" if key == "const" else key): ([item] if key == "const" else wire(item))
                for key, item in value.items() if key not in {"$schema", "$id", "uniqueItems"}}
    return {**request_base(config), "messages": [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)},
    ], "response_format": {"type": "json_schema", "json_schema": {
        "name": "SmartNoteClassSummary", "strict": True, "schema": wire(provider_schema(schema)),
    }}}
