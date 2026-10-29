from datetime import datetime

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.project.models import Project
    from app.knowledge.uploads.models import UploadJob,Document


class Tenant(Base):
    """
    The isolation boundary above projects. Every user belongs to one tenant
    and every project belongs to one tenant; L02 only lets a caller reach a
    project inside the caller's own tenant.
    """
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    role: Mapped[str] = mapped_column(
        String(20),
        default="USER"
    )

    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.tenant_id"),
        nullable=True,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    projects = relationship(
        "Project",
        back_populates="user"
    )

    upload_jobs = relationship(
        "UploadJob",
        back_populates="user"
    )

    documents = relationship(
        "Document",
        back_populates="user"
    )

    

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    refresh_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE")
    )

    jti: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    user = relationship(
        "User",
        back_populates="refresh_tokens"
    )