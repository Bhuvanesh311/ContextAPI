"""
Normalize uploaded text files to UTF-8.

Every text validator and parser downstream reads UTF-8. Files saved by
Notepad as "Unicode" (UTF-16), legacy Windows-1252 files and files with a
byte-order mark are converted once, at upload, so they are accepted like any
other text file. Binary formats are never touched.
"""

from __future__ import annotations

import codecs

from charset_normalizer import from_bytes

# Text-based formats read by a text/structured/config/source parser.
TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".sql",
    ".json", ".yaml", ".yml", ".xml", ".html", ".htm",
    ".ini", ".cfg", ".conf", ".properties", ".toml", ".env",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".cs", ".php",
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".rs", ".rb", ".swift",
    ".kt", ".kts", ".scala", ".sh", ".bash", ".lua", ".r", ".dart", ".vb",
})

# Larger files are left as they are (the validators enforce their own limits).
MAX_NORMALIZE_BYTES = 50 * 1024 * 1024

_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def _looks_utf16(data: bytes) -> bool:
    """UTF-16 without a BOM: for ASCII-range text every other byte is zero."""
    sample = data[:4096]
    if len(sample) < 4:
        return False
    return max(sample[0::2].count(0), sample[1::2].count(0)) > len(sample) // 4


def _looks_latin(text: str) -> bool:
    if not text:
        return False
    ordinary = sum(
        1 for ch in text
        if ch.isascii() or " " <= ch <= "ɏ" or "‐" <= ch <= "›" or ch in "€™"
    )
    return ordinary / len(text) > 0.98


def _decode(data: bytes) -> str | None:
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                return None

    if _looks_utf16(data):
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                continue
            if chr(0) not in text:
                return text

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Western text (by far the most common non-UTF-8 case). Statistical
    # detectors misread short Windows-1252 files as Asian encodings, so
    # take cp1252 when it decodes to ordinary Latin text.
    try:
        text = data.decode("cp1252")
        if _looks_latin(text):
            return text
    except UnicodeDecodeError:
        pass

    best = from_bytes(data).best()
    if best is not None:
        return str(best)

    # Last resort: every byte maps to a character in cp1252/latin-1.
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def normalize_to_utf8(data: bytes, extension: str) -> bytes | None:
    """
    UTF-8 bytes (without BOM) for a text file that needs converting, or
    None when the file is binary, already plain UTF-8, or too large.
    """
    if extension.lower() not in TEXT_EXTENSIONS or len(data) > MAX_NORMALIZE_BYTES:
        return None

    starts_with_bom = any(data.startswith(bom) for bom, _ in _BOMS)
    if not starts_with_bom and not _looks_utf16(data):
        try:
            data.decode("utf-8")
            return None
        except UnicodeDecodeError:
            pass

    text = _decode(data)
    if text is None:
        return None
    return text.encode("utf-8")
