# Step 13 Implementation Notes — Four Adjacent Complete Weeks

## Final domain decision

`Monthly Report = 4 adjacent complete organization weeks`.

This is deliberately independent of calendar months. The report period is identified by the `week_start_date` of its first Weekly Evaluation. The end is the `week_end_date` of the fourth adjacent Weekly Evaluation.

## Source of truth

Step 13 does not recalculate historical daily or weekly scores. Its source of truth is the already-persisted weekly layer:

- `weekly_evaluations`
- `weekly_activity_results`

This preserves historical category/config/rule/standard decisions and avoids applying current configuration to old periods.

## Previous-period comparison

For a current period starting on `S`, the previous comparison period must start exactly on `S - 28 days` and must contain all four adjacent complete weekly evaluations. A different older four-week run is never substituted.

## Partial lifecycle weeks

Step 10 policy A remains authoritative. Because partial lifecycle weeks have no official Weekly Evaluation, they naturally break a four-week sequence. They are retained as Daily Card history but are not prorated into Step 13.

## No persistence table

No new monthly-report table is required. The report is a deterministic read model over versioned/persisted weekly history. The agreed database architecture remains 19 application tables plus `alembic_version`.


## v0.11.1 stabilization

- Fixed category display serialization in monthly reports: `category_snapshot.display_name` is now used instead of nonexistent `category_snapshot.name`.
- Added a real-mapped-model report construction/serialization regression test.
- Consolidated suite: 143 tests with warnings-as-errors.
