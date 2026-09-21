from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from app.core.enums import ActivityInputType, RuleType, ScoringType
from app.models.daily_card import DailyActivityEntry, DailyActivityValue


class ScoringError(ValueError):
    """Base class for deterministic scoring failures."""


class ScoringConfigurationError(ScoringError):
    """Raised when a persisted scoring rule cannot be evaluated safely."""


@dataclass(frozen=True)
class ScoreOutcome:
    score: int | None
    details: dict[str, Any] | None


_SUPPORTED_OPERATORS = {"<", "<=", ">", ">=", "=", "==", "!="}


def _score_value(value: Any, *, name: str, max_score: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScoringConfigurationError(f"{name} must be an integer score")
    if value < 0 or value > max_score:
        raise ScoringConfigurationError(
            f"{name} must be between 0 and max_score ({max_score})"
        )
    return value


def _require_string(configuration: dict[str, Any], key: str) -> str:
    value = configuration.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ScoringConfigurationError(f"{key} must be a non-empty string")
    return value.strip()


def _parse_time(value: Any, *, name: str) -> time:
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if not isinstance(value, str):
        raise ScoringConfigurationError(f"{name} must be an HH:MM time string")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ScoringConfigurationError(f"{name} must be an HH:MM time string") from exc
    if parsed.tzinfo is not None:
        raise ScoringConfigurationError(f"{name} must be a local time without timezone")
    return parsed


def _parse_decimal(value: Any, *, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ScoringConfigurationError(f"{name} must be numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ScoringConfigurationError(f"{name} must be numeric") from exc
    if not parsed.is_finite():
        raise ScoringConfigurationError(f"{name} must be finite")
    return parsed


def validate_rule_configuration(
    rule_type: RuleType,
    configuration: dict[str, Any],
    max_score: int,
) -> None:
    """Validate the executable shape of a scoring-rule version.

    Step 7 intentionally stores rule bodies as JSONB so future rules remain configurable.
    Step 9 adds the execution contract: only rule shapes understood by the deterministic
    engine may be activated through the Admin API. Seeded baseline rules all conform to
    this contract.
    """

    if not isinstance(configuration, dict):
        raise ScoringConfigurationError("configuration must be a JSON object")
    if max_score < 0:
        raise ScoringConfigurationError("max_score cannot be negative")

    if rule_type == RuleType.NO_SCORE:
        return

    if rule_type == RuleType.BOOLEAN:
        _require_string(configuration, "input_field")
        _score_value(configuration.get("true_score"), name="true_score", max_score=max_score)
        _score_value(configuration.get("false_score"), name="false_score", max_score=max_score)
        return

    if rule_type == RuleType.THRESHOLD:
        thresholds = configuration.get("thresholds")
        if not isinstance(thresholds, list) or not thresholds:
            raise ScoringConfigurationError("thresholds must be a non-empty list")
        _score_value(configuration.get("otherwise"), name="otherwise", max_score=max_score)

        is_rounds_completion_rule = any(
            key in configuration
            for key in ("required_rounds", "rounds_field", "completion_field")
        )
        if is_rounds_completion_rule:
            _require_string(configuration, "rounds_field")
            _require_string(configuration, "completion_field")
            required_rounds = _parse_decimal(
                configuration.get("required_rounds"), name="required_rounds"
            )
            if required_rounds < 0:
                raise ScoringConfigurationError("required_rounds cannot be negative")
            previous: time | None = None
            for index, threshold in enumerate(thresholds):
                if not isinstance(threshold, dict):
                    raise ScoringConfigurationError(
                        f"thresholds[{index}] must be an object"
                    )
                boundary = _parse_time(
                    threshold.get("before"), name=f"thresholds[{index}].before"
                )
                if previous is not None and boundary <= previous:
                    raise ScoringConfigurationError(
                        "time thresholds must be in strictly increasing order"
                    )
                previous = boundary
                _score_value(
                    threshold.get("score"),
                    name=f"thresholds[{index}].score",
                    max_score=max_score,
                )
            return

        _require_string(configuration, "input_field")
        for index, threshold in enumerate(thresholds):
            if not isinstance(threshold, dict):
                raise ScoringConfigurationError(f"thresholds[{index}] must be an object")
            operator = threshold.get("operator")
            if operator not in _SUPPORTED_OPERATORS:
                raise ScoringConfigurationError(
                    f"thresholds[{index}].operator is unsupported"
                )
            if "value" not in threshold:
                raise ScoringConfigurationError(f"thresholds[{index}].value is required")
            _score_value(
                threshold.get("score"),
                name=f"thresholds[{index}].score",
                max_score=max_score,
            )
        return

    if rule_type == RuleType.SYSTEM_DERIVED:
        if configuration.get("formula") != "CARD_COMPLETION_PERCENTAGE":
            raise ScoringConfigurationError(
                "SYSTEM_DERIVED currently supports CARD_COMPLETION_PERCENTAGE only"
            )
        minimum = _parse_decimal(
            configuration.get("minimum_percentage"), name="minimum_percentage"
        )
        if minimum < 0 or minimum > 100:
            raise ScoringConfigurationError("minimum_percentage must be between 0 and 100")
        _score_value(
            configuration.get("score_if_met"),
            name="score_if_met",
            max_score=max_score,
        )
        _score_value(configuration.get("otherwise"), name="otherwise", max_score=max_score)
        if "exclude_self" in configuration and not isinstance(
            configuration["exclude_self"], bool
        ):
            raise ScoringConfigurationError("exclude_self must be boolean")
        return

    if rule_type == RuleType.PERCENTAGE:
        if configuration.get("formula") != "STANDARD_PERCENTAGE_X_MAX_SCORE":
            raise ScoringConfigurationError(
                "PERCENTAGE rules must use STANDARD_PERCENTAGE_X_MAX_SCORE"
            )
        cap = _parse_decimal(configuration.get("cap_percentage"), name="cap_percentage")
        if cap <= 0:
            raise ScoringConfigurationError("cap_percentage must be greater than zero")
        if configuration.get("rounding") != "HALF_UP":
            raise ScoringConfigurationError("Only HALF_UP percentage rounding is supported")
        return

    raise ScoringConfigurationError(f"Unsupported rule type: {rule_type.value}")


def _values_by_key(entry: DailyActivityEntry) -> dict[str, DailyActivityValue]:
    return {value.activity_field.field_key: value for value in entry.values}


def _typed_value(value: DailyActivityValue) -> Decimal | time | bool | str | None:
    if not value.is_filled:
        return None
    input_type = value.activity_field.input_type
    if input_type in {
        ActivityInputType.NUMBER,
        ActivityInputType.COUNT,
        ActivityInputType.DURATION,
    }:
        return value.numeric_value
    if input_type == ActivityInputType.TIME:
        return value.time_value
    if input_type == ActivityInputType.BOOLEAN:
        return value.boolean_value
    if input_type in {ActivityInputType.TEXT, ActivityInputType.SELECTION}:
        return value.text_value
    raise ScoringConfigurationError(
        f"Unsupported activity input type: {input_type.value}"
    )


def _json_value(value: Decimal | time | bool | str | None) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return str(value.normalize())
    if isinstance(value, time):
        return value.isoformat(timespec="seconds")
    return value


def _coerce_threshold_value(raw: Any, actual: Decimal | time | bool | str) -> Any:
    if isinstance(actual, Decimal):
        return _parse_decimal(raw, name="threshold value")
    if isinstance(actual, time):
        return _parse_time(raw, name="threshold value")
    if isinstance(actual, bool):
        if not isinstance(raw, bool):
            raise ScoringConfigurationError("threshold value must be boolean")
        return raw
    if isinstance(actual, str):
        if not isinstance(raw, str):
            raise ScoringConfigurationError("threshold value must be text")
        return raw
    raise ScoringConfigurationError("Unsupported threshold input value")


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "<":
        return actual < expected
    if operator == "<=":
        return actual <= expected
    if operator == ">":
        return actual > expected
    if operator == ">=":
        return actual >= expected
    if operator in {"=", "=="}:
        return actual == expected
    if operator == "!=":
        return actual != expected
    raise ScoringConfigurationError(f"Unsupported threshold operator: {operator}")


def _ensure_outcome_within_max(outcome: ScoreOutcome, *, max_score: int) -> ScoreOutcome:
    if outcome.score is None:
        return outcome
    if outcome.score < 0 or outcome.score > max_score:
        raise ScoringConfigurationError(
            f"Calculated score {outcome.score} is outside 0..{max_score}"
        )
    return outcome


def _evaluate_boolean(entry: DailyActivityEntry, configuration: dict[str, Any]) -> ScoreOutcome:
    field_key = _require_string(configuration, "input_field")
    values = _values_by_key(entry)
    raw = values.get(field_key)
    if raw is None or not raw.is_filled:
        return ScoreOutcome(
            score=0,
            details={
                "rule_type": RuleType.BOOLEAN.value,
                "input_field": field_key,
                "input_filled": False,
                "reason": "MISSING_INPUT",
            },
        )
    actual = _typed_value(raw)
    if not isinstance(actual, bool):
        raise ScoringConfigurationError(f"{field_key} must be a boolean activity field")
    score = configuration["true_score"] if actual else configuration["false_score"]
    return ScoreOutcome(
        score=int(score),
        details={
            "rule_type": RuleType.BOOLEAN.value,
            "input_field": field_key,
            "input_filled": True,
            "input_value": actual,
            "matched": actual,
        },
    )


def _evaluate_rounds_completion_threshold(
    entry: DailyActivityEntry,
    configuration: dict[str, Any],
) -> ScoreOutcome:
    values = _values_by_key(entry)
    rounds_key = _require_string(configuration, "rounds_field")
    completion_key = _require_string(configuration, "completion_field")
    required = _parse_decimal(configuration.get("required_rounds"), name="required_rounds")
    otherwise = int(configuration["otherwise"])

    rounds_raw = values.get(rounds_key)
    if rounds_raw is None or not rounds_raw.is_filled:
        return ScoreOutcome(
            score=otherwise,
            details={
                "rule_type": RuleType.THRESHOLD.value,
                "mode": "REQUIRED_ROUNDS_COMPLETION_TIME",
                "rounds_field": rounds_key,
                "rounds_filled": False,
                "required_rounds": _json_value(required),
                "reason": "MISSING_ROUNDS",
            },
        )
    rounds = _typed_value(rounds_raw)
    if not isinstance(rounds, Decimal):
        raise ScoringConfigurationError(f"{rounds_key} must be numeric")
    if rounds < required:
        return ScoreOutcome(
            score=otherwise,
            details={
                "rule_type": RuleType.THRESHOLD.value,
                "mode": "REQUIRED_ROUNDS_COMPLETION_TIME",
                "rounds_field": rounds_key,
                "rounds": _json_value(rounds),
                "required_rounds": _json_value(required),
                "reason": "REQUIRED_ROUNDS_NOT_REACHED",
            },
        )

    completion_raw = values.get(completion_key)
    if completion_raw is None or not completion_raw.is_filled:
        return ScoreOutcome(
            score=otherwise,
            details={
                "rule_type": RuleType.THRESHOLD.value,
                "mode": "REQUIRED_ROUNDS_COMPLETION_TIME",
                "rounds_field": rounds_key,
                "rounds": _json_value(rounds),
                "required_rounds": _json_value(required),
                "completion_field": completion_key,
                "completion_filled": False,
                "reason": "MISSING_COMPLETION_TIME",
            },
        )
    completion = _typed_value(completion_raw)
    if not isinstance(completion, time):
        raise ScoringConfigurationError(f"{completion_key} must be a time activity field")

    for threshold in configuration["thresholds"]:
        boundary = _parse_time(threshold["before"], name="threshold.before")
        if completion < boundary:
            return ScoreOutcome(
                score=int(threshold["score"]),
                details={
                    "rule_type": RuleType.THRESHOLD.value,
                    "mode": "REQUIRED_ROUNDS_COMPLETION_TIME",
                    "rounds": _json_value(rounds),
                    "required_rounds": _json_value(required),
                    "completion_time": _json_value(completion),
                    "matched_threshold": {
                        "operator": "<",
                        "value": boundary.isoformat(timespec="minutes"),
                        "score": int(threshold["score"]),
                    },
                },
            )

    return ScoreOutcome(
        score=otherwise,
        details={
            "rule_type": RuleType.THRESHOLD.value,
            "mode": "REQUIRED_ROUNDS_COMPLETION_TIME",
            "rounds": _json_value(rounds),
            "required_rounds": _json_value(required),
            "completion_time": _json_value(completion),
            "reason": "NO_THRESHOLD_MATCH",
        },
    )


def _evaluate_threshold(entry: DailyActivityEntry, configuration: dict[str, Any]) -> ScoreOutcome:
    if all(
        key in configuration
        for key in ("required_rounds", "rounds_field", "completion_field")
    ):
        return _evaluate_rounds_completion_threshold(entry, configuration)

    field_key = _require_string(configuration, "input_field")
    values = _values_by_key(entry)
    raw = values.get(field_key)
    if raw is None or not raw.is_filled:
        return ScoreOutcome(
            score=int(configuration["otherwise"]),
            details={
                "rule_type": RuleType.THRESHOLD.value,
                "input_field": field_key,
                "input_filled": False,
                "reason": "MISSING_INPUT",
            },
        )
    actual = _typed_value(raw)
    if actual is None:
        return ScoreOutcome(
            score=int(configuration["otherwise"]),
            details={
                "rule_type": RuleType.THRESHOLD.value,
                "input_field": field_key,
                "input_filled": False,
                "reason": "MISSING_TYPED_VALUE",
            },
        )

    for threshold in configuration["thresholds"]:
        operator = str(threshold["operator"])
        expected = _coerce_threshold_value(threshold["value"], actual)
        if _compare(actual, operator, expected):
            return ScoreOutcome(
                score=int(threshold["score"]),
                details={
                    "rule_type": RuleType.THRESHOLD.value,
                    "input_field": field_key,
                    "input_value": _json_value(actual),
                    "matched_threshold": {
                        "operator": operator,
                        "value": _json_value(expected),
                        "score": int(threshold["score"]),
                    },
                },
            )

    return ScoreOutcome(
        score=int(configuration["otherwise"]),
        details={
            "rule_type": RuleType.THRESHOLD.value,
            "input_field": field_key,
            "input_value": _json_value(actual),
            "reason": "NO_THRESHOLD_MATCH",
        },
    )


def _evaluate_card_completion(
    entry: DailyActivityEntry,
    configuration: dict[str, Any],
    *,
    card_entries: Iterable[DailyActivityEntry],
) -> ScoreOutcome:
    exclude_self = configuration.get("exclude_self", True)
    countable: list[DailyActivityEntry] = []
    for candidate in card_entries:
        if exclude_self and candidate.id == entry.id:
            continue
        if candidate.category_activity_config.counts_toward_card_fill:
            countable.append(candidate)

    completed = sum(1 for candidate in countable if candidate.is_filled)
    total = len(countable)
    percentage = (
        (Decimal(completed) * Decimal("100") / Decimal(total))
        if total
        else Decimal("0")
    )
    minimum = _parse_decimal(
        configuration.get("minimum_percentage"), name="minimum_percentage"
    )
    met = total > 0 and percentage >= minimum
    score = int(configuration["score_if_met"] if met else configuration["otherwise"])
    percentage_display = percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ScoreOutcome(
        score=score,
        details={
            "rule_type": RuleType.SYSTEM_DERIVED.value,
            "formula": "CARD_COMPLETION_PERCENTAGE",
            "completed_count": completed,
            "countable_count": total,
            "completion_percentage": str(percentage_display),
            "minimum_percentage": str(minimum.normalize()),
            "met": met,
        },
    )


def evaluate_daily_entry(
    entry: DailyActivityEntry,
    *,
    card_entries: Iterable[DailyActivityEntry] | None = None,
    allow_system_derived: bool = False,
) -> ScoreOutcome:
    """Evaluate one snapshotted daily entry using its exact stored rule version.

    Weekly-aggregated and non-scored activities intentionally return ``score=None``;
    their raw daily values are consumed by the later weekly evaluator. System-derived
    entries are evaluated only when ``allow_system_derived`` is true (finalization or
    an explicit historical recalculation), preserving the approved "at auto-finalization"
    card-fill rule.
    """

    scoring_type = entry.category_activity_config.scoring_type
    if scoring_type in {ScoringType.WEEKLY_AGGREGATED, ScoringType.NON_SCORED}:
        return ScoreOutcome(score=None, details=None)

    if entry.rule_version is None:
        raise ScoringConfigurationError(
            f"{entry.activity.code} has no snapshotted scoring-rule version"
        )
    rule = entry.rule_version.scoring_rule
    if rule is None:
        raise ScoringConfigurationError(
            f"{entry.activity.code} scoring-rule metadata was not loaded"
        )

    max_score = (
        entry.max_score_snapshot
        if entry.max_score_snapshot is not None
        else entry.rule_version.max_score
    )
    validate_rule_configuration(rule.rule_type, entry.rule_version.configuration, max_score)

    if scoring_type == ScoringType.SYSTEM_DERIVED:
        if not allow_system_derived:
            return ScoreOutcome(score=None, details=None)
        if rule.rule_type != RuleType.SYSTEM_DERIVED:
            raise ScoringConfigurationError(
                f"{entry.activity.code} SYSTEM_DERIVED config requires a SYSTEM_DERIVED rule"
            )
        if card_entries is None:
            raise ScoringConfigurationError(
                "System-derived scoring requires all card entries"
            )
        outcome = _evaluate_card_completion(
            entry,
            entry.rule_version.configuration,
            card_entries=card_entries,
        )
        return _ensure_outcome_within_max(outcome, max_score=max_score)

    if scoring_type != ScoringType.DAILY:
        raise ScoringConfigurationError(
            f"Unsupported daily scoring type: {scoring_type.value}"
        )

    if rule.rule_type == RuleType.BOOLEAN:
        outcome = _evaluate_boolean(entry, entry.rule_version.configuration)
    elif rule.rule_type == RuleType.THRESHOLD:
        outcome = _evaluate_threshold(entry, entry.rule_version.configuration)
    elif rule.rule_type == RuleType.NO_SCORE:
        outcome = ScoreOutcome(score=None, details=None)
    else:
        raise ScoringConfigurationError(
            f"Rule type {rule.rule_type.value} cannot be used for DAILY scoring"
        )
    return _ensure_outcome_within_max(outcome, max_score=max_score)
