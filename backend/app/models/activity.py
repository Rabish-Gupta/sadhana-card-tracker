from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.enums import ActivityCategory, ActivityInputType
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.daily_card import DailyActivityEntry, DailyActivityValue
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization import Organization
    from app.models.scoring import ScoringRule
    from app.models.standard import Standard
    from app.models.weekly_evaluation import WeeklyActivityResult


class Activity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Logical trackable activity.

    The activity itself is intentionally category-agnostic with respect to scoring.
    Per-devotee-category behavior lives in CategoryActivityConfig so the same activity
    can be evaluated differently for Sahadeva/Nakula/Arjuna/etc. without duplicating
    the activity definition.
    """

    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_activities_org_code"),
        Index("ix_activities_org_category_active", "organization_id", "category", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[ActivityCategory] = mapped_column(
        SAEnum(
            ActivityCategory,
            name="activity_category",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    organization: Mapped[Organization] = relationship(back_populates="activities")
    fields: Mapped[list[ActivityField]] = relationship(
        back_populates="activity",
        order_by="ActivityField.display_order",
    )
    scoring_rules: Mapped[list[ScoringRule]] = relationship(back_populates="activity")
    standards: Mapped[list[Standard]] = relationship(back_populates="activity")
    category_configs: Mapped[list[CategoryActivityConfig]] = relationship(
        back_populates="activity"
    )
    daily_entries: Mapped[list[DailyActivityEntry]] = relationship(back_populates="activity")
    weekly_results: Mapped[list[WeeklyActivityResult]] = relationship(back_populates="activity")


class ActivityField(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One raw input field belonging to an Activity.

    Once historical values exist, semantic attributes (field_key/input_type/unit_code)
    must not be repurposed. The service layer will archive the field and create a new
    one for semantic changes; display labels may be safely edited.
    """

    __tablename__ = "activity_fields"
    __table_args__ = (
        UniqueConstraint("activity_id", "field_key", name="uq_activity_fields_key"),
        Index("ix_activity_fields_activity_active", "activity_id", "is_active"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("activities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field_key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    input_type: Mapped[ActivityInputType] = mapped_column(
        SAEnum(
            ActivityInputType,
            name="activity_input_type",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    unit_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    required_for_completion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    activity: Mapped[Activity] = relationship(back_populates="fields")
    daily_values: Mapped[list[DailyActivityValue]] = relationship(
        back_populates="activity_field"
    )
