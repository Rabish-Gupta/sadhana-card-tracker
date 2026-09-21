from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import ChangeSource, EmploymentStatus
from app.schemas.base import ORMModel


class SahadevaReviewRequest(BaseModel):
    decision: Literal["CONTINUE_TO_NAKULA", "DEACTIVATE"]
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def normalize_reason(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 3:
            raise ValueError("Reason is required")
        return self


class BhimaStatusChangeRequest(BaseModel):
    employment_status: EmploymentStatus
    reason: str = Field(default="Devotee updated Bhima employment status", min_length=3, max_length=1000)

    @model_validator(mode="after")
    def normalize_reason(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 3:
            raise ValueError("Reason is required")
        return self


class PendingCategoryTransitionPublic(BaseModel):
    history_id: uuid.UUID
    target_category_code: str
    target_category_name: str
    effective_from_week: date
    change_source: ChangeSource
    reason: str


class LifecycleStatusPublic(BaseModel):
    current_category_code: str
    current_category_name: str
    current_academic_year: int | None
    next_promotion_week: date | None
    sahadeva_review_due: bool
    bhima_choice_required: bool
    pending_category_transition: PendingCategoryTransitionPublic | None
    pending_deactivation_week: date | None
    pending_deactivation_reason: str | None


class SahadevaReviewItem(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    due_week: date
    review_due: bool
    pending_decision: Literal["CONTINUE_TO_NAKULA", "DEACTIVATE"] | None
    pending_effective_week: date | None


class SahadevaReviewResult(BaseModel):
    user_id: uuid.UUID
    decision: Literal["CONTINUE_TO_NAKULA", "DEACTIVATE"]
    effective_from_week: date
    scheduled_at: datetime


class LifecycleRunResult(BaseModel):
    organization_id: uuid.UUID
    lock_acquired: bool
    configuration_activated: dict[str, int | str]
    pending_academic_lifecycle_rescheduled: int
    automatic_promotions_scheduled: int
    category_transitions_applied: int
    deactivations_applied: int
    cards_materialized_or_finalized: int
    weekly_evaluations_generated: int
    weekly_evaluations_skipped_partial: int
