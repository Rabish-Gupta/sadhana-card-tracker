"""Import models here so SQLAlchemy metadata contains every mapped table."""

from app.models.activity import Activity, ActivityField
from app.models.audit import AuditLog
from app.models.daily_card import DailyActivityEntry, DailyActivityValue, DailyCard
from app.models.devotee import DevoteeCategory, DevoteeCategoryHistory, DevoteeProfile
from app.models.evaluation_config import CategoryActivityConfig
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettingVersion
from app.models.scoring import ScoringRule, ScoringRuleVersion
from app.models.standard import Standard, StandardVersion
from app.models.user import User
from app.models.weekly_evaluation import WeeklyActivityResult, WeeklyEvaluation

__all__ = [
    "Organization",
    "OrganizationSettingVersion",
    "User",
    "DevoteeCategory",
    "DevoteeProfile",
    "DevoteeCategoryHistory",
    "Activity",
    "ActivityField",
    "ScoringRule",
    "ScoringRuleVersion",
    "Standard",
    "StandardVersion",
    "CategoryActivityConfig",
    "DailyCard",
    "DailyActivityEntry",
    "DailyActivityValue",
    "WeeklyEvaluation",
    "WeeklyActivityResult",
    "AuditLog",
]
