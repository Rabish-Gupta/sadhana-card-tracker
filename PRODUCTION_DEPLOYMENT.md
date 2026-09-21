# Production Deployment Guide

## Security model

The public browser should access only the Next.js application. Next.js talks to FastAPI server-to-server using `BACKEND_BASE_URL`. The FastAPI JWT remains in an HttpOnly, SameSite=Lax cookie managed by Next.js.

The frontend adds security headers, request timeouts, body-size limits, request correlation IDs, a deployment readiness endpoint, and a runtime version endpoint.

For public deployment, terminate **HTTPS** in a trusted reverse proxy/platform in front of port 3000. Do not expose PostgreSQL publicly.

## Docker Compose quick start

From the release root:

```powershell
Copy-Item .env.production.example .env.production
notepad .env.production
```

Replace at least:

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`

Generate a JWT secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use a URL-safe PostgreSQL password containing letters, numbers, `_`, and `-` because Compose interpolates it into `DATABASE_URL`.

Then:

```powershell
docker compose --env-file .env.production -f deploy/docker-compose.yml up --build -d
```

Check status:

```powershell
docker compose --env-file .env.production -f deploy/docker-compose.yml ps
```

Frontend readiness:

```powershell
Invoke-RestMethod http://localhost:3000/api/readiness
```

Expected `status` is `ready`.

Backend health is bound to localhost only by default:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Fresh database bootstrap

After the stack is healthy, create the first Admin and baseline configuration:

```powershell
.\scripts\bootstrap_admin.ps1 `
  -AdminEmail "admin@sadhanatracker.com" `
  -AdminFullName "Primary Admin" `
  -AdminPhone "+910000000000" `
  -AdminPassword "CHANGE_THIS_ADMIN_PASSWORD"
```

The backend seeder hashes the password with Argon2 before storage.

## Existing database

If deploying the existing verified database, take a PostgreSQL backup first. The `migrate` service runs `alembic upgrade head` before FastAPI starts. Current head is:

```text
0003_lifecycle_fields
```

No later migration is introduced by Step 17.

## Reverse proxy

Forward the public site to frontend port 3000. Preserve `X-Forwarded-Proto` and `X-Forwarded-For`. FastAPI is not intended to be browser-facing in this architecture.

Because the auth cookie is `Secure` in production, public production access must use HTTPS.

## Scheduler

The backend lifecycle scheduler is enabled by default. PostgreSQL advisory locking protects domain processing from duplicate execution when multiple API processes attempt the same lifecycle pass. For the MVP deployment, one backend container is the simplest topology.

## Backups

Before deployment changes and periodically in production, back up PostgreSQL. The application intentionally preserves historical records and audit data; do not replace archival behavior with hard deletion.
