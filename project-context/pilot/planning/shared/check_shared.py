"""Single offline gate for the shared specification, not a pilot-app smoke."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PILOT = HERE.parents[1]


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_artifacts():
    ai = PILOT / "ai"
    provenance = read(ai / "provenance.json")
    for key in ("prompt", "schema"):
        item = provenance[key]
        assert hashlib.sha256((ai / item["file"]).read_bytes()).hexdigest() == item["sha256"], key
    for item in read(ai / "examples/provenance.json")["examples"]:
        assert hashlib.sha256((ai / "examples" / item["file"]).read_bytes()).hexdigest() == item["sha256"], item["file"]
    print("PASS frozen checker prompt/schema and recorded dev examples", flush=True)


def ux_copy():
    data = read(HERE / "ux-copy.json")
    assert set(data) == {"locale", "messages", "placeholders"}
    assert data["locale"] == "ru-RU"
    messages = data["messages"]
    placeholders = data["placeholders"]
    assert messages and set(placeholders) <= set(messages)
    flow = (HERE / "ux-flows.md").read_text(encoding="utf-8")
    references = set(re.findall(r"`([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)`", flow))
    missing = set(messages) - references
    unknown = references - set(messages)
    # Dotted code paths/schema names are not copy identifiers. A copy reference
    # begins with one of the actual message namespaces.
    prefixes = {key.split(".")[0] for key in messages}
    unknown = {key for key in unknown if key.split(".")[0] in prefixes}
    assert not missing and not unknown, {"unused": sorted(missing), "unknown": sorted(unknown)}
    for key, message in messages.items():
        assert isinstance(message, str) and message.strip(), key
        actual = set(re.findall(r"\{([a-z][a-z0-9_]*)\}", message))
        declared = set(placeholders.get(key, {}))
        assert actual == declared, (key, actual, declared)
    print(f"PASS {len(messages)} UX strings, flow references and placeholders", flush=True)


def run(relative: str, *args: str):
    subprocess.run([sys.executable, str(HERE / relative), *args], cwd=REPO, check=True)


def main():
    frozen_artifacts()
    ux_copy()
    run("api/validate.py")
    run("analytics/validate.py")
    subprocess.run([sys.executable, "-m", "pytest", str(HERE / "api/tests"), str(HERE / "analytics/tests"), "-q"], cwd=REPO, check=True)
    print("PASS shared-spec gate; no live LLM/server/app acceptance performed", flush=True)


if __name__ == "__main__":
    main()
