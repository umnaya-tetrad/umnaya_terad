"""Private durable originals and normalized assets with one image policy."""

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
import hashlib, io, os, shutil, warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from .errors import DomainError

MAX_BYTES = 8_000_000
MAX_PIXELS = 36_000_000
MIN_EDGE = 32


@dataclass(frozen=True)
class PreparedPhoto:
    original_path: Path
    normalized_path: Path
    media_type: str
    sha256: str
    byte_count: int
    width: int
    height: int


@dataclass(frozen=True)
class PrivatePhoto:
    path: Path
    media_type: str


def discard_prepared(prepared):
    for path in {prepared.original_path, prepared.normalized_path}:
        path.unlink(missing_ok=True)
    try:
        prepared.original_path.parent.rmdir()
    except OSError:
        pass


def prepare_photo(stream, declared_type):
    raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise DomainError(413, "invalid_input", "Фото слишком большое.")
    if declared_type not in (
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    ):
        raise DomainError(
            415, "invalid_input", "Выберите фото JPEG, PNG, WebP или HEIC."
        )
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(raw))
            fmt = img.format
            if fmt not in ("JPEG", "PNG", "WEBP", "HEIF"):
                raise ValueError()
            w, h = img.size
            if w * h > MAX_PIXELS or min(w, h) < MIN_EDGE:
                raise ValueError()
            img.load()
            orientation = img.getexif().get(274, 1)
            normalize = fmt == "HEIF" or orientation != 1
            normalized = ImageOps.exif_transpose(img)
            if normalize:
                out = io.BytesIO()
                normalized.convert("RGB").save(out, format="JPEG", quality=95)
                data = out.getvalue()
                mime = "image/jpeg"
            else:
                data = raw
                mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[
                    fmt
                ]
            if (
                len(data) > MAX_BYTES
                or normalized.width * normalized.height > MAX_PIXELS
                or min(normalized.size) < MIN_EDGE
            ):
                raise ValueError()
            width, height = normalized.size
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as e:
        raise DomainError(
            422,
            "invalid_input",
            "Фото не удалось прочитать. Переснимите или выберите другое.",
        ) from e
    folder = Path(mkdtemp(prefix="smartnote-photo-"))
    original = folder / "original"
    asset = folder / "normalized"
    for path, content in [(original, raw), (asset, data)]:
        with path.open("wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    return PreparedPhoto(
        original, asset, mime, hashlib.sha256(raw).hexdigest(), len(data), width, height
    )


def persist_photo(svc, prepared, photo_id):
    folder = svc.storage_root / str(photo_id)
    folder.mkdir(parents=True, exist_ok=False)
    try:
        for name, source in [
            ("original", prepared.original_path),
            ("normalized", prepared.normalized_path),
        ]:
            with source.open("rb") as inp, (folder / name).open("wb") as out:
                shutil.copyfileobj(inp, out)
                out.flush()
                os.fsync(out.fileno())
        if hasattr(os, "O_DIRECTORY"):
            for directory in (folder, svc.storage_root):
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        return folder / "original", folder / "normalized"
    except BaseException:
        if folder.resolve().is_relative_to(svc.storage_root.resolve()):
            shutil.rmtree(folder)
        raise
