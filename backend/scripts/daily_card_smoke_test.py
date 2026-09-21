"""Step 8 end-to-end Daily Card smoke test against a running local API.

The script creates a disposable devotee, approves it, opens today's dynamically
configured card, verifies missing-vs-zero semantics and chanting completion, then
logically deactivates the disposable account. Run only against a local development DB.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

import httpx


def expect(response: httpx.Response, status_code: int, step: str):
    if response.status_code != status_code:
        print(f"FAIL: {step}: expected {status_code}, got {response.status_code}")
        print(response.text)
        sys.exit(1)
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    suffix = str(int(time.time()))
    devotee_email = f"card-smoke-{suffix}@example.com"
    devotee_password = "DevoteeCard123!"

    with httpx.Client(base_url=base, timeout=20.0) as client:
        health = expect(client.get("/health"), 200, "health")
        assert health["status"] == "ok"
        print("PASS: health")

        registration = expect(
            client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Daily Card Smoke Devotee",
                    "email": devotee_email,
                    "password": devotee_password,
                    "phone_number": "+919000000002",
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
            "Smoke test must run before the organization's snapshotted daily deadline"
        )
        assert card["editable"] is True
        assert card["category_code"] == "ARJUNA"
        assert len(card["activities"]) == 12
        activities = by_code(card)
        assert "FILLING_SADHANA_CARD" in activities
        assert activities["FILLING_SADHANA_CARD"]["is_system_derived"] is True
        print("PASS: today's card dynamically materialized with 12 configured activities")

        morning = activities["MORNING_PROGRAM"]
        chanting = activities["CHANTING"]
        reading = activities["BOOK_READING"]
        morning_field = field_by_key(morning, "attended")
        rounds_field = field_by_key(chanting, "rounds_chanted")
        reading_field = field_by_key(reading, "minutes")

        updated = expect(
            client.patch(
                "/api/v1/cards/today",
                headers=devotee_headers,
                json={
                    "activities": [
                        {
                            "activity_id": morning["activity_id"],
                            "values": [
                                {
                                    "field_id": morning_field["field_id"],
                                    "is_filled": True,
                                    "boolean_value": False,
                                }
                            ],
                        },
                        {
                            "activity_id": chanting["activity_id"],
                            "values": [
                                {
                                    "field_id": rounds_field["field_id"],
                                    "is_filled": True,
                                    "numeric_value": 12,
                                }
                            ],
                        },
                        {
                            "activity_id": reading["activity_id"],
                            "values": [
                                {
                                    "field_id": reading_field["field_id"],
                                    "is_filled": True,
                                    "numeric_value": 0,
                                }
                            ],
                        },
                    ]
                },
            ),
            200,
            "update today's card",
        )
        assert updated["revision_number"] == 1
        assert updated["first_update_at"] is not None
        assert updated["last_update_at"] is not None

        updated_activities = by_code(updated)
        morning = updated_activities["MORNING_PROGRAM"]
        assert morning["is_filled"] is True
        attended = field_by_key(morning, "attended")
        assert attended["is_filled"] is True
        assert attended["boolean_value"] is False

        chanting = updated_activities["CHANTING"]
        assert chanting["is_filled"] is True
        assert field_by_key(chanting, "rounds_chanted")["is_filled"] is True
        assert field_by_key(chanting, "completion_time")["is_filled"] is False

        reading = updated_activities["BOOK_READING"]
        assert reading["is_filled"] is True
        reading_minutes = field_by_key(reading, "minutes")
        assert reading_minutes["is_filled"] is True
        assert float(reading_minutes["numeric_value"]) == 0.0
        print("PASS: missing-vs-zero/False and chanting <16 completion semantics")

        dated = expect(
            client.get(
                f"/api/v1/cards/{updated['card_date']}", headers=devotee_headers
            ),
            200,
            "read card by date",
        )
        assert dated["id"] == updated["id"]
        print("PASS: dated card read returns the same persisted card")

        tomorrow = (date.fromisoformat(updated["card_date"]) + timedelta(days=1)).isoformat()
        expect(
            client.get(f"/api/v1/cards/{tomorrow}", headers=devotee_headers),
            422,
            "future card blocked",
        )
        print("PASS: future daily card blocked")

        # v0.7 keeps the Step 8 raw-data semantics while Step 9 now deterministically
        # scores DAILY entries. Weekly-aggregated Book Reading still has no daily mark.
        assert updated_activities["MORNING_PROGRAM"]["daily_score"] == 0
        assert updated_activities["CHANTING"]["daily_score"] == 0
        assert updated_activities["BOOK_READING"]["daily_score"] is None
        assert updated_activities["FILLING_SADHANA_CARD"]["daily_score"] is None
        print("PASS: Step 8 raw/completion semantics remain intact under Step 9 scoring")

        expect(
            client.post(
                f"/api/v1/admin/devotees/{devotee_id}/deactivate",
                headers=admin_headers,
                json={"reason": "Daily Card automated local smoke test cleanup"},
            ),
            200,
            "deactivate disposable devotee",
        )
        print("PASS: disposable devotee logically deactivated")

    print("\nALL DAILY CARD SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
