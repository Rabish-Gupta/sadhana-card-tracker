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
    SmallInteger,
    String,
    func,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.enums import ChangeSource, EmploymentStatus
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.daily_card import DailyCard
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.weekly_evaluation import WeeklyEvaluation


class DevoteeCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devotee_categories"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_devotee_categories_org_code",
        ),
        CheckConstraint(
            "academic_year IS NULL OR academic_year BETWEEN 1 AND 4",
            name="ck_devotee_categories_academic_year",
        ),
        CheckConstraint("stage_order >= 1", name="ck_devotee_categories_stage_order"),
        Index("ix_devotee_categories_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    academic_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    stage_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    employment_status: Mapped[EmploymentStatus | None] = mapped_column(
        SAEnum(
            EmploymentStatus,
            name="employment_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    organization: Mapped[Organization] = relationship(back_populates="devotee_categories")
    current_profiles: Mapped[list[DevoteeProfile]] = relationship(
        back_populates="current_category",
        foreign_keys="DevoteeProfile.current_category_id",
    )
    history_as_previous: Mapped[list[DevoteeCategoryHistory]] = relationship(
        back_populates="previous_category",
        foreign_keys="DevoteeCategoryHistory.previous_category_id",
    )
    history_as_new: Mapped[list[DevoteeCategoryHistory]] = relationship(
        back_populates="new_category",
        foreign_keys="DevoteeCategoryHistory.new_category_id",
    )
    activity_configs: Mapped[list[CategoryActivityConfig]] = relationship(
        back_populates="category"
    )
    daily_card_snapshots: Mapped[list[DailyCard]] = relationship(
        back_populates="category_snapshot",
        foreign_keys="DailyCard.category_snapshot_id",
    )
    weekly_evaluation_snapshots: Mapped[list[WeeklyEvaluation]] = relationship(
        back_populates="category_snapshot",
        foreign_keys="WeeklyEvaluation.category_snapshot_id",
    )


class DevoteeProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devotee_profiles"
    __table_args__ = (
        CheckConstraint(
            "current_academic_year IS NULL OR current_academic_year BETWEEN 1 AND 4",
            name="ck_devotee_profiles_current_academic_year",
        ),
        Index("ix_devotee_profiles_category", "current_category_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    current_category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    college: Mapped[str] = mapped_column(String(200), nullable=False)
    branch: Mapped[str] = mapped_column(String(120), nullable=False)
    college_joining_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expected_graduation_year: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    # Nullable at DB level because Bhima/pass-out devotees have no current academic year.
    # Registration/service validation requires this for student categories (Sahadeva-Yudhishthira).
    current_academic_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    user: Mapped[User] = relationship(back_populates="devotee_profile")
    current_category: Mapped[DevoteeCategory] = relationship(
        back_populates="current_profiles",
        foreign_keys=[current_category_id],
    )
    category_history: Mapped[list[DevoteeCategoryHistory]] = relationship(
        back_populates="devotee_profile",
        order_by="DevoteeCategoryHistory.effective_from_week",
    )
    daily_cards: Mapped[list[DailyCard]] = relationship(back_populates="devotee_profile")
    weekly_evaluations: Mapped[list[WeeklyEvaluation]] = relationship(
        back_populates="devotee_profile"
    )


class DevoteeCategoryHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "devotee_category_history"
    __table_args__ = (
        CheckConstraint(
            "previous_category_id IS NULL OR previous_category_id <> new_category_id",
            name="ck_category_history_changed_category",
        ),
        UniqueConstraint(
            "devotee_profile_id",
            "effective_from_week",
            name="uq_category_history_profile_effective",
        ),
        Index(
            "ix_category_history_profile_effective",
            "devotee_profile_id",
            "effective_from_week",
        ),
    )

    devotee_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    previous_category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    new_category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_from_week: Mapped[date] = mapped_column(Date, nullable=False)
    change_source: Mapped[ChangeSource] = mapped_column(
        SAEnum(
            ChangeSource,
            name="change_source",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    devotee_profile: Mapped[DevoteeProfile] = relationship(back_populates="category_history")
    previous_category: Mapped[DevoteeCategory | None] = relationship(
        back_populates="history_as_previous",
        foreign_keys=[previous_category_id],
    )
    new_category: Mapped[DevoteeCategory] = relationship(
        back_populates="history_as_new",
        foreign_keys=[new_category_id],
    )
    changed_by: Mapped[User | None] = relationship(
        back_populates="category_history_changes",
        foreign_keys=[changed_by_id],
    )
