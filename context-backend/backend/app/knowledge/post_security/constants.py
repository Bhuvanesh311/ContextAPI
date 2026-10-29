from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 4 resource limits
# ---------------------------------------------------------------------------

# Maximum characters accepted from the canonical parsed document.
MAX_DOCUMENT_CHARACTERS = 10_000_000

# Maximum number of Unicode code points examined for control-character
# validation. This is intentionally equal to the document limit.
MAX_DOCUMENT_SCAN_CHARACTERS = MAX_DOCUMENT_CHARACTERS

# Metadata is part of the untrusted parsed artifact.
MAX_METADATA_KEYS = 2_000
MAX_METADATA_SERIALIZED_BYTES = 1_000_000

# References are extracted from parsed metadata.
MAX_REFERENCES = 10_000
MAX_REFERENCE_LENGTH = 4_096

# Prevent pathological individual metadata values from consuming excessive
# memory downstream.
MAX_METADATA_VALUE_STRING_LENGTH = 100_000

# Normalized document must remain bounded.
MAX_NORMALIZED_DOCUMENT_CHARACTERS = MAX_DOCUMENT_CHARACTERS

# Current canonical parser contract.
#
# The current NormalizedDocument schema does not expose schema_version yet,
# therefore Stage 4 records the contract version internally rather than
# requiring a field that the sandbox does not currently emit.
CANONICAL_PARSED_DOCUMENT_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Unicode / control-character policy
# ---------------------------------------------------------------------------

# Explicitly forbidden characters.
FORBIDDEN_CONTROL_CODEPOINTS = {
    0x0000,  # NUL
    0x0001,
    0x0002,
    0x0003,
    0x0004,
    0x0005,
    0x0006,
    0x0007,
    0x0008,
    0x000B,  # vertical tab
    0x000C,  # form feed
    0x000E,
    0x000F,
    0x0010,
    0x0011,
    0x0012,
    0x0013,
    0x0014,
    0x0015,
    0x0016,
    0x0017,
    0x0018,
    0x0019,
    0x001A,
    0x001B,
    0x001C,
    0x001D,
    0x001E,
    0x001F,
    0x007F,
}


# ---------------------------------------------------------------------------
# Metadata keys used by the current parser
# ---------------------------------------------------------------------------

REFERENCES_METADATA_KEY = "references"

# Optional metadata keys that can be emitted by future parser versions.
SCHEMA_VERSION_METADATA_KEY = "schema_version"
PARSER_NAME_METADATA_KEY = "parser_name"
PARSER_VERSION_METADATA_KEY = "parser_version"
SOURCE_SHA256_METADATA_KEY = "source_sha256"
PROJECT_ID_METADATA_KEY = "project_id"