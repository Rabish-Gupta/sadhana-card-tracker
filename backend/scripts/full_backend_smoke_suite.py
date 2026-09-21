"""Run the project's real-PostgreSQL smoke tests as one regression command.

The API must already be running. Daily-card and scoring tests perform real same-day
updates and therefore should be run before the organization's configured deadline.
Each underlying script uses disposable accounts and performs logical cleanup.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument(
        "--skip-time-sensitive",
        action="store_true",
        help="Skip Daily Card and deterministic scoring smoke tests if running after the daily deadline.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    project_root = root.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
    scripts = [
        "auth_smoke_test.py",
        "configuration_smoke_test.py",
    ]
    if not args.skip_time_sensitive:
        scripts.extend(["daily_card_smoke_test.py", "scoring_smoke_test.py"])
    scripts.extend(
        [
            "weekly_evaluation_smoke_test.py",
            "lifecycle_scheduler_smoke_test.py",
            "historical_correction_smoke_test.py",
            "monthly_report_smoke_test.py",
        ]
    )

    common = [
        "--base-url",
        args.base_url,
        "--admin-email",
        args.admin_email,
        "--admin-password",
        args.admin_password,
    ]

    for name in scripts:
        print(f"\n=== RUNNING {name} ===", flush=True)
        result = subprocess.run(
            [sys.executable, str(root / name), *common],
            check=False,
            cwd=project_root,
            env=env,
        )
        if result.returncode != 0:
            raise SystemExit(f"REGRESSION SUITE FAILED: {name} exited with {result.returncode}")

    print("\nALL SELECTED BACKEND SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
