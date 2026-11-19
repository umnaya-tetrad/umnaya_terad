"""Offline validation of OpenAPI, JSON Schemas, frozen examples and HTTP fixtures.

This verifies the contract package. It is not a test of an implemented HTTP server.
All reference retrieval is confined to this repository; no HTTP resolver is used.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[4]
DOMAIN_PATH = ROOT / "schemas/domain.schema.json"
OPENAPI_PATH = ROOT / "openapi.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def retrieve(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        raise ValueError("Network and unknown URI schemes are forbidden: " + uri)
    path = Path(url2pathname(unquote(parsed.path))).resolve()
    if path != REPO and REPO not in path.parents:
        raise ValueError("Reference outside repository: " + str(path))
    return Resource.from_contents(read(path), default_specification=DRAFT202012)


def make_registry():
    registry = Registry(retrieve=retrieve)
    aliases = {"urn:smartnote:page-check:1.2": ROOT.parents[2] / "ai/response-schema-v1.2.json",
               "urn:smartnote:class-summary:1": ROOT.parent / "analytics/result.schema.json",
               "urn:smartnote:summary-input:1": ROOT.parent / "analytics/input.schema.json"}
    for alias, path in aliases.items():
        if path.is_file():
            registry = registry.with_resource(alias, Resource.from_contents(read(path), default_specification=DRAFT202012))
    return registry


REGISTRY = make_registry()


def validate(value, schema, base=None):
    validator = Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker(),
                                    _resolver=REGISTRY.resolver(base_uri=base or DOMAIN_PATH.as_uri()))
    validator.validate(value)


def domain(value, name):
    validate(value, {"$ref": DOMAIN_PATH.as_uri() + "#/$defs/" + name})


def dereference(value, resolver):
    if isinstance(value, list):
        return [dereference(item, resolver) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        target = resolver.lookup(value["$ref"])
        expanded = dereference(target.contents, target.resolver)
        # JSON Schema 2020-12 $ref siblings (descriptions) remain applicable.
        expanded.update({key: dereference(item, resolver) for key, item in value.items() if key not in ("$ref", "$id")})
        return expanded
    return {key: dereference(item, resolver) for key, item in value.items() if key != "$id"}


def validate_report(report, images):
    """Same semantic checks as frozen contract.validate_report, without changing it."""
    validate(report, {"$ref": (ROOT.parents[2] / "ai/response-schema-v1.2.json").as_uri()})
    for task in report["tasks"]:
        indices = task["photo_indices"]
        assert all(1 <= index <= images for index in indices), "photo index out of input"
        assert all(item["photo_index"] in indices for item in task["evidence"]), "evidence outside task"
        assert (task["result"] == "first_error_found") == (task["first_error"] is not None), "first_error/result mismatch"
        if task["first_error"]:
            assert task["first_error"]["photo_index"] in indices, "first error outside task"


def completion(check):
    values = dict(pending_jobs=0, unreviewed_tasks=0, unresolved_tasks=0, unresolved_bundles=0, unsent_drafts=0)
    has_input = False
    for notebook in check["notebooks"]:
        for bundle in notebook["bundles"]:
            values["unsent_drafts"] += int(bool(bundle["draft"] and bundle["draft"]["photos"]))
            if not bundle["current_input"]:
                continue
            has_input = True
            state = bundle["job"]["state"] if bundle["job"] else None
            if state in ("queued", "running", "retry_wait", "blocked", "unknown"):
                values["pending_jobs"] += 1
            report = bundle["result"]["report"] if bundle["result"] else None
            unresolved = state == "failed" or bundle["skipped"] or (report is not None and (report["status"] == "uncheckable" or not report["tasks"]))
            values["unresolved_bundles"] += int(unresolved and not bundle["skipped"])
            for task in bundle["tasks"]:
                if task["analysis"]["result"] == "not_assessed":
                    values["unresolved_tasks"] += int(not task["skipped"])
                else:
                    values["unreviewed_tasks"] += int(task["review"] is None)
    values["can_finalize"] = check["phase"] == "review" and has_input and not any(values.values())
    return values


def validate_check(check):
    domain(check, "Check")
    assert check["completion"] == completion(check), "completion differs from current active data"
    summary = check["summary"]
    assert summary["stale"] == (summary["snapshot_id"] is not None and summary["data_revision"] != check["data_revision"]), "incorrect summary freshness"
    assert (summary["state"] == "succeeded") == (summary["result"] is not None), "summary result/state mismatch"
    if summary["can_retry"]:
        assert check["phase"] == "finalized" and not summary["stale"] and summary["state"] == "failed", "unsafe summary retry"
    if summary["can_refresh"]:
        assert check["phase"] == "finalized" and summary["stale"] and summary["state"] in ("queued", "blocked", "succeeded", "failed", "cancelled", "superseded"), "unsafe summary refresh"
    if check["phase"] == "finalized" and summary["stale"] and summary["state"] in ("succeeded", "failed", "cancelled", "superseded"):
        assert summary["can_refresh"], "terminal stale summary must allow explicit refresh"
    task_ids, analysis_ids = set(), set()
    for notebook in check["notebooks"]:
        for bundle in notebook["bundles"]:
            current = bundle["current_input"]
            if current:
                assert current["state"] == "sealed"
                assert bundle["job"] and bundle["job"]["input_id"] == current["id"]
            if bundle["draft"]:
                assert bundle["draft"]["state"] == "draft"
                assert not current or bundle["draft"]["id"] != current["id"]
            if not bundle["result"]:
                assert not bundle["tasks"], "no analysis without published Report"
                continue
            assert current and bundle["result"]["input_version_id"] == current["id"]
            report = bundle["result"]["report"]
            validate_report(report, len(current["photos"]))
            for task in bundle["tasks"]:
                assert task["analysis"] in report["tasks"], "task does not belong to raw Report"
                assert task["task_id"] not in task_ids and task["analysis_id"] not in analysis_ids, "duplicate server IDs"
                task_ids.add(task["task_id"])
                analysis_ids.add(task["analysis_id"])
                if task["analysis"]["result"] == "not_assessed":
                    assert task["review"] is None, "unassessed is not mathematical confirmation"
                else:
                    assert not task["skipped"], "assessable task uses review, not skip"


def validate_history(history):
    domain(history, "BundleHistory")
    jobs, reports, task_ids, analysis_ids = set(), set(), set(), set()
    for version in history["versions"]:
        assert version["input"]["state"] == "sealed"
        for run in version["runs"]:
            assert run["job"]["id"] not in jobs and run["job"]["input_id"] == version["input"]["id"], "history generation/job mismatch"
            jobs.add(run["job"]["id"])
            if run["result"]:
                report = run["result"]
                assert report["id"] not in reports and report["input_version_id"] == version["input"]["id"], "history Report mismatch"
                reports.add(report["id"])
                validate_report(report["report"], len(version["input"]["photos"]))
                for task in run["tasks"]:
                    assert task["analysis"] in report["report"]["tasks"], "history task in wrong generation"
                    assert task["task_id"] not in task_ids and task["analysis_id"] not in analysis_ids, "history inherits old task IDs"
                    task_ids.add(task["task_id"])
                    analysis_ids.add(task["analysis_id"])
            else:
                assert not run["tasks"]
            assert set(run["deleted_task_ids"]) <= {task["task_id"] for task in run["tasks"]}, "tombstone in wrong generation"


def validate_png(path):
    import struct
    import zlib
    value = Path(path).read_bytes()
    assert value[:8] == b"\x89PNG\r\n\x1a\n", "not PNG"
    offset, raw_idat, dimensions, ended = 8, b"", None, False
    while offset < len(value):
        length = struct.unpack(">I", value[offset:offset + 4])[0]
        kind, payload = value[offset + 4:offset + 8], value[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", value[offset + 8 + length:offset + 12 + length])[0]
        assert crc == zlib.crc32(kind + payload) & 0xffffffff, "PNG CRC mismatch"
        if kind == b"IHDR":
            dimensions = struct.unpack(">IIBBBBB", payload)
            assert min(dimensions[:2]) >= 32, "PNG below frozen adapter minimum edge"
        if kind == b"IDAT":
            raw_idat += payload
        if kind == b"IEND":
            ended = True
        offset += length + 12
    assert offset == len(value) and ended and dimensions
    width, height, depth, color, compression, filtering, interlace = dimensions
    assert (depth, color, compression, filtering, interlace) == (8, 2, 0, 0, 0)
    assert len(zlib.decompress(raw_idat)) == height * (1 + width * 3), "invalid PNG scanlines"
    return width, height


def validate_http(document):
    operations = {op["operationId"]: (path, method, op) for path, methods in document["paths"].items() for method, op in methods.items()}
    fixtures = read(ROOT / "fixtures/http.json")
    covered = set()
    for fixture in fixtures:
        path, method, operation = operations[fixture["operation_id"]]
        covered.add(fixture["operation_id"])
        for parameter in operation.get("parameters", []):
            if parameter["in"] == "path":
                validate(fixture["path_parameters"][parameter["name"]], parameter["schema"])
            if parameter["in"] == "header" and parameter.get("required"):
                validate(fixture["request"]["headers"][parameter["name"]], parameter["schema"])
        if "requestBody" in operation:
            content = operation["requestBody"]["content"]
            media = "application/json" if "application/json" in content else "multipart/form-data"
            validate(fixture["request"]["body"], content[media]["schema"], OPENAPI_PATH.as_uri())
            if media == "multipart/form-data":
                assert (ROOT / "fixtures" / fixture["request"]["body"]["file"]).is_file()
        status = str(fixture["response"]["status"])
        response = operation["responses"][status]
        if "application/json" in response.get("content", {}):
            validate(fixture["response"]["body"], response["content"]["application/json"]["schema"], OPENAPI_PATH.as_uri())
            if fixture["operation_id"] == "getBundleHistory" and status == "200":
                validate_history(fixture["response"]["body"])
        else:
            assert fixture["response"]["body"] is None
    assert covered == set(operations), "HTTP route without fixture"
    first = next(f for f in fixtures if f["name"] == "submitBundle")
    replay = next(f for f in fixtures if f["name"] == "submit-response-lost-replay")
    assert first["request"] == replay["request"] and first["response"] == replay["response"]
    return len(fixtures), len(operations)


def run():
    from openapi_spec_validator import validate as validate_openapi
    from build_contract import check_generated
    check_generated()
    document = read(OPENAPI_PATH)
    for path in sorted((ROOT / "schemas").glob("*.json")):
        Draft202012Validator.check_schema(read(path))
    # Formal OpenAPI 3.1 validation receives a fully local materialized document.
    validate_openapi(dereference(document, REGISTRY.resolver(base_uri=OPENAPI_PATH.as_uri())))
    count, routes = validate_http(document)
    validate_png(ROOT / "fixtures/synthetic-photo.png")
    snapshots = read(ROOT / "fixtures/lifecycle.json")
    for name, value in snapshots.items():
        try:
            validate_check(value)
        except Exception as error:
            raise AssertionError(name + ": " + str(error)) from error
    for path in sorted((ROOT.parents[2] / "ai/examples").glob("*.response.json")):
        report = read(path)
        count_photos = max(i for task in report["tasks"] for i in task["photo_indices"])
        validate_report(report, count_photos)
    print(f"PASS OpenAPI 3.1; {routes} operations; {count} HTTP fixtures; {len(snapshots)} lifecycle snapshots; frozen examples")


if __name__ == "__main__":
    run()
