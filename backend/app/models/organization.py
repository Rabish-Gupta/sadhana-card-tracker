from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, SmallInteger, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.audit import AuditLog
    from app.models.daily_card import DailyCard
    from app.models.devotee import DevoteeCategory
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization_settings import OrganizationSettingVersion
    from app.models.scoring import ScoringRule
    from app.models.standard import Standard
    from app.models.user import User
    from app.models.weekly_evaluation import WeeklyEvaluation


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("code", name="uq_organizations_code"),
        CheckConstraint(
            "week_start_day BETWEEN 0 AND 6",
            name="ck_organizations_week_start_day",
        ),
        CheckConstraint(
            "promotion_month BETWEEN 1 AND 12",
            name="ck_organizations_promotion_month",
        ),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    week_start_day: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    daily_finalize_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    promotion_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users: Mapped[list[User]] = relationship(back_populates="organization")
    devotee_categories: Mapped[list[DevoteeCategory]] = relationship(
        back_populates="organization"
    )
    activities: Mapped[list[Activity]] = relationship(back_populates="organization")
    scoring_rules: Mapped[list[ScoringRule]] = relationship(back_populates="organization")
    standards: Mapped[list[Standard]] = relationship(back_populates="organization")
    category_activity_configs: Mapped[list[CategoryActivityConfig]] = relationship(
        back_populates="organization"
    )
    daily_cards: Mapped[list[DailyCard]] = relationship(back_populates="organization")
    weekly_evaluations: Mapped[list[WeeklyEvaluation]] = relationship(
        back_populates="organization"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="organization")
    setting_versions: Mapped[list[OrganizationSettingVersion]] = relationship(
        back_populates="organization",
        order_by="OrganizationSettingVersion.version_number",
    )
