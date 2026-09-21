# Step 16 Implementation Notes — Admin Frontend v0.3.0

## Integration architecture

Step 16 keeps the verified Step 14 architecture unchanged:

Browser → Next.js same-origin BFF → FastAPI v0.11.2 → PostgreSQL.

The HttpOnly JWT cookie remains server-managed. Admin client components call `/api/backend/...`, never the FastAPI origin directly.

## Admin routes

- `/admin`
- `/admin/registrations`
- `/admin/devotees`
- `/admin/lifecycle`
- `/admin/config`
- `/admin/config/activities`
- `/admin/config/rules`
- `/admin/config/standards`
- `/admin/config/category-activities`
- `/admin/config/organization`
- `/admin/corrections`

All routes are protected by `requireRole("ADMIN")` through the Admin layout.

## Versioning safeguards

The frontend intentionally mirrors backend immutability rules rather than trying to outsmart them:

- Scoring rule ACTIVE/ARCHIVED versions are displayed but not edited.
- Standard ACTIVE/ARCHIVED versions are displayed but not edited.
- Organization ACTIVE/ARCHIVED settings are history only; the form edits/creates the single PENDING version.
- Category/activity config history is displayed; only PENDING rows receive an editor.
- Backend validation is authoritative for effective-week constraints and executable JSON configuration.

## Activity-field history safety

For an existing ActivityField, the UI only offers label/display-order changes and archive. It does not expose mutation controls for `field_key`, `input_type`, or unit semantics. A semantic change therefore follows the agreed archive-old/create-replacement policy.

## Historical corrections

The correction workbench supports:

1. Policy-B category correction: corrected category remains effective from the selected week until the next actual different category transition.
2. Finalized-card raw-value correction: only changed raw fields are PATCHed, with explicit `is_filled` semantics for N/A vs intentional zero/false.
3. System-derived activities are never directly edited.

The backend remains responsible for historical rule/standard/config resolution, score recalculation, weekly recalculation and audit records.

## JSON editors

Scoring-rule executable configuration and Standard target definitions are versioned JSONB in the backend. The Admin UI therefore exposes JSON textareas for these expert configuration areas and parses them as JSON objects before submission. FastAPI performs semantic validation.

## Audit-log listing limitation

The stable backend has an `audit_logs` table but no general `GET /admin/audit-logs` API. Step 16 does not fabricate a client-side audit list. A future backend endpoint can be added later without changing the BFF architecture.
