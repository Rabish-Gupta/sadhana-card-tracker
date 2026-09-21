from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.enums import VersionStatus
from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class OrganizationSettingVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable historical snapshot of organization-wide temporal settings.

    The ``organizations`` row remains the materialized source for the currently active
    settings so ordinary request-time lookups stay simple.  This table preserves the
    version history and the next-week PENDING change.  Only a PENDING row may be edited.
    """

    __tablename__ = "organization_setting_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_organization_setting_versions_number",
        ),
        UniqueConstraint(
            "organization_id",
            "effective_from_week",
            name="uq_organization_setting_versions_effective_week",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_organization_setting_versions_number",
        ),
        CheckConstraint(
            "week_start_day BETWEEN 0 AND 6",
            name="ck_organization_setting_versions_week_start_day",
        ),
        CheckConstraint(
            "promotion_month BETWEEN 1 AND 12",
            name="ck_organization_setting_versions_promotion_month",
        ),
        Index(
            "ix_organization_setting_versions_effective",
            "organization_id",
            "effective_from_week",
        ),
        Index("ix_organization_setting_versions_status", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from_week: Mapped[date] = mapped_column(Date, nullable=False)
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
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    week_start_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    daily_finalize_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    promotion_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="setting_versions")
    created_by: Mapped[User | None] = relationship(
        back_populates="created_organization_setting_versions",
        foreign_keys=[created_by_id],
    )
