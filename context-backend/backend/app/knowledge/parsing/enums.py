from enum import Enum

class SandboxState(str, Enum):
    CREATING = "creating"
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    CLEANING = "cleaning"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    RECYCLING = "recycling"
    DESTROYED = "destroyed"

class ParserStatus(str, Enum):

    READY_FOR_PARSING = "READY_FOR_PARSING"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"

class ParserFormat(str, Enum):

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    XML = "xml"
    CSV = "csv"
    CONFIG = "config"
    LOG = "log"
    SOURCE_CODE = "source_code"
    SQL = "sql"
    PPTX = "pptx"
    XLSX = "xlsx"
    HTML = "html"
    IMAGE = "image"
    LEGACY_OFFICE = "legacy_office"