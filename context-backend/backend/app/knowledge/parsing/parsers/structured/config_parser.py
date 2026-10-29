from __future__ import annotations

import configparser
import json
import logging
import tomllib
from pathlib import Path
from typing import Any

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.parsing.exceptions import (
    FileParsingError,
    SourceFileNotFoundError,
)
from app.knowledge.parsing.schemas import (
    NormalizedDocument,
    ParsingRequest,
)

logger = logging.getLogger(__name__)


class ConfigParser(BaseParser):

    parser_name = "config_parser"

    supported_extensions = (
        ".ini",
        ".conf",
        ".cfg",
        ".properties",
        ".toml",
    )

    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
    MAX_ENTRIES = 100_000
    MAX_LINE_LENGTH = 1_000_000
    MAX_NESTING_DEPTH = 100

    # ================================================================
    # MAIN PARSER
    # ================================================================

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:

        self._validate_input(file_path, request)

        warnings: list[dict[str, str]] = []

        try:
            ext = file_path.suffix.lower()

            # IMPORTANT:
            # .ini and .cfg continue using the original strict
            # ConfigParser implementation.
            #
            # .conf gets its own tolerant parser.
            if ext == ".conf":
                data, strategy = self._parse_conf(
                    file_path,
                    warnings,
                )

            elif ext in {".ini", ".cfg"}:
                data, strategy = self._parse_ini(
                    file_path,
                    warnings,
                )

            elif ext == ".properties":
                data, strategy = self._parse_properties(
                    file_path,
                    warnings,
                )

            elif ext == ".toml":
                data, strategy = self._parse_toml(
                    file_path,
                )

            else:
                raise FileParsingError(
                    f"Unsupported configuration extension: {ext}"
                )

            self._validate_structure(
                data,
                file_path,
            )

            content = json.dumps(
                data,
                indent=4,
                ensure_ascii=False,
                sort_keys=False,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.CONFIG,
                content=content,
                metadata=self._build_metadata(
                    file_path,
                    ext,
                    data,
                    strategy,
                    warnings,
                ),
                page_count=0,
                character_count=len(content),
                word_count=len(content.split()),
                mime_type=request.mime_type,
            )

        except FileParsingError:
            raise

        except Exception as exc:

            logger.exception(
                "Configuration parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )

            raise FileParsingError(
                f"Failed to parse config file: "
                f"{file_path.name} | "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    # ================================================================
    # INPUT VALIDATION
    # ================================================================

    @classmethod
    def _validate_input(
        cls,
        file_path: Path,
        request: ParsingRequest,
    ) -> None:

        if not file_path.exists():

            raise SourceFileNotFoundError(
                f"Source file not found: {file_path}"
            )

        if not file_path.is_file():

            raise SourceFileNotFoundError(
                f"Invalid source file: {file_path}"
            )

        ext = file_path.suffix.lower()

        if ext not in cls.supported_extensions:

            raise FileParsingError(
                "Unsupported configuration extension: "
                f"{ext or '<none>'}"
            )

        if request.detected_format != ParserFormat.CONFIG:

            raise FileParsingError(
                "Config parser received a non-CONFIG format."
            )

        try:
            size = file_path.stat().st_size

        except OSError as exc:

            raise FileParsingError(
                f"Unable to inspect configuration file: "
                f"{file_path.name}"
            ) from exc

        if size <= 0:

            raise FileParsingError(
                f"Configuration file is empty: "
                f"{file_path.name}"
            )

        if size > cls.MAX_FILE_SIZE_BYTES:

            raise FileParsingError(
                "Configuration file exceeds "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes."
            )

    # ================================================================
    # INI / CFG
    #
    # DO NOT CHANGE THIS.
    # Existing behavior is intentionally preserved.
    # ================================================================

    @classmethod
    def _parse_ini(
        cls,
        file_path: Path,
        warnings: list[dict[str, str]],
    ) -> tuple[dict[str, Any], str]:

        parser = configparser.ConfigParser(
            interpolation=None,
            strict=True,
            empty_lines_in_values=True,
        )

        try:

            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as fh:

                cls._validate_line_lengths(fh)

            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as fh:

                parser.read_file(fh)

        except (
            UnicodeDecodeError,
            configparser.Error,
        ) as exc:

            raise FileParsingError(
                f"Invalid INI-style configuration: "
                f"{file_path.name}"
            ) from exc

        data: dict[str, Any] = {}

        defaults = {
            str(k): cls._normalize_scalar(v)
            for k, v in parser.defaults().items()
        }

        if defaults:
            data["DEFAULT"] = defaults

        for section in parser.sections():

            values: dict[str, str] = {}

            for key, value in parser.items(
                section,
                raw=True,
            ):

                if len(values) >= cls.MAX_ENTRIES:

                    raise FileParsingError(
                        f"Section exceeds entry limit: "
                        f"{section}"
                    )

                values[str(key)] = (
                    cls._normalize_scalar(value)
                )

            data[str(section)] = values

        if not data:

            warnings.append(
                {
                    "code": "CONFIG_NO_ENTRIES",
                    "severity": "WARNING",
                    "message": (
                        "Configuration contains no "
                        "sections or values."
                    ),
                }
            )

        return data, "configparser"

    # ================================================================
    # .CONF PARSER
    #
    # THIS IS THE NEW PART.
    #
    # .conf is NOT forced through ConfigParser.
    # ================================================================

    @classmethod
    def _parse_conf(
        cls,
        file_path: Path,
        warnings: list[dict[str, str]],
    ) -> tuple[dict[str, Any], str]:

        try:

            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as fh:

                physical_lines = list(fh)

        except UnicodeDecodeError as exc:

            raise FileParsingError(
                "CONF_FILE_ENCODING_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        except OSError as exc:

            raise FileParsingError(
                "CONF_FILE_READ_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        lines: list[tuple[int, str]] = []

        for number, raw_line in enumerate(
            physical_lines,
            start=1,
        ):

            line = raw_line.rstrip(
                "\r\n"
            )

            if len(line) > cls.MAX_LINE_LENGTH:

                raise FileParsingError(
                    "CONF_LINE_TOO_LONG | "
                    f"file={file_path.name} | "
                    f"line={number}"
                )

            lines.append(
                (
                    number,
                    line,
                )
            )

        data: dict[str, Any] = {}

        current_section: dict[str, Any] | None = None
        current_section_name: str | None = None

        raw_lines: list[dict[str, Any]] = []
        directives: list[dict[str, Any]] = []

        entry_count = 0

        for line_number, raw_line in lines:

            stripped = raw_line.strip()

            # --------------------------------------------------------
            # Empty lines
            # --------------------------------------------------------

            if not stripped:
                continue

            # --------------------------------------------------------
            # Comments
            # --------------------------------------------------------

            if cls._is_conf_comment(stripped):

                continue

            # --------------------------------------------------------
            # Section:
            #
            # [server]
            # [database]
            # --------------------------------------------------------

            section_name = cls._extract_conf_section(
                stripped
            )

            if section_name is not None:

                section_name = (
                    section_name.strip()
                )

                if not section_name:

                    warnings.append(
                        {
                            "code": "CONF_EMPTY_SECTION",
                            "severity": "WARNING",
                            "message": (
                                f"Empty section at "
                                f"line {line_number}."
                            ),
                        }
                    )

                    continue

                if section_name in data:

                    warnings.append(
                        {
                            "code": "CONF_DUPLICATE_SECTION",
                            "severity": "WARNING",
                            "message": (
                                f"Duplicate section "
                                f"'{section_name}' at "
                                f"line {line_number}."
                            ),
                        }
                    )

                current_section = {}

                data[
                    section_name
                ] = current_section

                current_section_name = section_name

                continue

            # --------------------------------------------------------
            # Block:
            #
            # server {
            #
            # nginx {
            # }
            # --------------------------------------------------------

            block_match = cls._extract_conf_block_start(
                stripped
            )

            if block_match is not None:

                block_name = block_match

                if block_name in data:

                    existing = data[
                        block_name
                    ]

                    if not isinstance(
                        existing,
                        dict,
                    ):

                        existing = {
                            "value": existing
                        }

                        data[
                            block_name
                        ] = existing

                    current_section = existing

                else:

                    current_section = {}

                    data[
                        block_name
                    ] = current_section

                current_section_name = block_name

                continue

            # --------------------------------------------------------
            # Closing block
            # --------------------------------------------------------

            if stripped == "}":

                current_section = None
                current_section_name = None

                continue

            # --------------------------------------------------------
            # key=value
            # key: value
            # --------------------------------------------------------

            key, value = cls._split_conf_assignment(
                stripped
            )

            if key is not None:

                key = key.strip()

                value = value.strip()

                if not key:

                    raw_lines.append(
                        {
                            "line": line_number,
                            "content": raw_line,
                        }
                    )

                    continue

                normalized_value = (
                    cls._normalize_conf_value(
                        value
                    )
                )

                target = (
                    current_section
                    if current_section is not None
                    else data
                )

                cls._insert_conf_value(
                    target=target,
                    key=key,
                    value=normalized_value,
                    line_number=line_number,
                    warnings=warnings,
                )

                entry_count += 1

                if entry_count > cls.MAX_ENTRIES:

                    raise FileParsingError(
                        "CONF_ENTRY_LIMIT_EXCEEDED | "
                        f"file={file_path.name} | "
                        f"maximum={cls.MAX_ENTRIES}"
                    )

                continue

            # --------------------------------------------------------
            # Bare directive
            #
            # include "foo.conf"
            # listen 8080
            # daemon
            # allow localhost
            # --------------------------------------------------------

            directive_name, directive_value = (
                cls._split_conf_directive(
                    stripped
                )
            )

            if directive_name is not None:

                directive = {
                    "name": directive_name,
                    "line": line_number,
                }

                if directive_value:

                    directive[
                        "value"
                    ] = cls._normalize_conf_value(
                        directive_value
                    )

                directives.append(
                    directive
                )

                continue

            # --------------------------------------------------------
            # Anything we cannot confidently classify is preserved.
            #
            # This is the key difference from strict INI parsing.
            # --------------------------------------------------------

            raw_lines.append(
                {
                    "line": line_number,
                    "content": raw_line,
                }
            )

        # ============================================================
        # Attach directives only if present.
        # ============================================================

        if directives:

            data[
                "__directives__"
            ] = directives

        # ============================================================
        # Attach unrecognized/raw lines only if present.
        # ============================================================

        if raw_lines:

            data[
                "__raw_lines__"
            ] = raw_lines

            warnings.append(
                {
                    "code": "CONF_RAW_LINES_PRESERVED",
                    "severity": "WARNING",
                    "message": (
                        "Some configuration lines did not "
                        "match a recognized key/value or "
                        "directive structure and were preserved "
                        "verbatim."
                    ),
                }
            )

        # ============================================================
        # Empty configuration is not an error.
        # ============================================================

        if not data:

            warnings.append(
                {
                    "code": "CONFIG_NO_ENTRIES",
                    "severity": "WARNING",
                    "message": (
                        "Configuration contains no "
                        "recognized entries."
                    ),
                }
            )

        return data, "tolerant_conf_parser"

    # ================================================================
    # CONF COMMENT DETECTION
    # ================================================================

    @staticmethod
    def _is_conf_comment(
        line: str,
    ) -> bool:

        return (
            line.startswith("#")
            or line.startswith(";")
            or line.startswith("//")
        )

    # ================================================================
    # CONF SECTION
    # ================================================================

    @staticmethod
    def _extract_conf_section(
        line: str,
    ) -> str | None:

        if (
            line.startswith("[")
            and line.endswith("]")
        ):

            return line[1:-1]

        return None

    # ================================================================
    # CONF BLOCK
    # ================================================================

    @staticmethod
    def _extract_conf_block_start(
        line: str,
    ) -> str | None:

        if not line.endswith("{"):

            return None

        name = line[:-1].strip()

        if not name:

            return None

        # Avoid treating key=value{
        # as a block.
        if "=" in name:

            return None

        if ":" in name:

            return None

        return name

    # ================================================================
    # CONF ASSIGNMENT
    # ================================================================

    @staticmethod
    def _split_conf_assignment(
        line: str,
    ) -> tuple[str | None, str]:

        # Find '=' first.
        #
        # This deliberately does not try to interpret
        # shell expansion or application-specific syntax.
        # It simply separates obvious assignments.

        escaped = False
        quote: str | None = None

        for index, char in enumerate(line):

            if escaped:

                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char in {'"', "'"}:

                if quote is None:

                    quote = char

                elif quote == char:

                    quote = None

                continue

            if quote is not None:
                continue

            if char == "=":

                key = line[:index]
                value = line[index + 1:]

                if key.strip():

                    return key, value

        # Colon assignment:
        #
        # key: value
        #
        # Do not interpret URLs such as:
        # http://example.com
        #
        quote = None
        escaped = False

        for index, char in enumerate(line):

            if escaped:

                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char in {'"', "'"}:

                if quote is None:

                    quote = char

                elif quote == char:

                    quote = None

                continue

            if quote is not None:
                continue

            if char == ":":

                key = line[:index].strip()
                value = line[index + 1:].strip()

                if (
                    key
                    and not key.endswith("/")
                    and not value.startswith("//")
                ):

                    return key, value

        return None, ""

    # ================================================================
    # CONF DIRECTIVE
    # ================================================================

    @staticmethod
    def _split_conf_directive(
        line: str,
    ) -> tuple[str | None, str]:

        if not line:

            return None, ""

        parts = line.split(
            None,
            1,
        )

        if not parts:

            return None, ""

        name = parts[0].strip()

        if not name:

            return None, ""

        value = (
            parts[1].strip()
            if len(parts) > 1
            else ""
        )

        # Don't treat punctuation-only lines
        # as directives.
        if all(
            not char.isalnum()
            and char != "_"
            and char != "-"
            for char in name
        ):

            return None, ""

        return name, value

    # ================================================================
    # CONF VALUE NORMALIZATION
    # ================================================================

    @staticmethod
    def _normalize_conf_value(
        value: str,
    ) -> str:

        value = (
            value
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\u00a0", " ")
            .strip()
        )

        # Remove matching surrounding quotes.
        if len(value) >= 2:

            if (
                value[0] == '"'
                and value[-1] == '"'
            ):

                value = value[1:-1]

            elif (
                value[0] == "'"
                and value[-1] == "'"
            ):

                value = value[1:-1]

        return value

    # ================================================================
    # CONF DUPLICATE KEY HANDLING
    # ================================================================

    @classmethod
    def _insert_conf_value(
        cls,
        *,
        target: dict[str, Any],
        key: str,
        value: str,
        line_number: int,
        warnings: list[dict[str, str]],
    ) -> None:

        if key not in target:

            target[key] = value
            return

        existing = target[key]

        # Preserve duplicate configuration values
        # instead of silently destroying one.
        if isinstance(existing, list):

            existing.append(value)

        else:

            target[key] = [
                existing,
                value,
            ]

        warnings.append(
            {
                "code": "CONF_DUPLICATE_KEY",
                "severity": "WARNING",
                "message": (
                    f"Duplicate configuration key "
                    f"'{key}' at line {line_number}; "
                    "values were preserved as a list."
                ),
            }
        )

    # ================================================================
    # PROPERTIES
    #
    # EXISTING BEHAVIOR PRESERVED
    # ================================================================

    @classmethod
    def _parse_properties(
        cls,
        file_path: Path,
        warnings: list[dict[str, str]],
    ) -> tuple[dict[str, str], str]:

        try:

            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as fh:

                physical = list(fh)

        except UnicodeDecodeError as exc:

            raise FileParsingError(
                "Properties file is not valid UTF-8: "
                f"{file_path.name}"
            ) from exc

        logical = cls._join_continuations(
            physical,
            file_path.name,
        )

        data: dict[str, str] = {}

        for line_number, raw in logical:

            line = raw.strip()

            if (
                not line
                or line.startswith("#")
                or line.startswith("!")
            ):

                continue

            key, value = cls._split_property(
                line
            )

            if key is None:

                warnings.append(
                    {
                        "code": "PROPERTY_LINE_SKIPPED",
                        "severity": "WARNING",
                        "message": (
                            "Invalid property assignment "
                            f"at line {line_number}."
                        ),
                    }
                )

                continue

            key = cls._decode_escapes(
                key.strip()
            )

            value = cls._decode_escapes(
                value.strip()
            )

            if not key:

                raise FileParsingError(
                    "Empty property key at "
                    f"line {line_number}: "
                    f"{file_path.name}"
                )

            if key in data:

                raise FileParsingError(
                    f"Duplicate property key "
                    f"'{key}' at line {line_number}."
                )

            if len(data) >= cls.MAX_ENTRIES:

                raise FileParsingError(
                    "Properties file exceeds "
                    f"{cls.MAX_ENTRIES} entries."
                )

            data[key] = cls._normalize_scalar(
                value
            )

        if not data:

            warnings.append(
                {
                    "code": "CONFIG_NO_ENTRIES",
                    "severity": "WARNING",
                    "message": (
                        "Properties file contains "
                        "no properties."
                    ),
                }
            )

        return data, "java_properties"

    # ================================================================
    # PROPERTIES CONTINUATIONS
    # ================================================================

    @classmethod
    def _join_continuations(
        cls,
        physical: list[str],
        file_name: str,
    ) -> list[tuple[int, str]]:

        result: list[tuple[int, str]] = []

        buffer = ""
        start = 0

        for number, raw in enumerate(
            physical,
            1,
        ):

            line = raw.rstrip(
                "\r\n"
            )

            if len(line) > cls.MAX_LINE_LENGTH:

                raise FileParsingError(
                    f"Line {number} exceeds "
                    f"maximum length: "
                    f"{file_name}"
                )

            if not buffer:

                start = number

            slash_count = 0

            for char in reversed(line):

                if char == "\\":
                    slash_count += 1

                else:
                    break

            if slash_count % 2:

                buffer += line[:-1]

            else:

                buffer += line

                result.append(
                    (
                        start,
                        buffer,
                    )
                )

                buffer = ""

        if buffer:

            raise FileParsingError(
                "Properties file ends with "
                "an incomplete continuation: "
                f"{file_name}"
            )

        return result

    # ================================================================
    # PROPERTIES SPLIT
    # ================================================================

    @staticmethod
    def _split_property(
        line: str,
    ) -> tuple[str | None, str]:

        escaped = False

        for i, char in enumerate(line):

            if escaped:

                escaped = False
                continue

            if char == "\\":

                escaped = True
                continue

            if (
                char in {"=", ":"}
                or char.isspace()
            ):

                key = line[:i]

                rest = line[i:].lstrip()

                if (
                    rest.startswith("=")
                    or rest.startswith(":")
                ):

                    rest = rest[1:].lstrip()

                return key, rest

        return line, ""

    # ================================================================
    # PROPERTIES ESCAPES
    # ================================================================

    @staticmethod
    def _decode_escapes(
        value: str,
    ) -> str:

        simple = {
            "t": "\t",
            "n": "\n",
            "r": "\r",
            "f": "\f",
            "\\": "\\",
            " ": " ",
            ":": ":",
            "=": "=",
            "#": "#",
            "!": "!",
        }

        result: list[str] = []

        i = 0

        while i < len(value):

            if value[i] != "\\":

                result.append(
                    value[i]
                )

                i += 1

                continue

            if i + 1 >= len(value):

                result.append("\\")

                i += 1

                continue

            escaped = value[
                i + 1
            ]

            if (
                escaped == "u"
                and i + 5 < len(value)
            ):

                raw_codepoint = value[
                    i + 2:i + 6
                ]

                try:

                    result.append(
                        chr(
                            int(
                                raw_codepoint,
                                16,
                            )
                        )
                    )

                    i += 6

                    continue

                except ValueError:

                    pass

            if escaped in simple:

                result.append(
                    simple[escaped]
                )

                i += 2

            else:

                result.extend(
                    [
                        "\\",
                        escaped,
                    ]
                )

                i += 2

        return "".join(result)

    # ================================================================
    # TOML
    #
    # EXISTING BEHAVIOR PRESERVED
    # ================================================================

    @classmethod
    def _parse_toml(
        cls,
        file_path: Path,
    ) -> tuple[dict[str, Any], str]:

        try:

            with file_path.open(
                "rb"
            ) as fh:

                data = tomllib.load(
                    fh
                )

        except (
            tomllib.TOMLDecodeError,
            UnicodeDecodeError,
            OSError,
        ) as exc:

            raise FileParsingError(
                f"Invalid TOML configuration: "
                f"{file_path.name}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):

            raise FileParsingError(
                "TOML root must be a table."
            )

        return data, "tomllib"

    # ================================================================
    # STRUCTURE VALIDATION
    # ================================================================

    @classmethod
    def _validate_structure(
        cls,
        data: Any,
        file_path: Path,
    ) -> None:

        if cls._count(data) > cls.MAX_ENTRIES:

            raise FileParsingError(
                "Configuration exceeds "
                f"{cls.MAX_ENTRIES} entries: "
                f"{file_path.name}"
            )

        if cls._depth(data) > cls.MAX_NESTING_DEPTH:

            raise FileParsingError(
                "Configuration exceeds nesting "
                f"depth {cls.MAX_NESTING_DEPTH}: "
                f"{file_path.name}"
            )

    # ================================================================
    # COUNT
    # ================================================================

    @classmethod
    def _count(
        cls,
        value: Any,
    ) -> int:

        if isinstance(
            value,
            dict,
        ):

            return sum(
                1 + cls._count(v)
                for v in value.values()
            )

        if isinstance(
            value,
            list,
        ):

            return sum(
                1 + cls._count(v)
                for v in value
            )

        return 1

    # ================================================================
    # DEPTH
    # ================================================================

    @classmethod
    def _depth(
        cls,
        value: Any,
        current: int = 0,
    ) -> int:

        if (
            isinstance(value, dict)
            and value
        ):

            return max(
                cls._depth(
                    v,
                    current + 1,
                )
                for v in value.values()
            )

        if (
            isinstance(value, list)
            and value
        ):

            return max(
                cls._depth(
                    v,
                    current + 1,
                )
                for v in value
            )

        return current

    # ================================================================
    # LINE LENGTH
    # ================================================================

    @classmethod
    def _validate_line_lengths(
        cls,
        fh: Any,
    ) -> None:

        for number, line in enumerate(
            fh,
            1,
        ):

            if len(
                line.rstrip(
                    "\r\n"
                )
            ) > cls.MAX_LINE_LENGTH:

                raise FileParsingError(
                    "Configuration line exceeds "
                    "maximum length at line "
                    f"{number}."
                )

    # ================================================================
    # SCALAR NORMALIZATION
    # ================================================================

    @staticmethod
    def _normalize_scalar(
        value: str,
    ) -> str:

        return (
            value
            .replace(
                "\r\n",
                "\n",
            )
            .replace(
                "\r",
                "\n",
            )
            .replace(
                "\u00a0",
                " ",
            )
            .strip()
        )

    # ================================================================
    # METADATA
    # ================================================================

    @classmethod
    def _build_metadata(
        cls,
        file_path: Path,
        extension: str,
        data: dict[str, Any],
        strategy: str,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:

        metadata: dict[str, Any] = {
            "file_name": file_path.name,
            "file_extension": extension,
            "parser": cls.parser_name,
            "format": "config",
            "structure": (
                "hierarchical_configuration"
            ),
            "file_size_bytes": (
                file_path.stat().st_size
            ),
            "entry_count": cls._count(data),
            "extraction_strategies": [
                strategy
            ],
            "warnings": warnings,
        }

        if extension == ".properties":

            metadata[
                "property_count"
            ] = len(data)

            metadata[
                "properties"
            ] = list(data.keys())

        else:

            metadata[
                "section_count"
            ] = len(data)

            metadata[
                "sections"
            ] = list(data.keys())

        return metadata