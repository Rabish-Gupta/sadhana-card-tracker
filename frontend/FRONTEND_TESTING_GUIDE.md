# Frontend v0.4.0 Testing Guide

## Static/build verification

```powershell
npm install
npm run verify
```

This runs:

1. frozen backend-contract verification
2. frontend integration/source audit
3. TypeScript strict typecheck
4. ESLint
5. production Next.js build

With FastAPI running, also execute:

```powershell
npm run contract:live -- --backend-url http://127.0.0.1:8000
```

## Runtime

Backend:

```powershell
uvicorn app.main:app --reload
```

Frontend:

```powershell
npm run dev
```

Readiness:

```powershell
Invoke-RestMethod http://localhost:3000/api/readiness
```

Expected `status`: `ready`.

## Full frontend regression

```powershell
npm run smoke:full -- `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

It runs production-integration checks first, followed by the verified foundation, devotee and Admin smoke suites.

Expected final line:

```text
ALL FRONTEND STEP 14 + STEP 15 + STEP 16 + STEP 17 SMOKE TESTS PASSED
```
