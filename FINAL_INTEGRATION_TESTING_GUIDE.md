# Step 17 Final Integration Testing Guide

This guide verifies the integrated release without retesting every feature manually.

## A. Static/backend regression

From `backend/`:

```powershell
pytest -q
python -m compileall -q app migrations scripts
alembic current
```

Expected Alembic head:

```text
0003_lifecycle_fields (head)
```

## B. Frontend build/contract verification

From `frontend/`:

```powershell
npm install
npm run verify
npm run contract:live -- --backend-url http://127.0.0.1:8000
```

`npm run verify` runs the frozen OpenAPI contract check, source/integration audit, strict TypeScript typecheck, ESLint, and production Next.js build.

## C. Runtime services

Backend:

```powershell
uvicorn app.main:app --reload
```

Frontend:

```powershell
npm run dev
```

Check:

```powershell
Invoke-RestMethod http://localhost:3000/api/readiness
Invoke-RestMethod http://localhost:3000/api/version
```

## D. Full backend regression

From `backend/`, with both services/database available as required by the smoke suite:

```powershell
python scripts/full_backend_smoke_suite.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

Expected:

```text
ALL SELECTED BACKEND SMOKE TESTS PASSED
```

## E. Full frontend regression

From `frontend/`:

```powershell
npm run smoke:full -- `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

Expected:

```text
ALL FRONTEND STEP 14 + STEP 15 + STEP 16 + STEP 17 SMOKE TESTS PASSED
```

The Step 17 portion additionally verifies readiness, runtime release identity, security headers, dedicated auth BFF routing, and request correlation.
