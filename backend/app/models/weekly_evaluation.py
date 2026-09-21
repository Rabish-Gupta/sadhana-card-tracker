from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.devotee import DevoteeCategory, DevoteeProfile
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization import Organization
    from app.models.scoring import ScoringRuleVersion
    from app.models.standard import StandardVersion


class WeeklyEvaluation(UUIDPrimaryKeyMixin, Base):
    """Persisted weekly evaluation for stable historical reporting."""

    __tablename__ = "weekly_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "devotee_profile_id",
            "week_start_date",
            name="uq_weekly_evaluations_devotee_week",
        ),
        CheckConstraint("week_end_date >= week_start_date", name="ck_weekly_eval_dates"),
        CheckConstraint("sadhana_score >= 0", name="ck_weekly_eval_sadhana_score"),
        CheckConstraint("sadhana_max_score >= 0", name="ck_weekly_eval_sadhana_max"),
        CheckConstraint("academic_score >= 0", name="ck_weekly_eval_academic_score"),
        CheckConstraint("academic_max_score >= 0", name="ck_weekly_eval_academic_max"),
        CheckConstraint("revision_number >= 0", name="ck_weekly_eval_revision"),
        Index("ix_weekly_devotee_week", "devotee_profile_id", "week_start_date"),
        Index("ix_weekly_org_week", "organization_id", "week_start_date"),
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
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    week_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    category_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devotee_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    timezone_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    sadhana_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sadhana_max_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sadhana_percentage: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    academic_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    academic_max_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    academic_percentage: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="weekly_evaluations")
    devotee_profile: Mapped[DevoteeProfile] = relationship(back_populates="weekly_evaluations")
    category_snapshot: Mapped[DevoteeCategory] = relationship(
        back_populates="weekly_evaluation_snapshots",
        foreign_keys=[category_snapshot_id],
    )
    activity_results: Mapped[list[WeeklyActivityResult]] = relationship(
        back_populates="weekly_evaluation"
    )


class WeeklyActivityResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "weekly_activity_results"
    __table_args__ = (
        UniqueConstraint(
            "weekly_evaluation_id",
            "activity_id",
            name="uq_weekly_activity_results_eval_activity",
        ),
        CheckConstraint(
            "daily_score_total IS NULL OR daily_score_total >= 0",
            name="ck_weekly_activity_results_daily_score",
        ),
        CheckConstraint(
            "final_activity_score IS NULL OR final_activity_score >= 0",
            name="ck_weekly_activity_results_final_score",
        ),
        CheckConstraint(
            "maximum_score IS NULL OR maximum_score >= 0",
            name="ck_weekly_activity_results_maximum",
        ),
        Index("ix_weekly_activity_results_eval", "weekly_evaluation_id"),
        Index("ix_weekly_activity_results_activity", "activity_id"),
    )

    weekly_evaluation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("weekly_evaluations.id", ondelete="RESTRICT"),
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
    aggregation_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    raw_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    daily_score_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_activity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scoring_rule_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    standard_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("standard_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    standard_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    standard_achievement: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    calculation_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    weekly_evaluation: Mapped[WeeklyEvaluation] = relationship(back_populates="activity_results")
    activity: Mapped[Activity] = relationship(back_populates="weekly_results")
    category_activity_config: Mapped[CategoryActivityConfig] = relationship(
        back_populates="weekly_results"
    )
    rule_version: Mapped[ScoringRuleVersion | None] = relationship(
        back_populates="weekly_results"
    )
    standard_version: Mapped[StandardVersion | None] = relationship(
        back_populates="weekly_results"
    )
