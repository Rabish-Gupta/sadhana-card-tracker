# Step 10 Weekly Evaluation Testing — v0.8.1


> **v0.8.1 note:** the smoke test uses one persistent asyncio event loop for its direct SQLAlchemy/asyncpg setup and cleanup operations. This fixes the Windows `RuntimeError: Event loop is closed` cleanup failure seen in v0.8.0 after all weekly assertions had already passed.

This checkpoint implements official **full-week** evaluation from finalized Daily Cards. It follows the approved lifecycle policy **A**: a week that begins after approval/reactivation or contains a deactivation/reactivation is retained as Daily Card history but receives **no official WeeklyEvaluation and no prorated targets/maxima**.

## 1. Install and run the automated suite

From the extracted v0.8.1 project directory, activate Python 3.12 and install the package:

```powershell
pip install -e ".[dev]"
pytest -q
```

Expected:

```text
88 passed
```

Then compile the Python sources:

```powershell
python -m compileall -q app migrations scripts
```

No output means success.

## 2. Confirm that no database migration is required

Step 10 uses the `weekly_evaluations` and `weekly_activity_results` tables that were already present in `0001_initial_schema`.

```powershell
alembic current
```

Expected:

```text
0002_org_setting_versions (head)
```

Do **not** create or modify a migration for this checkpoint.

## 3. Start the API

Terminal 1:

```powershell
uvicorn app.main:app --reload
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected status: `ok`.

## 4. Run the real PostgreSQL weekly smoke test

Terminal 2, with the same v0.8.1 virtual environment activated:

```powershell
python scripts/weekly_evaluation_smoke_test.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

The script uses a unique disposable devotee. It first proves that a newly approved partial week is excluded. For that disposable account only, it then backdates approval to the current week boundary and uses simulated domain times to create/finalize seven Daily Cards with full baseline values. It does **not** change the computer clock and does not modify real devotees.

Expected key checks:

```text
PASS: partial approval week is excluded from official weekly scoring (no proration)
PASS: full-week service evaluation keeps Sadhana and Academic maxima separate at 1750 each
PASS: weekly percentage rules, raw aggregates, daily-standard 7/7 analysis, and Seva non-score
PASS: weekly evaluation persistence is idempotent
PASS: disposable devotee logically deactivated

ALL WEEKLY EVALUATION SMOKE TESTS PASSED
```

## 5. What the smoke test proves

For one complete baseline week:

- Morning Program, Chanting, Morning Class, Shloka, Study, To Bed, Wake Up, Day Rest, and Filling Card aggregate their finalized daily marks using the configured weekly aggregation method.
- Book Reading aggregates daily minutes to 300 and scores `490` using the historical weekly rule + standard.
- Personal Hearing aggregates daily minutes to 120 and scores `210`.
- Seva aggregates to 420 minutes, keeps `final_activity_score = NULL`, and remains analytics-only.
- Daily standards store achieved-days/evaluated-days details such as `7/7`; these do not create extra marks.
- Weekly standard achievement is uncapped analytically, while percentage scoring is capped by its scoring rule.
- Sadhana total/max and Academic total/max remain separate (`1750` each in the baseline). There is no combined 3500 score.
- The weekly result stores exact category configuration, scoring-rule version, and standard-version references.
- Repeating the request returns the same persisted WeeklyEvaluation instead of duplicating it.

## 6. Weekly API surface

Devotee endpoints:

```text
GET /api/v1/weekly/latest
GET /api/v1/weekly/{week_start_date}
```

`GET /weekly/{week_start_date}` is idempotent. For an eligible completed week it ensures missing no-entry cards exist/finalize and then persists the official weekly result. A partial lifecycle week returns HTTP `409` and creates no official weekly score.

`GET /weekly/latest` resolves the latest completed organization week. If that week is a devotee's partial lifecycle week, the policy remains the same: no prorating and no official result.

## 7. Historical invariants

The weekly engine does not reinterpret old Daily Cards with today's configuration. It uses the category/activity config snapshotted on the seven daily entries. DAILY/SYSTEM_DERIVED rules come from the exact daily rule snapshots; WEEKLY_AGGREGATED rules and standards are resolved as-of the target week and their exact version IDs are persisted on `weekly_activity_results`.

Future historical-correction support must recalculate with these stored historical IDs, not current ACTIVE versions.
