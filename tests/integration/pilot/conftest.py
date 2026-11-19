"""Shared HTTP harness for release integration tests.

The tests drive a real local Compose stack over the public frontend origin
(``/api`` is proxied to the backend), so they never import application or
processing modules. Credentials come from the process environment or from the
local, git-ignored ``.env`` file; no secret is stored in the repository.

Missing configuration is a hard failure instead of a silent skip: an empty
collected suite must not be reported as a pass.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ORIGIN = f"http://127.0.0.1:{os.environ.get('PILOT_ACCEPTANCE_PORT', '5273')}"
PHOTO_FIXTURE = ROOT / "project-context/pilot/planning/shared/api/fixtures/synthetic-photo.png"
MEDIA = ROOT / "src/pilot/__fixtures__/media"
# Acceptance always runs in its own Compose project with its own volumes, so it
# never mixes with the working local stack. It is not the working project and
# never touches its database.
ACCEPTANCE_PROJECT = os.environ.get("PILOT_ACCEPTANCE_PROJECT", "smartnote-release-accept")
ACCEPTANCE_PORT = os.environ.get("PILOT_ACCEPTANCE_PORT", "5273")
# Local secrets live outside the repository: the structural context check rejects
# a stray .env, and release acceptance must never commit credentials.
def env_file() -> Path | None:
    explicit = os.environ.get("PILOT_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()
    return None


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
    base = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
    for filename in os.environ.get("PILOT_COMPOSE_OVERRIDES", "").split(os.pathsep):
        if filename:
            path = Path(filename).expanduser().resolve(strict=True)
            base.extend(["-f", str(path)])
    if ENV_PATH is not None and ENV_PATH.is_file():
        base.extend(["--env-file", str(ENV_PATH)])
    return base


COMPOSE = _compose_base()
# Every acceptance call targets the isolated project, never the working stack.
COMPOSE_ENV = {
    "COMPOSE_PROJECT_NAME": ACCEPTANCE_PROJECT,
    "PILOT_FRONTEND_PORT": ACCEPTANCE_PORT,
    "ALLOWED_BROWSER_ORIGINS": f"http://127.0.0.1:{ACCEPTANCE_PORT},http://localhost:{ACCEPTANCE_PORT}",
}


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


def compose_command(*args: str) -> list[str]:
    return [*COMPOSE, *args]


def compose(*args: str, check: bool = True, project: str | None = None) -> subprocess.CompletedProcess:
    environment = compose_environment()
    if project is not None:
        if not project.startswith("smartnote-restore-"):
            raise AssertionError("Only an explicit isolated restore project may override acceptance.")
        environment["COMPOSE_PROJECT_NAME"] = project
    return subprocess.run(
        compose_command(*args), cwd=ROOT, capture_output=True, text=True, check=check, env=environment
    )


def run_host_script(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run a trusted host wrapper against the isolated acceptance project."""
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=check,
        env=compose_environment(),
    )


def compose_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(COMPOSE_ENV)
    if ENV_PATH is not None:
        environment["PILOT_ENV_FILE"] = str(ENV_PATH)
    return environment


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


def reconcile_fixture_unknown(attempt_id: str) -> None:
    """Settle a fixture-only unknown attempt so it stops holding a global slot.

    Unknown execution keeps its reserve and slot until trusted reconciliation by
    design. The fixture transport reports a zero cost, so acceptance may settle
    its own synthetic attempts with that evidence and leave the stack reusable.
    """
    evidence = Path(tempfile.mkdtemp(prefix="pilot-accept-")) / "fixture-evidence.json"
    evidence.write_text(
        json.dumps({"reference": f"release-acceptance-{attempt_id}", "actual_cost_rub": "0"}), encoding="utf-8"
    )
    compose(
        "exec", "-T", "backend", "python", "-m", "pilot.operations.reconcile_cli",
        "--attempt-id", attempt_id, "--outcome", "settled",
        "--reference", f"release-acceptance-{attempt_id}",
        "--sha256", hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "--actual-cost-rub", "0", "--operator-ref", "release-acceptance",
        check=False,
    )


class ControlledProvider:
    """Two OS processes may execute the real worker against a mock HTTP POST boundary."""

    def __init__(self):
        self.processes = []

    def sql(self, query):
        return compose("exec", "-T", "postgres", "psql", "-U", "pilot", "-d", "pilot", "-tAc", query).stdout.strip()

    def register(self, job, count=3, outcomes=("success",), *, released=True, delay_ms=0):
        assert count in (3, 4, 5) and all(x in ("success", "temporary_failure") for x in outcomes)
        self.sql(
            "INSERT INTO release_test_jobs(job_id,task_count,outcomes,released,delay_ms) VALUES("
            f"'{job['id']}',{count},'{json.dumps(list(outcomes))}',{str(released).lower()},{delay_ms})"
        )

    def worker(self, mode="once"):
        process = subprocess.Popen(
            compose_command("exec", "-T", "backend", "python", "/tmp/release_fixture_worker.py", mode),
            cwd=ROOT, env=compose_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.processes.append(process)
        return process

    def finish(self, process, timeout=120):
        output, error = process.communicate(timeout=timeout)
        assert process.returncode == 0, error
        return output

    def wait(self, query, expected, timeout=60):
        cutoff = time.monotonic() + timeout
        while time.monotonic() < cutoff:
            if self.sql(query) == str(expected):
                return
            time.sleep(0.05)
        raise AssertionError(f"Controlled provider condition did not become {expected}: {self.sql(query)}")


@pytest.fixture
def controlled_provider(request):
    """Restore the normal worker and release every test barrier even on failure."""
    provider = ControlledProvider()
    provider.wait("SELECT count(*) FROM pilot_jobs WHERE state IN ('queued','running','retry_wait','blocked')", 0)
    compose("stop", "worker")
    compose("cp", str(ROOT / "tests/integration/pilot/fixture_worker.py"), "backend:/tmp/release_fixture_worker.py")
    provider.sql("""
CREATE TABLE IF NOT EXISTS release_test_jobs(job_id UUID PRIMARY KEY,task_count INTEGER NOT NULL,outcomes JSONB NOT NULL,released BOOLEAN NOT NULL,delay_ms INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS release_test_posts(id BIGSERIAL PRIMARY KEY,job_id UUID NOT NULL,input_id UUID NOT NULL,ordinal INTEGER NOT NULL,method TEXT NOT NULL,outcome TEXT NOT NULL,active_slots INTEGER NOT NULL,image_count INTEGER NOT NULL,started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),ended_at TIMESTAMPTZ,http_status INTEGER);
TRUNCATE release_test_posts,release_test_jobs RESTART IDENTITY;
""")
    try:
        yield provider
    finally:
        provider.sql("UPDATE release_test_jobs SET released=true")
        for process in provider.processes:
            if process.poll() is None:
                try:
                    process.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    # Kill only our explicitly copied helper, never the application/worker.
                    compose("exec", "-T", "backend", "python", "-c", "import os,signal; from pathlib import Path; [(os.kill(int(p.name),signal.SIGTERM)) for p in Path('/proc').iterdir() if p.name.isdigit() and int(p.name)!=os.getpid() and b'/tmp/release_fixture_worker.py' in (p/'cmdline').read_bytes()]", check=False)
                    process.communicate(timeout=10)
        evidence_dir = os.environ.get("PILOT_EVIDENCE_DIR")
        if evidence_dir:
            destination = Path(evidence_dir).resolve()
            assert ROOT.resolve() not in destination.parents
            destination.mkdir(parents=True, exist_ok=True)
            posts = provider.sql("SELECT coalesce(json_agg(p ORDER BY p.id),'[]') FROM release_test_posts p")
            state = provider.sql("SELECT json_build_object('attempts',(SELECT count(*) FROM pilot_attempts a JOIN release_test_jobs t ON t.job_id=a.job_id),'settlements',(SELECT count(*) FROM pilot_fund_ledger l JOIN pilot_attempts a ON a.id=l.attempt_id JOIN release_test_jobs t ON t.job_id=a.job_id WHERE l.operation='settlement'),'settled_rub',(SELECT coalesce(sum(l.amount_rub),0) FROM pilot_fund_ledger l JOIN pilot_attempts a ON a.id=l.attempt_id JOIN release_test_jobs t ON t.job_id=a.job_id WHERE l.operation='settlement'))")
            (destination / f"{request.node.name}.json").write_text(json.dumps({"transport":"in-process HTTPX MockTransport; no network", "posts":json.loads(posts),"accounting":json.loads(state)}, indent=2), encoding="utf-8")
        compose("start", "worker")
        wait_healthy()


@pytest.fixture(scope="session", autouse=True)
def _stack() -> None:
    """Prepare a clean, isolated acceptance project.

    REL-C02 requires a clean PostgreSQL for acceptance and REL-C04 requires
    persistence after restart. Both are only reproducible if the suite starts
    from its own empty volumes, so the session rebuilds *only* the dedicated
    acceptance project. The working project is refused explicitly.
    """
    if not ACCEPTANCE_PROJECT.startswith("smartnote-release-"):
        raise AssertionError("Acceptance requires its own smartnote-release-* project.")
    if ENV_PATH is None or not ENV_PATH.is_file():
        raise AssertionError("Set PILOT_ENV_FILE to an explicit private synthetic fixture env file.")
    if ROOT.resolve() in ENV_PATH.resolve().parents:
        raise AssertionError("Acceptance credentials must be outside the repository.")
    configuration = compose_json()
    assert configuration["services"]["backend"]["environment"]["PILOT_TRANSPORT"] == "fixture"
    assert configuration["services"]["worker"]["environment"]["PILOT_TRANSPORT"] == "fixture"
    assert configuration["services"]["frontend"]["environment"]["VITE_PILOT_TRANSPORT"] == "fixture"
    compose("down", "-v", "--remove-orphans", check=False)
    compose("run", "--rm", "migrate")
    compose("up", "-d", "--wait")
    compose("exec", "-T", "backend", "python", "-m", "pilot.operations.manage_accounts", "seed")
    try:
        response = Client().request("GET", "/auth/session")
    except Exception as exc:  # noqa: BLE001 - report a clear setup message
        raise AssertionError(
            f"Acceptance stack {ACCEPTANCE_PROJECT} is not reachable on {origin()}: {exc}. "
            "Prepare it with the REL-02 commands from the release runbook."
        ) from None
    assert response.status in {200, 401}, response.status
