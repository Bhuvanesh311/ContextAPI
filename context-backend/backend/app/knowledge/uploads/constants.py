
# Upload Limits


# Maximum number of files allowed in a single upload request
MAX_FILES_PER_UPLOAD = 10

# Maximum allowed file size (500 MB)
MAX_FILE_SIZE = 500 * 1024 * 1024

# Maximum filename length
MAX_FILENAME_LENGTH = 255


# Supported File Extensions

ALLOWED_FILE_EXTENSIONS = {
    # Documentation
    ".pdf",
    ".docx",
    ".txt",
    ".md",

    # API Specifications
    ".json",
    ".yaml",
    ".yml",

    # Configuration Files
    ".ini",
    ".conf",
    ".cfg",
    ".properties",
    ".toml",

    # Logs
    ".log",

    # Source Code
    ".py",
    ".js",
    ".ts",
    ".java",
    ".go",
    ".cs",
    ".php",
    ".c",
    ".cpp",
    ".rs",

    # Data Files
    ".xml",
    ".csv",
    ".sql",

    # Office / OpenDocument / RTF / web
    ".pptx",
    ".xlsx",
    ".doc",
    ".xls",
    ".ppt",
    ".rtf",
    ".odt",
    ".ods",
    ".odp",
    ".html",
    ".htm",
    ".rst",
    ".tsv",

    # Images (read with OCR)
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",

    # More source code
    ".jsx", ".tsx", ".h", ".hpp", ".cc", ".cxx", ".hh", ".rb", ".swift",
    ".kt", ".kts", ".scala", ".sh", ".bash", ".lua", ".r", ".dart", ".vb",

    #zip
    ".zip",
    ".tar",
}


# Supported MIME Types
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/json",
    "application/xml",

    "text/plain",
    "text/markdown",
    "text/csv",

    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",

    "application/json",
    "application/yaml",
    "text/yaml",
    "application/xml",
    "text/xml",

    "text/x-python",
    "text/plain",
    "text/javascript",
    "application/javascript",
    "text/x-java-source",
    "text/x-c",
    "text/x-c++",
    "application/sql",
    "text/plain",

    "application/zip",
    "application/x-zip-compressed",
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
}


# Blocked Extensions

BLOCKED_FILE_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".com",
    ".msi",
    ".scr",
    ".vbs",
    ".ps1",
    ".jar",
    ".apk",
    ".ipa",
}


# Reserved Filenames

RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
}


# Hashing

DEFAULT_HASH_ALGORITHM = "sha256"


# Archive Security Limits (Future Security Module)

MAX_ARCHIVE_DEPTH = 5

MAX_ARCHIVE_FILES = 1000

MAX_COMPRESSION_RATIO = 100


# Temporary Storage
TEMP_UPLOAD_DIRECTORY = "storage/temp"

DOCUMENT_STORAGE_DIRECTORY = "storage/documents"