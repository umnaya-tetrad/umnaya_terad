from uuid import uuid4

from .conftest import mutation_headers


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
