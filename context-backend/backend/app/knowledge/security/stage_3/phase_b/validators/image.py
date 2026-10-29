"""
Stage 3 validation for images (read with OCR).

Images carry no active content; the risks are a forged format and a
decompression bomb (a small file that decodes to a huge bitmap).
"""

from __future__ import annotations

import struct

from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import FormatSecurityError

MAX_IMAGE_BYTES = 50 * 1024 * 1024        # 50 MB
MAX_IMAGE_PIXELS = 100_000_000            # 100 megapixels

SIGNATURES = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".webp": (b"RIFF",),
}


def _fail(message: str, check: str, code: str) -> None:
    raise FormatSecurityError(message, phase="image_validation", check=check, code=code)


def _dimensions(extension: str, data: bytes) -> tuple[int, int] | None:
    """Width/height from the header, without decoding the image."""
    try:
        if extension == ".png" and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if extension == ".bmp":
            width, height = struct.unpack("<ii", data[18:26])
            return abs(width), abs(height)
        if extension in (".jpg", ".jpeg"):
            index = 2
            while index + 9 < len(data):
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    height, width = struct.unpack(">HH", data[index + 5:index + 9])
                    return width, height
                length = struct.unpack(">H", data[index + 2:index + 4])[0]
                index += 2 + length
    except struct.error:
        return None
    return None


def validate(context: ValidationContext) -> None:
    extension = (context.extension or "").lower()

    try:
        size = context.file_path.stat().st_size
        with context.file_path.open("rb") as file:
            # JPEG frame headers can sit after large EXIF blocks.
            data = file.read(min(size, 2 * 1024 * 1024))
    except OSError:
        _fail("Unable to read image.", "image_read", "IMAGE_READ_FAILED")

    if size > MAX_IMAGE_BYTES:
        _fail("Image is larger than 50 MB.", "image_size", "IMAGE_TOO_LARGE")

    if not any(data.startswith(sig) for sig in SIGNATURES.get(extension, ())):
        _fail("File content does not match its image extension.", "image_signature", "INVALID_IMAGE_SIGNATURE")
    if extension == ".webp" and data[8:12] != b"WEBP":
        _fail("File content does not match its image extension.", "image_signature", "INVALID_IMAGE_SIGNATURE")

    dimensions = _dimensions(extension, data)
    if dimensions is not None:
        width, height = dimensions
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            _fail("Image dimensions are invalid or too large.", "image_dimensions", "IMAGE_DIMENSIONS_REJECTED")

    context.security_validated = True
