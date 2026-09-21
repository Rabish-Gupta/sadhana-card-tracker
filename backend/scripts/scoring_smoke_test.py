"""Step 9 end-to-end deterministic scoring smoke test.

Run against a local development API + PostgreSQL database before the organization's
current daily deadline. The script creates a disposable devotee, verifies DAILY marks
through HTTP, finalizes that disposable card through the scheduler service seam with a
simulated post-deadline timestamp, verifies the system-derived 75% card-fill mark, then
logically deactivates the account.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.user import User
from app.services.daily_cards import get_daily_card, materialize_and_finalize_for_scheduler


def expect(response: httpx.Response, status_code: int, step: str):
    if response.status_code != status_code:
        print(f"FAIL: {step}: expected {status_code}, got {response.status_code}")
        print(response.text)
        raise SystemExit(1)
    if response.content:
        return response.json()
    return {}


def by_code(card: dict) -> dict[str, dict]:
    return {activity["code"]: activity for activity in card["activities"]}


def field_by_key(activity: dict, key: str) -> dict:
    for field in activity["values"]:
        if field["field_key"] == key:
            return field
    raise AssertionError(f"Missing field {activity['code']}.{key}")


def activity_update(activity: dict, field_key: str, **typed_value) -> dict:
    field = field_by_key(activity, field_key)
    return {
        "activity_id": activity["activity_id"],
        "values": [
            {
                "field_id": field["field_id"],
                "is_filled": True,
                **typed_value,
            }
        ],
    }


async def finalize_disposable_card(email: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            raise RuntimeError("Disposable scoring-smoke user not found in PostgreSQL")
        card = await get_daily_card(session, user=user)
        await materialize_and_finalize_for_scheduler(
            session,
            user=user,
            target_date=card.card_date,
            now_utc=card.deadline_at_utc + timedelta(seconds=1),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    suffix = str(time.time_ns())
    devotee_email = f"scoring-smoke-{suffix}@example.com"
    devotee_password = "DevoteeScore123!"
    devotee_id: str | None = None
    admin_headers: dict[str, str] | None = None

    with httpx.Client(base_url=base, timeout=20.0) as client:
        try:
            health = expect(client.get("/health"), 200, "health")
            assert health["status"] == "ok"
            print("PASS: health")

            registration = expect(
                client.post(
                    "/api/v1/auth/register",
                    json={
                        "full_name": "Scoring Smoke Devotee",
                        "email": devotee_email,
                        "password": devotee_password,
                        "phone_number": "+919000000003",
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
            devotee_headers = {
                "Authorization": f"Bearer {devotee_login['access_token']}"
            }

            card = expect(
                client.get("/api/v1/cards/today", headers=devotee_headers),
                200,
                "open today's card",
            )
            assert card["status"] == "IN_PROGRESS", (
                "Scoring smoke test must run before the organization's daily deadline"
            )
            assert card["editable"] is True
            activities = by_code(card)
            assert len(activities) == 12
            print("PASS: scoring test card dynamically materialized")

            # Exact boundary values deliberately verify strict/inclusive project rules.
            updates = [
                activity_update(
                    activities["MORNING_PROGRAM"], "attended", boolean_value=True
                ),
                {
                    "activity_id": activities["CHANTING"]["activity_id"],
                    "values": [
                        {
                            "field_id": field_by_key(
                                activities["CHANTING"], "rounds_chanted"
                            )["field_id"],
                            "is_filled": True,
                            "numeric_value": 16,
                        },
                        {
                            "field_id": field_by_key(
                                activities["CHANTING"], "completion_time"
                            )["field_id"],
                            "is_filled": True,
                            "time_value": "09:30:00",
                        },
                    ],
                },
                activity_update(
                    activities["BOOK_READING"], "minutes", numeric_value=0
                ),
                activity_update(
                    activities["MORNING_CLASS"], "attended", boolean_value=False
                ),
                activity_update(
                    activities["PERSONAL_HEARING"], "minutes", numeric_value=30
                ),
                activity_update(
                    activities["SHLOKA_VAISHNAVA_SONG"],
                    "count_learned",
                    numeric_value=1,
                ),
                activity_update(
                    activities["STUDY_PREPARATION"], "minutes", numeric_value=60
                ),
                activity_update(
                    activities["TO_BED"], "bedtime", time_value="21:15:00"
                ),
                activity_update(
                    activities["WAKE_UP"], "wake_up_time", time_value="03:40:00"
                ),
                activity_update(
                    activities["DAY_REST"], "minutes", numeric_value=45
                ),
                # SEVA intentionally left missing. We still have 10/11 countable
                # activities completed, comfortably above the 75% finalization rule.
            ]

            updated = expect(
                client.patch(
                    "/api/v1/cards/today",
                    headers=devotee_headers,
                    json={"activities": updates},
                ),
                200,
                "score daily activities",
            )
            scored = by_code(updated)
            expected_daily_scores = {
                "MORNING_PROGRAM": 30,
                "CHANTING": 50,  # exactly 09:30 is not "before 09:30"
                "MORNING_CLASS": 0,
                "SHLOKA_VAISHNAVA_SONG": 20,
                "STUDY_PREPARATION": 20,
                "TO_BED": 50,  # exactly 21:15 enters the next band
                "WAKE_UP": 50,  # exactly 03:40 enters the next band
                "DAY_REST": 50,  # exactly 45 minutes is explicitly 50
            }
            for code, expected_score in expected_daily_scores.items():
                actual = scored[code]["daily_score"]
                assert actual == expected_score, f"{code}: expected {expected_score}, got {actual}"
                assert scored[code]["score_calculated_at"] is not None
                assert scored[code]["score_details"] is not None

            assert scored["BOOK_READING"]["daily_score"] is None
            assert scored["PERSONAL_HEARING"]["daily_score"] is None
            assert scored["SEVA"]["daily_score"] is None
            assert scored["FILLING_SADHANA_CARD"]["daily_score"] is None
            print("PASS: deterministic DAILY threshold/boolean scores and weekly/non-scored separation")

            asyncio.run(finalize_disposable_card(devotee_email))
            finalized = expect(
                client.get("/api/v1/cards/today", headers=devotee_headers),
                200,
                "read finalized scoring card",
            )
            assert finalized["status"] == "FINALIZED"
            assert finalized["editable"] is False
            final_activities = by_code(finalized)
            fill = final_activities["FILLING_SADHANA_CARD"]
            assert fill["is_filled"] is True
            assert fill["daily_score"] == 10
            details = fill["score_details"]
            assert details["completed_count"] == 10
            assert details["countable_count"] == 11
            assert details["met"] is True
            print("PASS: finalization computes 75% system-derived Filling Sadhana Card score")

        finally:
            if devotee_id and admin_headers:
                response = client.post(
                    f"/api/v1/admin/devotees/{devotee_id}/deactivate",
                    headers=admin_headers,
                    json={"reason": "Step 9 automated local scoring smoke test cleanup"},
                )
                if response.status_code == 200:
                    print("PASS: disposable devotee logically deactivated")
                else:
                    print(
                        "WARN: cleanup failed; deactivate disposable user manually:",
                        devotee_email,
                        response.status_code,
                        response.text,
                    )

    print("\nALL SCORING SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
