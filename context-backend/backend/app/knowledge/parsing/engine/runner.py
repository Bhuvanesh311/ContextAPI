from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from app.knowledge.parsing.engine.engine import ParsingEngine
from app.knowledge.parsing.schemas import ParsingRequest


logger = logging.getLogger(__name__)


DEFAULT_INPUT_DIR = Path("/workspace/input")
DEFAULT_OUTPUT_DIR = Path("/workspace/output")

DEFAULT_RESULT_FILE = (
    DEFAULT_OUTPUT_DIR / "parser_result.json"
)

PARSING_REQUEST_ENV = "PARSING_REQUEST_JSON"

EXIT_SUCCESS = 0
EXIT_PARSER_FAILURE = 10
EXIT_INVALID_REQUEST = 20
EXIT_RUNTIME_FAILURE = 30


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
    )


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ContextAPI parser sandbox runner",
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Sandbox input directory.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULT_FILE,
        help="Path for the parser result JSON.",
    )

    return parser.parse_args()


def _ensure_inside_workspace(
    path: Path,
    allowed_root: Path,
) -> Path:
    resolved_path = path.resolve()
    resolved_root = allowed_root.resolve()

    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"Path '{path}' is outside the allowed "
            f"sandbox directory '{allowed_root}'."
        ) from exc

    return resolved_path


def _load_request_from_environment() -> ParsingRequest:
    request_json = os.environ.get(
        PARSING_REQUEST_ENV,
    )

    if not request_json:
        raise ValueError(
            f"Required environment variable "
            f"'{PARSING_REQUEST_ENV}' was not provided."
        )

    try:
        return ParsingRequest.model_validate_json(
            request_json,
        )
    except Exception as exc:
        raise ValueError(
            "Invalid ParsingRequest supplied to "
            "the parser sandbox."
        ) from exc


def _resolve_source_file(
    request: ParsingRequest,
    input_dir: Path,
) -> Path:
    filename = Path(
        request.original_filename,
    ).name

    if not filename:
        raise ValueError(
            "Parsing request contains an empty "
            "original filename."
        )

    source_file = input_dir / filename

    source_file = _ensure_inside_workspace(
        source_file,
        input_dir,
    )

    if not source_file.exists():
        raise FileNotFoundError(
            f"Source document does not exist: "
            f"{source_file}"
        )

    if not source_file.is_file():
        raise ValueError(
            f"Source document is not a regular file: "
            f"{source_file}"
        )

    return source_file


def _write_result(
    result_json: str,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        result_json,
        encoding="utf-8",
    )


def run(
    *,
    input_dir: Path,
    output_path: Path,
) -> int:

    input_dir = _ensure_inside_workspace(
        input_dir,
        DEFAULT_INPUT_DIR,
    )

    output_path = _ensure_inside_workspace(
        output_path,
        DEFAULT_OUTPUT_DIR,
    )

    try:
        # 1. LOAD + VALIDATE PARSING REQUEST

        request = _load_request_from_environment()

        logger.info(
            "Parsing request loaded",
            extra={
                "document_id": request.document_id,
                "original_filename": request.original_filename,
                "extension": request.extension,
                "quarantine_bucket": (
                    request.quarantine_bucket
                ),
                "source_object_key": (
                    request.source_object_key
                ),
                "parsed_bucket": (
                    request.parsed_bucket
                ),
                "parsed_object_key": (
                    request.parsed_object_key
                ),
            },
        )

        # 2. RESOLVE SOURCE DOCUMENT

        source_file = _resolve_source_file(
            request=request,
            input_dir=input_dir,
        )

        logger.info(
            "Source document resolved",
            extra={
                "document_id": request.document_id,
                "source_file": str(source_file),
            },
        )

        # 3. CREATE PARSING ENGINE

        engine = ParsingEngine()

        # 4. EXECUTE PARSING ENGINE

        result = engine.execute(
            file_path=source_file,
            request=request,
        )

        # 5. SERIALIZE PARSER RESULT

        result_json = result.model_dump_json(
            indent=2,
        )

        # 6. WRITE RESULT TO SANDBOX OUTPUT

        _write_result(
            result_json=result_json,
            output_path=output_path,
        )

        logger.info(
            "Parser result written",
            extra={
                "document_id": request.document_id,
                "output_file": str(output_path),
                "success": result.success,
            },
        )

        # 7. RETURN PROCESS STATUS

        if result.success:
            return EXIT_SUCCESS

        logger.error(
            "Parser engine returned failure",
            extra={
                "document_id": request.document_id,
            },
        )

        return EXIT_PARSER_FAILURE

    except FileNotFoundError as exc:
        logger.error(
            "Sandbox source file not found",
            extra={
                "error": str(exc),
            },
            exc_info=True,
        )

        return EXIT_INVALID_REQUEST

    except ValueError as exc:
        logger.error(
            "Sandbox input validation failed",
            extra={
                "error": str(exc),
            },
            exc_info=True,
        )

        return EXIT_INVALID_REQUEST

    except Exception as exc:
        logger.exception(
            "Unexpected parser runner failure",
            extra={
                "error": str(exc),
            },
        )

        return EXIT_RUNTIME_FAILURE


def main() -> int:
    _configure_logging()

    args = _parse_arguments()

    logger.info(
        "ContextAPI parser sandbox runner started",
    )

    return run(
        input_dir=args.input_dir,
        output_path=args.output,
    )


if __name__ == "__main__":
    sys.exit(main())