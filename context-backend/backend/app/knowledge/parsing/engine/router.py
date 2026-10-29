from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.schemas import ParsingRequest
from app.knowledge.parsing.exceptions import UnsupportedFileTypeError

from app.knowledge.parsing.parsers.document.pdf import PDFParser
from app.knowledge.parsing.parsers.document.docx import DOCXParser
from app.knowledge.parsing.parsers.structured.json_parser import JSONParser
from app.knowledge.parsing.parsers.structured.yaml_parser import YAMLParser
from app.knowledge.parsing.parsers.structured.xml_parser import XMLParser
from app.knowledge.parsing.parsers.structured.csv_parser import CSVParser
from app.knowledge.parsing.parsers.structured.config_parser import ConfigParser
from app.knowledge.parsing.parsers.text_code.text_parser import TextParser
from app.knowledge.parsing.parsers.text_code.markdown_parser import MarkdownParser
from app.knowledge.parsing.parsers.text_code.log_parser import LogParser
from app.knowledge.parsing.parsers.text_code.source_parser import SourceCodeParser
from app.knowledge.parsing.parsers.text_code.sql_parser import SQLParser
from app.knowledge.parsing.parsers.document.extra_formats import (
    HTMLParser,
    ImageParser,
    LegacyOfficeParser,
    PPTXParser,
    XLSXParser,
)


class ParserRouter:

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {
            ".pdf": PDFParser(),
            ".docx": DOCXParser(),

            ".json": JSONParser(),
            ".yaml": YAMLParser(),
            ".yml": YAMLParser(),
            ".xml": XMLParser(),
            ".csv": CSVParser(),

            ".ini": ConfigParser(),
            ".conf": ConfigParser(),
            ".cfg": ConfigParser(),
            ".properties": ConfigParser(),
            ".toml": ConfigParser(),

            ".txt": TextParser(),
            ".md": MarkdownParser(),
            ".log": LogParser(),

            ".py": SourceCodeParser(),
            ".js": SourceCodeParser(),
            ".ts": SourceCodeParser(),
            ".java": SourceCodeParser(),
            ".go": SourceCodeParser(),
            ".cs": SourceCodeParser(),
            ".php": SourceCodeParser(),
            ".c": SourceCodeParser(),
            ".cpp": SourceCodeParser(),
            ".rs": SourceCodeParser(),

            ".sql": SQLParser(),
            ".jsx": SourceCodeParser(),
            ".tsx": SourceCodeParser(),
            ".h": SourceCodeParser(),
            ".hpp": SourceCodeParser(),
            ".cc": SourceCodeParser(),
            ".cxx": SourceCodeParser(),
            ".hh": SourceCodeParser(),
            ".rb": SourceCodeParser(),
            ".swift": SourceCodeParser(),
            ".kt": SourceCodeParser(),
            ".kts": SourceCodeParser(),
            ".scala": SourceCodeParser(),
            ".sh": SourceCodeParser(),
            ".bash": SourceCodeParser(),
            ".lua": SourceCodeParser(),
            ".r": SourceCodeParser(),
            ".dart": SourceCodeParser(),
            ".vb": SourceCodeParser(),

            ".rst": TextParser(),
            ".tsv": TextParser(),

            ".pptx": PPTXParser(),
            ".xlsx": XLSXParser(),
            ".html": HTMLParser(),
            ".htm": HTMLParser(),
            ".png": ImageParser(),
            ".jpg": ImageParser(),
            ".jpeg": ImageParser(),
            ".bmp": ImageParser(),
            ".tif": ImageParser(),
            ".tiff": ImageParser(),
            ".webp": ImageParser(),
            ".doc": LegacyOfficeParser(),
            ".rtf": LegacyOfficeParser(),
            ".odt": LegacyOfficeParser(),
            ".xls": LegacyOfficeParser(),
            ".ods": LegacyOfficeParser(),
            ".ppt": LegacyOfficeParser(),
            ".odp": LegacyOfficeParser(),
        }

    def get_parser(
        self,
        request: ParsingRequest,
    ) -> BaseParser:
        extension = request.extension.strip().lower()

        if not extension.startswith("."):
            extension = f".{extension}"

        parser = self._parsers.get(extension)

        if parser is None:
            raise UnsupportedFileTypeError(
                f"Unsupported file extension: {request.extension}"
            )

        return parser
