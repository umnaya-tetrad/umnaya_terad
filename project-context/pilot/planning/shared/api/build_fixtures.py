"""Build portable synthetic HTTP examples and lifecycle snapshots, never live calls."""
import copy
import json
import uuid
from pathlib import Path

from build_contract import ROOT, PATHS, write


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "urn:smartnote:synthetic:" + name))


def ident(kind):
    return uid(kind)


def mutation(entity=None, job=None, revision=12):
    return {"check_id": ident("check"), "check_revision": revision, "entity_id": entity, "job": job}


def job(state="queued", reason=None, kind="page_check", name="job", can_retry=False):
    return {"id": ident(name), "kind": kind, "input_id": ident("snapshot" if kind == "class_analytics" else "input"),
            "state": state, "reason": reason, "can_retry": can_retry}


def summary(state="not_started", stale=False, result=None, can_refresh=False):
    started = state != "not_started"
    return {"state": state, "stale": stale, "snapshot_id": ident("snapshot") if started else None,
            "job_id": ident("analytics-job") if started else None, "data_revision": 5 if started else None,
            "can_retry": state == "failed" and not stale, "can_refresh": can_refresh, "result": result}


def complete(**values):
    base = dict(pending_jobs=0, unreviewed_tasks=0, unresolved_tasks=0, unresolved_bundles=0, unsent_drafts=0, can_finalize=False)
    base.update(values)
    return base


def task(analysis, index, state=None, skipped=False):
    return {"task_id": ident("task-" + str(index)), "analysis_id": ident("analysis-" + str(index)),
            "analysis": copy.deepcopy(analysis), "review": None if state is None else {"state": state, "comment": ""}, "skipped": skipped}


EXAMPLES = ROOT.parents[2] / "ai/examples"
MULTI = json.loads((EXAMPLES / "E_C01.response.json").read_text(encoding="utf-8"))
CONTINUATION = json.loads((EXAMPLES / "M06.response.json").read_text(encoding="utf-8"))
# Pick by content rather than depending on informal fixture names.
for source in sorted(EXAMPLES.glob("*.response.json")):
    value = json.loads(source.read_text(encoding="utf-8"))
    if len(value["tasks"]) > 1 and any(len(t["photo_indices"]) > 1 for t in value["tasks"]):
        CONTINUATION = value
    if len(value["tasks"]) > 1 and all(t["photo_indices"] == [1] for t in value["tasks"]):
        MULTI = value
PHOTOS = [{"id": ident("photo-1"), "media_type": "image/jpeg"}, {"id": ident("photo-2"), "media_type": "image/jpeg"}]
SEALED = {"id": ident("input"), "state": "sealed", "photos": PHOTOS[:1]}
DRAFT = {"id": ident("draft"), "state": "draft", "photos": []}
BUNDLE = {"id": ident("bundle"), "draft": None, "current_input": SEALED, "job": job("succeeded"),
          "result": {"id": ident("generation"), "input_version_id": SEALED["id"], "report": MULTI},
          "tasks": [task(value, index, "confirmed") for index, value in enumerate(MULTI["tasks"])], "skipped": False}
CHECK = {"id": ident("check"), "title": "Синтетическая проверка", "phase": "review", "revision": 12,
         "created_at": "2026-11-19T10:00:00Z", "data_revision": 5,
         "notebooks": [{"id": ident("notebook"), "number": 1, "bundles": [BUNDLE]}],
         "completion": complete(can_finalize=True), "summary": summary()}
LIST_ITEM = {key: CHECK[key] for key in ("id", "title", "phase", "revision", "created_at")}
RESULT = {"schema_version": "class-summary/1", "notebooks": {"total": 1, "with_errors": 1, "without_errors": 0, "partial": 0, "empty": 0},
          "average_errors_per_notebook": 1, "incomplete_tasks": 0, "disputed_tasks": 0, "unassessed_tasks": 0,
          "top_errors": [{"rule": "Знак при разложении на множители", "task_ids": [BUNDLE["tasks"][0]["task_id"]]}]}
HISTORY = {"bundle_id": ident("bundle"), "versions": [{"input": SEALED, "runs": [
    {"job": job("succeeded"), "result": copy.deepcopy(BUNDLE["result"]), "tasks": copy.deepcopy(BUNDLE["tasks"]),
     "deleted_task_ids": [BUNDLE["tasks"][1]["task_id"]]},
    {"job": job("succeeded", name="same-input-retry-job"),
     "result": {"id": ident("same-input-retry-report"), "input_version_id": SEALED["id"], "report": copy.deepcopy(MULTI)},
     "tasks": [task(value, "retry-" + str(index), "system_error" if index == 0 else "confirmed")
               for index, value in enumerate(MULTI["tasks"])], "deleted_task_ids": []}]}]}
HISTORY["versions"][0]["runs"][1]["result"]["report"]["message"] = "Синтетический повтор того же входа; новое поколение и отдельные отзывы."
RESPONSES = {"Session": {"user_id": ident("teacher"), "role": "teacher"}, "Check": CHECK,
             "Checks": {"items": [LIST_ITEM], "next_cursor": None}, "Mutation": mutation(), "Job": job(),
             "Summary": summary("succeeded", result=RESULT), "BundleHistory": HISTORY,
             "SummaryHistory": {"items": [{"created_at": "2026-11-19T10:02:00Z", "summary": summary("succeeded", result=RESULT)}]},
             "EventsAccepted": {"accepted_ids": [ident("event")]}}
RESPONSES["StaffChecks"] = {"items": [{"owner": {"user_id": ident("teacher"), "login": "synthetic_teacher"}, "check": LIST_ITEM}], "next_cursor": None}
RESPONSES["StaffCheck"] = {"owner": {"user_id": ident("teacher"), "login": "synthetic_teacher"}, "check": CHECK}
REQUESTS = {"Login": {"login": "synthetic_teacher", "password": "synthetic-fixture-only"},
            "Title": {"title": "Проверка алгебры"},
            "VersionCreate": {"photo_ids": [ident("photo-1")]}, "PhotoOrder": {"photo_ids": [p["id"] for p in PHOTOS]},
            "Submit": {"input_version_id": ident("draft")}, "InputTarget": {"input_version_id": ident("input")},
            "AnalysisTarget": {"analysis_id": ident("analysis-0")}, "ReviewWrite": {"analysis_id": ident("analysis-0"), "state": "confirmed", "comment": ""},
            "Events": {"events": [{"id": ident("event"), "session_id": ident("client-session"),
                "occurred_at": "2026-11-19T10:00:00Z", "name": "result_opened", "check_id": ident("check"), "entity_id": ident("task-0")}]}}


def http_fixtures():
    result = []
    for path, methods in PATHS.items():
        for method, operation in methods.items():
            opname = operation["operationId"]
            response_code = next(code for code in operation["responses"] if int(code) < 300)
            parameters = {param["name"]: ident(param["name"].replace("_id", "")) for param in operation.get("parameters", []) if param["in"] == "path"}
            headers = {"If-Match": '"11"', "Idempotency-Key": ident("intent-" + opname)} if any(p["name"] == "If-Match" for p in operation.get("parameters", [])) else {}
            if opname == "createCheck":
                headers["Idempotency-Key"] = ident("intent-create-check")
            request_body = None
            if "requestBody" in operation:
                content = operation["requestBody"]["content"]
                if "application/json" in content:
                    name = content["application/json"]["schema"]["$ref"].split("/")[-1]
                    request_body = copy.deepcopy(REQUESTS[name])
                else:
                    # Binary multipart parts are described by local fixtures, not base64 fields in the production API.
                    request_body = {"file": "synthetic-photo.png"}
            schema = operation["responses"][response_code].get("content", {}).get("application/json", {}).get("schema")
            response_body = copy.deepcopy(RESPONSES[schema["$ref"].split("/")[-1]]) if schema else None
            if schema and schema["$ref"].endswith("/Mutation"):
                entity_kind = {"createNotebook": "notebook", "deleteNotebook": "notebook",
                               "createBundle": "bundle", "deleteBundle": "bundle", "createInputVersion": "draft", "reorderPhotos": "draft",
                               "discardDraft": "draft", "uploadPhoto": "photo", "deleteDraftPhoto": "photo", "submitBundle": "bundle",
                               "retryBundle": "bundle", "skipBundle": "bundle", "deleteTask": "task", "saveReview": "task", "skipTask": "task"}.get(opname)
                response_body["entity_id"] = ident(entity_kind) if entity_kind else None
                if int(response_code) == 202:
                    response_body["job"] = job(kind="class_analytics", name="analytics-job") if opname in ("finalizeCheck", "refreshSummary", "retrySummary") else job()
                    if opname == "refreshSummary":
                        response_body["job"].update(id=ident("analytics-refresh-job"), input_id=ident("snapshot-refreshed"))
                    if opname == "retrySummary":
                        response_body["job"]["id"] = ident("analytics-retry-job")
            response_headers = {"ETag": '"12"'} if opname in ("getCheck", "getStaffCheck") else {}
            if opname == "getPhoto":
                response_headers["Content-Type"] = "image/png"
            result.append({"name": opname, "operation_id": opname, "path_parameters": parameters,
                           "request": {"headers": headers, "body": request_body},
                           "response": {"status": int(response_code), "headers": response_headers, "body": response_body}})
    for name, operation, status, code in [
        ("foreign-account", "getCheck", 404, "not_found"),
        ("unauthenticated-photo", "getPhoto", 401, "unauthenticated"),
        ("teacher-cannot-read-history", "getBundleHistory", 403, "forbidden"),
        ("bad-photo", "uploadPhoto", 422, "invalid_input"),
        ("review-conflict", "saveReview", 409, "revision_conflict"),
        ("finalize-pending", "finalizeCheck", 409, "completion_blocked"),
        ("finalized-composition", "deleteTask", 409, "invalid_state"),
        ("same-key-different-payload", "submitBundle", 409, "idempotency_conflict"),
        ("stale-analysis", "saveReview", 409, "stale_analysis")]:
        item = copy.deepcopy(next(item for item in result if item["name"] == operation))
        item["name"] = name
        item["response"] = {"status": status, "headers": {}, "body": {"error": {"code": code, "message": "Синтетический безопасный отказ", "current_revision": 12 if status == 409 else None}}}
        result.append(item)
    repeated = copy.deepcopy(next(item for item in result if item["name"] == "submitBundle"))
    repeated["name"] = "submit-response-lost-replay"
    result.append(repeated)
    return result


def variants():
    checks = {"multi-task-confirmed": copy.deepcopy(CHECK)}
    cont = copy.deepcopy(CHECK)
    bundle = cont["notebooks"][0]["bundles"][0]
    bundle["current_input"]["photos"] = copy.deepcopy(PHOTOS)
    bundle["result"]["report"] = copy.deepcopy(CONTINUATION)
    bundle["tasks"] = [task(t, i, "confirmed") for i, t in enumerate(CONTINUATION["tasks"])]
    checks["two-photo-continuation"] = cont
    mixed = copy.deepcopy(CHECK)
    bundle = mixed["notebooks"][0]["bundles"][0]
    unassessed = copy.deepcopy(bundle["tasks"][1]["analysis"])
    unassessed.update(result="not_assessed", completeness="unknown", detail_level="unknown", evidence=[], first_error=None,
                      uncheckable_reason="Синтетически не хватает условия")
    bundle["result"]["report"]["tasks"][1] = copy.deepcopy(unassessed)
    bundle["tasks"][1] = task(unassessed, 1, skipped=True)
    checks["mixed-skip-only-one-task"] = mixed
    red = copy.deepcopy(CHECK)
    red["notebooks"][0]["bundles"][0]["tasks"][1]["review"] = {"state": "system_error", "comment": "Ошибка распознавания"}
    checks["red-resolves-review-excluded-from-math"] = red
    pending = copy.deepcopy(CHECK)
    bundle = pending["notebooks"][0]["bundles"][0]
    bundle.update(job=job(), result=None, tasks=[])
    pending["completion"] = complete(pending_jobs=1)
    checks["completion-waits-checker"] = pending
    for name, job_state, reason in (("failed", "failed", "temporary_failure"), ("unknown", "unknown", "provider_outcome_unknown"), ("blocked", "blocked", "funds_unavailable")):
        value = copy.deepcopy(pending)
        value["notebooks"][0]["bundles"][0]["job"] = job(job_state, reason, can_retry=job_state == "failed")
        value["completion"] = complete(unresolved_bundles=1) if job_state == "failed" else complete(pending_jobs=1)
        checks[name + "-input-no-false-zero"] = value
    skipped = copy.deepcopy(checks["failed-input-no-false-zero"])
    skipped["notebooks"][0]["bundles"][0]["skipped"] = True
    skipped["completion"] = complete(can_finalize=True)
    checks["skipped-failed-bundle-stays-partial"] = skipped
    unknown_skipped = copy.deepcopy(skipped)
    unknown_skipped["notebooks"][0]["bundles"][0]["job"] = job("cancelled", "skipped")
    checks["skipped-unknown-attempt-reserve-retained"] = unknown_skipped
    uncheckable = copy.deepcopy(skipped)
    bundle = uncheckable["notebooks"][0]["bundles"][0]
    bundle["job"] = job("succeeded", "input_uncheckable")
    bundle["result"] = {"id": ident("uncheckable-report"), "input_version_id": ident("input"),
                        "report": {"schema_version": "page-check/1.2", "status": "uncheckable", "tasks": [], "message": "Нечитаемое синтетическое фото"}}
    checks["uncheckable-skipped-input"] = uncheckable
    draft = copy.deepcopy(CHECK)
    draft["notebooks"][0]["bundles"][0]["draft"] = {"id": ident("draft"), "state": "draft", "photos": copy.deepcopy(PHOTOS)}
    draft["completion"] = complete(unsent_drafts=1)
    checks["unsent-draft-blocks-finalize"] = draft
    finalized = copy.deepcopy(CHECK)
    finalized.update(phase="finalized", summary=summary("queued"))
    finalized["completion"]["can_finalize"] = False
    checks["finalize-queues-analytics"] = finalized
    old = copy.deepcopy(finalized)
    old["summary"] = summary("succeeded", result=RESULT)
    checks["saved-analytics"] = old
    changed = copy.deepcopy(old)
    changed.update(revision=13, data_revision=6)
    changed["summary"]["stale"] = True
    changed["summary"]["can_refresh"] = True
    changed["notebooks"][0]["bundles"][0]["tasks"][0]["review"] = {"state": "system_error", "comment": "Измененная оценка"}
    checks["review-change-stales-analytics"] = changed
    for state in ("queued", "blocked", "running", "retry_wait", "unknown", "failed"):
        value = copy.deepcopy(changed)
        value["summary"] = summary(state, stale=True, can_refresh=state in ("queued", "blocked", "failed"))
        checks["stale-analytics-" + state] = value
    failed_fresh = copy.deepcopy(finalized)
    failed_fresh["summary"] = summary("failed")
    checks["fresh-failed-analytics-can-retry"] = failed_fresh
    comment = copy.deepcopy(old)
    comment["revision"] += 1
    comment["notebooks"][0]["bundles"][0]["tasks"][0]["review"]["comment"] = "Изменен только комментарий"
    checks["comment-keeps-analytics-current"] = comment
    # 2 -> 3 generation replacement: no identity mapping and no review inheritance.
    replaced = copy.deepcopy(CHECK)
    replaced.update(revision=14, data_revision=7)
    bundle = replaced["notebooks"][0]["bundles"][0]
    bundle["current_input"]["id"] = ident("input-v2")
    bundle["job"]["id"] = ident("job-v2")
    bundle["job"]["input_id"] = ident("input-v2")
    bundle["result"]["id"] = ident("generation-v2")
    bundle["result"]["input_version_id"] = ident("input-v2")
    bundle["result"]["report"]["tasks"].append(copy.deepcopy(MULTI["tasks"][1]))
    bundle["result"]["report"]["tasks"][2]["task_id"] = "synthetic-task-3"
    bundle["tasks"] = [task(t, "v2-" + str(i)) for i, t in enumerate(bundle["result"]["report"]["tasks"])]
    replaced["completion"] = complete(unreviewed_tasks=3)
    checks["new-segmentation-two-to-three"] = replaced
    deleted = copy.deepcopy(CHECK)
    deleted.update(revision=13, data_revision=6)
    deleted["notebooks"][0]["bundles"][0]["tasks"].pop(0)
    checks["task-deleted-report-retained"] = deleted
    return checks


def summary_guards():
    cases = []
    for phase, stale, state, has_provider_attempt, declared_safe in (
        ("finalized", True, "queued", False, False), ("finalized", True, "blocked", False, False),
        ("finalized", True, "queued", True, False), ("finalized", True, "blocked", True, False),
        ("finalized", True, "running", True, False), ("finalized", True, "retry_wait", True, False),
        ("finalized", True, "unknown", True, False), ("finalized", True, "failed", False, True),
        ("finalized", True, "succeeded", True, True), ("finalized", False, "failed", False, True),
        ("finalized", False, "failed", True, False), ("finalized", False, "blocked", False, True),
        ("review", True, "queued", False, False), ("finalized", False, "succeeded", True, True)):
        can_refresh = phase == "finalized" and stale and (state in ("succeeded", "failed", "cancelled", "superseded") or (state in ("queued", "blocked") and not has_provider_attempt))
        can_retry = phase == "finalized" and not stale and state == "failed" and declared_safe
        cases.append(dict(phase=phase, stale=stale, state=state, has_provider_attempt=has_provider_attempt,
                          declared_safe=declared_safe, can_refresh=can_refresh, can_retry=can_retry))
    return cases


if __name__ == "__main__":
    write(ROOT / "fixtures/http.json", http_fixtures())
    write(ROOT / "fixtures/lifecycle.json", variants())
    write(ROOT / "fixtures/summary-guards.json", summary_guards())
    write(ROOT / "fixtures/ids.json", {key: ident(key) for key in ("teacher", "check", "notebook", "bundle", "input", "snapshot", "job")})
    # Empty synthetic HTTP/mock input, not a mathematical example. Meets frozen adapter edge>=32.
    import struct
    import zlib
    def png_chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    image = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
    image += png_chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\xff\xff" * 64) * 64)) + png_chunk(b"IEND", b"")
    (ROOT / "fixtures/synthetic-photo.png").write_bytes(image)
    print("Wrote synthetic HTTP fixtures and lifecycle snapshots")
