"""Step 10 end-to-end weekly evaluation smoke test.

The test uses one disposable devotee.  Because a newly approved account is, by policy,
not eligible for its partial first week, the script first proves that no official weekly
row is produced.  It then backdates only that disposable account's approval timestamp to
the current organization-week boundary and simulates the remainder of the week through
the domain service seam.  This lets us verify a full 7-day weekly evaluation without
changing the computer clock or polluting real devotees' data.

All baseline daily inputs are set to their full-score/standard targets.  Expected weekly
maxima therefore remain Sadhana=1750 and Academic=1750, with Book Reading 300 min -> 490
and Personal Hearing 120 min -> 210.  The account is logically deactivated afterward;
the cleanup audit timestamp is moved just after the simulated week so test history stays
consistent with the approved no-partial-week policy.
"""
from __future__ import annotations

import argparse
import asyncio
import time as time_module
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.enums import ActivityInputType
from app.core.timezone import get_week_bounds, organization_local_date
from app.db.session import get_session_factory
from app.models.audit import AuditLog
from app.models.daily_card import DailyActivityEntry, DailyActivityValue
from app.models.devotee import DevoteeCategoryHistory, DevoteeProfile
from app.models.organization import Organization
from app.models.user import User
from app.services.daily_cards import materialize_and_finalize_for_scheduler
from app.services.weekly_evaluations import (
    PartialLifecycleWeekError,
    generate_weekly_evaluation,
)


def expect(response: httpx.Response, status_code: int, step: str):
    if response.status_code != status_code:
        print(f"FAIL: {step}: expected {status_code}, got {response.status_code}")
        print(response.text)
        raise SystemExit(1)
    if response.content:
        return response.json()
    return {}


def by_code(summary: dict) -> dict[str, dict]:
    return {activity["code"]: activity for activity in summary["activities"]}


def _set_value(value: DailyActivityValue, raw) -> None:
    value.is_filled = True
    input_type = value.activity_field.input_type
    if input_type in {ActivityInputType.NUMBER, ActivityInputType.COUNT, ActivityInputType.DURATION}:
        value.numeric_value = Decimal(str(raw))
    elif input_type == ActivityInputType.TIME:
        value.time_value = raw
    elif input_type == ActivityInputType.BOOLEAN:
        value.boolean_value = bool(raw)
    else:
        value.text_value = str(raw)


def _entry_by_code(card, code: str) -> DailyActivityEntry:
    for entry in card.activity_entries:
        if entry.activity.code == code:
            return entry
    raise RuntimeError(f"Missing activity {code}")


def _value_by_key(entry: DailyActivityEntry, field_key: str) -> DailyActivityValue:
    for value in entry.values:
        if value.activity_field.field_key == field_key:
            return value
    raise RuntimeError(f"Missing field {entry.activity.code}.{field_key}")


async def prepare_full_week(email: str) -> tuple[str, str]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.devotee_profile).selectinload(DevoteeProfile.category_history))
        )
        user = result.scalar_one()
        organization = await session.get(Organization, user.organization_id)
        if organization is None or user.devotee_profile is None:
            raise RuntimeError("Disposable devotee context missing")

        local_today = organization_local_date(organization.timezone)
        week_start, week_end = get_week_bounds(local_today, organization.week_start_day)
        zone = ZoneInfo(organization.timezone)
        start_utc = datetime.combine(week_start, time.min, tzinfo=zone).astimezone(timezone.utc)
        simulated_after_week = datetime.combine(
            week_end + timedelta(days=1), time(hour=1), tzinfo=zone
        ).astimezone(timezone.utc)

        # First prove policy A on the just-approved account.
        try:
            await generate_weekly_evaluation(
                session,
                user=user,
                week_start=week_start,
                now_utc=simulated_after_week,
            )
        except PartialLifecycleWeekError:
            print("PASS: partial approval week is excluded from official weekly scoring (no proration)")
        else:
            raise RuntimeError("Partial lifecycle week unexpectedly produced an official evaluation")

        # Test-only backdate so this disposable account represents a full eligible week.
        user.approved_at = start_utc - timedelta(seconds=1)
        history = user.devotee_profile.category_history
        if len(history) != 1:
            raise RuntimeError("Smoke devotee should have exactly one initial category history row")
        history[0].effective_from_week = week_start
        await session.commit()

        book_minutes = [45, 45, 45, 45, 40, 40, 40]  # 300 total
        hearing_minutes = [20, 20, 20, 15, 15, 15, 15]  # 120 total

        for index in range(7):
            card_date = week_start + timedelta(days=index)
            pre_deadline_now = datetime.combine(
                card_date, time(hour=12), tzinfo=zone
            ).astimezone(timezone.utc)
            card = await materialize_and_finalize_for_scheduler(
                session,
                user=user,
                target_date=card_date,
                now_utc=pre_deadline_now,
            )

            perfect_inputs = {
                ("MORNING_PROGRAM", "attended"): True,
                ("CHANTING", "rounds_chanted"): 16,
                ("CHANTING", "completion_time"): time(9, 0),
                ("BOOK_READING", "minutes"): book_minutes[index],
                ("MORNING_CLASS", "attended"): True,
                ("PERSONAL_HEARING", "minutes"): hearing_minutes[index],
                ("SHLOKA_VAISHNAVA_SONG", "count_learned"): 1,
                ("STUDY_PREPARATION", "minutes"): 120,
                ("TO_BED", "bedtime"): time(21, 0),
                ("WAKE_UP", "wake_up_time"): time(3, 30),
                ("DAY_REST", "minutes"): 0,
                ("SEVA", "minutes"): 60,
            }
            for (activity_code, field_key), raw in perfect_inputs.items():
                entry = _entry_by_code(card, activity_code)
                _set_value(_value_by_key(entry, field_key), raw)
            await session.commit()

            await materialize_and_finalize_for_scheduler(
                session,
                user=user,
                target_date=card_date,
                now_utc=card.deadline_at_utc + timedelta(seconds=1),
            )

        evaluation = await generate_weekly_evaluation(
            session,
            user=user,
            week_start=week_start,
            now_utc=simulated_after_week,
        )
        assert evaluation.sadhana_score == 1750
        assert evaluation.sadhana_max_score == 1750
        assert evaluation.academic_score == 1750
        assert evaluation.academic_max_score == 1750
        print("PASS: full-week service evaluation keeps Sadhana and Academic maxima separate at 1750 each")
        return week_start.isoformat(), simulated_after_week.isoformat()


async def move_cleanup_after_week(email: str, simulated_after_week_iso: str) -> None:
    simulated_after_week = datetime.fromisoformat(simulated_after_week_iso)
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            return
        user.deactivated_at = simulated_after_week
        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "USER",
                AuditLog.entity_id == user.id,
                AuditLog.action == "ACCOUNT_DEACTIVATED",
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        audit = result.scalar_one_or_none()
        if audit is not None:
            audit.created_at = simulated_after_week
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    suffix = str(time_module.time_ns())
    devotee_email = f"weekly-smoke-{suffix}@example.com"
    devotee_password = "DevoteeWeekly123!"
    devotee_id: str | None = None
    admin_headers: dict[str, str] | None = None
    simulated_after_week_iso: str | None = None

    # Reuse one asyncio event loop for all direct database helper calls.
    # The SQLAlchemy async engine is process-cached; calling asyncio.run() twice would
    # create two event loops and could make a pooled asyncpg connection from the first
    # loop unusable during cleanup on Windows ("Event loop is closed").
    with asyncio.Runner() as runner, httpx.Client(base_url=base, timeout=30.0) as client:
        try:
            health = expect(client.get("/health"), 200, "health")
            assert health["status"] == "ok"
            print("PASS: health")

            registration = expect(
                client.post(
                    "/api/v1/auth/register",
                    json={
                        "full_name": "Weekly Evaluation Smoke Devotee",
                        "email": devotee_email,
                        "password": devotee_password,
                        "phone_number": "+919000000004",
                        "college": "Smoke Test Institute",
                        "branch": "Computer Science",
                        "current_academic_year": 3,
                        "college_joining_year": 2024,
                    },
                ),
                201,
                "self registration",
            )
            devotee_id = registration["user_id"]
            print("PASS: disposable devotee registered")

            admin_login = expect(
                client.post(
                    "/api/v1/auth/login",
                    json={"email": args.admin_email, "password": args.admin_password},
                ),
                200,
                "admin login",
            )
            admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
            expect(
                client.post(
                    f"/api/v1/admin/registrations/{devotee_id}/approve",
                    headers=admin_headers,
                ),
                200,
                "approve disposable devotee",
            )
            print("PASS: disposable devotee approved")

            devotee_login = expect(
                client.post(
                    "/api/v1/auth/login",
                    json={"email": devotee_email, "password": devotee_password},
                ),
                200,
                "devotee login",
            )
            devotee_headers = {"Authorization": f"Bearer {devotee_login['access_token']}"}

            week_start, simulated_after_week_iso = runner.run(prepare_full_week(devotee_email))

            summary = expect(
                client.get(f"/api/v1/weekly/{week_start}", headers=devotee_headers),
                200,
                "read persisted weekly evaluation",
            )
            assert summary["sadhana_score"] == 1750
            assert summary["sadhana_max_score"] == 1750
            assert summary["academic_score"] == 1750
            assert summary["academic_max_score"] == 1750
            assert "combined_score" not in summary
            activities = by_code(summary)
            assert len(activities) == 12

            book = activities["BOOK_READING"]
            assert Decimal(book["raw_total"]) == Decimal("300.00")
            assert book["final_activity_score"] == 490
            assert book["maximum_score"] == 490
            assert Decimal(book["standard_achievement"]) == Decimal("100.00")

            hearing = activities["PERSONAL_HEARING"]
            assert Decimal(hearing["raw_total"]) == Decimal("120.00")
            assert hearing["final_activity_score"] == 210
            assert hearing["maximum_score"] == 210

            seva = activities["SEVA"]
            assert Decimal(seva["raw_total"]) == Decimal("420.00")
            assert seva["final_activity_score"] is None
            assert seva["maximum_score"] is None
            assert Decimal(seva["standard_achievement"]) == Decimal("100.00")

            morning_program = activities["MORNING_PROGRAM"]
            assert morning_program["calculation_details"]["standard"]["achieved_days"] == 7
            assert morning_program["calculation_details"]["standard"]["evaluated_days"] == 7
            print("PASS: weekly percentage rules, raw aggregates, daily-standard 7/7 analysis, and Seva non-score")

            again = expect(
                client.get(f"/api/v1/weekly/{week_start}", headers=devotee_headers),
                200,
                "weekly evaluation idempotency",
            )
            assert again["id"] == summary["id"]
            assert again["revision_number"] == 0
            print("PASS: weekly evaluation persistence is idempotent")

        finally:
            if devotee_id and admin_headers:
                response = client.post(
                    f"/api/v1/admin/devotees/{devotee_id}/deactivate",
                    headers=admin_headers,
                    json={"reason": "Step 10 automated weekly-evaluation smoke test cleanup"},
                )
                if response.status_code == 200:
                    if simulated_after_week_iso:
                        runner.run(move_cleanup_after_week(devotee_email, simulated_after_week_iso))
                    print("PASS: disposable devotee logically deactivated")
                else:
                    print(
                        "WARN: cleanup failed; deactivate disposable user manually:",
                        devotee_email,
                        response.status_code,
                        response.text,
                    )

    print("\nALL WEEKLY EVALUATION SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
