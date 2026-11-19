from uuid import uuid4

import pytest

from .conftest import DomainError, mutation_headers


def test_app_c07_only_one_upload_reaches_shared_prepare_and_storage(adapter):
    adapter.teacher()
    version = uuid4()
    photo = ("fixture.heic", b"synthetic bytes for the port double", "image/heic")
    url = f"/api/input-versions/{version}/photos"
    result = adapter.client.post(url, files=[("file", photo), ("file", photo)], headers=mutation_headers())
    assert result.status_code == 422
    adapter.storage.prepare_photo.assert_not_called()

    result = adapter.client.post(url, files={"file": photo}, headers=mutation_headers())
    assert result.status_code == 201
    assert adapter.storage.prepare_photo.call_args.args[1] == "image/heic"
    assert adapter.mutations.upload_photo.await_args.args[-2:] == (version, adapter.prepared)


@pytest.mark.parametrize("status", [413, 415, 422])
def test_app_c08_domain_file_errors_preserve_status_and_skip_storage(adapter, status):
    adapter.teacher()
    adapter.storage.prepare_photo.side_effect = DomainError(status, "invalid_input", "Файл отклонён")
    response = adapter.client.post(
        f"/api/input-versions/{uuid4()}/photos",
        files={"file": ("synthetic.png", b"synthetic", "image/png")},
        headers=mutation_headers(),
    )
    assert response.status_code == status
    assert response.json() == {"error": {
        "code": "invalid_input", "message": "Файл отклонён", "current_revision": None,
    }}
    adapter.mutations.upload_photo.assert_not_awaited()
