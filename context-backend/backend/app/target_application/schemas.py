from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl

from app.core.enums import EnvironmentEnum

class TargetApplicationBase(BaseModel):
    base_url: HttpUrl
    environment: EnvironmentEnum
    api_version: str | None = None

class TargetApplicationCreate(TargetApplicationBase):
    project_id: str


class TargetApplicationUpdate(BaseModel):
    base_url: HttpUrl | None = None
    environment: EnvironmentEnum | None = None
    api_version: str | None = None

class TargetApplicationResponse(TargetApplicationBase):
    target_application_id: str
    project_id: str

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class TargetApplicationCreateResponse(BaseModel):
    message: str
    target_application: TargetApplicationResponse

class TargetApplicationUpdateResponse(BaseModel):
    message: str
    target_application: TargetApplicationResponse

class TargetApplicationDetailResponse(BaseModel):
    target_application: TargetApplicationResponse

class TargetApplicationListResponse(BaseModel):
    target_applications: list[TargetApplicationResponse]