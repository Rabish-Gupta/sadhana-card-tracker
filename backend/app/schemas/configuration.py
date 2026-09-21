from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    ActivityCategory,
    ActivityInputType,
    AggregationMethod,
    RoundingMode,
    RuleType,
    ScoringType,
    StandardPeriod,
    VersionStatus,
)
from app.core.timezone import get_zoneinfo
from app.schemas.base import ORMModel


class ActivityCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=150)
    category: ActivityCategory
    description: str | None = Field(default=None, max_length=2000)
    is_system_derived: bool = False

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class ActivityUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class ArchiveRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Reason is required")
        return value


class ActivityFieldCreateRequest(BaseModel):
    field_key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=150)
    input_type: ActivityInputType
    unit_code: str | None = Field(default=None, max_length=30)
    display_order: int = Field(default=0, ge=0, le=32767)
    required_for_completion: bool = True

    @field_validator("field_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        return value.strip()

    @field_validator("unit_code")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class ActivityFieldUpdateRequest(BaseModel):
    # Historical-card completeness depends on the semantic field contract.  Once a field
    # exists, only presentation metadata may be edited in place.  Semantic changes
    # (field_key/input_type/unit/required_for_completion) require archive + replacement.
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=150)
    display_order: int | None = Field(default=None, ge=0, le=32767)

    @model_validator(mode="after")
    def require_change(self) -> "ActivityFieldUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one presentation field must be supplied")
        return self


class ActivityFieldPublic(ORMModel):
    id: uuid.UUID
    field_key: str
    label: str
    input_type: ActivityInputType
    unit_code: str | None
    display_order: int
    required_for_completion: bool
    is_active: bool
    is_archived: bool


class ActivityPublic(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    category: ActivityCategory
    description: str | None
    is_system_derived: bool
    is_active: bool
    is_archived: bool
    fields: list[ActivityFieldPublic] = []


class ScoringRuleCreateRequest(BaseModel):
    activity_id: uuid.UUID
    name: str = Field(min_length=2, max_length=150)
    rule_type: RuleType


class ScoringRuleUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)


class ScoringRuleVersionCreateRequest(BaseModel):
    effective_from_week: date | None = None
    max_score: int = Field(ge=0)
    rounding_mode: RoundingMode = RoundingMode.HALF_UP
    configuration: dict[str, Any]


class ScoringRuleVersionUpdateRequest(BaseModel):
    effective_from_week: date | None = None
    max_score: int | None = Field(default=None, ge=0)
    rounding_mode: RoundingMode | None = None
    configuration: dict[str, Any] | None = None


class ScoringRuleVersionPublic(ORMModel):
    id: uuid.UUID
    scoring_rule_id: uuid.UUID
    version_number: int
    effective_from_week: date
    status: VersionStatus
    max_score: int
    rounding_mode: RoundingMode
    configuration: dict[str, Any]
    created_by_id: uuid.UUID
    created_at: datetime


class ScoringRulePublic(ORMModel):
    id: uuid.UUID
    activity_id: uuid.UUID
    name: str
    rule_type: RuleType
    is_active: bool
    is_archived: bool
    created_by_id: uuid.UUID


class StandardCreateRequest(BaseModel):
    activity_id: uuid.UUID
    name: str = Field(min_length=2, max_length=150)


class StandardUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)


class StandardVersionCreateRequest(BaseModel):
    effective_from_week: date | None = None
    period: StandardPeriod
    target_definition: dict[str, Any]


class StandardVersionUpdateRequest(BaseModel):
    effective_from_week: date | None = None
    period: StandardPeriod | None = None
    target_definition: dict[str, Any] | None = None


class StandardVersionPublic(ORMModel):
    id: uuid.UUID
    standard_id: uuid.UUID
    version_number: int
    effective_from_week: date
    period: StandardPeriod
    target_definition: dict[str, Any]
    status: VersionStatus
    created_by_id: uuid.UUID
    created_at: datetime


class StandardPublic(ORMModel):
    id: uuid.UUID
    activity_id: uuid.UUID
    name: str
    is_active: bool
    is_archived: bool
    created_by_id: uuid.UUID


class CategoryActivityConfigCreateRequest(BaseModel):
    category_id: uuid.UUID
    activity_id: uuid.UUID
    effective_from_week: date | None = None
    is_applicable: bool = True
    scoring_type: ScoringType
    weekly_aggregation: AggregationMethod | None = None
    scoring_rule_id: uuid.UUID | None = None
    standard_id: uuid.UUID | None = None
    counts_toward_card_fill: bool = True

    @model_validator(mode="after")
    def validate_obvious_relationships(self):
        if not self.is_applicable and self.counts_toward_card_fill:
            raise ValueError("A non-applicable activity cannot count toward card fill")
        if self.scoring_type == ScoringType.NON_SCORED and self.scoring_rule_id is not None:
            raise ValueError("NON_SCORED activities cannot have a scoring rule")
        return self


class CategoryActivityConfigUpdateRequest(BaseModel):
    effective_from_week: date | None = None
    is_applicable: bool | None = None
    scoring_type: ScoringType | None = None
    weekly_aggregation: AggregationMethod | None = None
    scoring_rule_id: uuid.UUID | None = None
    standard_id: uuid.UUID | None = None
    counts_toward_card_fill: bool | None = None


class CategoryActivityConfigPublic(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    category_id: uuid.UUID
    activity_id: uuid.UUID
    version_number: int
    effective_from_week: date
    is_applicable: bool
    scoring_type: ScoringType
    weekly_aggregation: AggregationMethod | None
    scoring_rule_id: uuid.UUID | None
    standard_id: uuid.UUID | None
    counts_toward_card_fill: bool
    status: VersionStatus
    created_by_id: uuid.UUID
    created_at: datetime


class CategoryPublic(ORMModel):
    id: uuid.UUID
    code: str
    display_name: str
    academic_year: int | None
    stage_order: int
    is_active: bool
    is_archived: bool


class ActivationResult(BaseModel):
    effective_week: date
    scoring_rule_versions_activated: int
    standard_versions_activated: int
    category_configs_activated: int
    organization_setting_versions_activated: int


class OrganizationSettingVersionCreateRequest(BaseModel):
    effective_from_week: date | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    week_start_day: int | None = Field(default=None, ge=0, le=6)
    daily_finalize_time: time | None = None
    promotion_month: int | None = Field(default=None, ge=1, le=12)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        get_zoneinfo(value)
        return value

    @model_validator(mode="after")
    def require_setting_change(self):
        changed = {
            "timezone",
            "week_start_day",
            "daily_finalize_time",
            "promotion_month",
        } & self.model_fields_set
        if not changed:
            raise ValueError("At least one organization setting must be supplied")
        for key in changed:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class OrganizationSettingVersionUpdateRequest(BaseModel):
    effective_from_week: date | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    week_start_day: int | None = Field(default=None, ge=0, le=6)
    daily_finalize_time: time | None = None
    promotion_month: int | None = Field(default=None, ge=1, le=12)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        get_zoneinfo(value)
        return value

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied")
        editable = {
            "timezone",
            "week_start_day",
            "daily_finalize_time",
            "promotion_month",
        }
        for key in editable & self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class OrganizationSettingVersionPublic(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    version_number: int
    effective_from_week: date
    status: VersionStatus
    timezone: str
    week_start_day: int
    daily_finalize_time: time
    promotion_month: int
    created_by_id: uuid.UUID | None
    created_at: datetime
