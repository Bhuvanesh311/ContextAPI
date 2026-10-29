from pydantic import BaseModel, Field
from typing import Any, Generic, Optional, TypeVar
from pydantic.generics import GenericModel


T = TypeVar("T")

class MessageResponse(BaseModel):
    message: str = Field(
    ...,
    description="Human-readable response message."
)

class SuccessResponse(GenericModel, Generic[T]):
    success: bool = Field(
        default=True,
        description="Indicates whether the request was successful."
    )

    message: str = Field(
        ...,
        description="Human-readable success message."
    )

    data: Optional[T] = Field(
        default=None,
        description="Response payload."
    )

class ErrorResponse(BaseModel):

    success: bool = Field(
        default=False,
        description="Indicates the request failed."
    )

    error_code: str = Field(
        ...,
        description="Machine-readable error code."
    )

    message: str = Field(
        ...,
        description="Human-readable error message."
    )

    details: Optional[Any] = Field(
        default=None,
        description="Additional error details."
    )


class PaginationResponse(GenericModel, Generic[T]):
    success: bool = Field(
        default=True,
        description="Indicates the request was successful."
    )

    message: str = Field(
        ...,
        description="Human-readable response message."
    )

    data: list[T] = Field(
        default_factory=list,
        description="List of returned items."
    )

    page: int = Field(
        ...,
        ge=1,
        description="Current page number."
    )

    page_size: int = Field(
        ...,
        ge=1,
        description="Number of items per page."
    )

    total_items: int = Field(
        ...,
        ge=0,
        description="Total number of items."
    )

    total_pages: int = Field(
        ...,
        ge=0,
        description="Total number of pages."
    )