# Sadhana Card Tracker Frontend — Step 17 v0.4.0

This is the production-hardened frontend built against the frozen FastAPI backend **v0.11.2**.

## Stack

- Next.js 15 App Router
- React 19
- TypeScript strict mode
- Tailwind CSS
- Same-origin Next.js BFF to FastAPI
- FastAPI JWT kept only in an HttpOnly cookie

## Functional scope

The verified Step 14–16 functionality remains intact: authentication, devotee Daily Card/history/weekly/four-week/lifecycle flows, and Admin registration/devotee/lifecycle/configuration/historical-correction flows.

## Step 17 integration hardening

- Central BFF timeout handling and 502/504 UX
- `x-request-id` correlation on BFF responses
- Generic BFF request-body size limit
- Dedicated auth session endpoints protected from generic proxy bypass
- `/api/readiness` and `/api/version`
- Live OpenAPI contract drift check
- Security headers and production HSTS
- Standalone Next.js output for container deployment
- Active navigation, skip link, focus styling, reduced-motion support, loading skeleton, accessible mutation feedback

The browser still never calls FastAPI directly.

## Environment

Copy `.env.example` to `.env.local`:

```env
BACKEND_BASE_URL=http://127.0.0.1:8000
BACKEND_REQUEST_TIMEOUT_MS=15000
BFF_MAX_BODY_BYTES=1048576
NEXT_PUBLIC_APP_NAME=Sadhana Card Tracker
NEXT_PUBLIC_APP_VERSION=0.4.0
```

`BACKEND_BASE_URL` is server-only and must not be renamed to `NEXT_PUBLIC_*`.

## Verify

```powershell
npm install
npm run verify
npm run contract:live -- --backend-url http://127.0.0.1:8000
```

## Run

```powershell
npm run dev
```

Then run the complete frontend regression:

```powershell
npm run smoke:full -- `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

Expected final line:

```text
ALL FRONTEND STEP 14 + STEP 15 + STEP 16 + STEP 17 SMOKE TESTS PASSED
```

For the complete backend+frontend release, see the parent release `START_HERE.md` and `PRODUCTION_DEPLOYMENT.md`.
