from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from sqlalchemy import Enum as SQLEnum 
from app.core.enums import EnvironmentEnum

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.project.models import Project



class TargetApplication(Base):
    __tablename__ = "target_applications"

    target_application_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    base_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    environment: Mapped[str|None] = mapped_column(
        SQLEnum(EnvironmentEnum, name ="environment"),
        nullable=False,
    )

    api_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    project = relationship(
        "Project",
        back_populates="target_applications"
    )