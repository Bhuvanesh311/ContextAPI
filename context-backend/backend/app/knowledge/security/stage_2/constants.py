from enum import StrEnum



# Stage


STAGE_NAME = "archive_validation"



# Phases


PHASE_IDENTITY_METADATA = "archive_identity_metadata"
PHASE_SECURITY = "archive_security"
PHASE_EXTRACTION = "controlled_extraction"
PHASE_ORCHESTRATION = "child_file_orchestration"



# Archive Types



class ArchiveType(StrEnum):
    ZIP = "zip"
    TAR = "tar"
    TAR_GZ = "tar.gz"
    SEVEN_Z = "7z"
    RAR = "rar"


SUPPORTED_ARCHIVE_TYPES = {
    ArchiveType.ZIP,
    ArchiveType.TAR,
    ArchiveType.TAR_GZ,
    ArchiveType.SEVEN_Z,
    ArchiveType.RAR,
}



# Archive Extensions


ARCHIVE_EXTENSION_MAP = {
    ".zip": ArchiveType.ZIP,
    ".tar": ArchiveType.TAR,
    ".tar.gz": ArchiveType.TAR_GZ,
    ".tgz": ArchiveType.TAR_GZ,
    ".7z": ArchiveType.SEVEN_Z,
    ".rar": ArchiveType.RAR,
}



# Archive MIME Types


ARCHIVE_MIME_MAP = {
    "application/zip": ArchiveType.ZIP,
    "application/x-zip": ArchiveType.ZIP,
    "application/x-zip-compressed": ArchiveType.ZIP,

    "application/x-tar": ArchiveType.TAR,

    "application/gzip": ArchiveType.TAR_GZ,
    "application/x-gzip": ArchiveType.TAR_GZ,

    "application/x-7z-compressed": ArchiveType.SEVEN_Z,

    "application/vnd.rar": ArchiveType.RAR,
    "application/x-rar": ArchiveType.RAR,
    "application/x-rar-compressed": ArchiveType.RAR,
}



# Archive Security Policy


# These are policy defaults.

# Keep all archive resource limits here instead of scattering
# magic numbers throughout validators.

# We can later move deployment-specific values into Settings.


# Maximum number of entries in one archive.
MAX_ARCHIVE_ENTRIES = 10_000


# Maximum total uncompressed size:
# 1 GiB.
MAX_TOTAL_EXTRACTED_SIZE = 1 * 1024 * 1024 * 1024


# Maximum size of one extracted entry:
# 250 MiB.
MAX_SINGLE_ENTRY_SIZE = 250 * 1024 * 1024


# Maximum permitted:
#
# uncompressed_size / compressed_size
#
# This is only ONE ZIP-bomb signal.
# We will also enforce absolute extracted-size and entry limits.
MAX_COMPRESSION_RATIO = 200.0


# Maximum nested user-archive depth.
#
# outer.zip          depth 0
#     inner.zip      depth 1
#         next.zip   depth 2
#
# Anything deeper is rejected.
MAX_ARCHIVE_DEPTH = 3


# Maximum length of an individual archive entry name.
MAX_ENTRY_NAME_LENGTH = 255


# Maximum complete archive path length.
MAX_ENTRY_PATH_LENGTH = 1024


# Buffer size used during controlled extraction.
EXTRACTION_CHUNK_SIZE = 1024 * 1024  # 1 MiB



# Archive Policy


# For the initial implementation, encrypted/password-protected
# archives are rejected because Stage 2 cannot safely inspect
# their contents without credentials.
ALLOW_ENCRYPTED_ARCHIVES = False


# Links are not required for the document/RAG ingestion flow.
# Keeping them disabled removes several extraction attack paths.
ALLOW_SYMBOLIC_LINKS = False
ALLOW_HARD_LINKS = False


# Empty archives have no useful ingestion payload.
ALLOW_EMPTY_ARCHIVES = False



# Context States


CONTEXT_PENDING = "pending"
CONTEXT_PASSED = "passed"
CONTEXT_REJECTED = "rejected"
CONTEXT_ERROR = "error"

