# Step 9 Deterministic Scoring — Local Verification

This checkpoint verifies the deterministic daily scoring engine against both the unit test suite
and your real local PostgreSQL/API setup.

## What Step 9 must preserve

Raw activity values remain the source of truth. A score is a deterministic evaluation derived
from the exact `CategoryActivityConfig` and `ScoringRuleVersion` already snapshotted on the
`DailyActivityEntry`. The engine must never look up the current rule when recalculating a
historical card.

Missing input remains different from intentional zero/False through `is_filled`, even when the
resulting score is 0 in both cases. `score_details` records why a score was produced without
changing the raw-data semantics.

`WEEKLY_AGGREGATED` activities (Book Reading, Personal Hearing) and `NON_SCORED` Seva do not
receive daily marks. Filling Sadhana Card is `SYSTEM_DERIVED` and receives its 0/10 mark only at
finalization, based on the configured countable-activity completion percentage.

## 1. Install and run automated tests

From the extracted v0.7.0 project directory:

```powershell
pip install -e ".[dev]"
pytest -q
```

Expected:

```text
81 passed
```

Then compile all Python files:

```powershell
python -m compileall -q app migrations scripts
```

No output means success.

## 2. Confirm no new migration is required

Step 9 uses columns already present in `daily_activity_entries`, so the migration head remains:

```powershell
alembic current
```

Expected:

```text
0002_org_setting_versions (head)
```

Do not create or modify a migration for Step 9.

## 3. Start the v0.7.0 API

In terminal 1:

```powershell
uvicorn app.main:app --reload
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected `status = ok`.

## 4. Run the Step 9 scoring smoke test

Run this before the organization's current daily finalization deadline (baseline: 10:00 PM
Asia/Kolkata). In terminal 2:

```powershell
python scripts/scoring_smoke_test.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

The test creates a disposable Arjuna devotee, updates a real card, and checks these important
boundary values:

- Morning Program `True` -> 30
- Chanting 16 rounds completed exactly at 09:30 -> 50 ("before 09:30" is strict)
- Morning Class `False` -> 0 while still factually filled
- Shloka count 1 -> 20
- Study exactly 60 minutes -> 20
- To Bed exactly 21:15 -> 50
- Wake Up exactly 03:40 -> 50
- Day Rest exactly 45 minutes -> 50
- Book Reading / Personal Hearing -> no daily score
- Seva -> no daily score
- Filling Sadhana Card -> no score while card is in progress

The script then uses the scheduler service seam with a simulated post-deadline time **only for its
disposable devotee**, finalizes that card, and verifies the 75% system-derived Filling Sadhana Card
rule. Ten of eleven countable baseline activities are completed, so the final filling-card score
must be 10.

Expected ending:

```text
PASS: deterministic DAILY threshold/boolean scores and weekly/non-scored separation
PASS: finalization computes 75% system-derived Filling Sadhana Card score
PASS: disposable devotee logically deactivated

ALL SCORING SMOKE TESTS PASSED
```

## 5. Optional PostgreSQL inspection

After the smoke test, inspect recent scoring rows in pgAdmin:

```sql
SELECT
    a.code,
    dae.is_filled,
    dae.daily_score,
    dae.max_score_snapshot,
    dae.score_calculated_at,
    dae.score_details,
    cac.scoring_type,
    dae.rule_version_id
FROM daily_activity_entries dae
JOIN activities a ON a.id = dae.activity_id
JOIN category_activity_configs cac ON cac.id = dae.category_activity_config_id
ORDER BY dae.created_at DESC, a.code
LIMIT 30;
```

For the disposable finalized scoring card, DAILY and SYSTEM_DERIVED activities should have
integer scores and non-null score metadata. `WEEKLY_AGGREGATED` and `NON_SCORED` rows should keep
`daily_score` as NULL.

## Step 9 scoring invariants

- No hard-coded combined Sadhana+Academic score exists.
- Threshold boundaries are evaluated in configured order using the configured operators.
- Exactly 45 minutes of Day Rest scores 50.
- Chanting below 16 rounds scores 0 without requiring completion time.
- Chanting at or above 16 rounds requires completion time; missing completion time scores 0.
- Filling Sadhana Card excludes itself from the completion denominator and is scored only at
  finalization.
- Historical scoring uses stored IDs/snapshots, not current configuration.
- Invalid future scoring-rule JSON is rejected by the Admin configuration service before it can
  become an executable pending rule version.
