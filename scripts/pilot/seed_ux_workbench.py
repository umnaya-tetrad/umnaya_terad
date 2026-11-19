"""Create five owned UX examples through the real HTTP API, without resetting data."""
from __future__ import annotations

import argparse
import json
import os
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def require_fixture_environment():
    if os.getenv("PILOT_TRANSPORT") != "fixture" or os.getenv("POLZA_API_KEY", ""):
        raise ValueError("UX seed requires explicit fixture mode and an empty model key")


class Client:
    def __init__(self, base_url: str, origin: str):
        address = urlsplit(base_url)
        if address.scheme != "http" or address.hostname not in {"localhost", "127.0.0.1", "backend"} or address.username or address.password:
            raise ValueError("UX seed is restricted to a local HTTP workbench")
        self.base = base_url.rstrip("/") + "/api"
        self.origin = origin
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def call(self, method, path, status=200, payload=None, revision=None, photo=None):
        headers = {"Origin": self.origin}
        body = None
        if method != "GET":
            headers["Idempotency-Key"] = str(uuid4())
        if revision is not None:
            headers["If-Match"] = f'"{revision}"'
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if photo is not None:
            boundary = uuid4().hex
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{photo.name}"\r\n'
                    'Content-Type: image/png\r\n\r\n').encode() + photo.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        with self.opener.open(Request(self.base + path, data=body, headers=headers, method=method), timeout=20) as response:
            if response.status != status:
                raise ValueError(f"UX seed unexpected HTTP status {response.status}")
            return json.load(response) if status != 204 else None


def wait_job(client, job_id, expected="succeeded", timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.call("GET", "/jobs/" + job_id)
        if job["state"] == expected:
            return job
        if job["state"] in {"failed", "unknown", "cancelled", "superseded"}:
            raise ValueError("UX fixture job ended in an unexpected state")
        time.sleep(0.3)
    raise TimeoutError("UX seed job did not finish")


def owned_checks(client):
    items, cursor = [], None
    while True:
        query = {"limit": 100}
        if cursor:
            query["cursor"] = cursor
        page = client.call("GET", "/checks?" + urlencode(query))
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            return items


def seed(client, credentials, fixtures: Path):
    session = client.call("POST", "/auth/login", payload=credentials)
    if session["role"] != "teacher":
        raise ValueError("UX examples require the workbench teacher account")
    catalog = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
    if catalog["schema_version"] != "ux-workbench/1":
        raise ValueError("Unsupported UX fixture catalog")
    existing = owned_checks(client)
    results = []
    for scenario in catalog["scenarios"]:
        # Exact owned title only: never reset a demo that the teacher has edited,
        # never touch fresh [UX RUN ...] copies or unrelated manual Checks.
        found = next((item for item in existing if item["title"] == scenario["title"]), None)
        if found:
            results.append({"scenario": scenario["id"], "check_id": found["id"], "reused": True})
            continue
        created = client.call("POST", "/checks", 201, {"title": scenario["title"]})
        check_id, revision = created["check_id"], created["check_revision"]
        check_path = "/checks/" + check_id
        notebook = client.call("POST", check_path + "/notebooks", 201, revision=revision)
        client.call("POST", "/notebooks/" + notebook["entity_id"] + "/bundles", 201,
                    revision=notebook["check_revision"])
        current = client.call("GET", check_path)
        bundle = current["notebooks"][0]["bundles"][0]
        revision = current["revision"]
        for relative in scenario["photos"]:
            photo = (fixtures / relative).resolve()
            if fixtures.resolve() not in photo.parents:
                raise ValueError("UX asset escaped fixture directory")
            received = client.call("POST", "/input-versions/" + bundle["draft"]["id"] + "/photos", 201,
                                   revision=revision, photo=photo)
            revision = received["check_revision"]
        if scenario["photos"]:
            submitted = client.call("POST", "/bundles/" + bundle["id"] + "/submit", 202,
                                    {"input_version_id": bundle["draft"]["id"]}, revision=revision)
            wait_job(client, submitted["job"]["id"], "failed" if scenario["id"] == "retry" else "succeeded")
        if scenario["id"] == "summary":
            current = client.call("GET", check_path)
            revision = client.call("POST", check_path + "/begin-completion", revision=current["revision"])["check_revision"]
            for task in current["notebooks"][0]["bundles"][0]["tasks"]:
                response = client.call("PUT", "/tasks/" + task["task_id"] + "/review",
                                       payload={"analysis_id": task["analysis_id"], "state": "confirmed", "comment": ""},
                                       revision=revision)
                revision = response["check_revision"]
            finalized = client.call("POST", check_path + "/finalize", 202, revision=revision)
            wait_job(client, finalized["job"]["id"])
            summary = client.call("GET", check_path + "/summary")
            if summary["state"] != "succeeded" or summary["stale"]:
                raise ValueError("UX summary was not saved")
        results.append({"scenario": scenario["id"], "check_id": check_id, "reused": False})
    return results


def main():
    require_fixture_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("PILOT_UX_BASE_URL", "http://127.0.0.1:5173"))
    parser.add_argument("--origin", default=os.getenv("PILOT_UX_ORIGIN", "http://127.0.0.1:5173"))
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--fixtures-root", type=Path, default=ROOT / "dev/ux-workbench")
    args = parser.parse_args()
    if args.credentials_file:
        credentials = json.loads(args.credentials_file.read_text(encoding="utf-8"))
        credentials = {name: credentials[name] for name in ("login", "password")}
    else:
        credentials = {"login": os.getenv("PILOT_UX_LOGIN") or os.getenv("PILOT_FIXTURE_TEACHER_1_LOGIN"),
                       "password": os.getenv("PILOT_UX_PASSWORD") or os.getenv("PILOT_FIXTURE_TEACHER_1_PASSWORD")}
    if not all(credentials.values()):
        raise ValueError("Provide teacher credentials in a private file or process environment")
    results = seed(Client(args.base_url, args.origin), credentials, args.fixtures_root)
    print(json.dumps({"checks": results, "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
