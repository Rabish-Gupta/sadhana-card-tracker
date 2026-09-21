import uuid
from datetime import time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums import ActivityInputType
from app.main import app
from app.models.activity import ActivityField
from app.models.daily_card import DailyActivityValue
from app.schemas.daily_card import DailyActivityValueUpdate
from app.services.daily_cards import compute_activity_completion


def _field(
    key: str,
    input_type: ActivityInputType,
    *,
    required: bool = True,
) -> ActivityField:
    return ActivityField(
        id=uuid.uuid4(),
        activity_id=uuid.uuid4(),
        field_key=key,
        label=key,
        input_type=input_type,
        unit_code=None,
        display_order=1,
        required_for_completion=required,
        is_active=True,
        is_archived=False,
    )


def _value(field: ActivityField, *, filled: bool, numeric=Decimal("0"), time_value=None, boolean=None):
    return DailyActivityValue(
        id=uuid.uuid4(),
        daily_activity_entry_id=uuid.uuid4(),
        activity_field_id=field.id,
        is_filled=filled,
        numeric_value=Decimal(str(numeric)),
        time_value=time_value,
        boolean_value=boolean,
        text_value=None,
    )


def test_step8_daily_card_routes_exist() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/cards/today",
        "/api/v1/cards/{card_date}",
    }
    assert expected.issubset(paths)

    operations = app.openapi()["paths"]["/api/v1/cards/today"]
    assert "get" in operations
    assert "patch" in operations


def test_intentional_zero_is_a_valid_filled_numeric_update() -> None:
    payload = DailyActivityValueUpdate(
        field_id=uuid.uuid4(),
        is_filled=True,
        numeric_value=Decimal("0"),
    )
    assert payload.is_filled is True
    assert payload.numeric_value == Decimal("0")


def test_unfilled_update_rejects_a_typed_value() -> None:
    with pytest.raises(ValidationError):
        DailyActivityValueUpdate(
            field_id=uuid.uuid4(),
            is_filled=False,
            numeric_value=Decimal("0"),
        )


def test_boolean_false_counts_as_filled_for_completion() -> None:
    attended = _field("attended", ActivityInputType.BOOLEAN)
    value = _value(attended, filled=True, boolean=False)
    assert compute_activity_completion(
        fields=[attended],
        values=[value],
        rule_configuration=None,
    ) is True


def test_missing_required_field_is_incomplete() -> None:
    minutes = _field("minutes", ActivityInputType.DURATION)
    value = _value(minutes, filled=False, numeric=0)
    assert compute_activity_completion(
        fields=[minutes],
        values=[value],
        rule_configuration=None,
    ) is False


def test_chanting_below_sixteen_rounds_is_complete_without_completion_time() -> None:
    rounds = _field("rounds_chanted", ActivityInputType.COUNT)
    completion = _field(
        "completion_time",
        ActivityInputType.TIME,
        required=False,
    )
    values = [
        _value(rounds, filled=True, numeric=12),
        _value(completion, filled=False),
    ]
    config = {
        "required_rounds": 16,
        "rounds_field": "rounds_chanted",
        "completion_field": "completion_time",
    }
    assert compute_activity_completion(
        fields=[rounds, completion],
        values=values,
        rule_configuration=config,
    ) is True


def test_chanting_sixteen_rounds_requires_completion_time() -> None:
    rounds = _field("rounds_chanted", ActivityInputType.COUNT)
    completion = _field(
        "completion_time",
        ActivityInputType.TIME,
        required=False,
    )
    config = {
        "required_rounds": 16,
        "rounds_field": "rounds_chanted",
        "completion_field": "completion_time",
    }
    incomplete_values = [
        _value(rounds, filled=True, numeric=16),
        _value(completion, filled=False),
    ]
    assert compute_activity_completion(
        fields=[rounds, completion],
        values=incomplete_values,
        rule_configuration=config,
    ) is False

    complete_values = [
        _value(rounds, filled=True, numeric=16),
        _value(completion, filled=True, time_value=time(8, 30)),
    ]
    assert compute_activity_completion(
        fields=[rounds, completion],
        values=complete_values,
        rule_configuration=config,
    ) is True
