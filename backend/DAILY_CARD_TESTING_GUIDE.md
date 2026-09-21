# Step 8 Daily Card Regression Testing — v0.7.0

This checkpoint adds the devotee-facing **Daily Card request/update engine** on top of the
verified v0.5.2 database and configuration layer.

## What Step 8 verifies

- `GET /api/v1/cards/today` dynamically materializes today's card from the devotee's
  effective category and category/activity configuration.
- The card snapshots category, organization timezone, daily deadline, and absolute UTC
  deadline.
- Daily-scored/system-derived entries snapshot the exact effective scoring-rule version.
- Weekly-aggregated and non-scored activities store raw daily input without prematurely
  awarding weekly marks.
- `PATCH /api/v1/cards/today` is the devotee's **Update** action; there is intentionally
  no Submit button.
- `first_update_at` is set only on the first successful update and `last_update_at`
  changes on later updates.
- Previous cards are read-only; future cards cannot be opened.
- Missing numeric values and intentional zero remain distinct through `is_filled`.
- Boolean `False` can be intentionally filled.
- Chanting completion follows the approved special rule: fewer than 16 rounds is a
  complete entry without completion time; 16 or more rounds requires completion time.
- System-derived `FILLING_SADHANA_CARD` cannot be edited by the devotee.
- A card automatically becomes read-only when its snapshotted deadline has passed when
  the service next observes it.

In the original v0.6 Step 8 checkpoint, scoring was deliberately deferred to Step 9. In v0.7+,
DAILY entries are now deterministically scored while preserving the exact raw data and rule/config snapshots used by Step 9.

The later scheduler phase will invoke the same lifecycle logic automatically so a devotee
who never opens the application still receives a no-entry finalized card. Step 8 does not
pretend that request-time finalization alone replaces that scheduled job.

## 1. Extract and install

When running this guide from the current v0.7.0 package, copy the already-working `.env` from your verified prior checkpoint.

PowerShell example:

```powershell
Copy-Item `
  "C:\path\to\v0.5.2\sadhana-card-tracker-backend\.env" `
  ".\.env" `
  -Force
```

Create/activate the virtual environment and install:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## 2. Automated tests

```powershell
pytest -q
```

Expected:

```text
81 passed
```

Then:

```powershell
python -m compileall -q app migrations scripts
```

No output means success.

## 3. Database migration status

Step 8 requires **no schema migration**. The 19-table schema already contains the Daily
Card tables.

```powershell
alembic current
```

Expected:

```text
0002_org_setting_versions (head)
```

Do not create a `0003` migration for this checkpoint.

## 4. Start the API

```powershell
uvicorn app.main:app --reload
```

Keep this terminal running.

Manual health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected `status = ok`.

## 5. Run the Daily Card smoke test

Run this **before the organization's daily deadline** (baseline: 10:00 PM Asia/Kolkata)
so the disposable devotee can make a normal Update.

In a second PowerShell window:

```powershell
python scripts/daily_card_smoke_test.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

Expected final line:

```text
ALL DAILY CARD SMOKE TESTS PASSED
```

The script creates one throwaway Arjuna devotee, approves it, opens today's 12-activity
card, updates Morning Program=`False`, Chanting=12 rounds, and Book Reading=0 minutes,
verifies the missing-vs-zero/False rules and Chanting completeness, then logically
deactivates the throwaway account.

## 6. Useful PostgreSQL inspection

After the smoke test:

```sql
SELECT
    dc.card_date,
    dc.status,
    dc.first_update_at,
    dc.last_update_at,
    dc.timezone_snapshot,
    dc.deadline_time_snapshot,
    dc.deadline_at_utc,
    dc.revision_number
FROM daily_cards dc
ORDER BY dc.created_at DESC
LIMIT 5;
```

Inspect the newest card's activity entries:

```sql
SELECT
    a.code,
    dae.is_filled,
    dae.daily_score,
    dae.max_score_snapshot,
    cac.scoring_type
FROM daily_activity_entries dae
JOIN activities a ON a.id = dae.activity_id
JOIN category_activity_configs cac ON cac.id = dae.category_activity_config_id
WHERE dae.daily_card_id = (
    SELECT id FROM daily_cards ORDER BY created_at DESC LIMIT 1
)
ORDER BY dae.created_at;
```

At the historical v0.6 Step 8 checkpoint, `daily_score` remained `NULL`. In v0.7+, DAILY and
finalized SYSTEM_DERIVED entries are scored; WEEKLY_AGGREGATED and NON_SCORED entries remain NULL.

Inspect raw values and the required `is_filled` distinction:

```sql
SELECT
    a.code,
    af.field_key,
    dav.is_filled,
    dav.numeric_value,
    dav.time_value,
    dav.boolean_value,
    dav.text_value
FROM daily_activity_values dav
JOIN daily_activity_entries dae ON dae.id = dav.daily_activity_entry_id
JOIN activities a ON a.id = dae.activity_id
JOIN activity_fields af ON af.id = dav.activity_field_id
WHERE dae.daily_card_id = (
    SELECT id FROM daily_cards ORDER BY created_at DESC LIMIT 1
)
ORDER BY a.code, af.display_order;
```

For the smoke card, Book Reading should show `is_filled = true` with numeric value `0`,
while untouched numeric fields show `is_filled = false` even though their storage default
is also numeric `0`.
