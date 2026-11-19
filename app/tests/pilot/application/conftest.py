"""ASGI adapter tests using explicit doubles for the unpublished processing ports."""
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import pytest
from starlette.responses import JSONResponse

SHARED = Path(__file__).resolve().parents[4] / "project-context/pilot/planning/shared/api"
ORIGIN = "https://pilot.test"

FIXTURES = {case["name"]: case for case in json.loads((SHARED / "fixtures/http.json").read_text(encoding="utf-8"))}
TEACHER = FIXTURES["login"]["response"]["body"]


def mutation_headers(revision='"12"'):
    headers = {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}
    if revision is not None:
        headers["If-Match"] = revision
    return headers


class DomainError(Exception):
    def __init__(self, http_status, code, message, current_revision=None):
        self.status = http_status
        self.detail = dict(code=code, message=message, current_revision=current_revision)


@dataclass
class Actor:
    user_id: UUID
    role: str


@dataclass
class MutationContext:
    actor: Actor
    expected_revision: int | None
    idempotency_key: UUID
    request_id: UUID


class Services:
    pass


@pytest.fixture
def adapter(monkeypatch):
    from auth import SESSION_COOKIE_NAME

    dto = importlib.util.spec_from_file_location("pilot.contracts", SHARED / "contracts.py")
    contracts = importlib.util.module_from_spec(dto)
    monkeypatch.setitem(sys.modules, "pilot.contracts", contracts)
    dto.loader.exec_module(contracts)

    domain = ModuleType("pilot.domain")
    domain.__path__ = []
    monkeypatch.setitem(sys.modules, "pilot.domain", domain)

    def port(name, **attributes):
        module = ModuleType(f"pilot.domain.{name}")
        vars(module).update(attributes)
        setattr(domain, name, module)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        return module

    def get_services(request: Request):
        return request.app.state.pilot_services

    async def require_actor(request: Request):
        value = request.cookies.get(SESSION_COOKIE_NAME)
        if value not in {"synthetic-cookie", "synthetic-staff-cookie"}:
            raise DomainError(401, "unauthenticated", "Login required")
        return Actor(UUID(TEACHER["user_id"]), "staff" if value == "synthetic-staff-cookie" else "teacher")

    port("access", Actor=Actor, get_services=get_services, require_actor=require_actor)
    port("services", Services=Services)
    port("revision", MutationContext=MutationContext)
    port("errors", DomainError=DomainError)
    auth = port("auth",
        authenticate=AsyncMock(return_value=SimpleNamespace(session=TEACHER, token="synthetic-cookie")),
        revoke=AsyncMock(),
    )
    mutation_methods = {
        "create_check": "createCheck", "create_notebook": "createNotebook", "create_bundle": "createBundle",
        "create_input_version": "createInputVersion", "reorder_photos": "reorderPhotos", "discard_draft": "discardDraft",
        "delete_draft_photo": "deleteDraftPhoto", "delete_task": "deleteTask", "delete_bundle": "deleteBundle",
        "delete_notebook": "deleteNotebook", "delete_check": "deleteCheck", "save_review": "saveReview", "upload_photo": "uploadPhoto",
    }
    mutations = port("mutations", **{
        name: AsyncMock(return_value=FIXTURES[fixture]["response"]["body"]) for name, fixture in mutation_methods.items()
    })
    queries = port("queries",
        list_checks=AsyncMock(return_value=FIXTURES["listChecks"]["response"]["body"]),
        get_check=AsyncMock(return_value=FIXTURES["getCheck"]["response"]["body"]),
        get_bundle_history=AsyncMock(return_value=FIXTURES["getBundleHistory"]["response"]["body"]),
        open_photo=AsyncMock(),
    )
    prepared = object()
    storage = port("storage", prepare_photo=Mock(return_value=prepared))

    application_modules = [
        "pilot.services.application", "pilot.services.payloads", "pilot.routes.auth", "pilot.routes.application",
    ]
    for name in application_modules:
        monkeypatch.delitem(sys.modules, name, raising=False)
        # Record the original state even when the module did not previously exist.
        monkeypatch.setitem(sys.modules, name, None)
        del sys.modules[name]

    auth_router = importlib.import_module("pilot.routes.auth").router
    application_router = importlib.import_module("pilot.routes.application").router
    app = FastAPI()
    app.state.pilot_origins = frozenset({ORIGIN})
    app.state.pilot_settings = SimpleNamespace(visitor_cookie_secure=False, auth_session_days=30)
    app.state.pilot_services = Services()
    app.include_router(auth_router, prefix="/api")
    app.include_router(application_router, prefix="/api")

    @app.exception_handler(DomainError)
    async def domain_error(_request, exc):
        return JSONResponse({"error": exc.detail}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _exc):
        return JSONResponse(
            {"error": {"code": "invalid_input", "message": "Invalid request", "current_revision": None}}, status_code=422,
        )

    with TestClient(app, base_url=ORIGIN) as client:
        yield SimpleNamespace(
            client=client, auth=auth, mutations=mutations, queries=queries, storage=storage,
            prepared=prepared, cookie=SESSION_COOKIE_NAME, app=app,
            teacher=lambda: client.cookies.set(SESSION_COOKIE_NAME, "synthetic-cookie"),
        )
