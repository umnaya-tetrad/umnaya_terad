from dataclasses import dataclass
from io import BytesIO

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from config import Settings


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    mime_type: str


MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
ALLOWED_MIME_TYPES = frozenset(MIME_BY_FORMAT.values())


async def read_validated_image(upload: UploadFile, settings: Settings) -> ValidatedImage:
    """Читает фото ограниченного размера и оставляет его только в оперативной памяти."""
    declared_mime = upload.content_type.lower() if upload.content_type else ""
    if declared_mime not in ALLOWED_MIME_TYPES:
        raise ImageValidationError("Поддерживаются только фотографии JPG, PNG и WebP.")

    content = await upload.read(settings.max_image_bytes + 1)
    if not content:
        raise ImageValidationError("Файл пустой. Выберите фотографию решения.")
    if len(content) > settings.max_image_bytes:
        raise ImageValidationError(
            f"Фотография больше {settings.max_image_bytes // 1_000_000} МБ. Сожмите её и попробуйте снова."
        )

    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            if width * height > settings.max_image_pixels:
                raise ImageValidationError('Разрешение фотографии слишком большое. Уменьшите её и попробуйте снова.')
            image.verify()
        with Image.open(BytesIO(content)) as image:
            image.load()
            image_format = image.format
            width, height = image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ImageValidationError("Не удалось прочитать изображение. Загрузите JPG, PNG или WebP.") from error

    actual_mime = MIME_BY_FORMAT.get(image_format or "")
    if actual_mime is None or actual_mime != declared_mime:
        raise ImageValidationError("Тип файла не совпадает с содержимым изображения.")
    if width < settings.min_image_edge or height < settings.min_image_edge:
        raise ImageValidationError("Фотография слишком маленькая. Нужна сторона не менее 240 пикселей.")
    if width * height > settings.max_image_pixels:
        raise ImageValidationError("Разрешение фотографии слишком большое. Уменьшите её и попробуйте снова.")

    return ValidatedImage(content=content, mime_type=actual_mime)
