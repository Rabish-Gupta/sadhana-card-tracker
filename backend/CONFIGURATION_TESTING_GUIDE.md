# Step 7 Configuration API Testing Guide — v0.5.2

This checkpoint adds Admin configuration APIs for activities, fields, scoring rules,
standards, category/activity configuration, version history, and due-version activation.

## 1. Install and run automated tests

```powershell
pip install -e ".[dev]"
pytest -q
python -m compileall -q app migrations scripts
```

Expected automated result for this checkpoint:

```text
50 passed
```

`0001_initial_schema.py` is intentionally unchanged. Run `alembic upgrade head` to apply the new `0002_org_setting_versions` migration. The project now has 19 application tables.

## 2. Start the API

```powershell
uvicorn app.main:app --reload
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 3. Login as Admin

Use Swagger at `http://127.0.0.1:8000/docs` or POST to `/api/v1/auth/login`.
All `/api/v1/admin/config/...` endpoints require an ACTIVE Admin JWT.

## 4. Read-only verification first

Check these endpoints with the Admin token:

- `GET /api/v1/admin/config/categories`
- `GET /api/v1/admin/config/activities`
- `GET /api/v1/admin/config/scoring-rules`
- `GET /api/v1/admin/config/standards`
- `GET /api/v1/admin/config/category-activity-configs`
- `GET /api/v1/admin/config/organization-settings/current`
- `GET /api/v1/admin/config/organization-settings/versions`

The seeded six categories and twelve baseline activities should be visible.

## 5. Versioning invariant to verify

For an existing ACTIVE scoring-rule version or standard version, try the corresponding
PATCH endpoint. The API must return HTTP 409 because ACTIVE/ARCHIVED history is immutable.

Create a new version without `effective_from_week`; it defaults to the next organization
week start. If a PENDING version already exists for the same logical rule/standard, the API
returns 409 and requires editing that existing PENDING version instead of creating another.

The same rule applies to category/activity configurations.

## 6. Activation

`POST /api/v1/admin/config/activate-due` activates only PENDING versions whose
`effective_from_week` is at or before the current organization-local week start. It archives
the previously ACTIVE version for the same logical object/pair and retains it for historical
resolution.

The later scheduler phase will call this same service logic automatically with a
PostgreSQL-backed job lock. This Admin endpoint exists in Step 7 for deterministic testing
and manual local activation.

## 7. Important safety behavior

- Activity and activity-field removal is archive/deactivate, not destructive deletion.
- Semantic field attributes (`field_key`, `input_type`, `unit_code`) are not editable.
  Archive the old field and create a replacement for a semantic change.
- System-derived activities cannot receive user-input fields.
- A non-applicable activity cannot count toward card-fill completion.
- NON_SCORED configuration cannot reference a scoring rule.
- Cross-organization and cross-activity rule/standard references are rejected.
- Percentage scoring requires a configured standard.
- Changes are audit logged.

## 8. Versioned organization settings

The approved 19th table is `organization_setting_versions`. The editable settings are timezone,
week start, daily finalization time, and promotion month. `organizations` still stores the
currently ACTIVE values so request-time calculations do not need a history lookup.

Create a change with `POST /api/v1/admin/config/organization-settings/versions`. If
`effective_from_week` is omitted, it defaults to the next week start according to the settings
that are ACTIVE now. Only one PENDING organization-settings version is allowed; edit it using
`PATCH /api/v1/admin/config/organization-setting-versions/{version_id}`. ACTIVE/ARCHIVED
versions return HTTP 409 if edited.

When a due settings version activates, the previous ACTIVE history row becomes ARCHIVED and
the `organizations` row is updated in the same transaction. A timezone or week-start change
therefore affects future interpretation only after the scheduled boundary. Historical daily
cards remain stable because they snapshot timezone and deadline information.

## 9. Read-only PostgreSQL/API smoke test

After `alembic upgrade head` and seeding, start Uvicorn and run:

```powershell
python scripts/configuration_smoke_test.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

Expected final line:

```text
ALL CONFIGURATION SMOKE TESTS PASSED
```

This smoke test is deliberately read-only so it does not leave a PENDING configuration that
would activate in a future week.

## v0.5.2 migration ID compatibility fix

The v0.5.1 second revision identifier was longer than Alembic's default
`alembic_version.version_num VARCHAR(32)`. PostgreSQL therefore completed the migration body
inside its transaction but rejected Alembic's final revision update, causing the transaction to
roll back. v0.5.2 uses the shorter revision id `0002_org_setting_versions` and adds an automated
regression test requiring every Alembic revision id to remain at most 32 characters.

If an upgrade from v0.5.1 failed with `StringDataRightTruncationError`, first confirm:

```powershell
alembic current
```

It should still report `0001_initial_schema`. Then use the v0.5.2 source and run:

```powershell
alembic upgrade head
alembic current
```

The expected head is `0002_org_setting_versions`.
