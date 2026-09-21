from datetime import date

import pytest
from pydantic import ValidationError

from app.core.enums import AggregationMethod, ScoringType
from app.main import app
from app.schemas.configuration import (
    OrganizationSettingVersionCreateRequest,
    OrganizationSettingVersionUpdateRequest,
    CategoryActivityConfigCreateRequest,
    ScoringRuleVersionCreateRequest,
)
from app.services.configuration_admin import ConfigurationConflictError, _validate_pending_week


class _Org:
    timezone = "Asia/Kolkata"
    week_start_day = 1


def test_step7_admin_configuration_routes_exist() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/admin/config/categories",
        "/api/v1/admin/config/organization-settings/current",
        "/api/v1/admin/config/organization-settings/versions",
        "/api/v1/admin/config/organization-setting-versions/{version_id}",
        "/api/v1/admin/config/activities",
        "/api/v1/admin/config/activities/{activity_id}/fields",
        "/api/v1/admin/config/activity-fields/{field_id}",
        "/api/v1/admin/config/scoring-rules",
        "/api/v1/admin/config/scoring-rules/{rule_id}/versions",
        "/api/v1/admin/config/scoring-rule-versions/{version_id}",
        "/api/v1/admin/config/standards",
        "/api/v1/admin/config/standards/{standard_id}/versions",
        "/api/v1/admin/config/standard-versions/{version_id}",
        "/api/v1/admin/config/category-activity-configs",
        "/api/v1/admin/config/category-activity-configs/{config_id}",
        "/api/v1/admin/config/activate-due",
    }
    assert expected.issubset(paths)


def test_non_applicable_config_cannot_count_toward_card_fill() -> None:
    with pytest.raises(ValidationError):
        CategoryActivityConfigCreateRequest(
            category_id="00000000-0000-0000-0000-000000000001",
            activity_id="00000000-0000-0000-0000-000000000002",
            is_applicable=False,
            scoring_type=ScoringType.NON_SCORED,
            weekly_aggregation=AggregationMethod.SUM,
            counts_toward_card_fill=True,
        )


def test_non_scored_config_rejects_scoring_rule() -> None:
    with pytest.raises(ValidationError):
        CategoryActivityConfigCreateRequest(
            category_id="00000000-0000-0000-0000-000000000001",
            activity_id="00000000-0000-0000-0000-000000000002",
            scoring_type=ScoringType.NON_SCORED,
            weekly_aggregation=AggregationMethod.SUM,
            scoring_rule_id="00000000-0000-0000-0000-000000000003",
        )


def test_pending_effective_week_must_be_week_boundary_and_not_current_week(monkeypatch) -> None:
    import app.services.configuration_admin as module

    monkeypatch.setattr(module, "organization_local_date", lambda _: date(2026, 9, 18))
    assert _validate_pending_week(_Org(), None) == date(2026, 9, 21)
    with pytest.raises(Exception):
        _validate_pending_week(_Org(), date(2026, 9, 22))
    with pytest.raises(ConfigurationConflictError):
        _validate_pending_week(_Org(), date(2026, 9, 14))


def test_scoring_rule_version_payload_allows_generic_json_configuration() -> None:
    payload = ScoringRuleVersionCreateRequest(
        max_score=70,
        configuration={"thresholds": [{"before": "09:30", "score": 70}]},
    )
    assert payload.max_score == 70
    assert payload.configuration["thresholds"][0]["score"] == 70


def test_organization_setting_change_validates_iana_timezone() -> None:
    payload = OrganizationSettingVersionCreateRequest(timezone="Asia/Kolkata")
    assert payload.timezone == "Asia/Kolkata"

    with pytest.raises(ValidationError):
        OrganizationSettingVersionCreateRequest(timezone="Not/A_Real_Timezone")


def test_organization_setting_change_requires_actual_setting_field() -> None:
    with pytest.raises(ValidationError):
        OrganizationSettingVersionCreateRequest(effective_from_week=date(2026, 9, 21))


def test_organization_setting_weekday_and_promotion_month_are_bounded() -> None:
    with pytest.raises(ValidationError):
        OrganizationSettingVersionCreateRequest(week_start_day=7)
    with pytest.raises(ValidationError):
        OrganizationSettingVersionCreateRequest(promotion_month=13)


def test_organization_setting_patch_rejects_empty_body() -> None:
    with pytest.raises(ValidationError):
        OrganizationSettingVersionUpdateRequest()
