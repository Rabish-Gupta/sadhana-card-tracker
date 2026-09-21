from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.daily_card import DailyActivityUpdate, DailyCardPublic
from app.schemas.weekly_evaluation import WeeklyEvaluationPublic


class HistoricalCardCorrectionRequest(BaseModel):
    """Admin-only correction of raw values on an already-finalized card.

    The request intentionally reuses the typed DailyActivityUpdate contract so missing
    versus intentional zero/False semantics remain identical to normal devotee updates.
    """

    reason: str = Field(min_length=3, max_length=1000)
    activities: list[DailyActivityUpdate] = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Reason is required")
        return value

    @model_validator(mode="after")
    def reject_duplicate_activities(self) -> "HistoricalCardCorrectionRequest":
        activity_ids = [item.activity_id for item in self.activities]
        if len(set(activity_ids)) != len(activity_ids):
            raise ValueError("Duplicate activity_id values are not allowed in one correction")
        return self


class HistoricalCardCorrectionResult(BaseModel):
    devotee_user_id: uuid.UUID
    card_date: date
    card: DailyCardPublic
    weekly_evaluation_recalculated: bool
    weekly_evaluation: WeeklyEvaluationPublic | None = None


class CategoryHistoryEntryPublic(BaseModel):
    id: uuid.UUID
    previous_category_code: str | None
    new_category_code: str
    effective_from_week: date
    change_source: str
    reason: str
    changed_by_id: uuid.UUID | None = None


class HistoricalCategoryHistoryPublic(BaseModel):
    devotee_user_id: uuid.UUID
    current_category_code: str
    current_academic_year: int | None
    history: list[CategoryHistoryEntryPublic]


class HistoricalCategoryCorrectionRequest(BaseModel):
    """Correct a category transition from one week forward until the next transition.

    Approved policy B: the corrected category is effective from ``effective_from_week``
    and remains effective until the next actual category transition.  If a recorded next
    transition becomes redundant because it transitions to the same corrected category,
    that no-op history row is removed and the correction naturally continues until the
    next different transition.
    """

    effective_from_week: date
    target_category_code: str = Field(min_length=2, max_length=50)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("target_category_code")
    @classmethod
    def normalize_category_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("target_category_code is required")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_category_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Reason is required")
        return value


class HistoricalCategoryCorrectionResult(BaseModel):
    devotee_user_id: uuid.UUID
    correction_batch_id: uuid.UUID
    effective_from_week: date
    effective_until_exclusive: date | None = None
    previous_category_code: str
    corrected_category_code: str
    next_transition_category_code: str | None = None
    history_rows_removed_as_redundant: int
    affected_daily_cards: int
    affected_weekly_evaluations: int
    current_profile_updated: bool
    current_category_code: str
    current_academic_year: int | None
