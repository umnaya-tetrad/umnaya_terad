from uuid import UUID

import pytest

from .conftest import mutation_headers

CHECK = "91b2e942-6dca-5c1f-a7a8-07845ad899e1"


def test_app_c04_create_list_check_and_etag(adapter):
    adapter.teacher()
    client = adapter.client
    assert client.post("/api/checks", json={"title": "ДЗ", "class": "7"}, headers=mutation_headers()).status_code == 422
    assert client.post("/api/checks", json={"title": "   "}, headers=mutation_headers(None)).status_code == 422
    result = client.post("/api/checks", json={"title": "  ДЗ  "}, headers=mutation_headers(None))
    assert result.status_code == 201
    ctx, payload = adapter.mutations.create_check.await_args.args[1:]
    assert ctx.expected_revision is None
    assert isinstance(ctx.idempotency_key, UUID)
    assert payload == {"title": "ДЗ"}
    assert client.get("/api/checks?cursor=next&limit=10").status_code == 200
    assert adapter.queries.list_checks.await_args.kwargs["cursor"] == "next"
    check = client.get(f"/api/checks/{CHECK}")
    assert check.status_code == 200
    assert check.headers["etag"] == f'"{check.json()["revision"]}"'


def test_app_c05_create_notebook_without_body_uses_shared_actor_and_guard(adapter):
    adapter.teacher()
    headers = mutation_headers()
    result = adapter.client.post(f"/api/checks/{CHECK}/notebooks", headers=headers)
    assert result.status_code == 201
    service, ctx, resource = adapter.mutations.create_notebook.await_args.args
    assert service is adapter.app.state.pilot_services
    assert ctx.expected_revision == 12
    assert ctx.actor.role == "teacher"
    assert ctx.idempotency_key == UUID(headers["Idempotency-Key"])
    assert resource == UUID(CHECK)


@pytest.mark.parametrize("revision", [None, "12", '"-1"', '"9999999999999999999"'])
def test_app_c28_rejects_invalid_revision_before_mutation(adapter, revision):
    adapter.teacher()
    assert adapter.client.delete(f"/api/checks/{CHECK}", headers=mutation_headers(revision)).status_code == 400
    adapter.mutations.delete_check.assert_not_awaited()
