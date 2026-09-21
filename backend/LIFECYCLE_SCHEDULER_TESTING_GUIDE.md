## v0.9.5 advisory-lock transaction fix

The scheduler now keeps the PostgreSQL advisory lock on a dedicated connection and performs lifecycle work through a normal AsyncSession. This ensures card materialization, promotions, deactivations, and weekly-evaluation commits persist instead of being hidden inside the lock connection's implicit outer transaction and rolled back on close. The disposable Nakula promotion probe is also backdated by one week so the test can legitimately schedule a current-week promotion.



The smoke test no longer backdates disposable users to the previous week unconditionally. It derives the organization reconstruction floor and uses yesterday as a guaranteed already-due date only when that date is reconstructable. This verifies real missing-card backfill without violating the historical-boundary rule introduced in v0.9.2.

# Step 11 Lifecycle/Scheduler Testing Guide — v0.9.5

This maintenance checkpoint fixes the pending Bhima-choice response when a Yudhishthira revises a future WORKING/NOT_WORKING choice before activation. No database migration is required beyond `0003_lifecycle_fields`.

# Step 11 — Lifecycle & Scheduler Testing Guide (v0.9.0)

This checkpoint adds automatic lifecycle processing while preserving the approved **19 application tables**. Migration `0003_lifecycle_fields` adds only pending-deactivation columns to `users`.

## 1. Extract into a new folder and copy the working `.env`

Use the `.env` that already passed Step 10. The new scheduler settings are optional because safe defaults are built in:

```env
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_SECONDS=60
SCHEDULER_RUN_ON_STARTUP=true
```

For local debugging you may temporarily set `SCHEDULER_ENABLED=false`; the Admin `run-now` smoke-test endpoint still lets you execute the lifecycle processor explicitly.

## 2. Install the checkpoint

```powershell
pip install -e ".[dev]"
```

Step 11 adds APScheduler as a runtime dependency.

## 3. Code verification

```powershell
pytest -q
python -m compileall -q app migrations scripts
```

Expected automated result for this package:

```text
98 passed
```

## 4. Upgrade the existing PostgreSQL database

Before upgrade, your Step 10 database should show:

```powershell
alembic current
```

```text
0002_org_setting_versions (head)
```

Upgrade:

```powershell
alembic upgrade head
```

Then:

```powershell
alembic current
```

Expected:

```text
0003_lifecycle_fields (head)
```

The migration does **not** create a 20th application table. It adds these nullable lifecycle fields to `users`:

```text
pending_deactivation_week
pending_deactivation_reason
pending_deactivation_requested_by_id
pending_deactivation_scheduled_at
```

Optional pgAdmin verification:

```sql
SELECT version_num FROM alembic_version;

SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'users'
  AND column_name LIKE 'pending_deactivation%'
ORDER BY column_name;
```

## 5. Start the API

```powershell
uvicorn app.main:app --reload
```

When `SCHEDULER_ENABLED=true`, FastAPI performs an idempotent lifecycle pass at startup and then APScheduler repeats it. PostgreSQL advisory locking prevents two API processes from running the same organization's lifecycle work simultaneously.

## 6. Run the real PostgreSQL Step 11 smoke test

In a second terminal, activate the same virtual environment and run:

```powershell
python scripts/lifecycle_scheduler_smoke_test.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

The script creates disposable devotee accounts and logically deactivates them at the end. It verifies Admin Sahadeva review, explicit Yudhishthira -> Bhima choice (policy A), automatic Nakula -> Arjuna progression, PostgreSQL advisory locking/idempotent retry, and scheduler no-entry-card finalization.

Expected ending:

```text
PASS: Sahadeva appears in Admin review workflow
PASS: Sahadeva review is future-week and revisable before activation
PASS: Yudhishthira explicitly chooses initial Bhima status; no automatic default
PASS: scheduler lifecycle run acquires PostgreSQL advisory lock and is retryable
PASS: scheduler backfills/finalizes missed no-entry Daily Cards
PASS: due Nakula -> Arjuna academic promotion is applied at a week boundary
PASS: repeated lifecycle execution is idempotent/safe
PASS: disposable devotees logically deactivated

ALL LIFECYCLE/SCHEDULER SMOKE TESTS PASSED
```

## Step 11 lifecycle rules being tested

- Sahadeva -> Nakula requires Admin review; a negative decision schedules account deactivation without deleting history.
- Nakula -> Arjuna and Arjuna -> Yudhishthira are automatic at the configured promotion-month week boundary.
- Yudhishthira chooses initial Bhima Working/Not Working status; the system never guesses it.
- Bhima Working <-> Not Working is devotee-controlled and effective next week.
- Pending category changes are represented by future `devotee_category_history` rows and applied to the materialized profile at the due week boundary.
- No-entry Daily Cards are created/finalized automatically for dates on which the account was active at the card deadline.
- Weekly evaluation automation continues to enforce policy A: partial lifecycle weeks are factual Daily Card history only and receive no official/prorated weekly score.
- Scheduler work is safe to retry and protected by a per-organization PostgreSQL advisory lock.


## v0.9.2 historical-boundary regression

The lifecycle scheduler may encounter legacy or disposable devotees whose approval/category history predates the first reconstructable versioned configuration. Catch-up intentionally begins at the later of the organization's first settings-version effective week and first category/activity-config effective week. It must not fabricate pre-configuration Daily Cards or Weekly Evaluations. Existing persisted cards are still finalized from their own snapshots.
