from datetime import datetime

from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    Text,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy import Enum as SQLEnum 

from app.core.database import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.auth.models import User
    from app.target_application.models import TargetApplication
    from app.knowledge.uploads.models import UploadJob,Document


from app.core.enums import ProjectStatus


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(
        String(20),
        primary_key= True,
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False,
        index=True
    )

    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.tenant_id"),
        nullable=True,
        index=True
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[ProjectStatus] = mapped_column(
        SQLEnum(ProjectStatus, name="project_status"),
        default=ProjectStatus.PENDING,
        nullable=False,
)

    created_at: Mapped[datetime] = mapped_column(
    DateTime,
    default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = relationship(
        "User",
        back_populates="projects"
    )

    target_applications = relationship(
        "TargetApplication",
        back_populates="project"
    )

    upload_jobs = relationship(
        "UploadJob",
        back_populates="project"
    )

    documents = relationship(
        "Document",
        back_populates="project"
    )