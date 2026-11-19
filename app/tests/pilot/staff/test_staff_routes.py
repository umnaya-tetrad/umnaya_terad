"""ASGI adapter tests for the release-owned staff read-only surface."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import SESSION_COOKIE_NAME
from pilot.domain import queries
from pilot.domain.access import Actor, require_actor
from pilot.domain.errors import DomainError, install_error_handlers
from pilot.routes import staff

SHARED = Path(__file__).resolve().parents[4] / "project-context/pilot/planning/shared/api"
ORIGIN = "https://pilot.test"
FIXTURES = {case["name"]: case for case in json.loads((SHARED / "fixtures/http.json").read_text(encoding="utf-8"))}
TEACHER_ID = UUID(FIXTURES["login"]["response"]["body"]["user_id"])
STAFF_ID = uuid4()


@pytest.fixture
def adapter(monkeypatch):
    async def actor_double(request: Request):
        value = request.cookies.get(SESSION_COOKIE_NAME)
        if value == "staff-cookie":
            return Actor(STAFF_ID, "staff")
        if value == "teacher-cookie":
            return Actor(TEACHER_ID, "teacher")
        raise DomainError(401, "unauthenticated", "Login required")

    calls: list[dict] = []

    async def list_staff_checks(svc, actor, *, owner_login=None, cursor=None, limit=30, request_id):
        calls.append({"name": "list", "actor": actor, "owner_login": owner_login, "cursor": cursor,
                      "limit": limit, "request_id": request_id})
        return FIXTURES["listStaffChecks"]["response"]["body"]

    async def get_staff_check(svc, actor, check_id, *, request_id):
        calls.append({"name": "get", "actor": actor, "check_id": check_id, "request_id": request_id})
        return FIXTURES["getStaffCheck"]["response"]["body"]

    monkeypatch.setattr(queries, "list_staff_checks", AsyncMock(side_effect=list_staff_checks))
    monkeypatch.setattr(queries, "get_staff_check", AsyncMock(side_effect=get_staff_check))

    app = FastAPI()
    install_error_handlers(app)
    app.state.pilot_origins = frozenset({ORIGIN})
    app.state.pilot_services = object()
    app.dependency_overrides[require_actor] = actor_double
    app.include_router(staff.router, prefix="/api")

    with TestClient(app, base_url=ORIGIN) as client:
        yield SimpleNamespace(client=client, calls=calls, cookie=SESSION_COOKIE_NAME,
                              staff=lambda: client.cookies.set(SESSION_COOKIE_NAME, "staff-cookie"),
                              teacher=lambda: client.cookies.set(SESSION_COOKIE_NAME, "teacher-cookie"))


def test_list_forwards_the_filter_and_cursor(adapter):
    adapter.staff()
    response = adapter.client.get("/api/staff/checks", params={"owner_login": " teacher-one ", "limit": 5, "cursor": "abc"})
    assert response.status_code == 200
    assert response.json() == FIXTURES["listStaffChecks"]["response"]["body"]
    call = adapter.calls[-1]
    assert call["owner_login"] == "teacher-one", "The route trims the exact login before the domain"
    assert call["limit"] == 5 and call["cursor"] == "abc"
    assert call["actor"].role == "staff"
    assert call["request_id"] is not None


def test_list_without_filter_passes_none(adapter):
    adapter.staff()
    assert adapter.client.get("/api/staff/checks").status_code == 200
    assert adapter.calls[-1]["owner_login"] is None


def test_limit_is_bounded(adapter):
    adapter.staff()
    assert adapter.client.get("/api/staff/checks", params={"limit": 101}).status_code == 422
    assert adapter.client.get("/api/staff/checks", params={"limit": 0}).status_code == 422
    assert adapter.client.get("/api/staff/checks", params={"owner_login": ""}).status_code == 422


def test_teacher_cannot_reach_staff_routes(adapter):
    adapter.teacher()
    assert adapter.client.get("/api/staff/checks").status_code == 403
    assert adapter.client.get(f"/api/staff/checks/{uuid4()}").status_code == 403


def test_anonymous_is_rejected(adapter):
    assert adapter.client.get("/api/staff/checks").status_code == 401
    assert adapter.client.get(f"/api/staff/checks/{uuid4()}").status_code == 401


def test_detail_sets_etag_and_private_cache(adapter):
    adapter.staff()
    check_id = uuid4()
    response = adapter.client.get(f"/api/staff/checks/{check_id}")
    assert response.status_code == 200
    body = FIXTURES["getStaffCheck"]["response"]["body"]
    assert response.headers["etag"] == f'"{body["check"]["revision"]}"'
    assert response.headers["cache-control"] == "private, no-store"
    assert adapter.calls[-1]["check_id"] == check_id


def test_detail_rejects_a_malformed_id(adapter):
    adapter.staff()
    assert adapter.client.get("/api/staff/checks/not-a-uuid").status_code == 422


def test_only_get_routes_exist(adapter):
    from pilot.routes import staff as staff_routes

    summary = {
        (route.path, tuple(sorted(route.methods))) for route in staff_routes.router.routes
    }
    assert summary == {
        ("/staff/checks", ("GET",)),
        ("/staff/checks/{check_id}", ("GET",)),
    }, summary
    assert all(route.methods == {"GET"} for route in staff_routes.router.routes), (
        "The staff surface must stay read-only"
    )
