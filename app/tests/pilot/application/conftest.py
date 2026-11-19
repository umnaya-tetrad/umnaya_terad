"""ASGI adapter tests using real shared validation and explicit service doubles."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from auth import SESSION_COOKIE_NAME
from pilot.domain import auth, mutations, queries, storage
from pilot.domain.access import Actor, require_actor
from pilot.domain.errors import DomainError, install_error_handlers
from pilot.routes import application
from pilot.routes import auth as auth_routes

SHARED = Path(__file__).resolve().parents[4] / "project-context/pilot/planning/shared/api"
ORIGIN = "https://pilot.test"

FIXTURES = {case["name"]: case for case in json.loads((SHARED / "fixtures/http.json").read_text(encoding="utf-8"))}
TEACHER = FIXTURES["login"]["response"]["body"]


def mutation_headers(revision='"12"'):
    headers = {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}
    if revision is not None:
        headers["If-Match"] = revision
    return headers


@pytest.fixture
def adapter(monkeypatch):
    async def actor_double(request: Request):
        value = request.cookies.get(SESSION_COOKIE_NAME)
        if value not in {"synthetic-cookie", "synthetic-staff-cookie"}:
            raise DomainError(401, "unauthenticated", "Login required")
        return Actor(UUID(TEACHER["user_id"]), "staff" if value == "synthetic-staff-cookie" else "teacher")

    monkeypatch.setattr(auth, "authenticate", AsyncMock(
        return_value=SimpleNamespace(session=TEACHER, token="synthetic-cookie"),
    ))
    monkeypatch.setattr(auth, "revoke", AsyncMock())

    mutation_methods = {
        "create_check": "createCheck", "create_notebook": "createNotebook", "create_bundle": "createBundle",
        "create_input_version": "createInputVersion", "reorder_photos": "reorderPhotos", "discard_draft": "discardDraft",
        "delete_draft_photo": "deleteDraftPhoto", "delete_task": "deleteTask", "delete_bundle": "deleteBundle",
        "delete_notebook": "deleteNotebook", "delete_check": "deleteCheck", "save_review": "saveReview", "upload_photo": "uploadPhoto",
    }
    query_methods = {
        "list_checks": "listChecks", "get_check": "getCheck", "get_bundle_history": "getBundleHistory",
    }
    for module, methods in ((mutations, mutation_methods), (queries, query_methods)):
        for name, fixture in methods.items():
            monkeypatch.setattr(module, name, AsyncMock(return_value=FIXTURES[fixture]["response"]["body"]))
    monkeypatch.setattr(queries, "open_photo", AsyncMock())
    prepared = object()
    monkeypatch.setattr(storage, "prepare_photo", Mock(return_value=prepared))

    app = FastAPI()
    install_error_handlers(app)
    app.state.pilot_origins = frozenset({ORIGIN})
    app.state.pilot_settings = SimpleNamespace(visitor_cookie_secure=False, auth_session_days=30)
    app.state.pilot_services = object()
    app.dependency_overrides[require_actor] = actor_double
    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(application.router, prefix="/api")

    with TestClient(app, base_url=ORIGIN) as client:
        yield SimpleNamespace(
            client=client, auth=auth, mutations=mutations, queries=queries, storage=storage,
            prepared=prepared, cookie=SESSION_COOKIE_NAME, app=app,
            teacher=lambda: client.cookies.set(SESSION_COOKIE_NAME, "synthetic-cookie"),
        )
