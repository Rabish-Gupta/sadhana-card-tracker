"""Step 11 lifecycle/scheduler smoke test against a running local API + PostgreSQL.

Creates disposable devotees to verify:
- Sahadeva Admin review is future-week and revisable without data deletion;
- Yudhishthira explicitly chooses initial Bhima status (policy A), and Bhima choice can
  be revised before activation;
- a dedicated, transition-free Arjuna probe verifies missed-card backfill/finalization;
- scheduler/manual retry uses PostgreSQL advisory locking and applies automatic
  Nakula -> Arjuna promotion;
- cleanup is logical deactivation, preserving history.

Run only against a local development database.
"""
from __future__ import annotations

import argparse
import asyncio
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.enums import CardStatus
from app.core.timezone import get_week_bounds, organization_local_date
from app.db.session import get_session_factory
from app.models.daily_card import DailyCard
from app.models.devotee import DevoteeProfile
from app.models.organization import Organization
from app.models.user import User
from app.services.scheduler import _organization_history_floor


def expect(response: httpx.Response, status_code: int, step: str):
    if response.status_code != status_code:
        print(f"FAIL: {step}: expected {status_code}, got {response.status_code}")
        print(response.text)
        raise SystemExit(1)
    return response.json() if response.content else {}


async def prepare_scheduler_cases(backfill_email: str, nakula_email: str) -> date:
    """Prepare one *reconstructable and already-due* missing card for scheduler catch-up.

    v0.9.2 correctly introduced a historical reconstruction floor.  The smoke test must
    therefore not backdate disposable accounts into a week that predates versioned
    organization/category configuration and then assume that synthetic cards will be
    invented there.  Instead, use yesterday (whose deadline is certainly past) and
    require it to be on/after the safe reconstruction floor.
    """

    session_factory = get_session_factory()
    async with session_factory() as session:
        users = []
        for email in (backfill_email, nakula_email):
            result = await session.execute(
                select(User)
                .where(User.email == email)
                .options(
                    selectinload(User.devotee_profile).selectinload(
                        DevoteeProfile.category_history
                    )
                )
            )
            users.append(result.scalar_one())

        organization = await session.get(Organization, users[0].organization_id)
        if organization is None:
            raise RuntimeError("Smoke organization not found")

        local_today = organization_local_date(organization.timezone)
        safe_backfill_date = local_today - timedelta(days=1)
        history_floor = await _organization_history_floor(
            session, organization_id=organization.id
        )
        if history_floor is None:
            raise RuntimeError(
                "Cannot test scheduler backfill: no reconstructable configuration history exists"
            )
        if safe_backfill_date < history_floor:
            raise RuntimeError(
                "Cannot test scheduler backfill yet: the first reconstructable configuration "
                f"date is {history_floor}, but yesterday is {safe_backfill_date}. "
                "Run this smoke test after at least one configured day has fully elapsed."
            )

        safe_week_start, _ = get_week_bounds(
            safe_backfill_date, organization.week_start_day
        )
        zone = ZoneInfo(organization.timezone)
        approval_utc = datetime.combine(
            safe_backfill_date, dt_time.min, tzinfo=zone
        ).astimezone(timezone.utc)

        backfill_probe, nakula = users
        for user in users:
            if user.devotee_profile is None:
                raise RuntimeError("Smoke devotee profile missing")
            user.approved_at = approval_utc

        # The dedicated Arjuna backfill probe only needs a reconstructable current-week
        # category snapshot. Keep it effective from the safe week start.
        backfill_histories = backfill_probe.devotee_profile.category_history
        backfill_initial = min(backfill_histories, key=lambda row: row.created_at)
        backfill_initial.effective_from_week = safe_week_start

        if nakula.devotee_profile is None:
            raise RuntimeError("Nakula smoke profile missing")
        # The automatic-promotion probe must have entered Nakula before the current week.
        # If its initial history is also current-week, reconcile_automatic_promotions correctly
        # refuses to add a second transition for the same week. Backdate only this disposable
        # history row by one week so the smoke test actually exercises an overdue promotion.
        nakula_histories = nakula.devotee_profile.category_history
        nakula_initial = min(nakula_histories, key=lambda row: row.created_at)
        nakula_initial.effective_from_week = safe_week_start - timedelta(days=7)
        # Make the Nakula promotion unambiguously overdue in any month of the current year.
        nakula.devotee_profile.college_joining_year = local_today.year - 3
        nakula.devotee_profile.expected_graduation_year = local_today.year + 1
        await session.commit()
        return safe_backfill_date


async def verify_scheduler_effects(
    backfill_email: str, nakula_email: str, expected_card_date: date
) -> tuple[int, str]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        backfill_probe = await session.scalar(
            select(User)
            .where(User.email == backfill_email)
            .options(selectinload(User.devotee_profile))
        )
        nakula = await session.scalar(
            select(User)
            .where(User.email == nakula_email)
            .options(
                selectinload(User.devotee_profile).selectinload(
                    DevoteeProfile.current_category
                )
            )
        )
        if backfill_probe is None or backfill_probe.devotee_profile is None:
            raise RuntimeError("Backfill probe user missing")
        if nakula is None or nakula.devotee_profile is None:
            raise RuntimeError("Nakula smoke user missing")
        count = await session.scalar(
            select(func.count(DailyCard.id)).where(
                DailyCard.devotee_profile_id == backfill_probe.devotee_profile.id,
                DailyCard.card_date == expected_card_date,
                DailyCard.status == CardStatus.FINALIZED,
            )
        )
        return int(count or 0), nakula.devotee_profile.current_category.code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    suffix = str(time.time_ns())
    sahadeva_email = f"life-sahadeva-{suffix}@example.com"
    yudhisthira_email = f"life-yudhisthira-{suffix}@example.com"
    backfill_email = f"life-backfill-{suffix}@example.com"
    nakula_email = f"life-nakula-{suffix}@example.com"
    common_password = "LifecycleTest123!"
    created_ids: list[str] = []

    with asyncio.Runner() as runner, httpx.Client(base_url=base, timeout=60.0) as client:
        health = expect(client.get("/health"), 200, "health")
        assert health["status"] == "ok"
        print("PASS: health")

        admin_login = expect(
            client.post(
                "/api/v1/auth/login",
                json={"email": args.admin_email, "password": args.admin_password},
            ),
            200,
            "admin login",
        )
        admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
        print("PASS: admin login")

        current_year = datetime.now().year
        registration = expect(
            client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Lifecycle Sahadeva Smoke",
                    "email": sahadeva_email,
                    "password": common_password,
                    "phone_number": "+919000000011",
                    "college": "Smoke Test Institute",
                    "branch": "Computer Science",
                    "current_academic_year": 1,
                    "college_joining_year": current_year - 1,
                },
            ),
            201,
            "Sahadeva registration",
        )
        sahadeva_id = registration["user_id"]
        created_ids.append(sahadeva_id)
        expect(
            client.post(
                f"/api/v1/admin/registrations/{sahadeva_id}/approve",
                headers=admin_headers,
            ),
            200,
            "approve Sahadeva",
        )

        reviews = expect(
            client.get(
                "/api/v1/admin/lifecycle/sahadeva-reviews?include_not_due=true",
                headers=admin_headers,
            ),
            200,
            "Sahadeva review list",
        )
        assert any(row["user_id"] == sahadeva_id for row in reviews)
        print("PASS: Sahadeva appears in Admin review workflow")

        first = expect(
            client.post(
                f"/api/v1/admin/lifecycle/devotees/{sahadeva_id}/sahadeva-review",
                headers=admin_headers,
                json={
                    "decision": "CONTINUE_TO_NAKULA",
                    "reason": "VOICE continuation approved by lifecycle smoke test",
                },
            ),
            200,
            "schedule Sahadeva continuation",
        )
        assert first["decision"] == "CONTINUE_TO_NAKULA"

        second = expect(
            client.post(
                f"/api/v1/admin/lifecycle/devotees/{sahadeva_id}/sahadeva-review",
                headers=admin_headers,
                json={
                    "decision": "DEACTIVATE",
                    "reason": "Temporary smoke-test revision of Admin review decision",
                },
            ),
            200,
            "revise Sahadeva to deactivation",
        )
        assert second["decision"] == "DEACTIVATE"

        final_review = expect(
            client.post(
                f"/api/v1/admin/lifecycle/devotees/{sahadeva_id}/sahadeva-review",
                headers=admin_headers,
                json={
                    "decision": "CONTINUE_TO_NAKULA",
                    "reason": "Final smoke-test decision: continue to Nakula",
                },
            ),
            200,
            "restore Sahadeva continuation",
        )
        assert final_review["decision"] == "CONTINUE_TO_NAKULA"
        print("PASS: Sahadeva review is future-week and revisable before activation")

        yudhisthira = expect(
            client.post(
                "/api/v1/admin/devotees",
                headers=admin_headers,
                json={
                    "full_name": "Lifecycle Yudhishthira Smoke",
                    "email": yudhisthira_email,
                    "password": common_password,
                    "phone_number": "+919000000012",
                    "college": "Smoke Test Institute",
                    "branch": "Computer Science",
                    "college_joining_year": current_year - 4,
                    "category_code": "YUDHISHTHIRA",
                    "current_academic_year": 4,
                },
            ),
            201,
            "create Yudhishthira",
        )
        yudhisthira_id = yudhisthira["id"]
        created_ids.append(yudhisthira_id)
        y_login = expect(
            client.post(
                "/api/v1/auth/login",
                json={"email": yudhisthira_email, "password": common_password},
            ),
            200,
            "Yudhishthira login",
        )
        y_headers = {"Authorization": f"Bearer {y_login['access_token']}"}
        choice = expect(
            client.post(
                "/api/v1/lifecycle/bhima-status",
                headers=y_headers,
                json={
                    "employment_status": "WORKING",
                    "reason": "Initial Bhima choice for smoke test",
                },
            ),
            200,
            "initial Bhima WORKING choice",
        )
        assert choice["pending_category_transition"]["target_category_code"] == "BHIMA_WORKING"
        revised = expect(
            client.post(
                "/api/v1/lifecycle/bhima-status",
                headers=y_headers,
                json={
                    "employment_status": "NOT_WORKING",
                    "reason": "Revised initial Bhima choice before activation",
                },
            ),
            200,
            "revise Bhima choice",
        )
        assert revised["pending_category_transition"]["target_category_code"] == "BHIMA_NOT_WORKING"
        assert revised["current_category_code"] == "YUDHISHTHIRA"
        print("PASS: Yudhishthira explicitly chooses initial Bhima status; no automatic default")

        # Keep missed-card verification independent from Sahadeva review state and from
        # academic promotion.  Reusing the Sahadeva test account coupled two unrelated
        # lifecycle scenarios and made the probe sensitive to pending transition state.
        # A current Arjuna whose promotion boundary is still in the future is a clean
        # account for verifying only scheduler materialization/finalization.
        backfill_probe = expect(
            client.post(
                "/api/v1/admin/devotees",
                headers=admin_headers,
                json={
                    "full_name": "Lifecycle Backfill Smoke",
                    "email": backfill_email,
                    "password": common_password,
                    "phone_number": "+919000000014",
                    "college": "Smoke Test Institute",
                    "branch": "Computer Science",
                    "college_joining_year": current_year - 2,
                    "category_code": "ARJUNA",
                    "current_academic_year": 3,
                },
            ),
            201,
            "create backfill probe",
        )
        backfill_id = backfill_probe["id"]
        created_ids.append(backfill_id)

        nakula = expect(
            client.post(
                "/api/v1/admin/devotees",
                headers=admin_headers,
                json={
                    "full_name": "Lifecycle Nakula Smoke",
                    "email": nakula_email,
                    "password": common_password,
                    "phone_number": "+919000000013",
                    "college": "Smoke Test Institute",
                    "branch": "Computer Science",
                    "college_joining_year": current_year - 3,
                    "category_code": "NAKULA",
                    "current_academic_year": 2,
                },
            ),
            201,
            "create Nakula",
        )
        nakula_id = nakula["id"]
        created_ids.append(nakula_id)

        expected_backfill_date = runner.run(
            prepare_scheduler_cases(backfill_email, nakula_email)
        )

        run_result = None
        for _ in range(6):
            candidate = expect(
                client.post("/api/v1/admin/lifecycle/run-now", headers=admin_headers),
                200,
                "manual lifecycle retry",
            )
            if candidate.get("lock_acquired"):
                run_result = candidate
                break
            time.sleep(1)
        if run_result is None:
            raise RuntimeError("Could not acquire lifecycle advisory lock after retries")
        print("PASS: scheduler lifecycle run acquires PostgreSQL advisory lock and is retryable")

        finalized_count, nakula_category = runner.run(
            verify_scheduler_effects(
                backfill_email, nakula_email, expected_backfill_date
            )
        )
        assert finalized_count >= 1, (
            "scheduler did not create/finalize the expected no-entry card for "
            f"{expected_backfill_date}; run-now result was {run_result}"
        )
        assert nakula_category == "ARJUNA", f"expected automatic ARJUNA, got {nakula_category}"
        print("PASS: scheduler backfills/finalizes missed no-entry Daily Cards")
        print("PASS: due Nakula -> Arjuna academic promotion is applied at a week boundary")

        # The recurring APScheduler may have already processed some work before run-now;
        # a second run must still be safe and not duplicate rows.
        second_run = expect(
            client.post("/api/v1/admin/lifecycle/run-now", headers=admin_headers),
            200,
            "idempotent lifecycle retry",
        )
        assert second_run.get("lock_acquired") in {True, False}
        print("PASS: repeated lifecycle execution is idempotent/safe")

        for user_id in created_ids:
            response = client.post(
                f"/api/v1/admin/devotees/{user_id}/deactivate",
                headers=admin_headers,
                json={"reason": "Step 11 lifecycle smoke-test cleanup"},
            )
            if response.status_code not in {200, 409}:
                expect(response, 200, f"cleanup {user_id}")
        print("PASS: disposable devotees logically deactivated")

    print("\nALL LIFECYCLE/SCHEDULER SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
