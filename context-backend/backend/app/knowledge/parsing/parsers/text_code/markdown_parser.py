from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
import mistune

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


class MarkdownParser(BaseParser):
    """
    ContextAPI Markdown parser.

    Pipeline:

        .md
         ↓
        UTF-8 read
         ↓
        Mistune tokenization
         ↓
        structural analysis
         ↓
        normalized JSON-compatible representation
         ↓
        NormalizedDocument

    This parser ONLY accepts Markdown files.

    It does not:
        - execute embedded code
        - evaluate HTML
        - resolve external URLs
        - execute plugins
        - access the network
    """

    parser_name = "markdown"

    SUPPORTED_EXTENSIONS = {
        ".md",
    }

    MAX_FILE_SIZE = 256 * 1024 * 1024
    MAX_LINES = 5_000_000
    MAX_TOKENS = 2_000_000

    # ============================================================
    # FORMAT SUPPORT
    # ============================================================

    @classmethod
    def supports(cls, file_path: Path) -> bool:
        return (
            Path(file_path).suffix.lower()
            in cls.SUPPORTED_EXTENSIONS
        )

    # ============================================================
    # MAIN PARSER
    # ============================================================

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:

        file_path = Path(file_path)

        self._validate_file(file_path)

        logger.info(
            "Starting Markdown parsing: %s",
            file_path.name,
        )

        try:
            content = self._read_file(
                file_path
            )

            content = self._normalize_content(
                content
            )

            tokens = self._tokenize(
                content=content,
                file_name=file_path.name,
            )

            structure = self._analyze_structure(
                tokens=tokens,
                content=content,
            )

            structured_document = (
                self._build_structured_document(
                    file_path=file_path,
                    content=content,
                    structure=structure,
                )
            )

            structured_json = json.dumps(
                structured_document,
                ensure_ascii=False,
            )

            metadata = {
                "parser": self.parser_name,
                "format": "markdown",
                "file_name": file_path.name,
                "file_extension": ".md",
                "character_count": len(content),
                "line_count": (
                    len(content.splitlines())
                    if content
                    else 0
                ),
                "word_count": len(
                    content.split()
                ),
                "token_count": len(tokens),
                "heading_count": structure[
                    "heading_count"
                ],
                "paragraph_count": structure[
                    "paragraph_count"
                ],
                "code_block_count": structure[
                    "code_block_count"
                ],
                "list_count": structure[
                    "list_count"
                ],
                "link_count": structure[
                    "link_count"
                ],
                "image_count": structure[
                    "image_count"
                ],
                "structured_json": structured_json,
            }

            logger.info(
                "Markdown parsing completed: %s",
                file_path.name,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.MARKDOWN,
                content=content,
                metadata=metadata,
                page_count=0,
                character_count=len(content),
                word_count=len(content.split()),
                mime_type=request.mime_type,
            )

        except FileParsingError:
            raise

        except Exception as exc:

            logger.exception(
                "Unexpected Markdown parser failure: %s",
                file_path.name,
            )

            raise FileParsingError(
                "MARKDOWN_PARSER_UNEXPECTED_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

    # ============================================================
    # FILE VALIDATION
    # ============================================================

    def _validate_file(
        self,
        file_path: Path,
    ) -> None:

        if not file_path.exists():
            raise SourceFileNotFoundError(
                f"Markdown file not found: {file_path}"
            )

        if not file_path.is_file():
            raise FileParsingError(
                f"Markdown path is not a file: "
                f"{file_path}"
            )

        if not self.supports(file_path):
            raise FileParsingError(
                "Unsupported Markdown file extension: "
                f"{file_path.suffix or '<none>'}. "
                "Only .md files are supported."
            )

        try:
            size = file_path.stat().st_size

        except OSError as exc:

            raise FileParsingError(
                "MARKDOWN_FILE_STAT_FAILED | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        if size == 0:
            raise FileParsingError(
                f"Markdown file is empty: "
                f"{file_path.name}"
            )

        if size > self.MAX_FILE_SIZE:
            raise FileParsingError(
                "Markdown file exceeds maximum size "
                f"of {self.MAX_FILE_SIZE} bytes: "
                f"{file_path.name}"
            )

    # ============================================================
    # FILE READING
    # ============================================================

    @staticmethod
    def _read_file(
        file_path: Path,
    ) -> str:

        try:
            return file_path.read_text(
                encoding="utf-8-sig"
            )

        except UnicodeDecodeError as exc:

            raise FileParsingError(
                "MARKDOWN_ENCODING_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        except OSError as exc:

            raise FileParsingError(
                "MARKDOWN_FILE_READ_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

    # ============================================================
    # CONTENT NORMALIZATION
    # ============================================================

    def _normalize_content(
        self,
        content: str,
    ) -> str:

        content = (
            content
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        line_count = (
            len(content.splitlines())
            if content
            else 0
        )

        if line_count > self.MAX_LINES:

            raise FileParsingError(
                "Markdown file exceeds maximum "
                f"line count of {self.MAX_LINES}"
            )

        return content

    # ============================================================
    # MISTUNE TOKENIZATION
    # ============================================================

    @staticmethod
    def _tokenize(
        *,
        content: str,
        file_name: str,
    ) -> list[dict[str, Any]]:

        try:
            markdown = mistune.create_markdown(
                escape=False
            )

            result = markdown(
                content
            )

        except Exception as exc:

            raise FileParsingError(
                "MARKDOWN_TOKENIZATION_FAILED | "
                f"file={file_name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        # Mistune's default renderer produces HTML.
        # We deliberately do not use the rendered HTML
        # as the canonical representation.
        #
        # Instead, perform structural extraction directly
        # from the original Markdown source.

        del result

        tokens = []

        lines = content.splitlines()

        for index, line in enumerate(
            lines,
            start=1,
        ):

            stripped = line.strip()

            if not stripped:
                continue

            token_type = (
                MarkdownParser._classify_line(
                    stripped
                )
            )

            tokens.append(
                {
                    "type": token_type,
                    "line": index,
                    "text": line,
                }
            )

        if len(tokens) > MarkdownParser.MAX_TOKENS:

            raise FileParsingError(
                "Markdown token count exceeds "
                f"maximum of "
                f"{MarkdownParser.MAX_TOKENS}"
            )

        return tokens

    # ============================================================
    # LINE CLASSIFICATION
    # ============================================================

    @staticmethod
    def _classify_line(
        line: str,
    ) -> str:

        if line.startswith("```"):
            return "fenced_code"

        if line.startswith("#"):
            return "heading"

        if (
            line.startswith("- ")
            or line.startswith("* ")
            or line.startswith("+ ")
        ):
            return "unordered_list_item"

        if len(line) >= 3:
            if (
                line[0].isdigit()
                and ". " in line[:5]
            ):
                return "ordered_list_item"

        if (
            line.startswith("> ")
            or line == ">"
        ):
            return "blockquote"

        if (
            line.startswith("---")
            or line.startswith("***")
            or line.startswith("___")
        ):
            return "thematic_break"

        if line.startswith("!["):
            return "image"

        if line.startswith("["):
            return "link"

        return "text"

    # ============================================================
    # STRUCTURE ANALYSIS
    # ============================================================

    def _analyze_structure(
        self,
        *,
        tokens: list[dict[str, Any]],
        content: str,
    ) -> dict[str, Any]:

        headings = []
        paragraphs = []
        code_blocks = []
        lists = []
        links = []
        images = []

        in_code_block = False
        current_code_block = None

        lines = content.splitlines()

        for token in tokens:

            token_type = token["type"]
            line_number = token["line"]
            text = token["text"]

            if token_type == "fenced_code":

                if not in_code_block:

                    in_code_block = True

                    current_code_block = {
                        "start_line": line_number,
                        "language": (
                            text[3:].strip()
                            or None
                        ),
                        "content": [],
                    }

                else:

                    in_code_block = False

                    if current_code_block:
                        current_code_block[
                            "end_line"
                        ] = line_number

                        current_code_block[
                            "content"
                        ] = "\n".join(
                            current_code_block[
                                "content"
                            ]
                        )

                        code_blocks.append(
                            current_code_block
                        )

                        current_code_block = None

                continue

            if in_code_block:

                if current_code_block:
                    current_code_block[
                        "content"
                    ].append(text)

                continue

            if token_type == "heading":

                level = len(text) - len(text.lstrip("#"))

                heading_text = text[
                    level:
                ].strip()

                headings.append(
                    {
                        "level": level,
                        "line": line_number,
                        "text": heading_text,
                    }
                )

            elif token_type in {
                "unordered_list_item",
                "ordered_list_item",
            }:

                lists.append(
                    {
                        "type": token_type,
                        "line": line_number,
                        "text": text,
                    }
                )

            elif token_type == "image":

                images.append(
                    {
                        "line": line_number,
                        "text": text,
                    }
                )

            elif token_type == "link":

                links.append(
                    {
                        "line": line_number,
                        "text": text,
                    }
                )

            elif token_type == "text":

                paragraphs.append(
                    {
                        "line": line_number,
                        "text": text,
                    }
                )

        if in_code_block and current_code_block:

            current_code_block[
                "end_line"
            ] = len(lines)

            current_code_block[
                "content"
            ] = "\n".join(
                current_code_block[
                    "content"
                ]
            )

            code_blocks.append(
                current_code_block
            )

        return {
            "heading_count": len(headings),
            "paragraph_count": len(paragraphs),
            "code_block_count": len(code_blocks),
            "list_count": len(lists),
            "link_count": len(links),
            "image_count": len(images),
            "headings": headings,
            "paragraphs": paragraphs,
            "code_blocks": code_blocks,
            "lists": lists,
            "links": links,
            "images": images,
        }

    # ============================================================
    # STRUCTURED DOCUMENT
    # ============================================================

    def _build_structured_document(
        self,
        *,
        file_path: Path,
        content: str,
        structure: dict[str, Any],
    ) -> dict[str, Any]:

        return {
            "type": "markdown_document",

            "source": {
                "file_name": file_path.name,
                "extension": ".md",
            },

            "statistics": {
                "character_count": len(
                    content
                ),
                "line_count": (
                    len(content.splitlines())
                    if content
                    else 0
                ),
                "word_count": len(
                    content.split()
                ),
                "heading_count": structure[
                    "heading_count"
                ],
                "paragraph_count": structure[
                    "paragraph_count"
                ],
                "code_block_count": structure[
                    "code_block_count"
                ],
                "list_count": structure[
                    "list_count"
                ],
                "link_count": structure[
                    "link_count"
                ],
                "image_count": structure[
                    "image_count"
                ],
            },

            "headings": structure[
                "headings"
            ],

            "paragraphs": structure[
                "paragraphs"
            ],

            "code_blocks": structure[
                "code_blocks"
            ],

            "lists": structure[
                "lists"
            ],

            "links": structure[
                "links"
            ],

            "images": structure[
                "images"
            ],
        }