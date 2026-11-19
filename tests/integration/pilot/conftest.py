"""Shared HTTP harness for release integration tests.

The tests drive a real local Compose stack over the public frontend origin
(``/api`` is proxied to the backend), so they never import application or
processing modules. Credentials come from the process environment or from the
local, git-ignored ``.env`` file; no secret is stored in the repository.

Missing configuration is a hard failure instead of a silent skip: an empty
collected suite must not be reported as a pass.
"""
from __future__ import annotations

import json
import os
import subprocess
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ORIGIN = "http://127.0.0.1:5173"
PHOTO_FIXTURE = ROOT / "project-context/pilot/planning/shared/api/fixtures/synthetic-photo.png"
MEDIA = ROOT / "src/pilot/__fixtures__/media"
# Local secrets live outside the repository: the structural context check rejects
# a stray .env, and release acceptance must never commit credentials.
DEFAULT_ENV_FILE = Path.home() / ".config/smartnote/pilot.env"


def env_file() -> Path | None:
    explicit = os.environ.get("PILOT_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()
    if DEFAULT_ENV_FILE.is_file():
        return DEFAULT_ENV_FILE
    legacy = ROOT / ".env"
    return legacy if legacy.is_file() else None


ENV_PATH = env_file()


def _local_env() -> dict[str, str]:
    """Read the local, non-tracked env file without exporting or logging values."""
    values: dict[str, str] = {}
    if ENV_PATH is None or not ENV_PATH.is_file():
        return values
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


LOCAL_ENV = _local_env()


def _compose_base() -> list[str]:
    base = ["docker", "compose", "-f", "compose.yaml"]
    if ENV_PATH is not None and ENV_PATH.is_file():
        base.extend(["--env-file", str(ENV_PATH)])
    return base


COMPOSE = _compose_base()


def setting(name: str, default: str | None = None) -> str:
    value = os.environ.get(name) or LOCAL_ENV.get(name) or default
    if value is None or value == "":
        raise RuntimeError(
            f"Set {name} in the environment or in the local .env before running release acceptance."
        )
    return value


def origin() -> str:
    return setting("PILOT_BASE_URL", DEFAULT_ORIGIN).rstrip("/")


def credentials(account: str) -> dict[str, str]:
    return {
        "login": setting(f"PILOT_FIXTURE_{account}_LOGIN"),
        "password": setting(f"PILOT_FIXTURE_{account}_PASSWORD"),
    }


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([*COMPOSE, *args], cwd=ROOT, capture_output=True, text=True, check=check)


def compose_json() -> dict:
    result = compose("config", "--format", "json")
    return json.loads(result.stdout)


def fixture_backend() -> None:
    mode = compose("exec", "-T", "backend", "printenv", "PILOT_TRANSPORT").stdout.strip()
    if mode != "fixture":
        raise RuntimeError(f"Release acceptance requires PILOT_TRANSPORT=fixture; got {mode!r}.")


class Headers(dict):
    """Case-insensitive header mapping over http.client's lowercase names."""

    def __init__(self, values: dict[str, str]):
        super().__init__({key.lower(): value for key, value in values.items()})

    def get(self, key, default=None):  # noqa: D401 - dict protocol
        return super().get(key.lower(), default)

    def __getitem__(self, key):
        return super().__getitem__(key.lower())

    def __contains__(self, key):
        return super().__contains__(str(key).lower())


class Response:
    def __init__(self, status: int, body, headers: dict[str, str], content: bytes):
        self.status = status
        self.body = body
        self.headers = Headers(headers)
        self.content = content


class Client:
    """One browser-like session: its own cookie jar and origin header."""

    def __init__(self) -> None:
        self._opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def request(
        self,
        method: str,
        path: str,
        *,
        payload=None,
        revision=None,
        key: str | None = None,
        photo: tuple[str, str, bytes] | None = None,
        origin_override: str | None = None,
        send_origin: bool = True,
        raw_body: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float = 30,
    ) -> Response:
        headers: dict[str, str] = {}
        if send_origin:
            headers["Origin"] = origin() if origin_override is None else origin_override
        if key is not None:
            headers["Idempotency-Key"] = key
        if revision is not None:
            headers["If-Match"] = f'"{revision}"'
        body = raw_body
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if photo is not None:
            name, declared, content = photo
            boundary = uuid4().hex
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            body = (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                f"Content-Type: {declared}\r\n\r\n"
            ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        if extra_headers:
            headers.update(extra_headers)
        url = origin() + "/api" + path
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                content = response.read()
                status = response.status
                response_headers = dict(response.headers.items())
        except HTTPError as exc:
            with exc:
                content = exc.read()
                status = exc.code
                response_headers = dict(exc.headers.items())
        parsed = None
        content_type = next(
            (value for key, value in response_headers.items() if key.lower() == "content-type"), ""
        )
        if content and content_type.startswith("application/json"):
            parsed = json.loads(content)
        return Response(status, parsed, response_headers, content)

    def expect(self, method: str, path: str, status: int, **kwargs) -> Response:
        response = self.request(method, path, **kwargs)
        if response.status != status:
            raise AssertionError(
                f"{method} {path} returned {response.status}, expected {status}: {response.content[:400]!r}"
            )
        return response

    def login(self, account: str = "TEACHER_1") -> dict:
        session = self.expect("POST", "/auth/login", 200, payload=credentials(account)).body
        return session

    def logout(self) -> None:
        self.expect("POST", "/auth/logout", 204)


def mutation_key() -> str:
    return str(uuid4())


def new_check(client: Client, title: str = "Приёмка release") -> tuple[str, int]:
    """Create a check with its first conditional notebook and empty bundle draft."""
    created = client.expect("POST", "/checks", 201, payload={"title": title}, key=mutation_key()).body
    check = f"/checks/{created['check_id']}"
    notebook = client.expect(
        "POST", f"{check}/notebooks", 201, revision=created["check_revision"], key=mutation_key()
    ).body
    bundle = client.expect(
        "POST", f"/notebooks/{notebook['entity_id']}/bundles", 201,
        revision=notebook["check_revision"], key=mutation_key(),
    ).body
    return check, bundle["check_revision"]


def draft_bundle(client: Client, check: str, notebook_index: int = 0) -> tuple[dict, dict]:
    """Return the existing notebook/bundle draft of a check with an uploaded draft."""
    current = client.expect("GET", check, 200).body
    notebook = current["notebooks"][notebook_index]
    return notebook, notebook["bundles"][0]


def upload_draft_photo(client: Client, check: str, notebook_index: int = 0) -> tuple[dict, dict, dict]:
    """Create/keep a draft in the notebook, upload one synthetic page, return draft and photo."""
    current = client.expect("GET", check, 200).body
    notebook = current["notebooks"][notebook_index]
    bundle = notebook["bundles"][0]
    draft = bundle["draft"]
    photo = client.expect(
        "POST", f"/input-versions/{draft['id']}/photos", 201,
        revision=current["revision"], key=mutation_key(),
        photo=(PHOTO_FIXTURE.name, "image/png", PHOTO_FIXTURE.read_bytes()),
    ).body
    return notebook, bundle, photo


def backend_health() -> str:
    """Health is served by the API itself; /api goes through the frontend proxy."""
    result = compose(
        "exec", "-T", "backend", "python", "-c",
        "from urllib.request import urlopen; "
        "import json,sys; print(json.load(urlopen('http://localhost:8000/health', timeout=5))['status'])",
    )
    return result.stdout.strip()


def wait_healthy(timeout: float = 90.0) -> None:
    """Wait until every Compose service reports healthy after a restart."""
    import time

    cutoff = time.monotonic() + timeout
    while time.monotonic() < cutoff:
        status = compose("ps", "--format", "json").stdout
        services = [json.loads(line) for line in status.splitlines() if line.strip()]
        checks = {item["Service"]: item.get("Health") for item in services if item.get("Health")}
        if all(checks.get(name) == "healthy" for name in ("postgres", "backend", "worker", "frontend")):
            return
        time.sleep(2)
    raise AssertionError(f"Compose services did not become healthy: {checks}")


@pytest.fixture(scope="session", autouse=True)
def _stack() -> None:
    fixture_backend()
