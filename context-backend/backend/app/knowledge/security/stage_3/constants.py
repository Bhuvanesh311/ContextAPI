"""
Stage 3 - Format-Specific Security Validation Constants

Purpose:
    Shared constants used across the Stage 3 security validation pipeline.

Responsibilities:
    - Stage metadata
    - Validation phases
    - Validation check names
    - Supported format families
    - Validation limits
    - Security policy constants

This module intentionally contains no business logic.
"""

# Stage Information

STAGE_NAME = "stage_3"

# Stage Status

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"

# Validation Phases

PHASE_FORMAT_IDENTIFICATION = "format_identification"

PHASE_FORMAT_SECURITY = "format_security"

PHASE_PARSER_ADMISSION = "parser_admission"

# Phase A Checks

CHECK_FORMAT_DETECTION = "format_detection"

CHECK_FORMAT_CLASSIFICATION = "format_classification"

CHECK_FORMAT_VERSION = "format_version"

# Phase B Checks

CHECK_VALIDATOR_SELECTION = "validator_selection"

CHECK_FORMAT_SECURITY_VALIDATION = "format_security_validation"

# Phase C Checks

CHECK_PARSER_ADMISSION = "parser_admission"

# Supported Format Families

FORMAT_FAMILY_PDF = "pdf"

FORMAT_FAMILY_OFFICE = "office"

FORMAT_FAMILY_STRUCTURED = "structured"

FORMAT_FAMILY_TEXT = "text"

FORMAT_FAMILY_CONFIGURATION = "configuration"

FORMAT_FAMILY_SOURCE_CODE = "source_code"

SUPPORTED_FORMAT_FAMILIES = frozenset({
    FORMAT_FAMILY_PDF,
    FORMAT_FAMILY_OFFICE,
    FORMAT_FAMILY_STRUCTURED,
    FORMAT_FAMILY_TEXT,
    FORMAT_FAMILY_CONFIGURATION,
    FORMAT_FAMILY_SOURCE_CODE,
})

# Office Formats

OFFICE_EXTENSIONS = frozenset({
    ".docx",
})

# Structured Formats

STRUCTURED_EXTENSIONS = frozenset({
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".csv",
})

# Text Formats

TEXT_EXTENSIONS = frozenset({
    ".txt",
    ".md",
    ".log",
})

# Configuration Formats

CONFIGURATION_EXTENSIONS = frozenset({
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".toml",
})

# Source Code Formats

SOURCE_CODE_EXTENSIONS = frozenset({
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
    ".sql",
})

# Security Validation Limits

MAX_JSON_DEPTH = 100

MAX_XML_DEPTH = 100

MAX_CONFIGURATION_DEPTH = 50

MAX_TEXT_LINE_LENGTH = 100_000

# Generous: minified JS/CSS and embedded data blobs are legitimate source.
MAX_SOURCE_LINE_LENGTH = 5_000_000
MAX_SOURCE_TOKEN_LENGTH = 5_000_000

# Stage Decisions

DECISION_READY_FOR_SANDBOX = "ready_for_sandbox"

DECISION_REJECT = "reject"

# Generic Error Codes

ERROR_UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"

ERROR_UNKNOWN_FORMAT = "UNKNOWN_FORMAT"

ERROR_VALIDATOR_NOT_FOUND = "VALIDATOR_NOT_FOUND"

ERROR_SECURITY_VALIDATION_FAILED = "SECURITY_VALIDATION_FAILED"

ERROR_PARSER_ADMISSION_FAILED = "PARSER_ADMISSION_FAILED"