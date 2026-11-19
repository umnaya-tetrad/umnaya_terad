"""Frozen page-check/1.2 builder and local semantic validation."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .checker_contract import Report, indexed_schema, provider_schema, validate_report
from .transport import ProviderConfig, request_base

ASSETS = Path(__file__).resolve().parent / "assets"
PROMPT_SHA256 = "7a44b3006e88680d88ced741ec65896930fa180c39ba95405200da7aecbf3aec"
MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def load_prompt() -> str:
    prompt = (ASSETS / "checker-v2.txt").read_text(encoding="utf-8")
    if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != PROMPT_SHA256:
        raise ValueError("Frozen checker prompt checksum mismatch")
    schema = ASSETS / "response-schema-v1.2.json"
    if hashlib.sha256(schema.read_bytes()).hexdigest() != "622318c350906c9d9f66f6d8286bae665083be95ab96992736688021329d49d5":
        raise ValueError("Frozen checker schema checksum mismatch")
    return prompt


def _image(path: Path) -> tuple[bytes, str]:
    if not isinstance(path, Path):
        raise ValueError("Image path must be a private Path")
    with path.open("rb") as stream:
        content = stream.read(8_000_001)
    if not content or len(content) > 8_000_000:
        raise ValueError("Image outside byte limit")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in MIME_BY_FORMAT or image.width * image.height > 36_000_000 or min(image.size) < 32:
                raise ValueError("Image outside supported format/dimensions")
            mime = MIME_BY_FORMAT[image.format]
            image.verify()
        with Image.open(BytesIO(content)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Image failed decoding") from error
    return content, mime


def validate_images(images: list[Path]) -> None:
    if not isinstance(images, list) or not images:
        raise ValueError("Ordered nonempty image list required")
    for path in images:
        _image(path)


def image_part(path: Path) -> dict:
    content, mime = _image(path)
    return {"type": "image_url", "image_url": {
        "url": f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}", "detail": "high",
    }}


def build_request(images: list[Path], config: ProviderConfig) -> dict:
    if not isinstance(images, list) or not images or any(not isinstance(path, Path) for path in images):
        raise ValueError("Ordered nonempty image Path list required")
    text = ("Проверь все приложенные изображения совместно."
            + f" Приложено {len(images)} фото. Фото нумеруются С ЕДИНИЦЫ: "
            + ",".join(str(index) for index in range(1, len(images) + 1))
            + ". Нулевого фото нет. Все photo_index и photo_indices используют эти номера.")
    return {**request_base(config), "messages": [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": [{"type": "text", "text": text}] + [image_part(path) for path in images]},
    ], "response_format": {"type": "json_schema", "json_schema": {
        "name": "SmartNotePage", "strict": True,
        "schema": provider_schema(indexed_schema(Report.model_json_schema(), len(images))),
    }}}


def validate_result(payload: dict, image_count: int) -> dict:
    report = validate_report(payload, image_count)
    for task in report.tasks:
        if len(task.photo_indices) != len(set(task.photo_indices)):
            raise ValueError("Duplicate task photo index")
    # Return the original object unchanged: normalization must not alter evidence.
    return payload
