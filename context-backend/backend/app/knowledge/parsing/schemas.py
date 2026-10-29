from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.knowledge.parsing.enums import (
    ParserFormat,
    ParserStatus,
)


@dataclass(slots=True)
class SandboxJob:

    job_id: str
    input_file: Path
    parser_command: list[str]
    request: ParsingRequest


@dataclass(slots=True)
class SandboxResult:

    job_id: str
    success: bool
    exit_code: int
    output: bytes
    error: bytes


class ParsingRequest(BaseModel):


    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    document_id: str = Field(
        min_length=2,
        max_length=100,
    )

    project_id: str = Field(
        min_length=1,
        max_length=100,
    )

    upload_id: str = Field(
        min_length=1,
        max_length=100,
    )

    original_filename: str = Field(
        min_length=1,
        max_length=255,
    )

    extension: str = Field(
        min_length=1,
        max_length=20,
    )

    mime_type: str = Field(
        min_length=1,
        max_length=255,
    )

    detected_format: ParserFormat

    size_bytes: int = Field(
        ge=0,
    )

    checksum: str = Field(
        min_length=1,
        max_length=128,
    )
    
    quarantine_bucket: str = Field(
        min_length=1,
        max_length=255,
    )

    source_object_key: str = Field(
        min_length=1,
        max_length=1500,
    )

    parsed_bucket: str = Field(
        min_length=1,
        max_length=255,
    )

    parsed_object_key: str = Field(
        min_length=1,
        max_length=1500,
    )

    status: ParserStatus

    @model_validator(mode="after")
    def validate_document_status(self) -> ParsingRequest:


        if self.status != ParserStatus.READY_FOR_PARSING:
            raise ValueError(
                f"Document must be in "
                f"{ParserStatus.READY_FOR_PARSING} status "
                f"before parsing."
            )

        return self


class NormalizedDocument(BaseModel):


    model_config = ConfigDict(
        extra="forbid",
    )

    document_id: str

    file_name: str

    source_format: ParserFormat

    content: str = ""

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    page_count: int | None = None

    character_count: int = 0

    word_count: int = 0

    mime_type: str | None = None


class ParserResult(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    success: bool

    parser_name: str

    document: NormalizedDocument | None = None

    error_message: str | None = None
