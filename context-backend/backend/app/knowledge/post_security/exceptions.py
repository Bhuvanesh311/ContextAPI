from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    
    CONTRACT_VALIDATION = "contract_validation"
    COMPLETENESS_VALIDATION = "completeness_validation"
    STRUCTURE_VALIDATION = "structure_validation"
    NORMALIZATION = "normalization"

    PROMPT_INJECTION = "prompt_injection"
    REFERENCE_VALIDATION = "reference_validation"
    KNOWLEDGE_POISONING = "knowledge_poisoning"

    INTERNAL_ERROR = "internal_error"


class PostSecurityError(Exception):
    
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}

        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:

              return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


class ContractValidationError(PostSecurityError):

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.CONTRACT_VALIDATION,
            message,
            details=details,
        )


class CompletenessValidationError(PostSecurityError):
    
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.COMPLETENESS_VALIDATION,
            message,
            details=details,
        )


class StructureValidationError(PostSecurityError):
    
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.STRUCTURE_VALIDATION,
            message,
            details=details,
        )


class NormalizationError(PostSecurityError):
    
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.NORMALIZATION,
            message,
            details=details,
        )


class PromptInjectionError(PostSecurityError):
    
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.PROMPT_INJECTION,
            message,
            details=details,
        )


class ReferenceValidationError(PostSecurityError):
    
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.REFERENCE_VALIDATION,
            message,
            details=details,
        )


class KnowledgePoisoningError(PostSecurityError):
   
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.KNOWLEDGE_POISONING,
            message,
            details=details,
        )