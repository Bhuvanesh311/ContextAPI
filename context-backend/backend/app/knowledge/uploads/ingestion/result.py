from typing import Any
from pydantic import BaseModel

class IngestionStageResult(BaseModel):
    success: bool
    error_message: str | None = None
    checkpoint_data: dict[str, Any] | None = None
