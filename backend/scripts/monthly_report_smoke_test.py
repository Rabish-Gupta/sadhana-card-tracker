"""Step 13 real-PostgreSQL smoke test for the project's four-week 'monthly' report.

The monthly report is deliberately NOT a calendar month.  This script creates a
disposable devotee and inserts eight synthetic, already-computed WeeklyEvaluation
snapshots (the weekly engine itself is covered by Step 10).  The report API must use
the latest four adjacent complete weeks as the current period and the immediately
preceding four adjacent complete weeks as the comparison period.

Synthetic weekly rows are deleted during cleanup; the disposable account is then
logically deactivated.  No production devotee history is modified.
"""
from __future__ import annotations

import argparse
import asyncio
import time as time_module
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import httpx
from sqlalchemy import delete, select

from app.core.enums import VersionStatus
from app.core.timezone import get_week_bounds, organization_local_date
from app.db.session import get_session_factory
from app.models.activity import Activity
from app.models.devotee import DevoteeProfile
from app.models.evaluation_config import CategoryActivityConfig
from app.models.organization import Organization
from app.models.user import User
from app.models.weekly_evaluation import WeeklyActivityResult, WeeklyEvaluation


def expect(response: httpx.Response, status_code: int, step: str):
    if response.status_code != status_code:
        print(f"FAIL: {step}: expected {status_code}, got {response.status_code}")
        print(response.text)
        raise SystemExit(1)
    if response.content:
        return response.json()
    return {}


def pct(score: int, maximum: int) -> Decimal:
    return (Decimal(score) / Decimal(maximum) * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


async def seed_synthetic_weekly_history(email: str) -> str:
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            raise RuntimeError("Disposable monthly-report devotee not found")
        profile = await session.scalar(
            select(DevoteeProfile).where(DevoteeProfile.user_id == user.id)
        )
        organization = await session.get(Organization, user.organization_id)
        if profile is None or organization is None or profile.current_category_id is None:
            raise RuntimeError("Disposable devotee profile/category context missing")

        config_rows = await session.execute(
            select(CategoryActivityConfig, Activity)
            .join(Activity, Activity.id == CategoryActivityConfig.activity_id)
            .where(
                CategoryActivityConfig.category_id == profile.current_category_id,
                CategoryActivityConfig.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
                Activity.code.in_(["BOOK_READING", "SEVA"]),
            )
            .order_by(CategoryActivityConfig.effective_from_week.desc())
        )
        configs: dict[str, tuple[CategoryActivityConfig, Activity]] = {}
        for config, activity in config_rows.all():
            configs.setdefault(activity.code, (config, activity))
        if set(configs) != {"BOOK_READING", "SEVA"}:
            raise RuntimeError("Baseline Book Reading/Seva configuration is missing")

        local_today = organization_local_date(organization.timezone)
        current_week_start, _ = get_week_bounds(local_today, organization.week_start_day)
        latest_complete_week = current_week_start - timedelta(days=7)
        current_period_start = latest_complete_week - timedelta(days=21)
        all_starts = [current_period_start - timedelta(days=28) + timedelta(days=7 * i) for i in range(8)]

        previous_sadhana = [900, 1000, 1100, 1200]
        current_sadhana = [1300, 1400, 1500, 1600]
        previous_academic = [800, 900, 1000, 1100]
        current_academic = [1150, 1250, 1350, 1450]
        sadhana_scores = previous_sadhana + current_sadhana
        academic_scores = previous_academic + current_academic

        for index, week_start in enumerate(all_starts):
            weekly = WeeklyEvaluation(
                organization_id=user.organization_id,
                devotee_profile_id=profile.id,
                week_start_date=week_start,
                week_end_date=week_start + timedelta(days=6),
                category_snapshot_id=profile.current_category_id,
                timezone_snapshot=organization.timezone,
                sadhana_score=sadhana_scores[index],
                sadhana_max_score=1750,
                sadhana_percentage=pct(sadhana_scores[index], 1750),
                academic_score=academic_scores[index],
                academic_max_score=1750,
                academic_percentage=pct(academic_scores[index], 1750),
                revision_number=0,
            )
            session.add(weekly)
            await session.flush()

            book_config, book_activity = configs["BOOK_READING"]
            book_raw = Decimal(250 if index < 4 else 300)
            book_score = 408 if index < 4 else 490
            session.add(
                WeeklyActivityResult(
                    weekly_evaluation_id=weekly.id,
                    activity_id=book_activity.id,
                    category_activity_config_id=book_config.id,
                    aggregation_method="SUM",
                    raw_total=book_raw,
                    daily_score_total=None,
                    final_activity_score=book_score,
                    maximum_score=490,
                    rule_version_id=None,
                    standard_version_id=None,
                    standard_snapshot={"kind": "DURATION", "value": 300, "operator": ">="},
                    standard_achievement=(
                        Decimal("83.33") if index < 4 else Decimal("100.00")
                    ),
                    calculation_details={
                        "standard": {
                            "period": "WEEKLY",
                            "actual": str(book_raw),
                            "target": "300",
                            "operator": ">=",
                            "met": index >= 4,
                        },
                        "evaluated_days": 7,
                    },
                )
            )

            seva_config, seva_activity = configs["SEVA"]
            seva_raw = Decimal(350 if index < 4 else 420)
            session.add(
                WeeklyActivityResult(
                    weekly_evaluation_id=weekly.id,
                    activity_id=seva_activity.id,
                    category_activity_config_id=seva_config.id,
                    aggregation_method="SUM",
                    raw_total=seva_raw,
                    daily_score_total=None,
                    final_activity_score=None,
                    maximum_score=None,
                    rule_version_id=None,
                    standard_version_id=None,
                    standard_snapshot={"kind": "DURATION", "value": 60, "operator": ">="},
                    standard_achievement=(
                        Decimal("85.71") if index < 4 else Decimal("100.00")
                    ),
                    calculation_details={
                        "standard": {
                            "period": "DAILY",
                            "achieved_days": 6 if index < 4 else 7,
                            "evaluated_days": 7,
                            "met_all_days": index >= 4,
                        },
                        "evaluated_days": 7,
                    },
                )
            )
        await session.commit()
        return current_period_start.isoformat()


async def cleanup_synthetic_weekly_history(email: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            return
        profile = await session.scalar(
            select(DevoteeProfile).where(DevoteeProfile.user_id == user.id)
        )
        if profile is None:
            return
        ids = list(
            (
                await session.scalars(
                    select(WeeklyEvaluation.id).where(
                        WeeklyEvaluation.devotee_profile_id == profile.id
                    )
                )
            ).all()
        )
        if ids:
            await session.execute(
                delete(WeeklyActivityResult).where(
                    WeeklyActivityResult.weekly_evaluation_id.in_(ids)
                )
            )
            await session.execute(
                delete(WeeklyEvaluation).where(WeeklyEvaluation.id.in_(ids))
            )
            await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    suffix = str(time_module.time_ns())
    devotee_email = f"monthly-smoke-{suffix}@example.com"
    devotee_password = "DevoteeMonthly123!"
    devotee_id: str | None = None
    admin_headers: dict[str, str] | None = None

    with asyncio.Runner() as runner, httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        try:
            expect(client.get("/health"), 200, "health")
            print("PASS: health")

            registration = expect(
                client.post(
                    "/api/v1/auth/register",
                    json={
                        "full_name": "Monthly Report Smoke Devotee",
                        "email": devotee_email,
                        "password": devotee_password,
                        "phone_number": "+919000000013",
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
            print("PASS: disposable devotee registered and approved")

            devotee_login = expect(
                client.post(
                    "/api/v1/auth/login",
                    json={"email": devotee_email, "password": devotee_password},
                ),
                200,
                "devotee login",
            )
            devotee_headers = {"Authorization": f"Bearer {devotee_login['access_token']}"}

            period_start = runner.run(seed_synthetic_weekly_history(devotee_email))

            latest = expect(
                client.get("/api/v1/monthly/latest", headers=devotee_headers),
                200,
                "latest four-week report",
            )
            assert latest["definition"] == "FOUR_ADJACENT_COMPLETE_WEEKS"
            assert latest["period_start_date"] == period_start
            assert latest["weeks_count"] == 4
            assert len(latest["weeks"]) == 4
            assert latest["sadhana"]["maximum_score"] == 7000
            assert latest["academic"]["maximum_score"] == 7000
            assert latest["previous_period"] is not None
            assert Decimal(latest["previous_period"]["sadhana_change_percentage_points"]) > 0
            assert Decimal(latest["previous_period"]["academic_change_percentage_points"]) > 0
            assert latest["metadata"]["combined_balance_score"] is False
            assert latest["metadata"]["spiritual_advancement_measurement"] is False
            print("PASS: latest report uses four adjacent complete weeks and keeps Sadhana/Academic separate")

            activities = {item["code"]: item for item in latest["activities"]}
            assert activities["BOOK_READING"]["final_score_total"] == 1960
            assert activities["BOOK_READING"]["weekly_standard_met_weeks"] == 4
            assert activities["BOOK_READING"]["previous_period"]["raw_total_sum"] == "1000.00"
            assert activities["SEVA"]["final_score_total"] is None
            assert activities["SEVA"]["raw_total_sum"] == "1680.00"
            assert activities["SEVA"]["daily_standard_achieved_days"] == 28
            print("PASS: activity raw/scored/standard analytics aggregate without giving Seva a score")

            specific = expect(
                client.get(f"/api/v1/monthly/{period_start}", headers=devotee_headers),
                200,
                "specific four-week report",
            )
            assert specific["period_start_date"] == latest["period_start_date"]
            assert specific["period_end_date"] == latest["period_end_date"]
            print("PASS: specific period lookup is deterministic")

            # Starting one week later cannot form four adjacent stored weeks.
            from datetime import date as _date
            invalid_start = (_date.fromisoformat(period_start) + timedelta(days=7)).isoformat()
            expect(
                client.get(f"/api/v1/monthly/{invalid_start}", headers=devotee_headers),
                409,
                "incomplete four-week period blocked",
            )
            print("PASS: incomplete/gapped four-week periods are not mislabeled as monthly reports")

            print("\nALL FOUR-WEEK MONTHLY REPORT SMOKE TESTS PASSED")
        finally:
            runner.run(cleanup_synthetic_weekly_history(devotee_email))
            if devotee_id and admin_headers:
                response = client.post(
                    f"/api/v1/admin/devotees/{devotee_id}/deactivate",
                    headers=admin_headers,
                    json={"reason": "Step 13 monthly report smoke-test cleanup"},
                )
                if response.status_code == 200:
                    print("PASS: disposable devotee logically deactivated")


if __name__ == "__main__":
    main()
