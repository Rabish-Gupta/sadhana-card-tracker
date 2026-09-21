from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ActivityCategory, ScoringType


class FourWeekTrendPublic(BaseModel):
    first_percentage: Decimal | None = None
    last_percentage: Decimal | None = None
    change_percentage_points: Decimal | None = None
    average_percentage: Decimal | None = None
    minimum_percentage: Decimal | None = None
    maximum_percentage: Decimal | None = None
    range_percentage_points: Decimal | None = None


class FourWeekScoreSummaryPublic(BaseModel):
    score: int
    maximum_score: int
    percentage: Decimal | None = None
    trend: FourWeekTrendPublic


class FourWeekWeekPublic(BaseModel):
    week_start_date: date
    week_end_date: date
    category_code: str
    category_name: str
    sadhana_score: int
    sadhana_max_score: int
    sadhana_percentage: Decimal | None = None
    academic_score: int
    academic_max_score: int
    academic_percentage: Decimal | None = None


class FourWeekActivityWeekPublic(BaseModel):
    week_start_date: date
    week_end_date: date
    raw_total: Decimal | None = None
    final_activity_score: int | None = None
    maximum_score: int | None = None
    standard_achievement: Decimal | None = None
    category_activity_config_id: uuid.UUID
    rule_version_id: uuid.UUID | None = None
    standard_version_id: uuid.UUID | None = None
    standard_snapshot: dict[str, Any] | None = None


class PreviousFourWeekActivityPublic(BaseModel):
    period_start_date: date
    period_end_date: date
    final_score_total: int | None = None
    maximum_score_total: int | None = None
    score_percentage: Decimal | None = None
    raw_total_sum: Decimal | None = None
    standard_achievement_average: Decimal | None = None


class FourWeekActivityPublic(BaseModel):
    activity_id: uuid.UUID
    code: str
    name: str
    category: ActivityCategory
    scoring_types_seen: list[ScoringType] = Field(default_factory=list)
    final_score_total: int | None = None
    maximum_score_total: int | None = None
    score_percentage: Decimal | None = None
    raw_total_sum: Decimal | None = None
    weekly_raw_totals: list[Decimal | None] = Field(default_factory=list)
    weekly_final_scores: list[int | None] = Field(default_factory=list)
    weekly_maximum_scores: list[int | None] = Field(default_factory=list)
    weekly_results: list[FourWeekActivityWeekPublic] = Field(default_factory=list)
    standard_achievement_average: Decimal | None = None
    standard_periods_seen: list[str] = Field(default_factory=list)
    daily_standard_achieved_days: int | None = None
    daily_standard_evaluated_days: int | None = None
    weekly_standard_met_weeks: int | None = None
    weekly_standard_evaluated_weeks: int | None = None
    previous_period: PreviousFourWeekActivityPublic | None = None


class PreviousFourWeekSummaryPublic(BaseModel):
    period_start_date: date
    period_end_date: date
    sadhana_score: int
    sadhana_max_score: int
    sadhana_percentage: Decimal | None = None
    academic_score: int
    academic_max_score: int
    academic_percentage: Decimal | None = None
    sadhana_change_percentage_points: Decimal | None = None
    academic_change_percentage_points: Decimal | None = None


class FourWeekReportPublic(BaseModel):
    """Project 'monthly' report: exactly four adjacent complete organization weeks."""

    period_start_date: date
    period_end_date: date
    weeks_count: int
    definition: str = "FOUR_ADJACENT_COMPLETE_WEEKS"
    weeks: list[FourWeekWeekPublic] = Field(default_factory=list)
    sadhana: FourWeekScoreSummaryPublic
    academic: FourWeekScoreSummaryPublic
    activities: list[FourWeekActivityPublic] = Field(default_factory=list)
    previous_period: PreviousFourWeekSummaryPublic | None = None
    observations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
