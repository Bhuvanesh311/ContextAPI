import logging
from pathlib import Path
from datetime import datetime, timezone
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult
from app.knowledge.parsing.enums import ParserFormat

logger = logging.getLogger(__name__)

class FormatIdentificationHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        checkpoint = dict(context.run.checkpoint_data or {})
        detected = checkpoint.get("detected_format")
        
        parser_format = None
        
        if detected:
            normalized = str(detected).strip().lower()
            source_code_formats = {
                "python", "javascript", "typescript", "java", "c", "cpp",
                "csharp", "go", "rust", "php", "ruby", "swift", "kotlin", "source_code",
            }
            if normalized in source_code_formats:
                parser_format = ParserFormat.SOURCE_CODE
            else:
                aliases = {
                    "markdown": ParserFormat.MARKDOWN,
                    "md": ParserFormat.MARKDOWN,
                    "text": ParserFormat.TXT,
                    "txt": ParserFormat.TXT,
                    "configuration": ParserFormat.CONFIG,
                    "config": ParserFormat.CONFIG,
                }
                if normalized in aliases:
                    parser_format = aliases[normalized]
                else:
                    try:
                        parser_format = ParserFormat(normalized)
                    except ValueError:
                        pass
                        
        if not parser_format:
            extension = (
                context.document_version.file_extension
                or Path(context.document_version.file_name).suffix
                or ""
            ).strip().lower()
            
            if extension and not extension.startswith("."):
                extension = f".{extension}"
                
            extension_map = {
                ".pdf": ParserFormat.PDF,
                ".docx": ParserFormat.DOCX,
                ".txt": ParserFormat.TXT,
                ".md": ParserFormat.MARKDOWN,
                ".json": ParserFormat.JSON,
                ".yaml": ParserFormat.YAML,
                ".yml": ParserFormat.YAML,
                ".xml": ParserFormat.XML,
                ".csv": ParserFormat.CSV,
                ".ini": ParserFormat.CONFIG,
                ".conf": ParserFormat.CONFIG,
                ".cfg": ParserFormat.CONFIG,
                ".properties": ParserFormat.CONFIG,
                ".toml": ParserFormat.CONFIG,
                ".log": ParserFormat.LOG,
                ".py": ParserFormat.SOURCE_CODE,
                ".js": ParserFormat.SOURCE_CODE,
                ".ts": ParserFormat.SOURCE_CODE,
                ".java": ParserFormat.SOURCE_CODE,
                ".go": ParserFormat.SOURCE_CODE,
                ".cs": ParserFormat.SOURCE_CODE,
                ".php": ParserFormat.SOURCE_CODE,
                ".c": ParserFormat.SOURCE_CODE,
                ".cpp": ParserFormat.SOURCE_CODE,
                ".rs": ParserFormat.SOURCE_CODE,
                ".sql": ParserFormat.SQL,
                ".jsx": ParserFormat.SOURCE_CODE,
                ".tsx": ParserFormat.SOURCE_CODE,
                ".h": ParserFormat.SOURCE_CODE,
                ".hpp": ParserFormat.SOURCE_CODE,
                ".cc": ParserFormat.SOURCE_CODE,
                ".cxx": ParserFormat.SOURCE_CODE,
                ".hh": ParserFormat.SOURCE_CODE,
                ".rb": ParserFormat.SOURCE_CODE,
                ".swift": ParserFormat.SOURCE_CODE,
                ".kt": ParserFormat.SOURCE_CODE,
                ".kts": ParserFormat.SOURCE_CODE,
                ".scala": ParserFormat.SOURCE_CODE,
                ".sh": ParserFormat.SOURCE_CODE,
                ".bash": ParserFormat.SOURCE_CODE,
                ".lua": ParserFormat.SOURCE_CODE,
                ".r": ParserFormat.SOURCE_CODE,
                ".dart": ParserFormat.SOURCE_CODE,
                ".vb": ParserFormat.SOURCE_CODE,
                ".rst": ParserFormat.TXT,
                ".tsv": ParserFormat.TXT,
                ".pptx": ParserFormat.PPTX,
                ".xlsx": ParserFormat.XLSX,
                ".html": ParserFormat.HTML,
                ".htm": ParserFormat.HTML,
                ".png": ParserFormat.IMAGE,
                ".jpg": ParserFormat.IMAGE,
                ".jpeg": ParserFormat.IMAGE,
                ".bmp": ParserFormat.IMAGE,
                ".tif": ParserFormat.IMAGE,
                ".tiff": ParserFormat.IMAGE,
                ".webp": ParserFormat.IMAGE,
                ".doc": ParserFormat.LEGACY_OFFICE,
                ".rtf": ParserFormat.LEGACY_OFFICE,
                ".odt": ParserFormat.LEGACY_OFFICE,
                ".xls": ParserFormat.LEGACY_OFFICE,
                ".ods": ParserFormat.LEGACY_OFFICE,
                ".ppt": ParserFormat.LEGACY_OFFICE,
                ".odp": ParserFormat.LEGACY_OFFICE,
            }
            parser_format = extension_map.get(extension)
            
            if not parser_format:
                return IngestionStageResult(
                    success=False,
                    error_message=f"No parser format could be resolved for extension '{extension}'."
                )

        checkpoint.update({
            "stage": IngestionStage.FORMAT_IDENTIFICATION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "parser_format": parser_format.value,
        })
        
        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
