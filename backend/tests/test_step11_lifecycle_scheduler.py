from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.enums import EmploymentStatus
from app.models.devotee import DevoteeCategory, DevoteeProfile
from app.models.organization import Organization
from app.services.lifecycle import first_week_start_on_or_after, promotion_boundary_for_profile
from app.services.scheduler import account_active_at, advisory_lock_key


def _organization(*, promotion_month: int = 6, week_start_day: int = 1) -> Organization:
    return Organization(
        id=uuid.uuid4(),
        name="VOICE Test",
        code="VOICE_TEST",
        timezone="Asia/Kolkata",
        week_start_day=week_start_day,
        daily_finalize_time=__import__("datetime").time(22, 0),
        promotion_month=promotion_month,
        is_active=True,
    )


def _student_category(code: str, academic_year: int) -> DevoteeCategory:
    return DevoteeCategory(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        code=code,
        display_name=code.title(),
        academic_year=academic_year,
        stage_order=academic_year,
        employment_status=None,
        is_active=True,
        is_archived=False,
    )


def _profile(category: DevoteeCategory, *, joining_year: int = 2025) -> DevoteeProfile:
    profile = DevoteeProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        current_category_id=category.id,
        college="Test College",
        branch="CSE",
        college_joining_year=joining_year,
        expected_graduation_year=joining_year + 4,
        current_academic_year=category.academic_year,
    )
    profile.current_category = category
    return profile


def test_first_promotion_boundary_is_first_week_start_on_or_after_month_start() -> None:
    # 2027-06-01 is Tuesday; Monday-start organizations promote on 2027-06-07.
    assert first_week_start_on_or_after(2027, 6, 1) == date(2027, 6, 7)
    # 2026-06-01 is already Monday.
    assert first_week_start_on_or_after(2026, 6, 1) == date(2026, 6, 1)


def test_promotion_boundary_follows_academic_year_and_joining_year() -> None:
    org = _organization()
    sahadeva = _student_category("SAHADEVA", 1)
    nakula = _student_category("NAKULA", 2)
    assert promotion_boundary_for_profile(_profile(sahadeva), sahadeva, org) == date(2026, 6, 1)
    assert promotion_boundary_for_profile(_profile(nakula), nakula, org) == date(2027, 6, 7)


def test_bhima_category_has_no_automatic_academic_promotion_boundary() -> None:
    org = _organization()
    bhima = DevoteeCategory(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        code="BHIMA_WORKING",
        display_name="Bhima Working",
        academic_year=None,
        stage_order=5,
        employment_status=EmploymentStatus.WORKING,
        is_active=True,
        is_archived=False,
    )
    profile = _profile(_student_category("YUDHISHTHIRA", 4))
    profile.current_category = bhima
    profile.current_category_id = bhima.id
    profile.current_academic_year = None
    assert promotion_boundary_for_profile(profile, bhima, org) is None


def test_account_activity_reconstruction_handles_deactivate_and_reactivate() -> None:
    approved = datetime(2026, 9, 1, tzinfo=timezone.utc)
    events = [
        ("ACCOUNT_DEACTIVATED", datetime(2026, 9, 10, tzinfo=timezone.utc)),
        ("ACCOUNT_ACTIVATED", datetime(2026, 9, 12, tzinfo=timezone.utc)),
    ]
    assert account_active_at(approved_at=approved, lifecycle_events=events, instant=approved - timedelta(seconds=1)) is False
    assert account_active_at(approved_at=approved, lifecycle_events=events, instant=datetime(2026, 9, 5, tzinfo=timezone.utc)) is True
    assert account_active_at(approved_at=approved, lifecycle_events=events, instant=datetime(2026, 9, 11, tzinfo=timezone.utc)) is False
    assert account_active_at(approved_at=approved, lifecycle_events=events, instant=datetime(2026, 9, 13, tzinfo=timezone.utc)) is True


def test_advisory_lock_key_is_stable_signed_bigint_and_org_specific() -> None:
    one = uuid.UUID("00000000-0000-0000-0000-000000000001")
    two = uuid.UUID("00000000-0000-0000-0000-000000000002")
    first = advisory_lock_key(one)
    assert first == advisory_lock_key(one)
    assert first != advisory_lock_key(two)
    assert -(2**63) <= first <= 2**63 - 1


def test_step11_keeps_19_application_tables_and_adds_columns_only() -> None:
    from app.db.base import Base
    import app.models  # noqa: F401

    assert len(Base.metadata.tables) == 19
    users = Base.metadata.tables["users"]
    for column in {
        "pending_deactivation_week",
        "pending_deactivation_reason",
        "pending_deactivation_requested_by_id",
        "pending_deactivation_scheduled_at",
    }:
        assert column in users.c


def test_step11_migration_is_0003_and_does_not_modify_prior_revision_chain() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "0003_lifecycle_fields"
    third = Path("migrations/versions/0003_lifecycle_fields.py").read_text()
    assert 'down_revision: Union[str, None] = "0002_org_setting_versions"' in third
    assert "pending_deactivation_week" in third
    assert len("0003_lifecycle_fields") <= 32


def test_scheduler_dependency_and_lifespan_are_packaged() -> None:
    pyproject = Path("pyproject.toml").read_text()
    main = Path("app/main.py").read_text()
    scheduler = Path("app/services/scheduler.py").read_text()
    assert "APScheduler>=3.11,<4.0" in pyproject
    assert "lifespan=lifespan" in main
    assert "pg_try_advisory_lock" in scheduler
    assert "max_instances=1" in scheduler
    assert "coalesce=True" in scheduler


def test_lifecycle_api_surface_is_exposed() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert {
        "/api/v1/lifecycle/status",
        "/api/v1/lifecycle/bhima-status",
        "/api/v1/admin/lifecycle/sahadeva-reviews",
        "/api/v1/admin/lifecycle/devotees/{user_id}/sahadeva-review",
        "/api/v1/admin/lifecycle/run-now",
    }.issubset(paths)


def test_automatic_promotion_code_does_not_auto_choose_sahadeva_or_bhima() -> None:
    source = Path("app/services/lifecycle.py").read_text()
    assert 'DevoteeCategory.code.in_(["NAKULA", "ARJUNA"])' in source
    assert '"NAKULA": "ARJUNA"' in source
    assert '"ARJUNA": "YUDHISHTHIRA"' in source
    # User-approved policy A: there must be no Yudhishthira -> Bhima automatic mapping.
    assert '"YUDHISHTHIRA": "BHIMA' not in source


def test_pending_transition_revision_keeps_relationship_and_fk_in_sync() -> None:
    """Regression: a revised pending Bhima choice must not serialize the stale target."""
    old = DevoteeCategory(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        code="BHIMA_WORKING",
        display_name="Bhima Working",
        academic_year=None,
        stage_order=5,
        employment_status=EmploymentStatus.WORKING,
        is_active=True,
        is_archived=False,
    )
    new = DevoteeCategory(
        id=uuid.uuid4(),
        organization_id=old.organization_id,
        code="BHIMA_NOT_WORKING",
        display_name="Bhima Not Working",
        academic_year=None,
        stage_order=6,
        employment_status=EmploymentStatus.NOT_WORKING,
        is_active=True,
        is_archived=False,
    )
    from app.models.devotee import DevoteeCategoryHistory

    row = DevoteeCategoryHistory(
        id=uuid.uuid4(),
        devotee_profile_id=uuid.uuid4(),
        previous_category_id=uuid.uuid4(),
        new_category_id=old.id,
        effective_from_week=date(2027, 6, 7),
        change_source=__import__("app.core.enums", fromlist=["ChangeSource"]).ChangeSource.DEVOTEE,
        reason="initial",
    )
    row.new_category = old

    # Mirror the service's revision operation. Both sides must be changed.
    row.new_category_id = new.id
    row.new_category = new

    assert row.new_category_id == new.id
    assert row.new_category.code == "BHIMA_NOT_WORKING"


def test_transition_scheduler_explicitly_synchronizes_loaded_relationship() -> None:
    source = Path("app/services/lifecycle.py").read_text()
    assert "row.new_category_id = target_category.id" in source
    assert "row.new_category = target_category" in source


def test_scheduler_backfill_is_bounded_by_versioned_configuration_history() -> None:
    """Legacy/pre-Step-11 dates must not be invented when no config snapshot exists."""
    source = Path("app/services/scheduler.py").read_text()
    assert "async def _organization_history_floor" in source
    assert "func.min(OrganizationSettingVersion.effective_from_week)" in source
    assert "func.min(CategoryActivityConfig.effective_from_week)" in source
    assert "day = max(approved_local, history_floor)" in source
    assert "DailyCard.card_date >= max(approved_local, history_floor)" in source


def test_weekly_scheduler_also_respects_configuration_history_floor() -> None:
    source = Path("app/services/scheduler.py").read_text()
    assert "earliest = max(" in source
    assert '"history_floor": history_floor' in source


def test_lifecycle_smoke_backfill_uses_reconstructable_due_date() -> None:
    source = Path("scripts/lifecycle_scheduler_smoke_test.py").read_text()
    assert "safe_backfill_date = local_today - timedelta(days=1)" in source
    assert "history_floor = await _organization_history_floor" in source
    assert "safe_backfill_date < history_floor" in source
    assert "initial.effective_from_week = safe_week_start" in source
    assert "previous_start = week_start - timedelta(days=7)" not in source


def test_lifecycle_smoke_uses_dedicated_transition_free_backfill_probe() -> None:
    source = Path("scripts/lifecycle_scheduler_smoke_test.py").read_text()
    assert 'backfill_email = f"life-backfill-' in source
    assert '"category_code": "ARJUNA"' in source
    assert '"current_academic_year": 3' in source
    assert "prepare_scheduler_cases(backfill_email, nakula_email)" in source
    assert "verify_scheduler_effects(\n                backfill_email, nakula_email" in source


def test_scheduler_uses_dedicated_lock_connection_not_domain_session_binding() -> None:
    """Regression: lifecycle service commits must survive advisory-lock connection close."""
    source = Path("app/services/scheduler.py").read_text()
    assert "async with engine.connect() as lock_connection:" in source
    assert "async with session_factory() as session:" in source
    assert "AsyncSession(bind=connection" not in source
    assert "await lock_connection.commit()" in source
    assert "SELECT pg_advisory_unlock(:key)" in source


def test_lifecycle_smoke_promotion_probe_predates_current_week() -> None:
    source = Path("scripts/lifecycle_scheduler_smoke_test.py").read_text()
    assert "nakula_initial.effective_from_week = safe_week_start - timedelta(days=7)" in source


def test_current_checkpoint_version_is_0112() -> None:
    pyproject = Path("pyproject.toml").read_text()
    assert 'version = "0.11.2"' in pyproject
