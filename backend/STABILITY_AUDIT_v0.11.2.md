# Sadhana Card Tracker Backend — Stability Audit v0.11.2

This checkpoint consolidates the backend through the four-adjacent-complete-weeks report.

## Frozen project invariants checked

- 19 application tables; Alembic remains at `0003_lifecycle_fields`.
- Sadhana and Academic scores remain separate; no combined balance score.
- Missing numeric value and intentional zero remain distinguishable through `is_filled`.
- Finalized Daily Cards are read-only to devotees; Admin historical corrections are audited.
- Historical evaluation uses stored configuration/rule/standard references rather than current rules.
- Weekly evaluations exclude partial lifecycle weeks; no proration.
- Project "monthly" report means exactly four adjacent complete organization weeks, not a calendar month.
- Sahadeva review remains Admin-controlled; Nakula→Arjuna and Arjuna→Yudhishthira are automatic at week boundaries.
- Initial Yudhishthira→Bhima status is devotee-selected; later Bhima Working↔Not Working changes take effect next week.
- Scheduler uses PostgreSQL advisory locking with independent transactional sessions.
- Missing-card backfill never fabricates dates earlier than reconstructable configuration history.

## Stabilization fixes in v0.11.2

- Corrected the Step 13 smoke test to respect the API's established Decimal JSON contract. Pydantic serializes precise `Decimal` values as strings, consistent with Weekly and Daily APIs.
- Added regression coverage for Decimal JSON serialization in four-week reports.
- Explicitly configured `pytest-asyncio` fixture loop scope to avoid future/deprecation warning failures under `-W error`.

## Verification performed in the build environment

- Full pytest suite.
- Full pytest suite with warnings treated as errors.
- Python `compileall` for application, migrations, and scripts.
- FastAPI OpenAPI generation and route-surface checks.
- ORM metadata application-table count and Alembic revision-chain checks.
- Static search for unresolved TODO/FIXME/NotImplemented markers in runtime code.
- Static search confirming scoring/report services are configuration-driven rather than branching on baseline activity codes.

Real PostgreSQL behavior still requires the included smoke tests on the user's PostgreSQL installation because the build container has no PostgreSQL server.
