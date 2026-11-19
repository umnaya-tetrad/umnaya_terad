import io
from pathlib import Path
import pytest
import pillow_heif
from PIL import Image
from pilot.domain.storage import (
    prepare_photo,
    discard_prepared,
    MAX_BYTES,
    MAX_PIXELS,
    MIN_EDGE,
)
from pilot.domain.errors import DomainError
from ..harness import png


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fmt,mime",
    [("JPEG", "image/jpeg"), ("HEIF", "image/heic"), ("HEIF", "image/heif")],
    ids=["jpeg", "heic", "heif"],
)
async def test_real_decoder_normalizes_exif_and_keeps_private_original(h, fmt, mime):
    pillow_heif.register_heif_opener()
    image = Image.new("RGB", (80, 40), "red")
    exif = Image.Exif()
    exif[274] = 6
    buf = io.BytesIO()
    image.save(buf, format=fmt, exif=exif.tobytes())
    ids = await h.create(photos=0)
    response = await h.call(
        "uploadPhoto",
        input_version_id=ids[3],
        files={"file": ("synthetic", buf.getvalue(), mime)},
        expected=201,
    )
    asset = await h.call(
        "getPhoto", photo_id=response.json()["entity_id"], expected=200
    )
    decoded = Image.open(io.BytesIO(asset.content))
    assert decoded.size == (40, 80)
    assert asset.headers["content-type"] == "image/jpeg"
    row = await h.svc.pool.fetchrow("SELECT * FROM pilot_photo_assets")
    assert Path(row["original_path"]).read_bytes() == buf.getvalue()
    assert Path(row["original_path"]) != Path(row["normalized_path"])


def test_actual_image_policy_boundaries():
    assert (MAX_BYTES, MAX_PIXELS, MIN_EDGE) == (8_000_000, 36_000_000, 32)
    raw = png((32, 32))
    prepared = prepare_photo(io.BytesIO(raw), "image/png")
    discard_prepared(prepared)
    with pytest.raises(DomainError) as error:
        prepare_photo(io.BytesIO(png((31, 32))), "image/png")
    assert error.value.http_status == 422
    padded = raw + b"\x00" * (MAX_BYTES - len(raw))
    prepared = prepare_photo(io.BytesIO(padded), "image/png")
    assert (
        prepared.byte_count == MAX_BYTES
        and prepared.normalized_path.read_bytes() == padded
    )
    discard_prepared(prepared)
    with pytest.raises(DomainError) as error:
        prepare_photo(io.BytesIO(padded + b"\x00"), "image/png")
    assert error.value.http_status == 413
    buf = io.BytesIO()
    Image.new("RGB", (6000, 6000), "white").save(buf, format="PNG")
    prepared = prepare_photo(io.BytesIO(buf.getvalue()), "image/png")
    assert prepared.width * prepared.height == MAX_PIXELS
    discard_prepared(prepared)
    buf = io.BytesIO()
    Image.new("RGB", (6001, 6000), "white").save(buf, format="PNG")
    with pytest.raises(DomainError) as error:
        prepare_photo(io.BytesIO(buf.getvalue()), "image/png")
    assert error.value.http_status == 422
