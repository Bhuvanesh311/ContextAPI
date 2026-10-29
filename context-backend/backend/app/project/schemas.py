from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ProjectStatus



class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

#project create schemas
class ProjectCreateRequest(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=100,
        description="Project name"
    )
    description: str | None = Field(
        default=None,
        description="Project description",
        max_length=1000
    )
    status: ProjectStatus = Field(
        default=ProjectStatus.PENDING,
        description="Retrieval only searches projects whose status is `active`.",
    )

    model_config = ConfigDict(json_schema_extra={"example": {
        "name": "My Docs",
        "description": "Documents to ask questions about",
        "status": "active",
    }})


class ProjectCreateResponse(BaseModel):
    message: str
    project: ProjectResponse

#project view schemas


class ProjectListResponse(BaseModel):
    total:int
    projects: list[ProjectResponse]

    model_config = ConfigDict(from_attributes=True)


#project update schemas
class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Project name"
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Project description"
    )

    status: ProjectStatus | None = Field(
        default=None,
        description="Project status"
    )

    # Send only the fields to change.
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"example": {"status": "active"}})


class ProjectUpdateResponse(BaseModel):
    message: str
    project: ProjectResponse
