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

from app.core.enums import RoundingMode, RuleType, VersionStatus
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.daily_card import DailyActivityEntry
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.weekly_evaluation import WeeklyActivityResult


class ScoringRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Logical scoring rule whose actual logic lives in immutable versions."""

    __tablename__ = "scoring_rules"
    __table_args__ = (
        Index("ix_scoring_rules_org_activity", "organization_id", "activity_id"),
        Index("ix_scoring_rules_org_active", "organization_id", "is_active"),
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
    rule_type: Mapped[RuleType] = mapped_column(
        SAEnum(RuleType, name="rule_type", native_enum=True, validate_strings=True),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    organization: Mapped[Organization] = relationship(back_populates="scoring_rules")
    activity: Mapped[Activity] = relationship(back_populates="scoring_rules")
    created_by: Mapped[User] = relationship(
        back_populates="created_scoring_rules",
        foreign_keys=[created_by_id],
    )
    versions: Mapped[list[ScoringRuleVersion]] = relationship(
        back_populates="scoring_rule",
        order_by="ScoringRuleVersion.version_number",
    )
    category_configs: Mapped[list[CategoryActivityConfig]] = relationship(
        back_populates="scoring_rule"
    )


class ScoringRuleVersion(UUIDPrimaryKeyMixin, Base):
    """Versioned scoring logic.

    ACTIVE/ARCHIVED versions are treated as immutable by the service layer. A change
    creates/updates a PENDING version which becomes effective only at a week boundary.
    """

    __tablename__ = "scoring_rule_versions"
    __table_args__ = (
        UniqueConstraint(
            "scoring_rule_id",
            "version_number",
            name="uq_scoring_rule_versions_number",
        ),
        UniqueConstraint(
            "scoring_rule_id",
            "effective_from_week",
            name="uq_scoring_rule_versions_effective_week",
        ),
        CheckConstraint("version_number >= 1", name="ck_scoring_rule_versions_number"),
        CheckConstraint("max_score >= 0", name="ck_scoring_rule_versions_max_score"),
        Index(
            "ix_scoring_rule_versions_effective",
            "scoring_rule_id",
            "effective_from_week",
        ),
        Index("ix_scoring_rule_versions_status", "status"),
    )

    scoring_rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scoring_rules.id", ondelete="RESTRICT"),
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
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    rounding_mode: Mapped[RoundingMode] = mapped_column(
        SAEnum(
            RoundingMode,
            name="rounding_mode",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=RoundingMode.HALF_UP,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
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

    scoring_rule: Mapped[ScoringRule] = relationship(back_populates="versions")
    created_by: Mapped[User] = relationship(
        back_populates="created_scoring_rule_versions",
        foreign_keys=[created_by_id],
    )
    daily_entries: Mapped[list[DailyActivityEntry]] = relationship(back_populates="rule_version")
    weekly_results: Mapped[list[WeeklyActivityResult]] = relationship(
        back_populates="rule_version"
    )
