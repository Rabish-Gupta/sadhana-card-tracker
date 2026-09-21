"""Read-only Step 7 smoke test against a running local API and PostgreSQL database.

The script intentionally does not create PENDING configuration.  It verifies that the
migrated/seeded baseline is readable through the Admin API without leaving test config
that could activate in a later week.
"""
from __future__ import annotations

import argparse
import sys

import httpx


def expect(response: httpx.Response, status_code: int, step: str):
    if response.status_code != status_code:
        print(f"FAIL: {step}: expected {status_code}, got {response.status_code}")
        print(response.text)
        sys.exit(1)
    if response.content:
        return response.json()
    return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=15.0) as client:
        health = expect(client.get("/health"), 200, "health")
        assert health["status"] == "ok"
        print("PASS: health")

        login = expect(
            client.post(
                "/api/v1/auth/login",
                json={"email": args.admin_email, "password": args.admin_password},
            ),
            200,
            "admin login",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        print("PASS: admin login")

        current = expect(
            client.get(
                "/api/v1/admin/config/organization-settings/current",
                headers=headers,
            ),
            200,
            "current organization settings",
        )
        assert current["status"] == "ACTIVE"
        assert current["timezone"]
        assert 0 <= current["week_start_day"] <= 6
        assert 1 <= current["promotion_month"] <= 12
        print("PASS: active organization settings version")

        versions = expect(
            client.get(
                "/api/v1/admin/config/organization-settings/versions",
                headers=headers,
            ),
            200,
            "organization settings history",
        )
        active = [item for item in versions if item["status"] == "ACTIVE"]
        assert len(active) == 1
        assert active[0]["id"] == current["id"]
        print("PASS: organization settings history has exactly one ACTIVE version")

        categories = expect(
            client.get("/api/v1/admin/config/categories", headers=headers),
            200,
            "categories",
        )
        assert len(categories) >= 6
        print("PASS: devotee categories readable")

        activities = expect(
            client.get("/api/v1/admin/config/activities", headers=headers),
            200,
            "activities",
        )
        assert len(activities) >= 12
        print("PASS: activities readable")

        rules = expect(
            client.get("/api/v1/admin/config/scoring-rules", headers=headers),
            200,
            "scoring rules",
        )
        assert len(rules) >= 11
        print("PASS: scoring rules readable")

        standards = expect(
            client.get("/api/v1/admin/config/standards", headers=headers),
            200,
            "standards",
        )
        assert len(standards) >= 11
        print("PASS: standards readable")

        configs = expect(
            client.get(
                "/api/v1/admin/config/category-activity-configs",
                headers=headers,
            ),
            200,
            "category activity configs",
        )
        assert len(configs) >= 72
        print("PASS: category/activity configurations readable")

    print("\nALL CONFIGURATION SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
