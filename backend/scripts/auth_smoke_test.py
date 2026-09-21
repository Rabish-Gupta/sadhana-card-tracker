"""End-to-end authentication/user-management smoke test against a running local API.

This script intentionally creates disposable devotee accounts. Run it only against a
local development database.
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx


def expect(response: httpx.Response, status_code: int, step: str) -> dict:
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
    suffix = str(int(time.time()))
    devotee_email = f"auth-smoke-{suffix}@example.com"
    devotee_password = "DevoteeTest123!"

    with httpx.Client(base_url=base, timeout=15.0) as client:
        health = expect(client.get("/health"), 200, "health")
        assert health["status"] == "ok"
        print("PASS: health")

        registration = expect(
            client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Auth Smoke Devotee",
                    "email": devotee_email,
                    "password": devotee_password,
                    "phone_number": "+919000000001",
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
        assert registration["account_status"] == "PENDING"
        print("PASS: self registration -> PENDING")

        expect(
            client.post(
                "/api/v1/auth/login",
                json={"email": devotee_email, "password": devotee_password},
            ),
            403,
            "pending account login blocked",
        )
        print("PASS: pending login blocked")

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

        pending = expect(
            client.get("/api/v1/admin/registrations/pending", headers=admin_headers),
            200,
            "pending registration list",
        )
        assert any(user["id"] == devotee_id for user in pending)
        print("PASS: pending list contains devotee")

        approved = expect(
            client.post(
                f"/api/v1/admin/registrations/{devotee_id}/approve",
                headers=admin_headers,
            ),
            200,
            "approve registration",
        )
        assert approved["account_status"] == "ACTIVE"
        print("PASS: approval -> ACTIVE")

        devotee_login = expect(
            client.post(
                "/api/v1/auth/login",
                json={"email": devotee_email, "password": devotee_password},
            ),
            200,
            "approved devotee login",
        )
        devotee_headers = {"Authorization": f"Bearer {devotee_login['access_token']}"}
        print("PASS: approved devotee login")

        me = expect(client.get("/api/v1/auth/me", headers=devotee_headers), 200, "me")
        assert me["email"].lower() == devotee_email
        assert me["devotee_profile"]["current_category"]["code"] == "ARJUNA"
        print("PASS: /me with Arjuna profile")

        expect(
            client.post(
                f"/api/v1/admin/devotees/{devotee_id}/deactivate",
                headers=admin_headers,
                json={"reason": "Automated local smoke test"},
            ),
            200,
            "deactivate devotee",
        )
        expect(client.get("/api/v1/auth/me", headers=devotee_headers), 403, "old token blocked")
        print("PASS: deactivation invalidates protected access")

        expect(
            client.post(
                f"/api/v1/admin/devotees/{devotee_id}/activate",
                headers=admin_headers,
                json={"reason": "Automated local smoke test reactivation"},
            ),
            200,
            "reactivate devotee",
        )
        expect(
            client.post(
                "/api/v1/auth/login",
                json={"email": devotee_email, "password": devotee_password},
            ),
            200,
            "reactivated devotee login",
        )
        print("PASS: reactivation restores login")

        # Verify a devotee cannot access Admin endpoints.
        fresh_login = expect(
            client.post(
                "/api/v1/auth/login",
                json={"email": devotee_email, "password": devotee_password},
            ),
            200,
            "fresh devotee login",
        )
        headers = {"Authorization": f"Bearer {fresh_login['access_token']}"}
        expect(client.get("/api/v1/admin/devotees", headers=headers), 403, "RBAC")
        print("PASS: devotee cannot use Admin endpoint")

    print("\nALL AUTH SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
