from app.core.enums import ActivityCategory, ScoringType
from app.db.seed_data import ACTIVITY_SEEDS, CATEGORY_SEEDS


def _activity(code: str):
    return next(item for item in ACTIVITY_SEEDS if item.code == code)


def test_seed_catalog_has_approved_categories_and_activities() -> None:
    assert [item.code for item in CATEGORY_SEEDS] == [
        "SAHADEVA",
        "NAKULA",
        "ARJUNA",
        "YUDHISHTHIRA",
        "BHIMA_WORKING",
        "BHIMA_NOT_WORKING",
    ]
    assert len(ACTIVITY_SEEDS) == 12
    assert len({item.code for item in ACTIVITY_SEEDS}) == 12


def test_shared_baseline_weekly_targets_match_v2_specification() -> None:
    book = _activity("BOOK_READING")
    hearing = _activity("PERSONAL_HEARING")

    assert book.standard is not None
    assert book.standard.target_definition["value"] == 300
    assert book.standard.target_definition["unit"] == "MINUTE"
    assert book.rule is not None and book.rule.max_score == 490

    assert hearing.standard is not None
    assert hearing.standard.target_definition["value"] == 120
    assert hearing.rule is not None and hearing.rule.max_score == 210


def test_chanting_seed_preserves_conditional_completion_rule() -> None:
    chanting = _activity("CHANTING")
    assert chanting.rule is not None
    assert chanting.rule.configuration["required_rounds"] == 16
    assert chanting.rule.configuration["thresholds"] == [
        {"before": "09:30", "score": 70},
        {"before": "11:00", "score": 50},
        {"before": "12:30", "score": 30},
        {"before": "16:00", "score": 20},
        {"before": "19:00", "score": 10},
    ]
    fields = {field.key: field for field in chanting.fields}
    assert fields["rounds_chanted"].required_for_completion is True
    assert fields["completion_time"].required_for_completion is False


def test_card_fill_and_non_scored_seva_are_seeded_correctly() -> None:
    filling = _activity("FILLING_SADHANA_CARD")
    seva = _activity("SEVA")

    assert filling.scoring_type == ScoringType.SYSTEM_DERIVED
    assert filling.counts_toward_card_fill is False
    assert filling.rule is not None
    assert filling.rule.configuration["minimum_percentage"] == 75
    assert filling.rule.max_score == 10

    assert seva.scoring_type == ScoringType.NON_SCORED
    assert seva.rule is None
    assert seva.standard is not None
    assert seva.standard.target_definition["value"] == 60


def test_shloka_has_no_weekly_standard() -> None:
    shloka = _activity("SHLOKA_VAISHNAVA_SONG")
    assert shloka.standard is None
    assert shloka.rule is not None
    assert shloka.rule.max_score == 20


def test_baseline_section_weekly_maxima_are_1750_each() -> None:
    totals = {ActivityCategory.SADHANA: 0, ActivityCategory.ACADEMIC: 0}
    for activity in ACTIVITY_SEEDS:
        if activity.rule is None:
            continue
        if activity.scoring_type == ScoringType.WEEKLY_AGGREGATED:
            totals[activity.category] += activity.rule.max_score
        else:
            totals[activity.category] += activity.rule.max_score * 7

    assert totals[ActivityCategory.SADHANA] == 1750
    assert totals[ActivityCategory.ACADEMIC] == 1750


def test_day_rest_exactly_45_minutes_is_in_50_mark_band() -> None:
    day_rest = _activity("DAY_REST")
    assert day_rest.rule is not None
    thresholds = day_rest.rule.configuration["thresholds"]
    assert thresholds[1] == {"operator": "<=", "value": 45, "score": 50}


def test_category_seed_semantics_are_unique_and_stable() -> None:
    assert len({item.code for item in CATEGORY_SEEDS}) == len(CATEGORY_SEEDS)
    identities = {
        (item.code, item.academic_year, item.stage_order, item.employment_status)
        for item in CATEGORY_SEEDS
    }
    assert len(identities) == len(CATEGORY_SEEDS)
