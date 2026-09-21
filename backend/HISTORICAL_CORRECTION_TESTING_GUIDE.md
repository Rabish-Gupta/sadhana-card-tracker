# Step 12 — Historical Correction & Configuration Hardening Testing Guide

This checkpoint is `v0.10.0`. It does **not** add a database migration. The Alembic head remains:

```text
0003_lifecycle_fields (head)
```

## 1. Install and run the automated suite

From the extracted Step 12 project directory:

```powershell
pip install -e ".[dev]"
pytest -q
```

Expected:

```text
134 passed
```

Also run:

```powershell
pytest -q -W error
python -m compileall -q app migrations scripts
alembic current
```

Expected Alembic head:

```text
0003_lifecycle_fields (head)
```

No `alembic upgrade` is required when moving from the verified Step 11 `v0.9.5` database because Step 12 changes services/APIs only.

## 2. Start the API

In terminal 1:

```powershell
uvicorn app.main:app --reload
```

Confirm:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected status: `ok`.

## 3. Run the real PostgreSQL historical-correction smoke test

In terminal 2, with the same Step 12 virtual environment active:

```powershell
python scripts/historical_correction_smoke_test.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

The script creates one disposable Arjuna account and constructs a fully finalized/evaluated baseline week. It first verifies approved **policy B** historical category correction (the corrected category is effective from the selected week until the next recorded different transition), including Daily Card/WeeklyEvaluation rebuilds. It then performs an Admin correction of one finalized Study/Preparation value from 120 minutes to an intentional zero.

Expected key checks:

```text
PASS: policy-B historical category correction rebuilds the interval and preserves the next transition
PASS: finalized raw value corrected with intentional-zero semantics and daily rescoring
PASS: affected WeeklyEvaluation recalculated with separate Sadhana/Academic totals
PASS: historical config/rule/standard IDs preserved and correction audited
PASS: corrected weekly result persisted idempotently
PASS: system-derived Filling Sadhana Card cannot be directly corrected
PASS: disposable devotee logically deactivated

ALL HISTORICAL CORRECTION SMOKE TESTS PASSED
```

The test deliberately verifies that the corrected Academic weekly score falls by 30 while the Sadhana score remains unchanged, and that the existing historical rule/config/standard identifiers do not change.

## 4. Optional audit-log inspection

In pgAdmin:

```sql
SELECT action, reason, entity_type, created_at
FROM audit_logs
WHERE action IN (
  'HISTORICAL_CATEGORY_CORRECTED',
  'HISTORICAL_CARD_CATEGORY_REBUILT',
  'WEEKLY_EVALUATION_CATEGORY_REBUILT',
  'HISTORICAL_CARD_CORRECTED',
  'WEEKLY_EVALUATION_RECALCULATED'
)
ORDER BY created_at DESC
LIMIT 20;
```

The correction reason should be present. `before_data` and `after_data` should be populated.

## 5. Configuration-hardening behavior

The Step 12 Admin configuration API now rejects:

- in-place changes to `required_for_completion` (semantic field changes require archive + replacement);
- malformed standard target JSON;
- Weekly Boolean/Time standards unsupported by the current weekly aggregate engine;
- incompatible standard field/unit definitions;
- due category/activity configs without an effective compatible rule/standard version;
- Non-Scored applicable configs without a weekly raw aggregation method.

These checks intentionally protect future Daily Cards and historical reports from configuration that the deterministic engines cannot execute.


## 6. Historical category correction policy B

Admin endpoints:

```text
GET   /api/v1/admin/corrections/devotees/{user_id}/category-history
PATCH /api/v1/admin/corrections/devotees/{user_id}/category
```

The PATCH payload requires `effective_from_week`, `target_category_code`, and a non-empty reason. The corrected category remains effective from that week until the next actual different category transition. A later history row that would transition to the same corrected category is redundant and is removed; the next different transition is repaired so its `previous_category` matches the corrected interval.

Existing Daily Cards in the corrected interval are rebuilt against the category/activity configuration and scoring-rule versions that were effective in each historical week. Overlapping raw values are preserved. Activities that become newly applicable are represented as missing/N/A rather than invented performance. Activities that were present only because of the wrong category are removed from the corrected card, with their original raw snapshot retained in the append-only audit log. Existing official WeeklyEvaluations are rebuilt from the corrected Daily Card snapshots using historically-effective rule/standard/config versions.

This is a special Admin correction workflow, not a normal midweek category change.
