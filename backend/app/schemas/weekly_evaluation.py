from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ActivityCategory, AggregationMethod, ScoringType


class PreviousWeekActivityPublic(BaseModel):
    week_start_date: date
    raw_total: Decimal | None = None
    final_activity_score: int | None = None
    maximum_score: int | None = None
    standard_achievement: Decimal | None = None


class WeeklyActivityResultPublic(BaseModel):
    activity_id: uuid.UUID
    code: str
    name: str
    category: ActivityCategory
    scoring_type: ScoringType
    aggregation_method: AggregationMethod | None = None
    raw_total: Decimal | None = None
    daily_score_total: int | None = None
    final_activity_score: int | None = None
    maximum_score: int | None = None
    rule_version_id: uuid.UUID | None = None
    standard_version_id: uuid.UUID | None = None
    standard_snapshot: dict[str, Any] | None = None
    standard_achievement: Decimal | None = None
    calculation_details: dict[str, Any] | None = None
    previous_week: PreviousWeekActivityPublic | None = None


class PreviousWeekEvaluationPublic(BaseModel):
    week_start_date: date
    week_end_date: date
    sadhana_score: int
    sadhana_max_score: int
    sadhana_percentage: Decimal | None = None
    academic_score: int
    academic_max_score: int
    academic_percentage: Decimal | None = None


class WeeklyEvaluationPublic(BaseModel):
    id: uuid.UUID
    week_start_date: date
    week_end_date: date
    category_code: str
    category_name: str
    timezone_snapshot: str
    sadhana_score: int
    sadhana_max_score: int
    sadhana_percentage: Decimal | None = None
    academic_score: int
    academic_max_score: int
    academic_percentage: Decimal | None = None
    revision_number: int
    generated_at: datetime
    updated_at: datetime
    activities: list[WeeklyActivityResultPublic] = Field(default_factory=list)
    previous_week: PreviousWeekEvaluationPublic | None = None
