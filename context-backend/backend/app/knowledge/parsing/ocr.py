"""
Offline OCR for documents without a text layer (scanned PDFs, PDFs printed
to "Microsoft Print to PDF", images).

Runs inside the parser sandbox, which ships `tesseract` and `pdftoppm`
(poppler). Both are called as subprocesses; nothing touches the network.
When the tools are missing (e.g. unit tests on a dev machine) every helper
degrades to "no OCR" instead of failing the parse.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Tesseract language packs to use, e.g. "eng" or "eng+tam".
OCR_LANGUAGES = os.environ.get("CONTEXTAPI_OCR_LANGUAGES", "eng")
OCR_DPI = 200
# The sandbox kills a job after 5 minutes; leave room for the rest of the parse.
OCR_TIME_BUDGET_SECONDS = 180
OCR_PAGE_TIMEOUT_SECONDS = 60
OCR_MAX_PAGES = 200


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def pdf_rendering_available() -> bool:
    return shutil.which("pdftoppm") is not None


def scratch_dir() -> Path:
    """A writable directory. The sandbox root filesystem (and /tmp) is
    read-only; /workspace/temp is the job's writable scratch space."""
    # tempfile.gettempdir() raises when no default location is writable
    # (the sandbox case), so it is only consulted last.
    for candidate in (os.environ.get("TMPDIR"), "/workspace/temp"):
        if candidate and os.path.isdir(candidate) and os.access(candidate, os.W_OK):
            return Path(candidate)
    return Path(tempfile.gettempdir())


def ocr_image(image_path: Path, timeout: float = OCR_PAGE_TIMEOUT_SECONDS) -> str:
    """Text in an image file, or "" when OCR is unavailable or fails."""
    if not ocr_available():
        return ""
    try:
        completed = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", OCR_LANGUAGES],
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("OCR failed for %s: %s", image_path.name, exc)
        return ""
    if completed.returncode != 0:
        logger.warning(
            "OCR failed for %s: %s",
            image_path.name,
            completed.stderr.decode("utf-8", "replace")[:300],
        )
        return ""
    return completed.stdout.decode("utf-8", "replace")


def ocr_pdf_pages(pdf_path: Path, page_numbers: list[int]) -> dict[int, str]:
    """
    Render the given 1-based PDF pages and OCR them.

    Bounded by OCR_MAX_PAGES and OCR_TIME_BUDGET_SECONDS; pages left over
    are simply not returned.
    """
    if not page_numbers or not (ocr_available() and pdf_rendering_available()):
        return {}

    results: dict[int, str] = {}
    deadline = time.monotonic() + OCR_TIME_BUDGET_SECONDS

    with tempfile.TemporaryDirectory(dir=scratch_dir()) as tmp:
        tmp_dir = Path(tmp)
        for page_number in page_numbers[:OCR_MAX_PAGES]:
            remaining = deadline - time.monotonic()
            if remaining < 5:
                logger.warning("OCR time budget used up; %d page(s) skipped", len(page_numbers) - len(results))
                break
            prefix = tmp_dir / f"page-{page_number}"
            try:
                subprocess.run(
                    [
                        "pdftoppm", "-f", str(page_number), "-l", str(page_number),
                        "-r", str(OCR_DPI), "-gray", "-png", "-singlefile",
                        str(pdf_path), str(prefix),
                    ],
                    capture_output=True,
                    timeout=min(OCR_PAGE_TIMEOUT_SECONDS, remaining),
                    check=True,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                logger.warning("Could not render PDF page %d: %s", page_number, exc)
                continue

            image_path = prefix.with_suffix(".png")
            text = ocr_image(image_path, timeout=min(OCR_PAGE_TIMEOUT_SECONDS, deadline - time.monotonic()))
            image_path.unlink(missing_ok=True)
            if text.strip():
                results[page_number] = text

    return results
