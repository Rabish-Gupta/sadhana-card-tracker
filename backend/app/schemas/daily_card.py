from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import (
    ActivityCategory,
    ActivityInputType,
    AggregationMethod,
    CardStatus,
    ScoringType,
)


class DailyActivityValuePublic(BaseModel):
    field_id: uuid.UUID
    field_key: str
    label: str
    input_type: ActivityInputType
    unit_code: str | None
    display_order: int
    required_for_completion: bool
    is_filled: bool
    numeric_value: Decimal
    time_value: time | None
    boolean_value: bool | None
    text_value: str | None


class DailyActivityPublic(BaseModel):
    entry_id: uuid.UUID
    activity_id: uuid.UUID
    code: str
    name: str
    category: ActivityCategory
    scoring_type: ScoringType
    weekly_aggregation: AggregationMethod | None
    is_system_derived: bool
    counts_toward_card_fill: bool
    is_filled: bool
    daily_score: int | None
    max_score_snapshot: int | None
    score_calculated_at: datetime | None
    score_details: dict | None
    values: list[DailyActivityValuePublic]


class DailyCardPublic(BaseModel):
    id: uuid.UUID
    card_date: date
    status: CardStatus
    editable: bool
    category_code: str
    category_name: str
    first_update_at: datetime | None
    last_update_at: datetime | None
    finalized_at: datetime | None
    timezone_snapshot: str
    deadline_time_snapshot: time
    deadline_at_utc: datetime
    revision_number: int
    activities: list[DailyActivityPublic]


class DailyActivityValueUpdate(BaseModel):
    field_id: uuid.UUID
    is_filled: bool = True
    numeric_value: Decimal | None = None
    time_value: time | None = None
    boolean_value: bool | None = None
    text_value: str | None = None

    @model_validator(mode="after")
    def validate_value_shape(self) -> "DailyActivityValueUpdate":
        supplied = [
            self.numeric_value is not None,
            self.time_value is not None,
            self.boolean_value is not None,
            self.text_value is not None,
        ]
        count = sum(supplied)
        if self.is_filled:
            if count != 1:
                raise ValueError(
                    "A filled field must supply exactly one typed value"
                )
        elif count != 0:
            raise ValueError(
                "An unfilled field must not include numeric/time/boolean/text values"
            )
        return self


class DailyActivityUpdate(BaseModel):
    activity_id: uuid.UUID
    values: list[DailyActivityValueUpdate] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_fields(self) -> "DailyActivityUpdate":
        field_ids = [item.field_id for item in self.values]
        if len(set(field_ids)) != len(field_ids):
            raise ValueError("Duplicate field_id values are not allowed in one activity update")
        return self


class DailyCardUpdateRequest(BaseModel):
    activities: list[DailyActivityUpdate] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_activities(self) -> "DailyCardUpdateRequest":
        activity_ids = [item.activity_id for item in self.activities]
        if len(set(activity_ids)) != len(activity_ids):
            raise ValueError("Duplicate activity_id values are not allowed in one update")
        return self
