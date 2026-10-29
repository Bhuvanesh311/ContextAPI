
# Stage 1 - Universal Validation
 
STAGE_NAME = "universal_validation"
STAGE_NUMBER = 1


# Phase Names
 
PHASE_IDENTITY_METADATA = "identity_metadata"
PHASE_INTEGRITY_TRUST = "integrity_trust"
PHASE_SECURITY = "security"


# Validation Status
 
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"


# File Classification
 
FILE_TYPE_TEXT = "text"
FILE_TYPE_BINARY = "binary"
FILE_TYPE_UNKNOWN = "unknown"


# Hashing
 
HASH_ALGORITHM = "sha256"

HASH_CHUNK_SIZE = 1024 * 1024  # 1 MiB


# MIME Detection
 
MIME_SAMPLE_SIZE = 8192  # 8 KiB

UNKNOWN_MIME_TYPE = "application/octet-stream"


# Encoding Detection
 
ENCODING_SAMPLE_SIZE = 64 * 1024  # 64 KiB

MIN_ENCODING_CONFIDENCE = 0.70

DEFAULT_TEXT_ENCODING = "utf-8"


# Binary / Text Detection
 
CONTENT_SAMPLE_SIZE = 8192  # 8 KiB

NULL_BYTE = b"\x00"


# Entropy Analysis
 
ENTROPY_SAMPLE_SIZE = 64 * 1024  # 64 KiB

ENTROPY_MIN = 0.0
ENTROPY_MAX = 8.0

ENTROPY_NORMAL = "normal"
ENTROPY_HIGH = "high"
ENTROPY_SUSPICIOUS = "suspicious"

HIGH_ENTROPY_THRESHOLD = 7.0
SUSPICIOUS_ENTROPY_THRESHOLD = 7.8


# Malware Scanning
 
MALWARE_SCAN_CLEAN = "clean"
MALWARE_SCAN_INFECTED = "infected"
MALWARE_SCAN_ERROR = "error"

CLAMAV_HOST = "127.0.0.1"
CLAMAV_PORT = 3310
CLAMAV_TIMEOUT = 30


# Duplicate Detection
 
DUPLICATE_NOT_FOUND = "not_found"
DUPLICATE_FOUND = "found"

DUPLICATE_CACHE_PREFIX = "stage1:duplicate:"


# Storage Verification
 
STORAGE_VERIFIED = "verified"
STORAGE_MISSING = "missing"
STORAGE_SIZE_MISMATCH = "size_mismatch"
STORAGE_HASH_MISMATCH = "hash_mismatch"
STORAGE_UNREADABLE = "unreadable"


# Audit

AUDIT_STAGE = "stage_1"

AUDIT_RESULT_PASS = "pass"
AUDIT_RESULT_FAIL = "fail"
AUDIT_RESULT_ERROR = "error"
AUDIT_RESULT_SKIP = "skip"