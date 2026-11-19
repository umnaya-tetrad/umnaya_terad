"""Smoke the local fixture Compose application with the shared synthetic photo."""
import argparse
from http.cookiejar import CookieJar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_PHOTO = ROOT / "project-context/pilot/planning/shared/api/fixtures/synthetic-photo.png"
MEDIA = ROOT / "src/pilot/__fixtures__/media"
ORIGIN = "http://127.0.0.1:5173"


def fixture_backend():
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "exec", "-T", "backend", "printenv", "PILOT_TRANSPORT"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode or result.stdout.strip() != "fixture":
        raise SystemExit("Start the local Compose stack with PILOT_TRANSPORT=fixture.")


def compose(*args):
    subprocess.run(["docker", "compose", "-f", "compose.yaml", *args], cwd=ROOT, check=True)


def check_composition(call):
    created = call("POST", "/checks", 201, {"title": "Порядок тетрадей fixture"}, mutate=True)
    check = f"/checks/{created['check_id']}"
    first_page = call("GET", "/checks?limit=1", 200)
    if not first_page["next_cursor"]:
        raise RuntimeError("Expected a second page of fixture checks.")
    next_page = call("GET", "/checks?" + urlencode({"limit": 1, "cursor": first_page["next_cursor"]}), 200)
    if not next_page["items"] or next_page["items"][0]["id"] == first_page["items"][0]["id"]:
        raise RuntimeError("History cursor repeated or omitted the next check.")

    first = call("POST", f"{check}/notebooks", 201, revision=created["check_revision"], mutate=True)
    second = call("POST", f"{check}/notebooks", 201, revision=first["check_revision"], mutate=True)
    stale = call("POST", f"{check}/notebooks", 409, revision=first["check_revision"], mutate=True)
    if stale["error"]["code"] != "revision_conflict" or stale["error"]["current_revision"] != second["check_revision"]:
        raise RuntimeError("A stale composition request did not report the current revision.")
    removed = call("DELETE", f"/notebooks/{first['entity_id']}", 200,
                   revision=second["check_revision"], mutate=True)
    third = call("POST", f"{check}/notebooks", 201, revision=removed["check_revision"], mutate=True)
    current = call("GET", check, 200)
    if [book["number"] for book in current["notebooks"]] != [2, 3]:
        raise RuntimeError("Deleting a notebook must not reuse its number.")
    draft_bundle = call("POST", f"/notebooks/{third['entity_id']}/bundles", 201,
                        revision=current["revision"], mutate=True)
    surviving = call("POST", f"/notebooks/{third['entity_id']}/bundles", 201,
                     revision=draft_bundle["check_revision"], mutate=True)
    current = call("GET", check, 200)
    draft = current["notebooks"][1]["bundles"][0]["draft"]
    call("POST", f"/bundles/{draft_bundle['entity_id']}/submit", 409, {"input_version_id": draft["id"]},
         revision=current["revision"], mutate=True)
    added = call("POST", f"/input-versions/{draft['id']}/photos", 201, revision=current["revision"], mutate=True,
                 photo=(SYNTHETIC_PHOTO.name, "image/png", SYNTHETIC_PHOTO.read_bytes()))
    discarded = call("DELETE", f"/input-versions/{draft['id']}", 200, revision=added["check_revision"], mutate=True)
    call("GET", f"/assets/{added['entity_id']}", 404)
    call("DELETE", f"/bundles/{draft_bundle['entity_id']}", 200,
         revision=discarded["check_revision"], mutate=True)
    current = call("GET", check, 200)
    if [bundle["id"] for bundle in current["notebooks"][1]["bundles"]] != [surviving["entity_id"]]:
        raise RuntimeError("Discard and delete must preserve the adjacent bundle.")
    call("DELETE", check, 200, revision=current["revision"], mutate=True)
    call("GET", check, 404)


def check_replacement(call, wait_for, check):
    current = call("GET", check, 200)
    first, second = (book["bundles"][0] for book in current["notebooks"])
    bundle = f"/bundles/{first['id']}"
    task = next(item for item in first["tasks"] if item["analysis"]["result"] != "not_assessed")
    reviewed = call("PUT", f"/tasks/{task['task_id']}/review", 200,
                    {"analysis_id": task["analysis_id"], "state": "confirmed", "comment": ""},
                    revision=current["revision"], mutate=True)
    photo_ids = [photo["id"] for photo in first["current_input"]["photos"]]
    candidate = call("POST", f"{bundle}/versions", 201, {"photo_ids": photo_ids},
                     revision=reviewed["check_revision"], mutate=True)
    discarded = call("DELETE", f"/input-versions/{candidate['entity_id']}", 200,
                     revision=candidate["check_revision"], mutate=True)
    unchanged = call("GET", check, 200)["notebooks"][0]["bundles"][0]
    if unchanged["current_input"] != first["current_input"] or not any(
        item["task_id"] == task["task_id"] and item["review"]["state"] == "confirmed"
        for item in unchanged["tasks"] if item["review"]
    ):
        raise RuntimeError("Discarding a replacement draft altered the accepted result or its review.")

    replacement = call("POST", f"{bundle}/versions", 201, {"photo_ids": photo_ids},
                       revision=discarded["check_revision"], mutate=True)
    job = call("POST", f"{bundle}/submit", 202, {"input_version_id": replacement["entity_id"]},
               revision=replacement["check_revision"], mutate=True)["job"]
    wait_for(lambda: call("GET", f"/jobs/{job['id']}", 200), lambda value: value["state"] == "succeeded", "replacement checker")
    current = call("GET", check, 200)
    updated, adjacent = (book["bundles"][0] for book in current["notebooks"])
    old_ids = {item["task_id"] for item in first["tasks"]}
    if (
        updated["current_input"]["id"] != replacement["entity_id"] or adjacent != second
        or any(item["task_id"] in old_ids or item["review"] for item in updated["tasks"])
    ):
        raise RuntimeError("Publishing the replacement did not isolate the new generation.")
    target, *remaining = updated["tasks"]
    call("DELETE", f"/tasks/{target['task_id']}", 200, revision=current["revision"], mutate=True)
    after_delete = call("GET", check, 200)["notebooks"][0]["bundles"][0]
    if after_delete["tasks"] != remaining or after_delete["current_input"] != updated["current_input"]:
        raise RuntimeError("Deleting a task altered the shared input or an adjacent task.")
    call("GET", f"/assets/{photo_ids[0]}", 200, asset_type="image/png")


def check_summary_retry(call, wait_for, check, review_path, review):
    current = call("GET", check, 200)
    reviewed = call("PUT", review_path, 200, review, revision=current["revision"], mutate=True)
    compose("stop", "worker")
    try:
        refreshed = call("POST", f"{check}/summary/refresh", 202, revision=reviewed["check_revision"], mutate=True)
        run_one = """
import asyncio
from pathlib import Path

import asyncpg
from config import get_settings
from pilot.domain.services import create_services
from pilot.processing.worker import run_once

async def main():
    settings = get_settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        services = create_services(pool, Path(settings.pilot_storage_root), settings)
        assert services.mode == "fixture"
        services.fixture_scenario = "invalid_response"
        assert await run_once(services)

asyncio.run(main())
"""
        compose("run", "--rm", "--no-deps", "worker", "python", "-c", run_one)
        failed = call("GET", f"{check}/summary", 200)
        if failed["job_id"] != refreshed["job"]["id"] or failed["state"] != "failed" or failed["stale"] or not failed["can_retry"]:
            raise RuntimeError("A failed current snapshot must allow retry.")
        current = call("GET", check, 200)
        retry = call("POST", f"{check}/summary/retry", 202, revision=current["revision"], mutate=True)
    finally:
        compose("start", "worker")

    saved = wait_for(lambda: call("GET", f"{check}/summary", 200),
                     lambda value: value["state"] == "succeeded", "retried summary")
    if saved["snapshot_id"] != failed["snapshot_id"] or saved["job_id"] != retry["job"]["id"]:
        raise RuntimeError("Retry did not reuse the failed snapshot.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry", action="store_true", help="Exercise summary retry by temporarily stopping the isolated fixture worker.")
    options = parser.parse_args()
    fixture_backend()
    def credentials(account):
        login = os.getenv(f"PILOT_FIXTURE_{account}_LOGIN")
        password = os.getenv(f"PILOT_FIXTURE_{account}_PASSWORD")
        if not login or not password:
            raise SystemExit(f"Set the fixture credentials for {account} in the process environment.")
        return {"login": login, "password": password}

    def session():
        return build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    api = session()
    guest = session()
    other_teacher = session()
    staff = session()
    teacher_credentials = credentials("TEACHER_1")

    def call(method, path, status, payload=None, revision=None, mutate=False, photo=None, key=None,
             opener=api, origin=ORIGIN, asset_type=None):
        headers = {"Origin": origin} if origin else {}
        body = None
        if mutate:
            headers["Idempotency-Key"] = key or str(uuid4())
        if revision is not None:
            headers["If-Match"] = f'"{revision}"'
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if photo:
            name, declared_type, content = photo
            boundary = uuid4().hex
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            body = (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: {declared_type}\r\n\r\n"
            ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        request = Request(ORIGIN + "/api" + path, data=body, headers=headers, method=method)
        try:
            with opener.open(request, timeout=15) as response:
                if response.status != status:
                    raise RuntimeError(f"{method} {path} returned {response.status}; expected {status}")
                if asset_type:
                    if response.headers.get_content_type() != asset_type or response.headers.get("Cache-Control") != "private, no-store":
                        raise RuntimeError("The photo response lacks its private cache policy or normalized media type.")
                    return response.read()
                return json.load(response) if status != 204 else None
        except HTTPError as exc:
            if exc.code == status:
                with exc:
                    return json.load(exc)
            raise RuntimeError(f"{method} {path} returned {exc.code}; expected {status}") from None

    def wait_for(read, ready, label):
        cutoff = time.monotonic() + 60
        while time.monotonic() < cutoff:
            value = read()
            if ready(value):
                return value
            time.sleep(1)
        raise RuntimeError(f"Timed out waiting for {label}")

    call("POST", "/auth/login", 403, teacher_credentials, opener=guest, origin=None)
    call("POST", "/auth/login", 401, {**teacher_credentials, "password": "incorrect-smoke-password"}, opener=guest)
    call("POST", "/auth/login", 200, teacher_credentials)
    call("POST", "/auth/login", 200, credentials("TEACHER_2"), opener=other_teacher)
    if call("POST", "/auth/login", 200, credentials("STAFF"), opener=staff)["role"] != "staff":
        raise RuntimeError("Fixture staff account has the wrong role.")
    call("POST", "/checks", 422, {"title": "   "}, mutate=True)
    created = call("POST", "/checks", 201, {"title": "  Приёмка fixture  "}, mutate=True)
    check = f"/checks/{created['check_id']}"
    if call("GET", check, 200)["title"] != "Приёмка fixture":
        raise RuntimeError("The API did not normalize a padded check title.")
    call("GET", check, 404, opener=other_teacher)
    call("POST", f"{check}/notebooks", 403, revision=created["check_revision"], mutate=True, opener=staff)
    for index in range(2):
        current = call("GET", check, 200)
        notebook = call("POST", f"{check}/notebooks", 201, revision=current["revision"], mutate=True)
        notebook_id = notebook["entity_id"]
        bundle = call("POST", f"/notebooks/{notebook_id}/bundles", 201, revision=notebook["check_revision"], mutate=True)
        current = call("GET", check, 200)
        book = next(item for item in current["notebooks"] if item["id"] == notebook_id)
        draft = book["bundles"][0]["draft"]
        collection = f"/input-versions/{draft['id']}/photos"
        revision = current["revision"]
        received = []
        images = [(SYNTHETIC_PHOTO, "image/png", "image/png")]
        if index == 1:
            images.extend((MEDIA / f"synthetic-page.{ext}", declared, normalized) for ext, declared, normalized in [
                ("jpg", "image/jpeg", "image/jpeg"), ("webp", "image/webp", "image/webp"),
                ("heic", "image/heic", "image/jpeg"), ("heif", "image/heif", "image/jpeg"),
            ])
            for status, photo in [
                (415, ("fake.pdf", "application/pdf", b"%PDF synthetic")),
                (422, ("bad.png", "image/png", b"invalid synthetic PNG")),
                (413, ("large.png", "image/png", bytes(8_000_001))),
            ]:
                call("POST", collection, status, revision=revision, mutate=True, photo=photo)
        for image, declared, normalized in images:
            content = image.read_bytes()
            uploaded = call("POST", collection, 201, revision=revision, mutate=True,
                            photo=(image.name, declared, content))
            revision = uploaded["check_revision"]
            photo_id = uploaded["entity_id"]
            received.append(photo_id)
            asset = f"/assets/{photo_id}"
            decoded = call("GET", asset, 200, asset_type=normalized)
            if not decoded or (declared == normalized and decoded != content):
                raise RuntimeError("A supported photo did not preserve its expected bytes.")
            call("GET", asset, 401, opener=guest)
            call("GET", asset, 404, opener=other_teacher)
            call("GET", asset, 200, opener=staff, asset_type=normalized)
        if index == 1:
            ordered = list(reversed(received))
            reordered = call("PATCH", f"/input-versions/{draft['id']}", 200, {"photo_ids": ordered},
                             revision=revision, mutate=True)
            revision = reordered["check_revision"]
            read_back = call("GET", check, 200)
            saved = next(item for item in read_back["notebooks"] if item["id"] == notebook_id)["bundles"][0]["draft"]
            if [photo["id"] for photo in saved["photos"]] != ordered:
                raise RuntimeError("The persisted photo order did not match the draft request.")
            old_photo = ordered[-1]
            replacement = ("replacement.png", "image/png", MEDIA.joinpath("synthetic-page.png").read_bytes())
            added = call("POST", collection, 201, photo=replacement, revision=revision, mutate=True)
            removed = call("DELETE", f"{collection}/{old_photo}", 200,
                           revision=added["check_revision"], mutate=True)
            ordered[-1] = added["entity_id"]
            arranged = call("PATCH", f"/input-versions/{draft['id']}", 200, {"photo_ids": ordered},
                            revision=removed["check_revision"], mutate=True)
            revision = arranged["check_revision"]
            call("GET", f"/assets/{old_photo}", 404)
        submit_path = f"/bundles/{bundle['entity_id']}/submit"
        submit_payload = {"input_version_id": draft["id"]}
        submit_key = str(uuid4())
        submitted = call("POST", submit_path, 202, submit_payload,
                         revision=revision, mutate=True, key=submit_key)
        repeated = call("POST", submit_path, 202, submit_payload,
                        revision=revision, mutate=True, key=submit_key)
        if repeated != submitted:
            raise RuntimeError("Submit did not replay the original checker Job.")
        conflict = call("POST", submit_path, 409, {"input_version_id": str(uuid4())},
                        revision=revision, mutate=True, key=submit_key)
        if conflict["error"]["code"] != "idempotency_conflict":
            raise RuntimeError("A repeated key with a different input did not fail as a conflict.")
        job_id = submitted["job"]["id"]
        wait_for(lambda: call("GET", f"/jobs/{job_id}", 200),
                 lambda value: value["state"] == "succeeded", "fixture checker")
        history = f"/bundles/{bundle['entity_id']}/history"
        call("GET", history, 403)
        call("GET", history, 200, opener=staff)

    call("POST", "/auth/logout", 204)
    call("GET", "/auth/session", 401)
    call("POST", "/auth/login", 200, teacher_credentials)
    check_replacement(call, wait_for, check)
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
    call("GET", f"{check}/summary/history", 403)
    call("GET", f"{check}/summary/history", 200, opener=staff)
    event_id = str(uuid4())
    events = {"events": [{
        "id": event_id, "session_id": str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "name": "app_visible", "check_id": created["check_id"], "entity_id": None,
    }]}
    for _ in range(2):
        if call("POST", "/events", 202, events) != {"accepted_ids": [event_id]}:
            raise RuntimeError("Telemetry did not accept the original event id on replay.")

    current = call("GET", check, 200)
    review_path = f"/tasks/{assessable['task_id']}/review"
    call("POST", f"{check}/notebooks", 409, revision=current["revision"], mutate=True)
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
    if options.retry:
        check_summary_retry(call, wait_for, check, review_path, review)
        print("PASS: a fresh failed analytics job was retried with the same snapshot.")
    check_composition(call)
    call("POST", "/auth/logout", 204)
    print("PASS: fixture auth/ACL, five photo formats, reorder/replace, generations, shared photo, replay, stale revision, history/numbering and summary.")


if __name__ == "__main__":
    main()
