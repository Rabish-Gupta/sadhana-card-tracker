# Step 13 — Four-Week Monthly Reporting Testing Guide

## Definition used by this project

A **monthly report is exactly four adjacent, completed organization weeks**. It is not a calendar-month report.

Example:

- Week 1: Mon 17 Aug → Sun 23 Aug
- Week 2: Mon 24 Aug → Sun 30 Aug
- Week 3: Mon 31 Aug → Sun 06 Sep
- Week 4: Mon 07 Sep → Sun 13 Sep

Those four weeks form one report even though the block crosses a calendar-month boundary.

Only persisted official `WeeklyEvaluation` rows participate. A partial lifecycle week that was excluded from official weekly scoring cannot silently count as one of the four weeks. There is no prorating.

## API

- `GET /api/v1/monthly/latest`
  - returns the latest available run of four adjacent completed Weekly Evaluations.
- `GET /api/v1/monthly/{period_start_date}`
  - the date is the `week_start_date` of the first of the four weeks.
  - if one of the next three adjacent weeks is missing/incomplete, the request is rejected.

The immediately preceding comparison period is exactly the four weeks immediately before the current block. If that exact four-week comparison block is unavailable, `previous_period` is `null`; the service does not substitute a non-adjacent older period.

## Scoring/analysis invariants

- Sadhana and Academic totals stay separate.
- Baseline four-week maxima are normally `7000` Sadhana and `7000` Academic (`1750 × 4`), but the API sums historical weekly maxima rather than hard-coding 7000.
- No combined `14000`/balance score is calculated.
- Weekly Book Reading and Personal Hearing results are aggregated from already-persisted weekly results; old daily data is not rescored with current rules.
- Seva remains raw analytics only and receives no score.
- Standard achievement is analysis and gives no additional marks.
- Raw standard achievement may exceed 100% where the underlying weekly result allows it.
- Weekly historical rule/config/standard snapshots are exposed per activity week where available.
- The report does not claim to measure spiritual advancement.

## Local automated checks

```powershell
pip install -e ".[dev]"
pytest -q
python -m compileall -q app migrations scripts
alembic current
```

Expected automated suite for v0.11.1:

```text
143 passed
```

Expected migration remains:

```text
0003_lifecycle_fields (head)
```

There is no Step 13 schema migration.

## Real PostgreSQL/API smoke test

Start the API in terminal 1:

```powershell
uvicorn app.main:app --reload
```

Run in terminal 2:

```powershell
python scripts/monthly_report_smoke_test.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

The smoke test creates a disposable devotee and eight synthetic persisted weekly snapshots because Steps 9–10 already separately verify daily/weekly calculation. This isolates Step 13 and verifies the reporting API itself against real PostgreSQL.

Expected final result:

```text
PASS: health
PASS: disposable devotee registered and approved
PASS: latest report uses four adjacent complete weeks and keeps Sadhana/Academic separate
PASS: activity raw/scored/standard analytics aggregate without giving Seva a score
PASS: specific period lookup is deterministic
PASS: incomplete/gapped four-week periods are not mislabeled as monthly reports

ALL FOUR-WEEK MONTHLY REPORT SMOKE TESTS PASSED
PASS: disposable devotee logically deactivated
```

The synthetic Weekly Evaluation rows are deleted during cleanup. The disposable user is logically deactivated rather than physically deleting the account.
