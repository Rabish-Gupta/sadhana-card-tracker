from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.enums import StandardPeriod, VersionStatus
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.weekly_evaluation import WeeklyActivityResult


class Standard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Logical target/standard whose values are stored in weekly-versioned records."""

    __tablename__ = "standards"
    __table_args__ = (
        Index("ix_standards_org_activity", "organization_id", "activity_id"),
        Index("ix_standards_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("activities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    organization: Mapped[Organization] = relationship(back_populates="standards")
    activity: Mapped[Activity] = relationship(back_populates="standards")
    created_by: Mapped[User] = relationship(
        back_populates="created_standards",
        foreign_keys=[created_by_id],
    )
    versions: Mapped[list[StandardVersion]] = relationship(
        back_populates="standard",
        order_by="StandardVersion.version_number",
    )
    category_configs: Mapped[list[CategoryActivityConfig]] = relationship(
        back_populates="standard"
    )


class StandardVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "standard_versions"
    __table_args__ = (
        UniqueConstraint("standard_id", "version_number", name="uq_standard_versions_number"),
        UniqueConstraint(
            "standard_id",
            "effective_from_week",
            name="uq_standard_versions_effective_week",
        ),
        CheckConstraint("version_number >= 1", name="ck_standard_versions_number"),
        Index("ix_standard_versions_effective", "standard_id", "effective_from_week"),
        Index("ix_standard_versions_status", "status"),
    )

    standard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("standards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from_week: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[StandardPeriod] = mapped_column(
        SAEnum(
            StandardPeriod,
            name="standard_period",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    target_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(
        SAEnum(
            VersionStatus,
            name="version_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=VersionStatus.PENDING,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    standard: Mapped[Standard] = relationship(back_populates="versions")
    created_by: Mapped[User] = relationship(
        back_populates="created_standard_versions",
        foreign_keys=[created_by_id],
    )
    weekly_results: Mapped[list[WeeklyActivityResult]] = relationship(
        back_populates="standard_version"
    )
