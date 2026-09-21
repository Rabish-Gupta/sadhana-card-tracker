from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.enums import AggregationMethod, ScoringType, VersionStatus
from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.daily_card import DailyActivityEntry
    from app.models.devotee import DevoteeCategory
    from app.models.organization import Organization
    from app.models.scoring import ScoringRule
    from app.models.standard import Standard
    from app.models.user import User
    from app.models.weekly_evaluation import WeeklyActivityResult


class CategoryActivityConfig(UUIDPrimaryKeyMixin, Base):
    """Versioned evaluation profile entry for one category/activity pair.

    This is the bridge that allows the same Activity to use different rules,
    standards, scoring periods, and aggregation behavior for different devotee
    categories. Versions become effective only from a week boundary.
    """

    __tablename__ = "category_activity_configs"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "activity_id",
            "version_number",
            name="uq_category_activity_configs_version",
        ),
        UniqueConstraint(
            "category_id",
            "activity_id",
            "effective_from_week",
            name="uq_category_activity_configs_effective_week",
        ),
        CheckConstraint("version_number >= 1", name="ck_category_activity_configs_version"),
        Index(
            "ix_category_activity_configs_effective",
            "category_id",
            "activity_id",
            "effective_from_week",
        ),
        Index("ix_category_activity_configs_status", "status"),
        Index("ix_category_activity_configs_org", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("activities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from_week: Mapped[date] = mapped_column(Date, nullable=False)
    is_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scoring_type: Mapped[ScoringType] = mapped_column(
        SAEnum(
            ScoringType,
            name="scoring_type",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    weekly_aggregation: Mapped[AggregationMethod | None] = mapped_column(
        SAEnum(
            AggregationMethod,
            name="aggregation_method",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=True,
    )
    scoring_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scoring_rules.id", ondelete="RESTRICT"),
        nullable=True,
    )
    standard_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("standards.id", ondelete="RESTRICT"),
        nullable=True,
    )
    counts_toward_card_fill: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
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

    organization: Mapped[Organization] = relationship(back_populates="category_activity_configs")
    category: Mapped[DevoteeCategory] = relationship(back_populates="activity_configs")
    activity: Mapped[Activity] = relationship(back_populates="category_configs")
    scoring_rule: Mapped[ScoringRule | None] = relationship(back_populates="category_configs")
    standard: Mapped[Standard | None] = relationship(back_populates="category_configs")
    created_by: Mapped[User] = relationship(
        back_populates="created_category_activity_configs",
        foreign_keys=[created_by_id],
    )
    daily_entries: Mapped[list[DailyActivityEntry]] = relationship(
        back_populates="category_activity_config"
    )
    weekly_results: Mapped[list[WeeklyActivityResult]] = relationship(
        back_populates="category_activity_config"
    )
