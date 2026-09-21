# Sadhana Card Tracker — Step 17 Integrated Release v1.0.0

This release combines the verified backend **v0.11.2** with the production-hardened frontend **v0.4.0**.

## Preserved project rules

- Sadhana and Academic evaluation remain separate. There is no combined balance score.
- The system tracks practices and academics; it does not claim to measure spiritual advancement.
- Missing values remain distinct from intentional `0` and intentional `No`.
- Daily Cards are Update-only for devotees and become read-only after finalization.
- Historical calculations use the stored historical configuration/rule/standard versions.
- Partial lifecycle weeks are not officially scored or prorated.
- A monthly report means four adjacent complete organization weeks, not a calendar month.
- Sahadeva progression requires Admin review.
- Nakula → Arjuna and Arjuna → Yudhishthira promotion remains week-boundary based.
- Yudhishthira explicitly chooses the initial Bhima Working/Not Working state.
- Bhima Working ↔ Not Working changes take effect from the next week.
- Historical corrections require an Admin reason and preserve audit history.

## Local development

### 1. Backend

From `backend/`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Use your already-verified PostgreSQL `.env` when continuing from the existing project database.

### 2. Frontend

From `frontend/`:

```powershell
Copy-Item .env.example .env.local
npm install
npm run verify
npm run contract:live -- --backend-url http://127.0.0.1:8000
npm run dev
```

Open `http://localhost:3000`.

### 3. Consolidated integration smoke test

With backend and frontend running:

```powershell
cd frontend
npm run smoke:full -- `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

Expected final line:

```text
ALL FRONTEND STEP 14 + STEP 15 + STEP 16 + STEP 17 SMOKE TESTS PASSED
```

The complete backend regression remains available from `backend/scripts/full_backend_smoke_suite.py`.

## Production-like Docker deployment

See `PRODUCTION_DEPLOYMENT.md`. The Docker topology is:

```text
Browser
  ↓ HTTPS at your reverse proxy / hosting platform
Next.js frontend (port 3000)
  ↓ internal server-to-server HTTP
FastAPI backend (port 8000, bound to localhost on host)
  ↓
PostgreSQL
```

The browser never receives the FastAPI JWT. The Next.js BFF stores it in an HttpOnly cookie.
