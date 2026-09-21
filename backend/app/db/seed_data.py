"""Approved v2.0 baseline seed catalogue.

This module contains data only. It deliberately mirrors the approved documentation
rather than burying scoring values inside service code. The actual seeder persists
these specifications as normal configurable/versioned database records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import (
    ActivityCategory,
    ActivityInputType,
    AggregationMethod,
    EmploymentStatus,
    RuleType,
    ScoringType,
    StandardPeriod,
)


@dataclass(frozen=True)
class CategorySeed:
    code: str
    display_name: str
    academic_year: int | None
    stage_order: int
    employment_status: EmploymentStatus | None = None


@dataclass(frozen=True)
class FieldSeed:
    key: str
    label: str
    input_type: ActivityInputType
    unit_code: str | None
    display_order: int
    required_for_completion: bool = True


@dataclass(frozen=True)
class RuleSeed:
    key: str
    name: str
    rule_type: RuleType
    max_score: int
    configuration: dict[str, Any]


@dataclass(frozen=True)
class StandardSeed:
    key: str
    name: str
    period: StandardPeriod
    target_definition: dict[str, Any]


@dataclass(frozen=True)
class ActivitySeed:
    code: str
    name: str
    category: ActivityCategory
    scoring_type: ScoringType
    weekly_aggregation: AggregationMethod
    fields: tuple[FieldSeed, ...]
    rule: RuleSeed | None
    standard: StandardSeed | None
    counts_toward_card_fill: bool = True
    is_system_derived: bool = False
    description: str | None = None


CATEGORY_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed("SAHADEVA", "Sahadeva", 1, 1),
    CategorySeed("NAKULA", "Nakula", 2, 2),
    CategorySeed("ARJUNA", "Arjuna", 3, 3),
    CategorySeed("YUDHISHTHIRA", "Yudhishthira", 4, 4),
    CategorySeed(
        "BHIMA_WORKING",
        "Bhima - Working",
        None,
        5,
        EmploymentStatus.WORKING,
    ),
    CategorySeed(
        "BHIMA_NOT_WORKING",
        "Bhima - Not Working",
        None,
        5,
        EmploymentStatus.NOT_WORKING,
    ),
)


ACTIVITY_SEEDS: tuple[ActivitySeed, ...] = (
    ActivitySeed(
        code="MORNING_PROGRAM",
        name="Morning Program",
        category=ActivityCategory.SADHANA,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("attended", "Attended", ActivityInputType.BOOLEAN, None, 1),
        ),
        rule=RuleSeed(
            "MORNING_PROGRAM_BASELINE",
            "Morning Program - Shared Baseline",
            RuleType.BOOLEAN,
            30,
            {
                "input_field": "attended",
                "true_score": 30,
                "false_score": 0,
            },
        ),
        standard=StandardSeed(
            "MORNING_PROGRAM_STANDARD",
            "Morning Program - Daily Attendance Standard",
            StandardPeriod.DAILY,
            {"kind": "BOOLEAN", "value": True, "operator": "="},
        ),
        description="Daily Morning Program attendance.",
    ),
    ActivitySeed(
        code="CHANTING",
        name="Chanting",
        category=ActivityCategory.SADHANA,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed(
                "rounds_chanted",
                "Rounds Chanted",
                ActivityInputType.COUNT,
                "ROUND",
                1,
            ),
            # Conditional: required only when rounds_chanted >= 16. Generic field
            # completeness therefore leaves this false; the chanting evaluator enforces it.
            FieldSeed(
                "completion_time",
                "16-Round Completion Time",
                ActivityInputType.TIME,
                None,
                2,
                required_for_completion=False,
            ),
        ),
        rule=RuleSeed(
            "CHANTING_BASELINE",
            "Chanting - Shared Baseline",
            RuleType.THRESHOLD,
            70,
            {
                "required_rounds": 16,
                "rounds_field": "rounds_chanted",
                "completion_field": "completion_time",
                "thresholds": [
                    {"before": "09:30", "score": 70},
                    {"before": "11:00", "score": 50},
                    {"before": "12:30", "score": 30},
                    {"before": "16:00", "score": 20},
                    {"before": "19:00", "score": 10},
                ],
                "otherwise": 0,
            },
        ),
        standard=StandardSeed(
            "CHANTING_STANDARD",
            "Chanting - Daily Rounds Standard",
            StandardPeriod.DAILY,
            {"kind": "COUNT", "value": 16, "unit": "ROUND", "operator": ">="},
        ),
        description="Daily chanting rounds and the time the required 16 rounds are completed.",
    ),
    ActivitySeed(
        code="BOOK_READING",
        name="Book Reading",
        category=ActivityCategory.SADHANA,
        scoring_type=ScoringType.WEEKLY_AGGREGATED,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("minutes", "Book Reading", ActivityInputType.DURATION, "MINUTE", 1),
        ),
        rule=RuleSeed(
            "BOOK_READING_BASELINE",
            "Book Reading - Shared Baseline",
            RuleType.PERCENTAGE,
            490,
            {
                "formula": "STANDARD_PERCENTAGE_X_MAX_SCORE",
                "cap_percentage": 100,
                "rounding": "HALF_UP",
            },
        ),
        standard=StandardSeed(
            "BOOK_READING_STANDARD",
            "Book Reading - Weekly Standard",
            StandardPeriod.WEEKLY,
            {"kind": "DURATION", "value": 300, "unit": "MINUTE", "operator": ">="},
        ),
        description="Daily reading minutes aggregated and scored at the end of the week.",
    ),
    ActivitySeed(
        code="MORNING_CLASS",
        name="Morning Class",
        category=ActivityCategory.SADHANA,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("attended", "Attended", ActivityInputType.BOOLEAN, None, 1),
        ),
        rule=RuleSeed(
            "MORNING_CLASS_BASELINE",
            "Morning Class - Shared Baseline",
            RuleType.BOOLEAN,
            30,
            {"input_field": "attended", "true_score": 30, "false_score": 0},
        ),
        standard=StandardSeed(
            "MORNING_CLASS_STANDARD",
            "Morning Class - Daily Attendance Standard",
            StandardPeriod.DAILY,
            {"kind": "BOOLEAN", "value": True, "operator": "="},
        ),
        description="Daily scheduled Morning Class attendance.",
    ),
    ActivitySeed(
        code="PERSONAL_HEARING",
        name="Personal Hearing",
        category=ActivityCategory.SADHANA,
        scoring_type=ScoringType.WEEKLY_AGGREGATED,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("minutes", "Personal Hearing", ActivityInputType.DURATION, "MINUTE", 1),
        ),
        rule=RuleSeed(
            "PERSONAL_HEARING_BASELINE",
            "Personal Hearing - Shared Baseline",
            RuleType.PERCENTAGE,
            210,
            {
                "formula": "STANDARD_PERCENTAGE_X_MAX_SCORE",
                "cap_percentage": 100,
                "rounding": "HALF_UP",
            },
        ),
        standard=StandardSeed(
            "PERSONAL_HEARING_STANDARD",
            "Personal Hearing - Weekly Standard",
            StandardPeriod.WEEKLY,
            {"kind": "DURATION", "value": 120, "unit": "MINUTE", "operator": ">="},
        ),
        description="Daily hearing minutes aggregated and scored at the end of the week.",
    ),
    ActivitySeed(
        code="SHLOKA_VAISHNAVA_SONG",
        name="Shloka / Vaishnava Song",
        category=ActivityCategory.SADHANA,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed(
                "count_learned",
                "Number Learned / Memorized",
                ActivityInputType.COUNT,
                "COUNT",
                1,
            ),
        ),
        rule=RuleSeed(
            "SHLOKA_VAISHNAVA_SONG_BASELINE",
            "Shloka / Vaishnava Song - Shared Baseline",
            RuleType.THRESHOLD,
            20,
            {
                "input_field": "count_learned",
                "thresholds": [{"operator": ">", "value": 0, "score": 20}],
                "otherwise": 0,
            },
        ),
        standard=None,
        description="Number of new shlokas or Vaishnava songs learned/memorized that day.",
    ),
    ActivitySeed(
        code="STUDY_PREPARATION",
        name="Study / Preparation",
        category=ActivityCategory.ACADEMIC,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("minutes", "Study / Preparation", ActivityInputType.DURATION, "MINUTE", 1),
        ),
        rule=RuleSeed(
            "STUDY_PREPARATION_BASELINE",
            "Study / Preparation - Shared Baseline",
            RuleType.THRESHOLD,
            30,
            {
                "input_field": "minutes",
                "thresholds": [
                    {"operator": ">=", "value": 120, "score": 30},
                    {"operator": ">=", "value": 60, "score": 20},
                    {"operator": ">=", "value": 30, "score": 10},
                ],
                "otherwise": 0,
            },
        ),
        standard=StandardSeed(
            "STUDY_PREPARATION_STANDARD",
            "Study / Preparation - Daily Standard",
            StandardPeriod.DAILY,
            {"kind": "DURATION", "value": 120, "unit": "MINUTE", "operator": ">="},
        ),
        description="Daily academic study/preparation duration.",
    ),
    ActivitySeed(
        code="TO_BED",
        name="To Bed",
        category=ActivityCategory.ACADEMIC,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("bedtime", "Bedtime", ActivityInputType.TIME, None, 1),
        ),
        rule=RuleSeed(
            "TO_BED_BASELINE",
            "To Bed - Shared Baseline",
            RuleType.THRESHOLD,
            70,
            {
                "input_field": "bedtime",
                "thresholds": [
                    {"operator": "<", "value": "21:15", "score": 70},
                    {"operator": "<", "value": "21:30", "score": 50},
                    {"operator": "<", "value": "21:45", "score": 30},
                    {"operator": "<", "value": "22:00", "score": 10},
                ],
                "otherwise": 0,
            },
        ),
        standard=StandardSeed(
            "TO_BED_STANDARD",
            "To Bed - Daily Standard",
            StandardPeriod.DAILY,
            {"kind": "TIME", "value": "21:15", "operator": "<"},
        ),
        description="Daily bedtime. Intentionally part of Academic evaluation per approved design.",
    ),
    ActivitySeed(
        code="WAKE_UP",
        name="Wake Up",
        category=ActivityCategory.ACADEMIC,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("wake_up_time", "Wake-up Time", ActivityInputType.TIME, None, 1),
        ),
        rule=RuleSeed(
            "WAKE_UP_BASELINE",
            "Wake Up - Shared Baseline",
            RuleType.THRESHOLD,
            70,
            {
                "input_field": "wake_up_time",
                "thresholds": [
                    {"operator": "<", "value": "03:40", "score": 70},
                    {"operator": "<", "value": "03:50", "score": 50},
                    {"operator": "<", "value": "04:00", "score": 30},
                    {"operator": "<", "value": "04:15", "score": 10},
                ],
                "otherwise": 0,
            },
        ),
        standard=StandardSeed(
            "WAKE_UP_STANDARD",
            "Wake Up - Daily Standard",
            StandardPeriod.DAILY,
            {"kind": "TIME", "value": "03:45", "operator": "<"},
        ),
        description="Daily wake-up time. Intentionally part of Academic evaluation per approved design.",
    ),
    ActivitySeed(
        code="DAY_REST",
        name="Day Rest",
        category=ActivityCategory.ACADEMIC,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("minutes", "Day Rest", ActivityInputType.DURATION, "MINUTE", 1),
        ),
        rule=RuleSeed(
            "DAY_REST_BASELINE",
            "Day Rest - Shared Baseline",
            RuleType.THRESHOLD,
            70,
            {
                "input_field": "minutes",
                "thresholds": [
                    {"operator": "<", "value": 30, "score": 70},
                    {"operator": "<=", "value": 45, "score": 50},
                    {"operator": "<=", "value": 60, "score": 30},
                ],
                "otherwise": 0,
            },
        ),
        standard=StandardSeed(
            "DAY_REST_STANDARD",
            "Day Rest - Daily Standard",
            StandardPeriod.DAILY,
            {"kind": "DURATION", "value": 30, "unit": "MINUTE", "operator": "<"},
        ),
        description="Daily rest duration. Intentionally part of Academic evaluation per approved design.",
    ),
    ActivitySeed(
        code="FILLING_SADHANA_CARD",
        name="Filling Sadhana Card",
        category=ActivityCategory.ACADEMIC,
        scoring_type=ScoringType.SYSTEM_DERIVED,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(),
        rule=RuleSeed(
            "FILLING_SADHANA_CARD_BASELINE",
            "Filling Sadhana Card - Shared Baseline",
            RuleType.SYSTEM_DERIVED,
            10,
            {
                "formula": "CARD_COMPLETION_PERCENTAGE",
                "minimum_percentage": 75,
                "score_if_met": 10,
                "otherwise": 0,
                "exclude_self": True,
            },
        ),
        standard=StandardSeed(
            "FILLING_SADHANA_CARD_STANDARD",
            "Filling Sadhana Card - Daily Standard",
            StandardPeriod.DAILY,
            {"kind": "BOOLEAN", "value": True, "operator": "="},
        ),
        counts_toward_card_fill=False,
        is_system_derived=True,
        description="System-derived score based on completing at least 75% of countable activities.",
    ),
    ActivitySeed(
        code="SEVA",
        name="Seva",
        category=ActivityCategory.ACADEMIC,
        scoring_type=ScoringType.NON_SCORED,
        weekly_aggregation=AggregationMethod.SUM,
        fields=(
            FieldSeed("minutes", "Seva", ActivityInputType.DURATION, "MINUTE", 1),
        ),
        rule=None,
        standard=StandardSeed(
            "SEVA_STANDARD",
            "Seva - Daily Standard",
            StandardPeriod.DAILY,
            {"kind": "DURATION", "value": 60, "unit": "MINUTE", "operator": ">="},
        ),
        description="Seva duration is stored for standards and analysis but carries no marks.",
    ),
)


CATEGORY_CODES = tuple(seed.code for seed in CATEGORY_SEEDS)
ACTIVITY_CODES = tuple(seed.code for seed in ACTIVITY_SEEDS)
