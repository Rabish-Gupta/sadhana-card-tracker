from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
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
    Numeric,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.enums import CardStatus
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity, ActivityField
    from app.models.devotee import DevoteeCategory, DevoteeProfile
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization import Organization
    from app.models.scoring import ScoringRuleVersion


class DailyCard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organization-local daily card for one devotee.

    Deadline/timezone/category snapshots ensure later configuration changes cannot
    reinterpret an already-created historical card.
    """

    __tablename__ = "daily_cards"
    __table_args__ = (
        UniqueConstraint(
            "devotee_profile_id",
            "card_date",
            name="uq_daily_cards_devotee_date",
        ),
        CheckConstraint("revision_number >= 0", name="ck_daily_cards_revision"),
        Index("ix_daily_cards_finalize", "status", "deadline_at_utc"),
        Index("ix_daily_cards_devotee_date", "devotee_profile_id", "card_date"),
        Index("ix_daily_cards_org_date", "organization_id", "card_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    devotee_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    card_date: Mapped[date] = mapped_column(Date, nullable=False)
    category_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[CardStatus] = mapped_column(
        SAEnum(CardStatus, name="card_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=CardStatus.IN_PROGRESS,
    )
    first_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    deadline_time_snapshot: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    deadline_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    organization: Mapped[Organization] = relationship(back_populates="daily_cards")
    devotee_profile: Mapped[DevoteeProfile] = relationship(back_populates="daily_cards")
    category_snapshot: Mapped[DevoteeCategory] = relationship(
        back_populates="daily_card_snapshots",
        foreign_keys=[category_snapshot_id],
    )
    activity_entries: Mapped[list[DailyActivityEntry]] = relationship(
        back_populates="daily_card",
        order_by="DailyActivityEntry.created_at",
    )


class DailyActivityEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Activity instance inside a card, with exact historical config/rule references."""

    __tablename__ = "daily_activity_entries"
    __table_args__ = (
        UniqueConstraint(
            "daily_card_id",
            "activity_id",
            name="uq_daily_activity_entries_card_activity",
        ),
        CheckConstraint(
            "daily_score IS NULL OR daily_score >= 0",
            name="ck_daily_activity_entries_score",
        ),
        CheckConstraint(
            "max_score_snapshot IS NULL OR max_score_snapshot >= 0",
            name="ck_daily_activity_entries_max_score",
        ),
        Index("ix_daily_activity_entries_card", "daily_card_id"),
        Index("ix_daily_activity_entries_activity", "activity_id"),
    )

    daily_card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("daily_cards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("activities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category_activity_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("category_activity_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_filled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    daily_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scoring_rule_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    max_score_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    score_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    daily_card: Mapped[DailyCard] = relationship(back_populates="activity_entries")
    activity: Mapped[Activity] = relationship(back_populates="daily_entries")
    category_activity_config: Mapped[CategoryActivityConfig] = relationship(
        back_populates="daily_entries"
    )
    rule_version: Mapped[ScoringRuleVersion | None] = relationship(
        back_populates="daily_entries"
    )
    values: Mapped[list[DailyActivityValue]] = relationship(
        back_populates="daily_activity_entry"
    )


class DailyActivityValue(UUIDPrimaryKeyMixin, Base):
    """Typed raw value for one ActivityField.

    For numeric values, `is_filled=False, numeric_value=0` means "not filled", while
    `is_filled=True, numeric_value=0` means the devotee intentionally entered zero.
    """

    __tablename__ = "daily_activity_values"
    __table_args__ = (
        UniqueConstraint(
            "daily_activity_entry_id",
            "activity_field_id",
            name="uq_daily_activity_values_entry_field",
        ),
        Index("ix_daily_activity_values_entry", "daily_activity_entry_id"),
    )

    daily_activity_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("daily_activity_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activity_field_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("activity_fields.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_filled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    numeric_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0"),
    )
    time_value: Mapped[time | None] = mapped_column(Time(timezone=False), nullable=True)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    daily_activity_entry: Mapped[DailyActivityEntry] = relationship(back_populates="values")
    activity_field: Mapped[ActivityField] = relationship(back_populates="daily_values")
