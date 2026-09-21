"""Step 12 end-to-end historical Daily Card correction smoke test.

The script creates one disposable devotee, builds a full finalized baseline week through
existing service seams, then uses the Admin historical-correction API to change one
finalized Study / Preparation value from 120 minutes to an intentional zero.  It verifies:

* finalized raw data can be corrected only through the Admin correction flow;
* missing-vs-zero semantics are retained (0 + is_filled=true stays intentional zero);
* the Daily score is deterministically recalculated using the same stored rule/config IDs;
* the existing WeeklyEvaluation is recalculated atomically using its stored historical
  rule/standard/config references, not today's active configuration;
* DailyCard and WeeklyEvaluation revision numbers increment;
* Sadhana and Academic totals remain separate;
* system-derived Filling Sadhana Card cannot be directly overwritten;
* both historical correction and weekly recalculation are audited with the Admin reason.

The account is logically deactivated at the end.  As in the Step 10 smoke test, direct DB
helpers use one asyncio.Runner so the cached asyncpg pool stays on a single Windows event
loop.
"""
from __future__ import annotations

import argparse
import asyncio
import time as time_module
import uuid
from datetime import date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_session_factory
from app.models.audit import AuditLog
from app.models.daily_card import DailyActivityEntry, DailyCard
from app.core.enums import ChangeSource
from app.models.devotee import DevoteeCategory, DevoteeCategoryHistory, DevoteeProfile
from app.models.user import User
from app.models.weekly_evaluation import WeeklyActivityResult, WeeklyEvaluation
from scripts.weekly_evaluation_smoke_test import (
    by_code,
    expect,
    move_cleanup_after_week,
    prepare_full_week,
)


def _activity_by_code(card: dict, code: str) -> dict:
    for activity in card["activities"]:
        if activity["code"] == code:
            return activity
    raise AssertionError(f"Missing activity {code}")


def _field_by_key(activity: dict, field_key: str) -> dict:
    for value in activity["values"]:
        if value["field_key"] == field_key:
            return value
    raise AssertionError(f"Missing field {activity['code']}.{field_key}")




async def prepare_policy_b_next_transition(email: str, *, week_start: date) -> date:
    """Create one future transition so the smoke test proves policy-B interval repair."""

    from datetime import timedelta

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category))
        )
        if user is None or user.devotee_profile is None:
            raise RuntimeError("Disposable devotee context missing")
        profile = user.devotee_profile
        target = await session.scalar(
            select(DevoteeCategory).where(
                DevoteeCategory.organization_id == user.organization_id,
                DevoteeCategory.code == "BHIMA_NOT_WORKING",
            )
        )
        if target is None:
            raise RuntimeError("BHIMA_NOT_WORKING category missing")
        effective = week_start + timedelta(days=7)
        existing = await session.scalar(
            select(DevoteeCategoryHistory).where(
                DevoteeCategoryHistory.devotee_profile_id == profile.id,
                DevoteeCategoryHistory.effective_from_week == effective,
            )
        )
        if existing is not None:
            await session.delete(existing)
            await session.flush()
        session.add(
            DevoteeCategoryHistory(
                devotee_profile_id=profile.id,
                previous_category_id=profile.current_category_id,
                new_category_id=target.id,
                effective_from_week=effective,
                change_source=ChangeSource.ADMIN,
                reason="Step 12 policy-B future-boundary fixture",
                changed_by_id=None,
            )
        )
        await session.commit()
        return effective


async def verify_category_correction_audit(email: str, *, reason: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.devotee_profile))
        )
        if user is None or user.devotee_profile is None:
            raise RuntimeError("Disposable devotee missing during category-audit verification")
        profile = user.devotee_profile
        rows = list(
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.organization_id == user.organization_id,
                        AuditLog.action.in_(
                            [
                                "HISTORICAL_CATEGORY_CORRECTED",
                                "HISTORICAL_CARD_CATEGORY_REBUILT",
                                "WEEKLY_EVALUATION_CATEGORY_REBUILT",
                            ]
                        ),
                    )
                )
            ).scalars()
        )
        actions = {row.action for row in rows}
        assert "HISTORICAL_CATEGORY_CORRECTED" in actions
        assert "HISTORICAL_CARD_CATEGORY_REBUILT" in actions
        assert "WEEKLY_EVALUATION_CATEGORY_REBUILT" in actions
        main = next(
            row
            for row in rows
            if row.action == "HISTORICAL_CATEGORY_CORRECTED" and row.entity_id == profile.id
        )
        assert main.reason == reason
        assert main.before_data and main.after_data
        assert main.after_data["corrected_category_code"] == "YUDHISHTHIRA"


async def capture_historical_refs(
    email: str,
    *,
    card_date: date,
    week_start: date,
) -> dict[str, str | int | None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.devotee_profile))
        )
        if user is None or user.devotee_profile is None:
            raise RuntimeError("Disposable devotee context missing")
        profile = user.devotee_profile

        card = await session.scalar(
            select(DailyCard)
            .where(
                DailyCard.devotee_profile_id == profile.id,
                DailyCard.card_date == card_date,
            )
            .options(
                selectinload(DailyCard.activity_entries).selectinload(
                    DailyActivityEntry.activity
                )
            )
        )
        if card is None:
            raise RuntimeError("Historical Daily Card missing")
        study_entry = next(
            entry for entry in card.activity_entries if entry.activity.code == "STUDY_PREPARATION"
        )

        evaluation = await session.scalar(
            select(WeeklyEvaluation)
            .where(
                WeeklyEvaluation.devotee_profile_id == profile.id,
                WeeklyEvaluation.week_start_date == week_start,
            )
            .options(
                selectinload(WeeklyEvaluation.activity_results).selectinload(
                    WeeklyActivityResult.activity
                )
            )
        )
        if evaluation is None:
            raise RuntimeError("WeeklyEvaluation missing")
        study_week = next(
            row for row in evaluation.activity_results if row.activity.code == "STUDY_PREPARATION"
        )

        audit_rows = list(
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.organization_id == user.organization_id,
                        AuditLog.entity_id.in_([card.id, evaluation.id]),
                        AuditLog.action.in_(
                            [
                                "HISTORICAL_CARD_CORRECTED",
                                "WEEKLY_EVALUATION_RECALCULATED",
                            ]
                        ),
                    )
                )
            ).scalars()
        )
        return {
            "card_id": str(card.id),
            "card_revision": card.revision_number,
            "daily_config_id": str(study_entry.category_activity_config_id),
            "daily_rule_version_id": (
                str(study_entry.rule_version_id) if study_entry.rule_version_id else None
            ),
            "weekly_id": str(evaluation.id),
            "weekly_revision": evaluation.revision_number,
            "weekly_config_id": str(study_week.category_activity_config_id),
            "weekly_rule_version_id": (
                str(study_week.rule_version_id) if study_week.rule_version_id else None
            ),
            "weekly_standard_version_id": (
                str(study_week.standard_version_id) if study_week.standard_version_id else None
            ),
            "audit_count": len(audit_rows),
        }


async def verify_correction_audit(
    email: str,
    *,
    card_id: str,
    weekly_id: str,
    reason: str,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            raise RuntimeError("Disposable devotee missing during audit verification")
        rows = list(
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.organization_id == user.organization_id,
                        AuditLog.entity_id.in_([uuid.UUID(card_id), uuid.UUID(weekly_id)]),
                        AuditLog.action.in_(
                            [
                                "HISTORICAL_CARD_CORRECTED",
                                "WEEKLY_EVALUATION_RECALCULATED",
                            ]
                        ),
                    )
                )
            ).scalars()
        )
        actions = {row.action for row in rows}
        assert "HISTORICAL_CARD_CORRECTED" in actions
        assert "WEEKLY_EVALUATION_RECALCULATED" in actions
        correction = next(row for row in rows if row.action == "HISTORICAL_CARD_CORRECTED")
        assert correction.reason == reason
        assert correction.actor_user_id is not None
        assert correction.before_data and correction.after_data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    suffix = str(time_module.time_ns())
    devotee_email = f"correction-smoke-{suffix}@example.com"
    devotee_password = "DevoteeCorrection123!"
    devotee_id: str | None = None
    admin_headers: dict[str, str] | None = None
    simulated_after_week_iso: str | None = None
    reason = "Step 12 verified historical correction smoke test"

    with asyncio.Runner() as runner, httpx.Client(base_url=base, timeout=30.0) as client:
        try:
            health = expect(client.get("/health"), 200, "health")
            assert health["status"] == "ok"
            print("PASS: health")

            registration = expect(
                client.post(
                    "/api/v1/auth/register",
                    json={
                        "full_name": "Historical Correction Smoke Devotee",
                        "email": devotee_email,
                        "password": devotee_password,
                        "phone_number": "+919000000012",
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

            week_start_iso, simulated_after_week_iso = runner.run(
                prepare_full_week(devotee_email)
            )
            week_start = date.fromisoformat(week_start_iso)
            card_date = week_start

            before_week = expect(
                client.get(f"/api/v1/weekly/{week_start_iso}", headers=devotee_headers),
                200,
                "baseline weekly evaluation",
            )
            assert before_week["sadhana_score"] == 1750
            assert before_week["academic_score"] == 1750
            assert before_week["revision_number"] == 0

            # Policy B: correct ARJUNA from this week forward, but preserve the next
            # recorded transition boundary. The future row's previous category must be
            # repaired to YUDHISHTHIRA and all existing cards/weekly results in the
            # corrected interval must be rebuilt from historically-effective config.
            next_transition = runner.run(
                prepare_policy_b_next_transition(devotee_email, week_start=week_start)
            )
            category_reason = "Step 12 verified policy-B historical category correction"
            category_corrected = expect(
                client.patch(
                    f"/api/v1/admin/corrections/devotees/{devotee_id}/category",
                    headers=admin_headers,
                    json={
                        "effective_from_week": week_start_iso,
                        "target_category_code": "YUDHISHTHIRA",
                        "reason": category_reason,
                    },
                ),
                200,
                "historical category correction",
            )
            assert category_corrected["previous_category_code"] == "ARJUNA"
            assert category_corrected["corrected_category_code"] == "YUDHISHTHIRA"
            assert category_corrected["effective_until_exclusive"] == next_transition.isoformat()
            assert category_corrected["next_transition_category_code"] == "BHIMA_NOT_WORKING"
            assert category_corrected["affected_daily_cards"] == 7
            assert category_corrected["affected_weekly_evaluations"] == 1
            assert category_corrected["current_category_code"] == "YUDHISHTHIRA"
            assert category_corrected["current_academic_year"] == 4

            category_history = expect(
                client.get(
                    f"/api/v1/admin/corrections/devotees/{devotee_id}/category-history",
                    headers=admin_headers,
                ),
                200,
                "corrected category history",
            )
            by_week = {row["effective_from_week"]: row for row in category_history["history"]}
            assert by_week[week_start_iso]["new_category_code"] == "YUDHISHTHIRA"
            assert by_week[next_transition.isoformat()]["previous_category_code"] == "YUDHISHTHIRA"
            assert by_week[next_transition.isoformat()]["new_category_code"] == "BHIMA_NOT_WORKING"

            category_week = expect(
                client.get(f"/api/v1/weekly/{week_start_iso}", headers=devotee_headers),
                200,
                "category-corrected weekly evaluation",
            )
            assert category_week["category_code"] == "YUDHISHTHIRA"
            assert category_week["sadhana_score"] == 1750
            assert category_week["academic_score"] == 1750
            assert category_week["revision_number"] == 1
            runner.run(
                verify_category_correction_audit(devotee_email, reason=category_reason)
            )
            print(
                "PASS: policy-B historical category correction rebuilds the interval and preserves the next transition"
            )

            card = expect(
                client.get(
                    f"/api/v1/admin/corrections/devotees/{devotee_id}/cards/{card_date.isoformat()}",
                    headers=admin_headers,
                ),
                200,
                "admin read finalized historical card",
            )
            study = _activity_by_code(card, "STUDY_PREPARATION")
            study_minutes = _field_by_key(study, "minutes")
            filling = _activity_by_code(card, "FILLING_SADHANA_CARD")
            assert study["daily_score"] == 30
            assert filling["daily_score"] == 10
            assert card["status"] == "FINALIZED"

            before_refs = runner.run(
                capture_historical_refs(
                    devotee_email, card_date=card_date, week_start=week_start
                )
            )
            assert before_refs["audit_count"] == 0

            corrected = expect(
                client.patch(
                    f"/api/v1/admin/corrections/devotees/{devotee_id}/cards/{card_date.isoformat()}",
                    headers=admin_headers,
                    json={
                        "reason": reason,
                        "activities": [
                            {
                                "activity_id": study["activity_id"],
                                "values": [
                                    {
                                        "field_id": study_minutes["field_id"],
                                        "is_filled": True,
                                        "numeric_value": 0,
                                    }
                                ],
                            }
                        ],
                    },
                ),
                200,
                "historical card correction",
            )
            corrected_card = corrected["card"]
            corrected_study = _activity_by_code(corrected_card, "STUDY_PREPARATION")
            corrected_minutes = _field_by_key(corrected_study, "minutes")
            corrected_filling = _activity_by_code(corrected_card, "FILLING_SADHANA_CARD")
            assert corrected_card["revision_number"] == before_refs["card_revision"] + 1
            assert corrected_minutes["is_filled"] is True
            assert float(corrected_minutes["numeric_value"]) == 0.0
            assert corrected_study["daily_score"] == 0
            assert corrected_filling["daily_score"] == 10
            assert corrected["weekly_evaluation_recalculated"] is True
            print("PASS: finalized raw value corrected with intentional-zero semantics and daily rescoring")

            corrected_week = corrected["weekly_evaluation"]
            assert corrected_week is not None
            assert corrected_week["id"] == before_refs["weekly_id"]
            assert corrected_week["revision_number"] == before_refs["weekly_revision"] + 1
            assert corrected_week["sadhana_score"] == 1750
            assert corrected_week["sadhana_max_score"] == 1750
            assert corrected_week["academic_score"] == 1720
            assert corrected_week["academic_max_score"] == 1750
            assert "combined_score" not in corrected_week
            corrected_activities = by_code(corrected_week)
            assert corrected_activities["STUDY_PREPARATION"]["final_activity_score"] == 180
            print("PASS: affected WeeklyEvaluation recalculated with separate Sadhana/Academic totals")

            after_refs = runner.run(
                capture_historical_refs(
                    devotee_email, card_date=card_date, week_start=week_start
                )
            )
            assert after_refs["daily_config_id"] == before_refs["daily_config_id"]
            assert after_refs["daily_rule_version_id"] == before_refs["daily_rule_version_id"]
            assert after_refs["weekly_config_id"] == before_refs["weekly_config_id"]
            assert after_refs["weekly_rule_version_id"] == before_refs["weekly_rule_version_id"]
            assert (
                after_refs["weekly_standard_version_id"]
                == before_refs["weekly_standard_version_id"]
            )
            assert after_refs["audit_count"] >= 2
            runner.run(
                verify_correction_audit(
                    devotee_email,
                    card_id=str(before_refs["card_id"]),
                    weekly_id=str(before_refs["weekly_id"]),
                    reason=reason,
                )
            )
            print("PASS: historical config/rule/standard IDs preserved and correction audited")

            persisted_week = expect(
                client.get(f"/api/v1/weekly/{week_start_iso}", headers=devotee_headers),
                200,
                "persisted corrected weekly evaluation",
            )
            assert persisted_week["revision_number"] == corrected_week["revision_number"]
            assert persisted_week["academic_score"] == 1720
            print("PASS: corrected weekly result persisted idempotently")

            # The system-derived card-filling activity must only change indirectly from raw
            # corrections; Admins cannot overwrite it as if it were user input.
            system_response = client.patch(
                f"/api/v1/admin/corrections/devotees/{devotee_id}/cards/{card_date.isoformat()}",
                headers=admin_headers,
                json={
                    "reason": "Attempt direct system-derived overwrite",
                    "activities": [
                        {
                            "activity_id": filling["activity_id"],
                            "values": [
                                {
                                    "field_id": str(uuid.uuid4()),
                                    "is_filled": True,
                                    "numeric_value": 0,
                                }
                            ],
                        }
                    ],
                },
            )
            expect(system_response, 422, "reject direct system-derived correction")
            print("PASS: system-derived Filling Sadhana Card cannot be directly corrected")

        finally:
            if devotee_id and admin_headers:
                response = client.post(
                    f"/api/v1/admin/devotees/{devotee_id}/deactivate",
                    headers=admin_headers,
                    json={"reason": "Step 12 historical-correction smoke test cleanup"},
                )
                if response.status_code == 200:
                    if simulated_after_week_iso:
                        runner.run(
                            move_cleanup_after_week(devotee_email, simulated_after_week_iso)
                        )
                    print("PASS: disposable devotee logically deactivated")
                else:
                    print(
                        "WARN: cleanup failed; deactivate disposable user manually:",
                        devotee_email,
                        response.status_code,
                        response.text,
                    )

    print("\nALL HISTORICAL CORRECTION SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
