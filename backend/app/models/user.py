from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.enums import AccountStatus, RegistrationSource, UserRole
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.audit import AuditLog
    from app.models.devotee import DevoteeCategoryHistory, DevoteeProfile
    from app.models.evaluation_config import CategoryActivityConfig
    from app.models.organization import Organization
    from app.models.organization_settings import OrganizationSettingVersion
    from app.models.scoring import ScoringRule, ScoringRuleVersion
    from app.models.standard import Standard, StandardVersion


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        Index("ix_users_org_status", "organization_id", "account_status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=True, validate_strings=True),
        nullable=False,
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        SAEnum(
            AccountStatus,
            name="account_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=AccountStatus.PENDING,
    )
    registration_source: Mapped[RegistrationSource] = mapped_column(
        SAEnum(
            RegistrationSource,
            name="registration_source",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )

    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pending_deactivation_week: Mapped[date | None] = mapped_column(Date, nullable=True)
    pending_deactivation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_deactivation_requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    pending_deactivation_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    organization: Mapped[Organization] = relationship(back_populates="users")
    devotee_profile: Mapped[DevoteeProfile | None] = relationship(
        back_populates="user",
        uselist=False,
    )

    approved_by: Mapped[User | None] = relationship(
        "User",
        remote_side="User.id",
        foreign_keys=[approved_by_id],
        back_populates="approved_users",
    )
    approved_users: Mapped[list[User]] = relationship(
        "User",
        foreign_keys="User.approved_by_id",
        back_populates="approved_by",
    )

    category_history_changes: Mapped[list[DevoteeCategoryHistory]] = relationship(
        back_populates="changed_by",
        foreign_keys="DevoteeCategoryHistory.changed_by_id",
    )
    created_scoring_rules: Mapped[list[ScoringRule]] = relationship(
        back_populates="created_by",
        foreign_keys="ScoringRule.created_by_id",
    )
    created_scoring_rule_versions: Mapped[list[ScoringRuleVersion]] = relationship(
        back_populates="created_by",
        foreign_keys="ScoringRuleVersion.created_by_id",
    )
    created_standards: Mapped[list[Standard]] = relationship(
        back_populates="created_by",
        foreign_keys="Standard.created_by_id",
    )
    created_standard_versions: Mapped[list[StandardVersion]] = relationship(
        back_populates="created_by",
        foreign_keys="StandardVersion.created_by_id",
    )
    created_category_activity_configs: Mapped[list[CategoryActivityConfig]] = relationship(
        back_populates="created_by",
        foreign_keys="CategoryActivityConfig.created_by_id",
    )
    created_organization_setting_versions: Mapped[list[OrganizationSettingVersion]] = relationship(
        back_populates="created_by",
        foreign_keys="OrganizationSettingVersion.created_by_id",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="actor_user",
        foreign_keys="AuditLog.actor_user_id",
    )
