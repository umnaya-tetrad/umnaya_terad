"""Static gate for the three task specifications; never runs the future app."""
from __future__ import annotations

import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
STREAMS = {"application": "APP", "processing": "PROC", "release": "REL"}


def definitions(text: str, prefix: str) -> list[str]:
    return re.findall(r"^#{2,4}\s+(" + re.escape(prefix) + r"\d{2})(?=[.\s:–—-]|$)", text, re.MULTILINE)


def references(text: str, prefix: str) -> set[str]:
    # A linked range [REL-C01](...)–[REL-C28](...) has the same meaning as
    # REL-C01–REL-C28; do not mistake its middle cases for unassigned work.
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    found = set(re.findall(r"\b" + re.escape(prefix) + r"\d{2}\b", text))
    # Allow explicit compact ranges as well as individual case references.
    pattern = re.escape(prefix) + r"(\d{2})\s*[–—-]\s*(?:" + re.escape(prefix) + r")?(\d{2})"
    for start, end in re.findall(pattern, text):
        found.update(prefix + f"{value:02d}" for value in range(int(start), int(end) + 1))
    return found


def main():
    all_requirements: set[str] = set()
    totals = [0, 0]
    for stream, tag in STREAMS.items():
        folder = HERE / stream
        content = {}
        for name in ("README.md", "TASKS.md", "ACCEPTANCE.md", "HANDOFF.md"):
            content[name] = (folder / name).read_text(encoding="utf-8")
            assert content[name].strip(), (stream, name)
        tasks = definitions(content["TASKS.md"], tag + "-")
        cases = definitions(content["ACCEPTANCE.md"], tag + "-C")
        assert tasks and len(tasks) == len(set(tasks)), (stream, "missing/duplicate task IDs")
        assert cases and len(cases) == len(set(cases)), (stream, "missing/duplicate case IDs")
        task_refs = references(content["TASKS.md"], tag + "-C")
        assert task_refs <= set(cases), (stream, "undefined acceptance cases", task_refs - set(cases))
        assert set(cases) <= task_refs, (stream, "unassigned acceptance cases", set(cases) - task_refs)
        assert "planned" in content["HANDOFF.md"].lower(), (stream, "handoff must state planned implementation")
        assert "not_run" in content["HANDOFF.md"].lower(), (stream, "runtime proof must remain not_run")
        sections = re.split(r"(?=^#{2,4}\s+" + tag + r"-\d{2}[.\s:–—-])", content["TASKS.md"], flags=re.MULTILINE)[1:]
        for section in sections:
            assert any(word in section.lower() for word in ("dod", "definition of done")), (stream, section[:100], "missing DoD")
            assert references(section, tag + "-C"), (stream, section[:100], "missing case reference")
        joined = "\n".join(content.values())
        all_requirements.update(re.findall(r"\bA\d{2}\b", joined))
        for private_phrase in ("человек один", "человек два", "человек три", "50% работы", "25% работы", "критическое мышление", "производительность участника"):
            assert private_phrase not in joined.lower(), (stream, "private participant detail")
        totals[0] += len(tasks)
        totals[1] += len(cases)
        print(f"PASS {stream}: {len(tasks)} tasks, {len(cases)} linked acceptance cases, planned/not_run handoff")
    required = {f"A{i:02d}" for i in range(1, 26)}
    assert required <= all_requirements, ("Unassigned requirements", required - all_requirements)
    api = json.loads((HERE / "shared/api/openapi.json").read_text(encoding="utf-8"))
    operation_ids = {op["operationId"] for path in api["paths"].values() for method, op in path.items() if method in {"get", "post", "put", "patch", "delete"}}
    application_cases = (HERE / "application/ACCEPTANCE.md").read_text(encoding="utf-8")
    assert all(operation in application_cases for operation in operation_ids), "Application surface table omits operation"
    print(f"PASS {totals[0]} tasks / {totals[1]} acceptance cases; A01–A25 and {len(operation_ids)} operation consumers covered")
    print("Scope: document integrity only; semantic review and future runtime acceptance are separate.")


if __name__ == "__main__":
    main()
