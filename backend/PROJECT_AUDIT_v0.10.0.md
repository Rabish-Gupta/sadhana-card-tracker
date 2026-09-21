# Sadhana Card Tracker — Full Backend Recheck before Reporting

**Checkpoint reviewed:** stable Step 11 `v0.9.5`  
**Hardened checkpoint produced:** Step 12 `v0.10.0`  
**Scope:** FastAPI backend, SQLAlchemy mappings, Alembic chain, seed catalogue, authentication/RBAC, versioned configuration, Daily Cards, deterministic scoring, weekly evaluation, lifecycle scheduler, audit/correction invariants.

## Verification performed

The stable Step 11 source was re-extracted and reviewed before adding new behavior. The audit checked the source-of-truth v2 project requirements against the implemented services and API surface, then re-ran the backend verification stack.

- Baseline Step 11 automated suite: **107 passed**.
- Step 12 hardened suite after fixes: **134 passed**.
- `pytest -q -W error`: passes.
- `python -m compileall -q app migrations scripts`: passes.
- Editable package metadata/build for version `0.10.0`: passes.
- FastAPI OpenAPI generation: passes; historical correction route exposes both GET and PATCH.
- SQLAlchemy model metadata: **19 application tables**.
- Alembic offline chain renders `0001 -> 0002 -> 0003` and creates 19 application tables plus `alembic_version`.
- SHA-256 comparison confirms migrations `0001`, `0002`, and `0003` are unchanged from the verified `v0.9.5` checkpoint.

## Rechecked project invariants

The implementation continues to preserve the project decisions made through Step 11:

- Separate **Sadhana** and **Academic** evaluation; no combined balance score.
- No claim that marks measure spiritual advancement.
- Raw factual data remains distinct from evaluation and later analysis.
- Organization-local timezone/week/deadline logic with historical snapshots.
- Versioned organization settings, scoring rules, standards, and category/activity configuration.
- Activated/historical versions remain immutable; pending versions activate on week boundaries.
- Missing values remain distinct from intentional `0`/`False`.
- 12 approved baseline activities and 6 devotee categories remain unchanged.
- Baseline weekly maxima remain `1750` Sadhana and `1750` Academic.
- Partial lifecycle weeks remain unscored and unprorated.
- Sahadeva Admin review, automatic Nakula/Arjuna progression, explicit Yudhishthira Bhima choice, and devotee-controlled Bhima employment changes remain intact.
- Scheduler remains PostgreSQL-lock protected, retryable, idempotent, and bounded by reconstructable configuration history.

## Gaps found during the recheck and fixed in v0.10.0

### 1. Historical finalized-card correction was missing

The v2 source-of-truth explicitly requires an Admin historical-card correction flow with mandatory reason, before/after audit data, historical-rule recalculation, affected weekly regeneration, and revision increments. Step 11 did not yet implement it.

`v0.10.0` adds Admin-only endpoints:

```text
GET   /api/v1/admin/corrections/devotees/{user_id}/cards/{card_date}
PATCH /api/v1/admin/corrections/devotees/{user_id}/cards/{card_date}
```

The correction service:

- accepts only already-finalized cards;
- requires a non-empty Admin reason;
- reuses the typed Daily Card value contract, preserving missing-vs-zero/False semantics;
- blocks direct edits to system-derived activities;
- recalculates completion and daily/system-derived scores from the exact historical DailyActivityEntry rule/config snapshots;
- increments `daily_cards.revision_number`;
- if an official WeeklyEvaluation already exists, recalculates that exact persisted week from its stored category-config/rule/standard references rather than resolving current configuration;
- increments `weekly_evaluations.revision_number`;
- writes `HISTORICAL_CARD_CORRECTED` and, when applicable, `WEEKLY_EVALUATION_RECALCULATED` audit records;
- commits card correction, weekly recalculation, and audit records atomically.

### 2. Activity-field semantic immutability was too permissive

The Admin field PATCH previously allowed `required_for_completion` to be changed in place. That could reinterpret whether already-persisted historical cards count an activity as complete.

`v0.10.0` restricts in-place ActivityField edits to **presentation metadata only**:

- `label`
- `display_order`

Semantic properties (`field_key`, `input_type`, `unit_code`, `required_for_completion`) now require the approved archive-and-replacement workflow. Unknown semantic fields in this PATCH payload are rejected instead of silently ignored.

### 3. Standard-version JSON was not validated strongly enough

Scoring rule JSON already had executable validation, but standard `target_definition` could previously be stored without proving that the weekly-analysis engine understood it.

`v0.10.0` validates standard versions before creation/update and again during due-version activation. Validation covers supported kinds/operators, boolean/time/numeric value types, nonnegative count/duration targets, whole-number counts, weekly numeric-only targets, activity-field resolution, and unit compatibility. System-derived standards are constrained to the supported Daily Boolean form.

### 4. Category/config activation dependency preflight was incomplete

A category/activity configuration could be structurally valid yet have no executable scoring-rule or standard version effective on its own target week.

`v0.10.0` preflights the entire due activation batch **before mutating statuses**. An activating configuration must have compatible, effective rule/standard versions for that target week. Current engine compatibility is enforced: Daily uses Boolean/Threshold rules, Weekly Aggregated uses Percentage rules plus a Weekly standard, System Derived uses a System Derived rule, and Non-Scored has no scoring rule. Applicable Non-Scored analytics also require a weekly aggregation method because the weekly engine aggregates their raw data (for example Seva).

## Historical category correction policy resolved

The historical-category correction ambiguity was resolved with **policy B**: an Admin correction changes the category from the selected effective week forward until the next actual different recorded category transition. If a later row would transition to the same corrected category, that row is a no-op and is removed; the next different transition is repaired so its `previous_category` matches the corrected interval.

`v0.10.0` therefore adds Admin category-history/correction endpoints with mandatory reason. Existing Daily Cards inside the corrected interval are rebound to the category/activity configuration and daily rule versions that were historically effective for each week. Overlapping raw values are preserved. Newly applicable activities are materialized as missing/N/A rather than invented performance; activities that belonged only to the wrong category are removed from the corrected card while their complete original raw snapshot is retained in append-only audit data. Existing official WeeklyEvaluations are rebuilt from the corrected card snapshots using historically-effective rule/standard/config versions. Category history, cards, weekly results, and the materialized current profile are updated atomically and audited under one correction batch ID.

This is a special Admin correction path and does not weaken the normal lifecycle rules: Sahadeva review remains Admin-governed, Yudhishthira's initial Bhima choice remains devotee-owned, and ordinary category changes remain week-boundary based.

## Documentation note

The formal v2.0 document predates the later approved decision to add `organization_setting_versions`, so references to 18 main application tables are superseded by the approved **19-table architecture** implemented since Step 7. The runtime schema and current README are consistent with the later decision.

## Reporting readiness

With policy B now implemented and audited, the backend is ready to proceed to monthly reporting/trend APIs. Monthly reporting should consume persisted Daily/Weekly facts and historical snapshots rather than recalculate old periods with current configuration.
