### v0.10.0 — Step 12 Full Recheck, Historical Correction & Configuration Hardening

Before starting reporting work, the complete backend through stable Step 11 was rechecked against the project source-of-truth and verified again. The audit found and fixed gaps around finalized-card correction, historical category correction, ActivityField semantic immutability, standard-definition validation, and category-config activation dependency preflight.

Step 12 adds Admin-only historical finalized-card GET/PATCH APIs. Raw-value corrections require a reason, preserve missing-vs-zero/False semantics, recompute daily/system-derived scores from the card's stored historical rule/config IDs, increment the DailyCard revision, and atomically recalculate an existing WeeklyEvaluation from its stored historical rule/standard/config references. Audit actions `HISTORICAL_CARD_CORRECTED` and `WEEKLY_EVALUATION_RECALCULATED` preserve before/after data. Direct editing of system-derived Filling Sadhana Card is forbidden.

Historical category correction now follows approved **policy B**: a correction is effective from the selected week until the next actual different recorded transition. Category history is repaired, overlapping raw card data is preserved, newly applicable activities become missing/N/A rather than invented performance, wrong-category-only activities are removed from the corrected card with their original raw snapshot retained in audit data, and existing official WeeklyEvaluations are rebuilt from historically-effective corrected category/rule/standard/config versions. The normal Sahadeva/Bhima lifecycle rules remain unchanged.

Configuration hardening limits in-place ActivityField changes to label/display order; semantic changes require archive + replacement. Standard versions are validated against the analysis engine and their active activity fields. Due category-config activation performs a full dependency preflight before changing any statuses. Audit JSON conversion is recursive so nested historical snapshots are safely stored in PostgreSQL JSONB. No schema change is required: Alembic remains at `0003_lifecycle_fields`, and all 19 application tables are unchanged. See `PROJECT_AUDIT_v0.10.0.md` and `HISTORICAL_CORRECTION_TESTING_GUIDE.md`.

### v0.9.5 scheduler commit-persistence fix

Step 11 now holds the PostgreSQL session advisory lock on a dedicated connection while domain work uses the normal AsyncSession factory. This fixes a real persistence bug where binding the lifecycle AsyncSession to the same lock connection left an outer implicit SQLAlchemy transaction open; service-level commits could then be rolled back when the lock connection closed even though `run-now` reported materialized cards/promotions. The smoke test also makes its Nakula promotion probe effective from the prior week so it genuinely tests a due current-week promotion. No schema or migration change.

The Step 11 smoke harness now chooses an already-due date that is on/after the versioned configuration reconstruction floor. This keeps the test aligned with the v0.9.2 production rule that missing cards must never be invented before reliable historical configuration exists.

### v0.9.2 scheduler historical-boundary fix

Step 11 scheduler catch-up now respects the earliest date for which both versioned organization settings and category/activity configuration exist. Missing cards and generated weekly evaluations are never invented for legacy dates that predate reconstructable configuration history. Existing persisted cards earlier than that boundary still finalize from their own snapshots. This fixes `DailyCardConfigurationError: No effective organization settings version exists for this date` when legacy/test devotee history predates the configuration baseline.


### v0.9.2 lifecycle pending-transition response fix

Revising an already-loaded pending category transition now synchronizes both the foreign-key
value and SQLAlchemy relationship object. This prevents the lifecycle status response from
showing the previous Bhima target after a Yudhishthira revises WORKING -> NOT_WORKING (or the
reverse) in the same request/session. No schema or migration change is required.

# Sadhana Card Tracker Backend

FastAPI + async SQLAlchemy 2.0 backend for the VOICE Sadhana Card Tracker.

The implementation follows the approved **Sadhana Card Tracker Project Documentation v2.0**. The central invariant is that **raw historical data and the exact rule/standard/config versions used to evaluate it must never be silently reinterpreted by later configuration changes**.

## Current implementation status

**Version:** `0.10.0`

### Core platform

- FastAPI application skeleton
- Async SQLAlchemy 2.0 session setup using `asyncpg`
- Alembic migration environment
- PostgreSQL migration chain for all 19 project tables (Step 11 adds lifecycle columns without adding a 20th application table)
- PostgreSQL `citext` and `pgcrypto` extension setup
- UUID primary keys and timestamp mixins
- Stable domain enums
- Organization-local IANA timezone helpers
- Versioned organization settings for timezone, week start, daily finalization time, and promotion month

### Accounts and devotee lifecycle models

- `Organization`
- `User`
- `DevoteeCategory`
- `DevoteeProfile`
- `DevoteeCategoryHistory`
- Mandatory registration/profile storage for phone, college, branch, and college joining year
- SYSTEM / ADMIN / DEVOTEE category-history sources
- Week-boundary category transition model

`current_academic_year` is nullable at database level because Bhima/pass-out devotees have no current academic year. The API/service layer will require it for student categories (Sahadeva through Yudhishthira).


### Authentication & user management (Step 6)

- Mandatory devotee self-registration (name, email, password, phone, college, branch, academic year, joining year)
- Self-registration starts as `PENDING`; Admin approval is required before login succeeds
- Academic-year category lookup from configured `devotee_categories` data
- Argon2 password hashing
- Simple MVP JWT access-token authentication (no refresh token yet)
- Active-account check on every protected request
- `ADMIN` / `DEVOTEE` route authorization
- Admin pending-registration list and approve/reject actions
- Admin direct devotee creation as `ACTIVE`
- Admin devotee listing and status filtering
- Admin deactivate/reactivate with mandatory reason and audit logging
- Current-user/profile endpoint
- Simple client-side logout endpoint for the stateless MVP access token
- End-to-end local auth smoke-test script

### Configurable evaluation engine models

- `Activity`
- `ActivityField`
- `ScoringRule`
- `ScoringRuleVersion`
- `Standard`
- `StandardVersion`
- `CategoryActivityConfig`

One logical activity can use different rules and standards for different devotee categories without duplicating the activity itself.

### Daily, weekly, and governance models

- `DailyCard`
- `DailyActivityEntry`
- `DailyActivityValue`
- `WeeklyEvaluation`
- `WeeklyActivityResult`
- `AuditLog`

Daily cards snapshot category, timezone, local deadline, and absolute UTC deadline. Daily/weekly results keep exact historical config/rule/standard references.

### Deterministic daily scoring engine (Step 9)

- DAILY entries are recalculated from raw values on every successful card Update.
- Boolean and threshold rules are configuration-driven rather than activity-code hard-coded.
- Chanting uses the stored `required_rounds` + completion-time threshold configuration.
- Missing and intentional zero/False remain distinct in raw data even when both can yield score 0.
- Book Reading and Personal Hearing remain `WEEKLY_AGGREGATED` and therefore keep `daily_score = NULL`.
- Seva remains `NON_SCORED` and keeps `daily_score = NULL`.
- Filling Sadhana Card remains unscored while the card is in progress and is calculated only at finalization from the configured countable-activity completion percentage.
- Every calculated daily score stores `score_calculated_at` and transparent `score_details`.
- Runtime evaluation uses the exact `category_activity_config_id` and `rule_version_id` snapshotted on the historical entry; it never resolves the current rule for historical recalculation.
- v0.6 finalized cards with NULL daily marks are safely backfilled on read from their stored historical snapshots.
- Admin rule-version creation/update now rejects JSON rule bodies the deterministic engine cannot execute safely.
- Sadhana and Academic marks remain separate; no combined balance score is introduced.

### Configuration safety services

- Week-boundary validation for new versions/configurations
- Semantic validation of category/activity configurations
- Historical version resolver that permits archived historical versions but excludes pending future versions
- Percentage-scoring validation requiring a standard
- Cross-organization/activity validation for linked rules and standards

### Approved baseline seeding

The seed catalogue contains the approved shared v2.0 baseline:

- Organization defaults: `Asia/Kolkata`, Monday week start, 10:00 PM daily finalization, June promotion month
- 6 devotee categories
- 12 activities and their raw input fields
- 11 baseline scoring rules (Seva is non-scored)
- 11 baseline standards (Shloka/Vaishnava Song has no weekly standard)
- Shared category/activity configuration for all 6 categories
- Book Reading target: 300 minutes/week
- Personal Hearing target: 120 minutes/week
- Separate Sadhana and Academic baseline weekly maxima of 1750 each

The seed logic is idempotent and refuses to silently overwrite semantic conflicts or historically meaningful configuration.

## Database model count

19 mapped PostgreSQL tables:

1. `organizations`
2. `organization_setting_versions`
3. `users`
4. `devotee_categories`
5. `devotee_profiles`
6. `devotee_category_history`
7. `activities`
8. `activity_fields`
9. `scoring_rules`
10. `scoring_rule_versions`
11. `standards`
12. `standard_versions`
13. `category_activity_configs`
14. `daily_cards`
15. `daily_activity_entries`
16. `daily_activity_values`
17. `weekly_evaluations`
18. `weekly_activity_results`
19. `audit_logs`

## Local setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Run PostgreSQL migrations

Create the target database, ensure the database user can create extensions on the first migration, then run:

```bash
alembic upgrade head
```

Inspect the generated PostgreSQL SQL without connecting to a database:

```bash
alembic upgrade head --sql
```

Downgrade the complete migration chain:

```bash
alembic downgrade base
```

The migration intentionally leaves `pgcrypto` and `citext` installed on downgrade because PostgreSQL extensions are database-wide objects and may be shared by other schemas/applications.

## Seed the approved baseline

Run migrations before seeding.

Every rule/standard/config keeps a non-null creator Admin. Therefore the seeder needs an existing Admin email, or enough data to bootstrap the first Admin. **The seeder accepts the bootstrap password only through `--admin-password`, hashes it with Argon2 immediately, and stores only the encoded hash.**

Fresh database example:

```bash

> Bootstrap password safety: `--admin-password` is hashed with Argon2 inside the seeder before it is written to PostgreSQL. The seed command no longer requires copying an encoded hash through PowerShell. Existing Admin passwords are never replaced unless `--reset-admin-password` is explicitly supplied.

python -m app.db.seed \
  --admin-email admin@example.com \
  --admin-full-name "VOICE Admin" \
  --admin-phone "+91XXXXXXXXXX" \
  --admin-password 'AdminTest123!'
```

If the Admin already exists:

```bash
python -m app.db.seed --admin-email admin@example.com
```

By default, the first baseline becomes effective from the current organization-local week start. To make the baseline effective from an explicit Monday:

```bash
python -m app.db.seed \
  --admin-email admin@example.com \
  --effective-week 2026-09-14
```

The seed command refuses a non-week-boundary effective date.

## Historical-safety invariants represented in code

- Operational dates are calculated in each organization's configured IANA timezone.
- Absolute timestamps are stored timezone-aware (`TIMESTAMPTZ` in PostgreSQL).
- Daily deadlines are snapshotted so later timezone/deadline changes do not alter history.
- One devotee has at most one card per local calendar date.
- Missing numeric input is distinguishable from intentionally entered zero through `is_filled`.
- Daily-scored tasks and weekly-aggregated tasks are structurally distinct.
- Activated/historical rule, standard, category-config, and organization-setting versions are immutable at the service layer.
- New versions become effective only at organization week boundaries. Organization-setting changes are scheduled against the currently ACTIVE week definition, then become the definition for subsequent weeks after activation.
- Historical relationships use restrictive foreign keys instead of destructive cascade deletion.
- Sadhana and Academic evaluation remain separate; there is no combined balance score.
- Important administrative changes are designed for append-only audit logging.
- Semantic changes to historically used activity fields require archive + replacement rather than mutation.


### Weekly evaluation engine (Step 10)

- Official weekly evaluations are generated only for complete seven-day lifecycle weeks.
- Approved policy A is enforced: approval/reactivation/deactivation inside a week produces no official weekly score and no prorating. Raw Daily Cards remain factual history.
- Missing no-entry cards for an eligible completed week are materialized/finalized through the existing scheduler service seam before evaluation.
- DAILY and SYSTEM_DERIVED activities aggregate their finalized daily marks using the configured weekly aggregation method.
- Book Reading and Personal Hearing aggregate raw daily minutes and apply the historical percentage rule only once at week end.
- Weekly percentage scoring uses HALF_UP rounding and caps marks at the configured maximum; analytical standard achievement itself may exceed 100%.
- Daily standards persist achieved-days/evaluated-days details (for example 6/7) without awarding extra marks.
- Seva remains NON_SCORED while retaining weekly raw totals and standard-achievement analysis.
- `weekly_activity_results` persist exact category config, rule version, standard version, standard snapshot, raw aggregate, score, maximum, and calculation details.
- Sadhana and Academic weekly totals stay separate; the baseline maxima are 1750 and 1750. No combined 3500 score exists.
- Devotee endpoints: `GET /api/v1/weekly/latest` and `GET /api/v1/weekly/{week_start_date}`.
- Weekly generation is idempotent and forms the service seam for the later scheduler phase.

### Automated lifecycle and scheduler engine (Step 11)

- APScheduler runs an idempotent organization lifecycle tick at startup and on a configurable interval.
- PostgreSQL session advisory locks serialize one organization's lifecycle work across multiple API processes/workers.
- Due scoring-rule, standard, category-config, and organization-setting versions activate automatically at week boundaries.
- Missing due Daily Cards are backfilled as no-entry cards and finalized at their historical snapshotted deadlines; account activation history is reconstructed from approval/audit events.
- Due `IN_PROGRESS` cards finalize even if the devotee was later deactivated.
- Nakula -> Arjuna and Arjuna -> Yudhishthira are automatic academic promotions at the configured promotion-month week boundary.
- Sahadeva never auto-promotes: Admin explicitly schedules either continuation to Nakula or week-boundary deactivation, with a mandatory reason. The pending decision may be revised before it becomes effective.
- Yudhishthira never receives an arbitrary Bhima default. Under approved policy A, the devotee explicitly chooses `BHIMA_WORKING` or `BHIMA_NOT_WORKING`; early choices wait for the graduation boundary, late choices take effect next week.
- Existing Bhima devotees may switch Working <-> Not Working themselves, effective next week. Other student categories cannot self-change category.
- Future category transitions reuse `devotee_category_history`; scheduled Sahadeva deactivation uses lifecycle columns on `users`, keeping the approved 19-table architecture.
- Completed full lifecycle weeks are automatically evaluated with the existing no-proration policy A.
- Manual `POST /api/v1/admin/lifecycle/run-now` exists only as an Admin diagnostic/retry seam; production automation uses APScheduler.
- Important lifecycle scheduling/application actions are audit logged.

Step 11 adds migration `0003_lifecycle_fields`, which adds pending-deactivation columns to `users`; it does **not** alter `0001` or `0002` and does not add a new application table.

Devotee lifecycle APIs:

```text
GET  /api/v1/lifecycle/status
POST /api/v1/lifecycle/bhima-status
```

Admin lifecycle APIs:

```text
GET  /api/v1/admin/lifecycle/sahadeva-reviews
POST /api/v1/admin/lifecycle/devotees/{user_id}/sahadeva-review
POST /api/v1/admin/lifecycle/run-now
```

## Verification

Current automated verification covers:

- all SQLAlchemy mappings;
- PostgreSQL schema compilation;
- timezone/week calculations;
- configuration validation and historical resolution;
- the complete approved seed catalogue;
- exact 1750/1750 baseline weekly maxima;
- Alembic offline rendering of all 19 project tables, extensions, indexes, and native enum types;
- Step 8 Daily Card API contract, missing-vs-zero/False validation, and approved Chanting completion behavior;
- Step 9 deterministic boolean/threshold/system-derived scoring, exact boundary cases, baseline rule executability, and separation of daily vs weekly/non-scored activities;
- Step 10 partial-lifecycle exclusion, separate 1750/1750 weekly maxima, percentage weekly scoring, and weekly API contract.

Run:

```bash
pytest -q
python -m compileall -q app migrations scripts
alembic upgrade head --sql
```

For authentication testing, see `AUTH_TESTING_GUIDE.md`. For Step 7 configuration verification, see `CONFIGURATION_TESTING_GUIDE.md`. For Step 8 Daily Card verification, see `DAILY_CARD_TESTING_GUIDE.md`. For Step 9 scoring verification, see `SCORING_TESTING_GUIDE.md`. For Step 10 weekly evaluation verification, see `WEEKLY_EVALUATION_TESTING_GUIDE.md`. For Step 11 lifecycle/scheduler verification, see `LIFECYCLE_SCHEDULER_TESTING_GUIDE.md`. For the Step 12 audit/correction checkpoint, see `PROJECT_AUDIT_v0.10.0.md` and `HISTORICAL_CORRECTION_TESTING_GUIDE.md`.

## Next implementation phase

The database foundation and MVP authentication/user-management layer are implemented. Before proceeding, run the real PostgreSQL auth smoke test in `AUTH_TESTING_GUIDE.md`.

Step 7 configuration management, Step 8 daily-card request/update handling, Step 9 deterministic daily scoring, Step 10 official weekly evaluation, Step 11 automated lifecycle/scheduler processing, and Step 12 historical finalized-card correction/configuration hardening are now implemented.

Historical category correction policy B is now implemented. Monthly summaries and previous-period trend/report APIs are the next phase, followed later by AI-assisted observations only after deterministic reporting is stable.

## Windows timezone data

The project depends on Python's IANA timezone database for organization-local calculations such as `Asia/Kolkata`. The runtime dependency `tzdata` is included in `pyproject.toml`, so a normal `pip install -e ".[dev]"` installs it automatically. If an older environment was created before v0.3.2, run `python -m pip install tzdata` once and rerun the tests.

## v0.5.2 — Step 7 Admin Configuration + Versioned Organization Settings

Adds Admin-only configuration management for activities/fields, scoring rules and immutable
versions, standards and immutable versions, category/activity configuration versions, audit
logging, week-boundary validation, due-version activation, and the approved 19th application
table `organization_setting_versions`.

`organizations` keeps the materialized currently ACTIVE timezone/week-start/deadline/promotion
settings for efficient runtime reads. `organization_setting_versions` is the historical source
of truth for those settings and holds at most one editable PENDING change. At activation, the
old ACTIVE version is archived and the organization row is updated transactionally.

Migration `0001_initial_schema.py` remains unchanged. The new table is introduced only by
`0002_org_setting_versions.py`, including a safe baseline backfill for organizations
that already existed before this migration. See `CONFIGURATION_TESTING_GUIDE.md`.

### v0.5.2 migration compatibility correction

The v0.5.1 revision label `0002_organization_setting_versions` exceeded Alembic's default
32-character `alembic_version.version_num` column. v0.5.2 keeps the same schema change but uses
`0002_org_setting_versions`, which fits the Alembic version table. No change was made to
`0001_initial_schema.py`. A regression test now prevents revision identifiers longer than 32
characters.


## v0.6.0 — Step 8 Daily Card request/update engine

Adds devotee-only Daily Card APIs: `GET /api/v1/cards/today`, `PATCH /api/v1/cards/today`,
and `GET /api/v1/cards/{card_date}`. Today's card is dynamically materialized from the
devotee category effective for that organization week and the latest eligible category/activity
configuration. It snapshots category, timezone/deadline, and daily/system-derived rule versions.

The update contract preserves missing-vs-zero and missing-vs-`False`, supports partial updates,
tracks first/last successful update timestamps and revision number, applies the approved Chanting
completion rule, rejects edits to system-derived activities, blocks future cards, and enforces the
snapshotted deadline. Daily marks remain intentionally unset until Step 9's deterministic scoring
engine. See `DAILY_CARD_TESTING_GUIDE.md`.


## v0.7.0 — Step 9 Deterministic Daily Scoring

Adds the deterministic scoring service and integrates it into the Daily Card lifecycle. DAILY
activities are recalculated after every successful Update from the exact snapshotted scoring-rule
version; weekly-aggregated and non-scored activities intentionally remain without daily marks.
The engine supports the approved boolean and ordered threshold rule shapes, including the special
round-count + completion-time Chanting rule, and records transparent score details.

At finalization, all factual completion flags are recomputed first and the system-derived Filling
Sadhana Card rule then evaluates the configured countable activities. Its own activity is excluded
from the denominator, preventing circularity. The score is awarded only at finalization, matching
the approved project rule. Existing v0.6 finalized cards with NULL marks are lazily backfilled
from their historical config/rule IDs rather than from current configuration.

No schema migration is required for Step 9: `daily_activity_entries` already contained
`daily_score`, `rule_version_id`, `max_score_snapshot`, `score_calculated_at`, and `score_details`.
Both existing Alembic migration files remain unchanged.


## v0.8.1 — Windows async smoke-test cleanup fix

The Step 10 weekly smoke test now reuses a single `asyncio.Runner` for all direct database helper calls. This avoids reusing a pooled `asyncpg` connection on a second, already-different event loop during cleanup on Windows. Application runtime behavior, weekly scoring rules, database schema, and Alembic revisions are unchanged from v0.8.0.

## v0.8.1 — Step 10 Weekly Evaluation Engine

Adds persisted official weekly evaluation using the existing `weekly_evaluations` and
`weekly_activity_results` tables. No Alembic schema change is required.

The engine enforces the approved lifecycle policy A: only a devotee who was continuously active
for the entire organization-local seven-day week receives an official weekly score. Approval or
reactivation after the week begins, or deactivation/reactivation during the week, leaves Daily
Cards as factual history but creates no WeeklyEvaluation and does not prorate targets or maxima.

For complete eligible weeks, the engine ensures all seven cards exist and are finalized, aggregates
DAILY/SYSTEM_DERIVED marks using each category configuration's weekly aggregation method, scores
WEEKLY_AGGREGATED activities from raw weekly totals using the historical rule + standard version,
and preserves NON_SCORED activities such as Seva as raw analytics only. Daily standards store
achieved-days/evaluated-days analysis; weekly standard achievement remains analytically uncapped
while percentage scoring is capped at the configured maximum. Historical config/rule/standard IDs
and target snapshots are persisted on each weekly activity result.

Baseline weekly maxima remain exactly 1750 for Sadhana and 1750 for Academic, with no combined
score. See `WEEKLY_EVALUATION_TESTING_GUIDE.md`.

## Step 13 / v0.11.1 — Four-week monthly reporting

The project definition of a monthly report is **four adjacent complete organization weeks**, not a calendar month. A four-week block may cross a calendar-month boundary without being split or prorated.

New devotee routes:

- `GET /api/v1/monthly/latest`
- `GET /api/v1/monthly/{period_start_date}`

The report is built only from persisted official `WeeklyEvaluation` / `WeeklyActivityResult` history. It keeps Sadhana and Academic totals separate, aggregates raw/scored activity results, summarizes standard achievement and weekly variability, and compares with the exact immediately preceding four-week block when available. It intentionally does not create a combined balance score or claim to measure spiritual advancement.

See `MONTHLY_REPORT_TESTING_GUIDE.md` for verification instructions.

### v0.11.1 stabilization

Fixed the real-ORM monthly response construction to use `DevoteeCategory.display_name` (the actual model field) rather than a nonexistent `name` attribute. Added a regression test that builds and JSON-serializes a four-week report using real mapped model classes so this class of API/runtime mismatch is caught before packaging.


## Stable consolidated checkpoint / v0.11.2

This checkpoint keeps the Step 13 four-adjacent-complete-weeks reporting behavior and consolidates regression fixes. Decimal metrics in JSON are intentionally serialized as strings for precision, matching the existing weekly/daily API convention. Use `scripts/full_backend_smoke_suite.py` for one-command real-PostgreSQL regression testing.
