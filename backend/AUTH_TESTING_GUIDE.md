# Step 6 Authentication & User Management — Local Test Guide

This guide tests the v0.4.0 authentication layer against the already-verified local PostgreSQL database.

## What this step implements

- mandatory self-registration for student devotees;
- academic-year → current devotee-category resolution from configured category data;
- `PENDING` self-registration workflow;
- Argon2 password hashing;
- JWT access-token login (simple MVP: access token only, no refresh token yet);
- active-account enforcement on every protected request;
- `GET /api/v1/auth/me`;
- simple MVP logout endpoint (client discards the stateless access token);
- Admin pending-registration list;
- Admin approve/reject;
- Admin direct devotee creation (`ACTIVE` immediately);
- Admin devotee list/status filtering;
- Admin deactivate/reactivate with mandatory reason;
- ADMIN vs DEVOTEE role protection;
- audit rows for Admin create/approve/reject/deactivate/reactivate actions.

No database schema change was needed for Step 6, so the verified `0001_initial_schema` migration is unchanged.

## 1. Update dependencies

From the backend folder with `.venv` activated:

```powershell
pip install -e ".[dev]"
pytest -q
python -m compileall -q app migrations scripts
```

Expected unit/static result for v0.4.0:

```text
38 passed
```

## 2. Configure JWT secret

Open `.env` and add/replace:

```env
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
DEFAULT_ORGANIZATION_CODE=VOICE
```

Generate a strong local secret if desired:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output into `JWT_SECRET_KEY`.

## 3. Give the local Admin a real password hash

Older test checkpoints could contain `TEST_ONLY_HASH`, which is not a usable password hash. v0.4.2 prevents that state for new bootstrap Admins by hashing `--admin-password` internally with Argon2.

Generate a real Argon2 hash:

```powershell
# No manual hash copy is required in v0.4.2.
$ADMIN_HASH
```

### Cleanest option for the disposable development database

Because the database has only test/seed data at this stage, rebuild and reseed it:

```powershell
alembic downgrade base
alembic upgrade head
python -m app.db.seed --admin-email admin@sadhanatracker.com --admin-full-name "Test Admin" --admin-phone "+910000000000" --admin-password "AdminTest123!"
```

Do **not** use `AdminTest123!` in production. It is only a local-development example.

## 4. Start FastAPI

Terminal 1:

```powershell
uvicorn app.main:app --reload
```

Check:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## 5. Run the complete auth smoke test

Open a second PowerShell in the same backend folder, activate `.venv`, then run:

```powershell
python scripts/auth_smoke_test.py --admin-email admin@sadhanatracker.com --admin-password "AdminTest123!"
```

The script automatically verifies:

1. health endpoint;
2. self-registration creates `PENDING` devotee;
3. pending devotee cannot log in;
4. Admin can log in;
5. pending devotee appears in Admin pending list;
6. Admin can approve registration;
7. approved devotee can log in;
8. `/auth/me` returns the profile and correctly resolves year 3 to Arjuna;
9. Admin can deactivate devotee with a reason;
10. an already-issued devotee token stops working after deactivation;
11. Admin can reactivate the devotee;
12. devotee can log in again;
13. devotee is forbidden from Admin endpoints.

Expected final line:

```text
ALL AUTH SMOKE TESTS PASSED
```

The script creates a disposable test devotee with a timestamped email so it can be rerun.

## 6. Optional manual Swagger test

In `/docs`:

### Self-register

`POST /api/v1/auth/register`

```json
{
  "full_name": "Madhav Das",
  "email": "madhav@example.com",
  "password": "StrongPass123!",
  "phone_number": "+919876543210",
  "college": "Example Institute of Technology",
  "branch": "Computer Science",
  "current_academic_year": 3,
  "college_joining_year": 2024
}
```

The account should return `PENDING`.

### Admin login

`POST /api/v1/auth/login`

```json
{
  "email": "admin@sadhanatracker.com",
  "password": "AdminTest123!"
}
```

Copy `access_token`, press **Authorize** in Swagger, and paste the token.

Then test the `/api/v1/admin/...` endpoints.

## 7. Database audit verification

In pgAdmin Query Tool:

```sql
SELECT action, reason, created_at
FROM audit_logs
ORDER BY created_at DESC
LIMIT 20;
```

After the smoke test you should see actions such as:

- `ACCOUNT_APPROVED`
- `ACCOUNT_DEACTIVATED`
- `ACCOUNT_ACTIVATED`

## 8. Important MVP behavior

- Self-registration is currently for academic years 1–4 and resolves the active category by the configured `academic_year` value; the API does not hard-code the category rule/standard profile.
- Admin-created devotees can explicitly use a category such as `BHIMA_WORKING` or `BHIMA_NOT_WORKING`.
- A student Admin-created under a category with an academic year must provide the matching `current_academic_year`.
- A Bhima category must omit `current_academic_year`.
- Rejected users cannot log in.
- Inactive users cannot log in and existing tokens also stop authorizing protected requests because account status is rechecked in PostgreSQL.
- Account deactivation/reactivation requires a reason and is audited.
- The Admin approval flow does not edit the devotee's submitted profile, matching the approved requirement.

## Stop condition

Do not move to daily-card APIs until both of these pass on the real local PostgreSQL installation:

```text
38 passed
ALL AUTH SMOKE TESTS PASSED
```


## FastAPI route-surface compatibility note

The route-surface test uses the generated OpenAPI paths rather than inspecting
FastAPI's private `app.routes` representation. This keeps the test valid across
FastAPI releases that may wrap included routers internally as `_IncludedRouter`.
The public API contract is the source of truth.

## Repairing an older bootstrap Admin

If an older local database contains a placeholder or malformed password hash, repair it explicitly:

```powershell
python -m app.db.seed --admin-email admin@sadhanatracker.com --admin-password "AdminTest123!" --reset-admin-password
```

The reset is explicit by design; normal idempotent seeding never silently changes an existing Admin password.
