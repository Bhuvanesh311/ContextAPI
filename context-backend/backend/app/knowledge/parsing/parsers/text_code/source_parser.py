from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tree_sitter_language_pack import get_parser

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


class SourceCodeParser(BaseParser):
    """
    ContextAPI source-code parser.

    Input:
        Source-code files only.

    Output:
        NormalizedDocument containing:
            - original source text
            - parser metadata
            - structured JSON representation

    Security:
        Uploaded source code is parsed as data.
        It is NEVER imported or executed.
    """

    parser_name = "source_code"

    # ------------------------------------------------------------------
    # Supported source-code extensions
    # ------------------------------------------------------------------

    LANGUAGE_MAP: dict[str, str] = {
        ".py": "python",

        ".js": "javascript",
        ".jsx": "javascript",

        ".ts": "typescript",
        ".tsx": "tsx",

        ".java": "java",

        ".go": "go",

        ".rs": "rust",

        ".c": "c",
        ".h": "c",

        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".hh": "cpp",
        ".hxx": "cpp",

        ".cs": "c_sharp",

        ".php": "php",

        ".rb": "ruby",

        ".swift": "swift",

        ".kt": "kotlin",
        ".kts": "kotlin",

        ".scala": "scala",

        ".sh": "bash",
        ".bash": "bash",

        ".sql": "sql",

        ".lua": "lua",

        ".r": "r",

        ".dart": "dart",

        ".ex": "elixir",
        ".exs": "elixir",

        ".erl": "erlang",
        ".hrl": "erlang",

        ".fs": "fsharp",
        ".fsx": "fsharp",

        ".vb": "c_sharp",
    }

    # ------------------------------------------------------------------
    # Safety limits
    # ------------------------------------------------------------------

    MAX_FILE_SIZE = 256 * 1024 * 1024
    MAX_LINES = 5_000_000
    MAX_TREE_NODES = 2_000_000
    MAX_DECLARATIONS = 100_000

    # ------------------------------------------------------------------
    # Common declaration node types
    # ------------------------------------------------------------------

    DECLARATION_TYPES = {
        # Python
        "function_definition",
        "class_definition",

        # JavaScript / TypeScript
        "function_declaration",
        "function_expression",
        "arrow_function",
        "class_declaration",
        "method_definition",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",

        # Java
        "method_declaration",
        "constructor_declaration",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "annotation_type_declaration",

        # Go
        "function_declaration",
        "method_declaration",
        "type_declaration",

        # Rust
        "function_item",
        "struct_item",
        "enum_item",
        "trait_item",
        "impl_item",
        "type_item",
        "mod_item",

        # C / C++
        "function_definition",
        "struct_specifier",
        "class_specifier",
        "enum_specifier",

        # C#
        "method_declaration",
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "enum_declaration",

        # PHP
        "function_definition",
        "method_declaration",
        "class_declaration",
        "interface_declaration",
        "trait_declaration",

        # Ruby
        "method",
        "singleton_method",
        "class",
        "module",

        # Swift
        "function_declaration",
        "class_declaration",
        "struct_declaration",
        "protocol_declaration",
        "enum_declaration",

        # Kotlin
        "function_declaration",
        "class_declaration",
        "object_declaration",

        # Scala
        "function_definition",
        "class_definition",
        "object_definition",
        "trait_definition",

        # Bash
        "function_definition",
    }

    IDENTIFIER_TYPES = {
        "identifier",
        "type_identifier",
        "field_identifier",
        "property_identifier",
        "namespace_identifier",
    }

    # ==================================================================
    # FORMAT SUPPORT
    # ==================================================================

    @classmethod
    def supports(cls, file_path: Path) -> bool:
        """
        Return True only when the extension is supported.
        """

        return (
            Path(file_path).suffix.lower()
            in cls.LANGUAGE_MAP
        )

    # ==================================================================
    # MAIN PARSE ENTRYPOINT
    # ==================================================================

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:

        file_path = Path(file_path)

        self._validate_file(file_path)

        logger.info(
            "Starting source-code parsing: %s",
            file_path.name,
        )

        try:
            content = self._read_file(
                file_path
            )

            content = self._normalize_content(
                content
            )

            language = self._get_language(
                file_path
            )

            parser = self._initialize_parser(
                language=language,
                file_name=file_path.name,
            )

            tree = self._parse_source(
                parser=parser,
                content=content,
                language=language,
                file_name=file_path.name,
            )

            structure = self._analyze_tree(
                tree=tree,
                content=content,
                language=language,
            )

            structured_document = (
                self._build_structured_document(
                    file_path=file_path,
                    content=content,
                    language=language,
                    structure=structure,
                )
            )

            structured_json = json.dumps(
                structured_document,
                ensure_ascii=False,
            )

            metadata = {
                "parser": self.parser_name,
                "format": "source_code",

                "file_name": file_path.name,
                "file_extension": (
                    file_path.suffix.lower()
                ),

                "language": language,

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

                "tree_root_type": structure[
                    "tree_root_type"
                ],

                "tree_node_count": structure[
                    "tree_node_count"
                ],

                "syntax_error_count": structure[
                    "syntax_error_count"
                ],

                "declaration_count": structure[
                    "declaration_count"
                ],

                "declarations": structure[
                    "declarations"
                ],

                "structured_json": structured_json,
            }

            logger.info(
                "Source-code parsing completed: %s",
                file_path.name,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.SOURCE_CODE,
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
                "Unexpected source-code parser "
                "failure: %s",
                file_path.name,
            )

            raise FileParsingError(
                "SOURCE_CODE_PARSER_UNEXPECTED_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

    # ==================================================================
    # FILE VALIDATION
    # ==================================================================

    def _validate_file(
        self,
        file_path: Path,
    ) -> None:

        if not file_path.exists():

            raise SourceFileNotFoundError(
                f"Source file not found: {file_path}"
            )

        if not file_path.is_file():

            raise FileParsingError(
                f"Source path is not a file: {file_path}"
            )

        extension = file_path.suffix.lower()

        if extension not in self.LANGUAGE_MAP:

            raise FileParsingError(
                "Unsupported source-code extension: "
                f"{extension or '<none>'}"
            )

        try:
            size = file_path.stat().st_size

        except OSError as exc:

            raise FileParsingError(
                "SOURCE_FILE_STAT_FAILED | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        if size == 0:

            raise FileParsingError(
                f"Source file is empty: "
                f"{file_path.name}"
            )

        if size > self.MAX_FILE_SIZE:

            raise FileParsingError(
                "Source file exceeds maximum size "
                f"of {self.MAX_FILE_SIZE} bytes: "
                f"{file_path.name}"
            )

    # ==================================================================
    # FILE READING
    # ==================================================================

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
                "SOURCE_FILE_ENCODING_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        except OSError as exc:

            raise FileParsingError(
                "SOURCE_FILE_READ_ERROR | "
                f"file={file_path.name} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

    # ==================================================================
    # CONTENT NORMALIZATION
    # ==================================================================

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
                "SOURCE_FILE_LINE_LIMIT_EXCEEDED | "
                f"maximum_lines={self.MAX_LINES} | "
                f"actual_lines={line_count}"
            )

        return content

    # ==================================================================
    # LANGUAGE RESOLUTION
    # ==================================================================

    def _get_language(
        self,
        file_path: Path,
    ) -> str:

        extension = file_path.suffix.lower()

        language = self.LANGUAGE_MAP.get(
            extension
        )

        if language is None:

            raise FileParsingError(
                "SOURCE_LANGUAGE_NOT_CONFIGURED | "
                f"extension={extension}"
            )

        return language

    # ==================================================================
    # TREE-SITTER INITIALIZATION
    # ==================================================================

    @staticmethod
    def _initialize_parser(
        *,
        language: str,
        file_name: str,
    ) -> Any:

        try:

            parser = get_parser(
                language
            )

        except Exception as exc:

            raise FileParsingError(
                "TREE_SITTER_INITIALIZATION_FAILED | "
                f"file={file_name} | "
                f"language={language} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        if parser is None:

            raise FileParsingError(
                "TREE_SITTER_INITIALIZATION_FAILED | "
                f"file={file_name} | "
                f"language={language} | "
                "message=Parser instance is None"
            )

        return parser

    # ==================================================================
    # TREE-SITTER PARSE
    # ==================================================================

    @staticmethod
    def _parse_source(
        *,
        parser: Any,
        content: str,
        language: str,
        file_name: str,
    ) -> Any:

        try:

            source_bytes = content.encode(
                "utf-8"
            )

            tree = parser.parse(
                source_bytes
            )

        except Exception as exc:

            raise FileParsingError(
                "TREE_SITTER_PARSE_FAILED | "
                f"file={file_name} | "
                f"language={language} | "
                f"exception_type={type(exc).__name__} | "
                f"message={exc}"
            ) from exc

        if tree is None:

            raise FileParsingError(
                "TREE_SITTER_PARSE_FAILED | "
                f"file={file_name} | "
                f"language={language} | "
                "message=Parser returned None"
            )

        return tree

    # ==================================================================
    # TREE ANALYSIS
    # ==================================================================

    def _analyze_tree(
        self,
        *,
        tree: Any,
        content: str,
        language: str,
    ) -> dict[str, Any]:

        root = tree.root_node

        node_count = self._count_nodes(
            root
        )

        if node_count > self.MAX_TREE_NODES:

            raise FileParsingError(
                "TREE_NODE_LIMIT_EXCEEDED | "
                f"language={language} | "
                f"maximum_nodes={self.MAX_TREE_NODES}"
            )

        error_count = self._count_error_nodes(
            root
        )

        declarations = (
            self._find_declarations(
                root=root,
                content=content,
            )
        )

        return {
            "language": language,

            "tree_root_type": root.type,

            "tree_node_count": node_count,

            "syntax_error_count": error_count,

            "declaration_count": len(
                declarations
            ),

            "declarations": declarations,
        }

    # ==================================================================
    # NODE COUNT
    # ==================================================================

    def _count_nodes(
        self,
        root: Any,
    ) -> int:

        count = 0

        stack = [root]

        while stack:

            node = stack.pop()

            count += 1

            if count > self.MAX_TREE_NODES:

                return count

            children = getattr(
                node,
                "children",
                (),
            )

            if children:

                stack.extend(
                    children
                )

        return count

    # ==================================================================
    # SYNTAX ERROR COUNT
    # ==================================================================

    @staticmethod
    def _count_error_nodes(
        root: Any,
    ) -> int:

        count = 0

        stack = [root]

        while stack:

            node = stack.pop()

            if (
                node.type == "ERROR"
                or getattr(
                    node,
                    "is_missing",
                    False,
                )
            ):

                count += 1

            children = getattr(
                node,
                "children",
                (),
            )

            if children:

                stack.extend(
                    children
                )

        return count

    # ==================================================================
    # DECLARATION EXTRACTION
    # ==================================================================

    def _find_declarations(
        self,
        *,
        root: Any,
        content: str,
    ) -> list[dict[str, Any]]:

        declarations = []

        stack = [root]

        while (
            stack
            and len(declarations)
            < self.MAX_DECLARATIONS
        ):

            node = stack.pop()

            if node.type in self.DECLARATION_TYPES:

                declarations.append(
                    self._serialize_declaration(
                        node=node,
                        content=content,
                    )
                )

            children = getattr(
                node,
                "children",
                (),
            )

            if children:

                stack.extend(
                    reversed(children)
                )

        return declarations

    # ==================================================================
    # DECLARATION SERIALIZATION
    # ==================================================================

    def _serialize_declaration(
        self,
        *,
        node: Any,
        content: str,
    ) -> dict[str, Any]:

        start_row, start_column = (
            node.start_point
        )

        end_row, end_column = (
            node.end_point
        )

        return {
            "type": node.type,

            "name": self._extract_name(
                node=node,
                content=content,
            ),

            "start_line": start_row + 1,
            "start_column": start_column + 1,

            "end_line": end_row + 1,
            "end_column": end_column + 1,

            "text": self._node_text(
                node=node,
                content=content,
            ),
        }

    # ==================================================================
    # DECLARATION NAME
    # ==================================================================

    def _extract_name(
        self,
        *,
        node: Any,
        content: str,
    ) -> str | None:

        stack = list(
            reversed(
                getattr(
                    node,
                    "children",
                    (),
                )
            )
        )

        while stack:

            child = stack.pop()

            if child.type in self.IDENTIFIER_TYPES:

                value = self._node_text(
                    node=child,
                    content=content,
                )

                if value:

                    return value

            children = getattr(
                child,
                "children",
                (),
            )

            if children:

                stack.extend(
                    reversed(children)
                )

        return None

    # ==================================================================
    # NODE TEXT
    # ==================================================================

    @staticmethod
    def _node_text(
        *,
        node: Any,
        content: str,
    ) -> str:

        try:

            source = content.encode(
                "utf-8"
            )

            return source[
                node.start_byte:node.end_byte
            ].decode(
                "utf-8"
            )

        except (
            UnicodeDecodeError,
            AttributeError,
            TypeError,
            ValueError,
        ):

            return ""

    # ==================================================================
    # STRUCTURED JSON
    # ==================================================================

    def _build_structured_document(
        self,
        *,
        file_path: Path,
        content: str,
        language: str,
        structure: dict[str, Any],
    ) -> dict[str, Any]:

        return {
            "type": "source_code_document",

            "source": {
                "file_name": file_path.name,
                "extension": file_path.suffix.lower(),
                "language": language,
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

                "tree_root_type": structure[
                    "tree_root_type"
                ],

                "tree_node_count": structure[
                    "tree_node_count"
                ],

                "syntax_error_count": structure[
                    "syntax_error_count"
                ],

                "declaration_count": structure[
                    "declaration_count"
                ],
            },

            "declarations": structure[
                "declarations"
            ],
        }