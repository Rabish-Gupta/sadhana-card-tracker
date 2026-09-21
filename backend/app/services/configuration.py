from __future__ import annotations

from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, TypeVar

from app.core.enums import ActivityInputType, RuleType, ScoringType, StandardPeriod, VersionStatus
from app.core.timezone import get_week_bounds
from app.models.evaluation_config import CategoryActivityConfig
from app.models.scoring import ScoringRule
from app.models.standard import Standard


class ConfigurationValidationError(ValueError):
    """Raised when an Admin configuration would violate project invariants."""




_STANDARD_OPERATORS = {"=", ">=", ">", "<=", "<"}
_STANDARD_KINDS = {"BOOLEAN", "TIME", "COUNT", "DURATION", "NUMBER"}
_STANDARD_KIND_TO_INPUT = {
    "BOOLEAN": ActivityInputType.BOOLEAN,
    "TIME": ActivityInputType.TIME,
    "COUNT": ActivityInputType.COUNT,
    "DURATION": ActivityInputType.DURATION,
    "NUMBER": ActivityInputType.NUMBER,
}


def _standard_decimal(value: Any, *, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ConfigurationValidationError(f"{name} must be numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ConfigurationValidationError(f"{name} must be numeric") from exc
    if not parsed.is_finite():
        raise ConfigurationValidationError(f"{name} must be finite")
    return parsed


def validate_standard_target_definition(
    period: StandardPeriod,
    definition: dict[str, Any],
) -> None:
    """Validate the executable JSON contract consumed by weekly analysis.

    Standards are versioned historical configuration, so malformed JSON must be rejected
    before it can become active.  Weekly standards currently operate on numeric aggregates;
    daily standards may target boolean, local time, count, duration, or number fields.
    """

    if not isinstance(definition, dict):
        raise ConfigurationValidationError("target_definition must be a JSON object")

    missing = {key for key in ("kind", "value", "operator") if key not in definition}
    if missing:
        raise ConfigurationValidationError(
            "target_definition requires kind, value, and operator"
        )

    kind_raw = definition.get("kind")
    if not isinstance(kind_raw, str) or not kind_raw.strip():
        raise ConfigurationValidationError("standard kind must be a non-empty string")
    kind = kind_raw.strip().upper()
    if kind not in _STANDARD_KINDS:
        raise ConfigurationValidationError(f"Unsupported standard kind: {kind}")

    operator = definition.get("operator")
    if operator not in _STANDARD_OPERATORS:
        raise ConfigurationValidationError(f"Unsupported standard operator: {operator}")

    if period == StandardPeriod.WEEKLY and kind not in {"COUNT", "DURATION", "NUMBER"}:
        raise ConfigurationValidationError(
            "WEEKLY standards currently require COUNT, DURATION, or NUMBER targets"
        )

    value = definition.get("value")
    if kind == "BOOLEAN":
        if not isinstance(value, bool):
            raise ConfigurationValidationError("BOOLEAN standard value must be true or false")
        if operator != "=":
            raise ConfigurationValidationError("BOOLEAN standards support '=' only")
    elif kind == "TIME":
        if isinstance(value, time):
            if value.tzinfo is not None:
                raise ConfigurationValidationError(
                    "TIME standard value must be a local time without timezone"
                )
        elif isinstance(value, str):
            try:
                parsed = time.fromisoformat(value)
            except ValueError as exc:
                raise ConfigurationValidationError(
                    "TIME standard value must be a valid local HH:MM time"
                ) from exc
            if parsed.tzinfo is not None:
                raise ConfigurationValidationError(
                    "TIME standard value must be a local time without timezone"
                )
        else:
            raise ConfigurationValidationError(
                "TIME standard value must be a valid local HH:MM time"
            )
    else:
        numeric = _standard_decimal(value, name=f"{kind} standard value")
        if kind in {"COUNT", "DURATION"} and numeric < 0:
            raise ConfigurationValidationError(f"{kind} standard value cannot be negative")
        if kind == "COUNT" and numeric != numeric.to_integral_value():
            raise ConfigurationValidationError("COUNT standard value must be a whole number")

    field_key = definition.get("field_key")
    if field_key is not None and (not isinstance(field_key, str) or not field_key.strip()):
        raise ConfigurationValidationError("field_key must be a non-empty string when supplied")
    unit = definition.get("unit")
    if unit is not None and (not isinstance(unit, str) or not unit.strip()):
        raise ConfigurationValidationError("unit must be a non-empty string when supplied")


def standard_kind_input_type(definition: dict[str, Any]) -> ActivityInputType:
    """Return the raw input type represented by a validated target definition."""

    kind = str(definition.get("kind", "")).upper()
    try:
        return _STANDARD_KIND_TO_INPUT[kind]
    except KeyError as exc:
        raise ConfigurationValidationError(f"Unsupported standard kind: {kind}") from exc
class EffectiveVersion(Protocol):
    effective_from_week: date
    status: VersionStatus


TVersion = TypeVar("TVersion", bound=EffectiveVersion)


def require_week_boundary(effective_from_week: date, week_start_day: int) -> None:
    """Ensure a config/version becomes effective only at an organization week start."""

    resolved_week_start, _ = get_week_bounds(effective_from_week, week_start_day)
    if resolved_week_start != effective_from_week:
        raise ConfigurationValidationError(
            "effective_from_week must be the organization's configured week start"
        )


def resolve_latest_effective_version(
    versions: list[TVersion],
    target_week_start: date,
) -> TVersion | None:
    """Resolve the latest non-pending version effective for a target week.

    ARCHIVED versions remain eligible for historical resolution. This is deliberate:
    archived means "not current for new weeks", not "invalid historically".
    """

    eligible = [
        version
        for version in versions
        if version.status in {VersionStatus.ACTIVE, VersionStatus.ARCHIVED}
        and version.effective_from_week <= target_week_start
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda version: version.effective_from_week)


def validate_category_activity_config(
    config: CategoryActivityConfig,
    *,
    scoring_rule: ScoringRule | None,
    standard: Standard | None,
) -> None:
    """Validate the cross-entity invariants of one category/activity configuration.

    Database foreign keys protect existence. This service protects semantic integrity:
    a category cannot accidentally point an activity to a rule/standard belonging to
    another organization or activity, and required evaluation pieces cannot be omitted.
    """

    if not config.is_applicable:
        if config.counts_toward_card_fill:
            raise ConfigurationValidationError(
                "A non-applicable activity cannot count toward card-fill completion"
            )
        return

    if config.scoring_rule_id is None:
        if config.scoring_type != ScoringType.NON_SCORED:
            raise ConfigurationValidationError(
                f"{config.scoring_type.value} activities require a scoring rule"
            )
    else:
        if scoring_rule is None:
            raise ConfigurationValidationError("Configured scoring rule was not supplied")
        if scoring_rule.id != config.scoring_rule_id:
            raise ConfigurationValidationError("Resolved scoring rule does not match config")
        if scoring_rule.organization_id != config.organization_id:
            raise ConfigurationValidationError(
                "Scoring rule must belong to the same organization as the config"
            )
        if scoring_rule.activity_id != config.activity_id:
            raise ConfigurationValidationError(
                "Scoring rule must belong to the same activity as the config"
            )

    if config.standard_id is not None:
        if standard is None:
            raise ConfigurationValidationError("Configured standard was not supplied")
        if standard.id != config.standard_id:
            raise ConfigurationValidationError("Resolved standard does not match config")
        if standard.organization_id != config.organization_id:
            raise ConfigurationValidationError(
                "Standard must belong to the same organization as the config"
            )
        if standard.activity_id != config.activity_id:
            raise ConfigurationValidationError(
                "Standard must belong to the same activity as the config"
            )

    if config.weekly_aggregation is None:
        raise ConfigurationValidationError(
            f"{config.scoring_type.value} activities need a weekly aggregation method"
        )

    if config.scoring_type == ScoringType.NON_SCORED and config.scoring_rule_id is not None:
        raise ConfigurationValidationError("NON_SCORED activities cannot have a scoring rule")

    if scoring_rule is not None and scoring_rule.rule_type == RuleType.PERCENTAGE:
        if config.standard_id is None:
            raise ConfigurationValidationError(
                "Percentage-based scoring requires a configured standard"
            )
