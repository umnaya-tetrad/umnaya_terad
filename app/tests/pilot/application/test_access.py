from types import SimpleNamespace
from uuid import UUID, uuid4

from .conftest import SHARED


def test_app_c27_private_photo_and_staff_history(adapter):
    photo = str(uuid4())
    bundle = str(uuid4())
    photo_path = SHARED / "fixtures/synthetic-photo.png"
    adapter.queries.open_photo.return_value = SimpleNamespace(path=photo_path, media_type="image/png")
    assert adapter.client.get(f"/api/assets/{photo}").status_code == 401
    adapter.teacher()
    response = adapter.client.get(f"/api/assets/{photo}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content == photo_path.read_bytes()
    assert adapter.queries.open_photo.await_args.args[-1] == UUID(photo)
    assert adapter.client.get(f"/api/bundles/{bundle}/history").status_code == 403
    adapter.queries.get_bundle_history.assert_not_awaited()

    adapter.client.cookies.set(adapter.cookie, "synthetic-staff-cookie")
    assert adapter.client.get(f"/api/bundles/{bundle}/history").status_code == 200
    adapter.queries.get_bundle_history.assert_awaited_once()
