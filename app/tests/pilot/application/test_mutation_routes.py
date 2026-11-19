"""Check the adapter wiring for the remaining guarded composition routes."""
import json
from uuid import UUID

import pytest

from .conftest import FIXTURES, ORIGIN, SHARED

OPENAPI = json.loads((SHARED / "openapi.json").read_text(encoding="utf-8"))
OPERATIONS = {
    operation["operationId"]: (method.upper(), path)
    for path, methods in OPENAPI["paths"].items()
    for method, operation in methods.items()
    if isinstance(operation, dict) and "operationId" in operation
}


@pytest.mark.parametrize(
    ("operation", "port"),
    [
        pytest.param("deleteCheck", "delete_check", id="app_c20_delete_check"),
        pytest.param("deleteNotebook", "delete_notebook", id="app_c05_delete_notebook"),
        pytest.param("createBundle", "create_bundle", id="app_c06_create_bundle"),
        pytest.param("deleteBundle", "delete_bundle", id="app_c06_delete_bundle"),
        pytest.param("createInputVersion", "create_input_version", id="app_c19_replacement"),
        pytest.param("reorderPhotos", "reorder_photos", id="app_c09_reorder"),
        pytest.param("discardDraft", "discard_draft", id="app_c19_discard"),
        pytest.param("deleteDraftPhoto", "delete_draft_photo", id="app_c09_delete_photo"),
        pytest.param("deleteTask", "delete_task", id="app_c20_delete_task"),
    ],
)
def test_app_mutation_contract(adapter, operation, port):
    case = FIXTURES[operation]
    method, template = OPERATIONS[operation]
    params = case["path_parameters"]
    body = case["request"]["body"]
    request = case["request"]
    adapter.teacher()
    response = adapter.client.request(
        method,
        template.format(**params),
        headers={**request["headers"], "Origin": ORIGIN},
        **({"json": body} if body is not None else {}),
    )
    assert response.status_code == case["response"]["status"]
    assert response.json() == case["response"]["body"]
    service, ctx, *args = getattr(adapter.mutations, port).await_args.args
    assert service is adapter.app.state.pilot_services
    assert ctx.actor.role == "teacher"
    assert ctx.expected_revision == int(request["headers"]["If-Match"].strip('"'))
    assert ctx.idempotency_key == UUID(request["headers"]["Idempotency-Key"])
    assert args == [*(UUID(value) for value in params.values()), *([body] if body is not None else [])]


def test_app_c09_reorder_rejects_duplicate_photo_ids(adapter):
    case = FIXTURES["reorderPhotos"]
    method, template = OPERATIONS["reorderPhotos"]
    adapter.teacher()
    photo = case["request"]["body"]["photo_ids"][0]
    response = adapter.client.request(
        method,
        template.format(**case["path_parameters"]),
        headers={**case["request"]["headers"], "Origin": ORIGIN},
        json={"photo_ids": [photo, photo]},
    )
    assert response.status_code == 422
    adapter.mutations.reorder_photos.assert_not_awaited()
