# Sadhana Card Tracker — Consolidated Project Audit v0.11.0

## Scope

This audit was performed before Step 13 monthly reporting was packaged. It rechecks the developed backend from foundation through lifecycle automation and historical correction, then verifies the new four-week reporting layer against the same architectural rules.

## Preserved domain invariants

- Two independent domains remain visible: Sadhana and Academic/Work/Lifestyle. There is no combined balance score.
- The system records/evaluates practices; it does not claim to measure spiritual advancement.
- Raw factual data remains the source of truth. Evaluation and analysis remain separate layers.
- Missing values remain distinguishable from intentional zero/False.
- Daily card history is read-only to devotees after finalization; Admin correction is separate, reason-required, and audited.
- Historical recalculation uses stored/config-effective historical versions, not current rule/standard versions.
- Category/config/rule/standard changes remain week-boundary based.
- Partial lifecycle weeks retain factual Daily Card history but do not receive official Weekly Evaluations and are not prorated.
- Initial Yudhishthira→Bhima status is explicitly selected by the devotee; there is no automatic Working/Not Working default.
- Sahadeva continuation remains Admin-reviewed.
- Missing no-entry cards are scheduler-created/finalized only where history is safely reconstructable.
- PostgreSQL advisory locking and lifecycle commits remain separated so scheduler writes persist.

## Database/migrations

Application table count remains **19**:

1. organizations
2. users
3. devotee_categories
4. devotee_profiles
5. devotee_category_history
6. activities
7. activity_fields
8. scoring_rules
9. scoring_rule_versions
10. standards
11. standard_versions
12. category_activity_configs
13. daily_cards
14. daily_activity_entries
15. daily_activity_values
16. weekly_evaluations
17. weekly_activity_results
18. audit_logs
19. organization_setting_versions

Alembic remains separate. Step 13 does not add a monthly-report table because the report is a deterministic read model over persisted Weekly Evaluations.

Migration chain remains unchanged:

- `0001_initial_schema`
- `0002_org_setting_versions`
- `0003_lifecycle_fields`

Migration checksums were compared with v0.10.0 and are unchanged.

## Rechecked functional layers

### Authentication/RBAC

Registration, approval/rejection, login, active-account enforcement, Admin/Devotee authorization, deactivate/reactivate, Argon2 hashing, and JWT behavior remain covered by the consolidated suite.

### Versioned configuration

Activities/fields, scoring-rule versions, standards, category/activity configs, organization-setting versions, future-week activation, immutable active/history versions, and validation hardening remain intact.

### Daily Card

Dynamic activity materialization, organization-local deadline snapshots, first/last update timestamps, missing-vs-zero semantics, Chanting completion semantics, read-only historical cards, and no-entry-card support remain intact.

### Deterministic scoring

Daily boolean/threshold rules, exact boundary behavior, weekly-only activity separation, non-scored Seva, and system-derived Filling Sadhana Card remain intact.

### Weekly evaluation

Full-week-only policy, separate 1750 baseline maxima, weekly Book Reading/Personal Hearing scoring, daily standards analysis, Seva raw analytics, historical snapshots, previous-week comparison, and idempotent persistence remain intact.

### Lifecycle scheduler

Sahadeva review, Bhima choice, Nakula→Arjuna/Arjuna→Yudhishthira progression, pending transitions, configuration activation, reconstruction floor, PostgreSQL advisory locking, persisted commits, missed-card processing, weekly generation, and idempotent retry behavior remain intact.

### Historical corrections

Finalized Daily Card correction and Policy B category correction remain reason-required/audited. Category correction applies from the chosen historical week until the next real category transition, rebuilding affected persisted daily/weekly history without applying current rules to old periods.

## Step 13 monthly-report definition

The project definition is now explicit:

> **Monthly Report = exactly 4 adjacent complete organization weeks.**

It is not a calendar month. The block may cross a calendar-month boundary.

The report:

- reads persisted official Weekly Evaluations only;
- requires four consecutive week starts exactly seven days apart;
- rejects incomplete/gapped blocks;
- excludes the unfinished current week;
- naturally excludes partial lifecycle weeks because they have no official Weekly Evaluation;
- sums historical weekly maxima instead of hard-coding 7000;
- keeps Sadhana and Academic totals/percentages/trends separate;
- aggregates activity raw/scored results and standard achievement;
- keeps Seva non-scored;
- exposes per-week historical config/rule/standard references through activity weekly results;
- compares only with the exact immediately preceding four-week block;
- provides factual observations/variability, not a combined judgment or spiritual-advancement claim.

## Verification performed in package environment

- `pytest -q -W error` → **142 passed**
- `python -m compileall -q app migrations scripts` → passed
- SQLAlchemy metadata → **19 application tables**
- FastAPI OpenAPI generation → passed
- Required core routes including both monthly endpoints → present
- Migration SHA-256 comparison against v0.10.0 → unchanged

A real PostgreSQL smoke script is included for Step 13 and should be run locally before the checkpoint is frozen for the next phase.
