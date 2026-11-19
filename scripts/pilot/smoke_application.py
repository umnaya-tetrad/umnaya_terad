"""Smoke the local fixture Compose application with the shared synthetic photo."""
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_PHOTO = ROOT / "project-context/pilot/planning/shared/api/fixtures/synthetic-photo.png"
ORIGIN = "http://127.0.0.1:5173"


def fixture_backend():
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "exec", "-T", "backend", "printenv", "PILOT_TRANSPORT"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode or result.stdout.strip() != "fixture":
        raise SystemExit("Start the local Compose stack with PILOT_TRANSPORT=fixture.")


def main():
    fixture_backend()
    login = os.getenv("PILOT_FIXTURE_TEACHER_1_LOGIN")
    password = os.getenv("PILOT_FIXTURE_TEACHER_1_PASSWORD")
    if not login or not password:
        raise SystemExit("Set the fixture teacher login and password in this process environment.")
    api = build_opener(HTTPCookieProcessor(CookieJar()))

    def call(method, path, status, payload=None, revision=None, mutate=False, photo=False, key=None):
        headers = {"Origin": ORIGIN}
        body = None
        if mutate:
            headers["Idempotency-Key"] = key or str(uuid4())
        if revision is not None:
            headers["If-Match"] = f'"{revision}"'
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if photo:
            boundary = uuid4().hex
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            body = (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"synthetic.png\"\r\n"
                "Content-Type: image/png\r\n\r\n"
            ).encode() + SYNTHETIC_PHOTO.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        request = Request(ORIGIN + "/api" + path, data=body, headers=headers, method=method)
        try:
            with api.open(request, timeout=15) as response:
                if response.status != status:
                    raise RuntimeError(f"{method} {path} returned {response.status}; expected {status}")
                return json.load(response) if status != 204 else None
        except HTTPError as exc:
            raise RuntimeError(f"{method} {path} returned {exc.code}; expected {status}") from None

    def wait_for(read, ready, label):
        cutoff = time.monotonic() + 60
        while time.monotonic() < cutoff:
            value = read()
            if ready(value):
                return value
            time.sleep(1)
        raise RuntimeError(f"Timed out waiting for {label}")

    call("POST", "/auth/login", 200, {"login": login, "password": password})
    created = call("POST", "/checks", 201, {"title": "Приёмка fixture"}, mutate=True)
    check = f"/checks/{created['check_id']}"
    for _ in range(2):
        current = call("GET", check, 200)
        notebook = call("POST", f"{check}/notebooks", 201, revision=current["revision"], mutate=True)
        notebook_id = notebook["entity_id"]
        bundle = call("POST", f"/notebooks/{notebook_id}/bundles", 201, revision=notebook["check_revision"], mutate=True)
        current = call("GET", check, 200)
        book = next(item for item in current["notebooks"] if item["id"] == notebook_id)
        draft = book["bundles"][0]["draft"]
        uploaded = call("POST", f"/input-versions/{draft['id']}/photos", 201,
                        revision=current["revision"], mutate=True, photo=True)
        submit_path = f"/bundles/{bundle['entity_id']}/submit"
        submit_payload = {"input_version_id": draft["id"]}
        submit_key = str(uuid4())
        submitted = call("POST", submit_path, 202, submit_payload,
                         revision=uploaded["check_revision"], mutate=True, key=submit_key)
        repeated = call("POST", submit_path, 202, submit_payload,
                        revision=uploaded["check_revision"], mutate=True, key=submit_key)
        if repeated != submitted:
            raise RuntimeError("Submit did not replay the original checker Job.")
        job_id = submitted["job"]["id"]
        wait_for(lambda: call("GET", f"/jobs/{job_id}", 200),
                 lambda value: value["state"] == "succeeded", "fixture checker")

    call("POST", "/auth/logout", 204)
    call("GET", "/auth/session", 401)
    call("POST", "/auth/login", 200, {"login": login, "password": password})
    current = call("GET", check, 200)
    if len(current["notebooks"]) != 2 or any(not book["bundles"][0]["tasks"] for book in current["notebooks"]):
        raise RuntimeError("Both saved fixture reports must survive a new login.")
    task_list = [task for book in current["notebooks"] for task in book["bundles"][0]["tasks"]]
    assessable = next((task for task in task_list if task["analysis"]["result"] != "not_assessed"), None)
    if not assessable:
        raise RuntimeError("The fixture must yield a task suitable for testing review changes.")
    began = call("POST", f"{check}/begin-completion", 200, revision=current["revision"], mutate=True)
    revision = began["check_revision"]
    for task in task_list:
        if task["analysis"]["result"] == "not_assessed":
            modified = call("POST", f"/tasks/{task['task_id']}/skip", 200, {"analysis_id": task["analysis_id"]},
                            revision=revision, mutate=True)
        else:
            modified = call("PUT", f"/tasks/{task['task_id']}/review", 200,
                            {"analysis_id": task["analysis_id"], "state": "confirmed", "comment": ""},
                            revision=revision, mutate=True)
        revision = modified["check_revision"]
    current = call("GET", check, 200)
    if not current["completion"]["can_finalize"]:
        raise RuntimeError("Fixture completion blockers were not resolved.")
    key = str(uuid4())
    finalized = call("POST", f"{check}/finalize", 202, revision=current["revision"], mutate=True, key=key)
    replay = call("POST", f"{check}/finalize", 202, revision=current["revision"], mutate=True, key=key)
    if replay != finalized:
        raise RuntimeError("Finalize did not replay the original AnalyticsJob.")
    summary = wait_for(lambda: call("GET", f"{check}/summary", 200),
                       lambda value: value["state"] == "succeeded", "saved fixture summary")
    if summary["result"] is None or summary["job_id"] != finalized["job"]["id"]:
        raise RuntimeError("The saved summary does not match the accepted AnalyticsJob.")

    current = call("GET", check, 200)
    review_path = f"/tasks/{assessable['task_id']}/review"
    review = {"analysis_id": assessable["analysis_id"], "state": "confirmed", "comment": "Fixture smoke"}
    commented = call("PUT", review_path, 200, review, revision=current["revision"], mutate=True)
    after_comment = call("GET", f"{check}/summary", 200)
    if after_comment["stale"] or after_comment["snapshot_id"] != summary["snapshot_id"]:
        raise RuntimeError("A comment-only change altered the current summary.")

    changed = call("PUT", review_path, 200, {**review, "state": "system_error"},
                   revision=commented["check_revision"], mutate=True)
    stale = call("GET", f"{check}/summary", 200)
    if not stale["stale"] or not stale["can_refresh"]:
        raise RuntimeError("The changed review did not allow refreshing the stale summary.")
    refreshed = call("POST", f"{check}/summary/refresh", 202, revision=changed["check_revision"], mutate=True)
    updated = wait_for(lambda: call("GET", f"{check}/summary", 200),
                       lambda value: value["state"] == "succeeded" and not value["stale"], "refreshed summary")
    if updated["snapshot_id"] == summary["snapshot_id"] or updated["job_id"] != refreshed["job"]["id"]:
        raise RuntimeError("Refresh did not create and publish a new summary snapshot.")
    call("POST", "/auth/logout", 204)
    print("PASS: two notebooks, submit replay, login recovery, finalize replay, saved summary, comment and state changes, refresh.")


if __name__ == "__main__":
    main()
