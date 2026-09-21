# Architecture Decision — Versioned Organization Settings

**Decision:** The Sadhana Card Tracker now has **19 main application tables**. The 19th table is `organization_setting_versions`.

The settings covered by this decision are the organization IANA timezone, week-start day, daily card finalization time, and promotion month. They affect date interpretation, deadline calculation, configuration activation, category promotion, reporting boundaries, and future scheduler jobs, so they must not be mutated mid-week without history.

`organizations` remains the materialized current-state row. Its four temporal setting columns always mirror the ACTIVE organization-settings version and are used for ordinary runtime calculations. `organization_setting_versions` preserves ACTIVE/ARCHIVED history and the single editable PENDING change.

A change is scheduled for a week boundary according to the settings that are ACTIVE when the change is created. Before that boundary, the PENDING row can be edited instead of creating additional versions. At activation, the previous ACTIVE version becomes ARCHIVED, the PENDING version becomes ACTIVE, and the four materialized columns on `organizations` are updated in the same database transaction.

This rule is especially important when timezone or week-start day itself changes: the transition occurs at the boundary defined by the old/current configuration; after activation, subsequent weeks use the new configuration. Historical daily cards are not reinterpreted because card date, timezone, local deadline, and absolute UTC deadline are snapshotted on the card.

Migration `0001_initial_schema.py` remains frozen. `0002_org_setting_versions.py` creates the new table and backfills one ACTIVE baseline version for organizations that already existed. Fresh organizations receive their baseline ACTIVE settings version through the seed/bootstrap flow.
