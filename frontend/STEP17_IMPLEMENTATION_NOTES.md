# Step 17 — Final Integration, Production Hardening & UX Polish

## Baselines

- Backend: v0.11.2, unchanged domain/business logic
- Frontend: v0.4.0, based on verified v0.3.0 Admin/Devotee UI
- Database: 19 application tables + `alembic_version`
- Alembic head: `0003_lifecycle_fields`

## Integration hardening

1. Centralized BFF → FastAPI fetch helper with configurable timeout.
2. Correlation ID (`x-request-id`) generated/preserved across BFF responses.
3. Generic BFF mutation body-size limit.
4. Dedicated login/logout endpoints remain mandatory; generic proxy blocks those auth paths.
5. Runtime `/api/readiness` endpoint verifies FastAPI health.
6. Runtime `/api/version` exposes frontend and frozen backend-contract versions.
7. Live OpenAPI contract verification script compares the running FastAPI service with the frozen 48-path frontend snapshot.
8. Production Next.js standalone output and Docker deployment topology.
9. Security headers: nosniff, frame denial, same-origin referrer policy, restricted browser permissions, frame-ancestor/base/form CSP directives, and HSTS in production.
10. Secure HttpOnly auth cookie in production with high priority and SameSite=Lax.

## UX/accessibility hardening

- Active navigation state with `aria-current`.
- Keyboard skip-to-content link.
- Visible focus styles.
- Reduced-motion support.
- Global loading skeleton.
- Mutation feedback uses live regions for screen readers.
- User-facing 502/504 backend messages are differentiated.

## Deployment

The release includes Dockerfiles and Compose for PostgreSQL, one-shot Alembic migration, FastAPI, and Next.js. The FastAPI host port is bound to localhost by default; browser traffic is intended to enter through Next.js only.

## Business rules intentionally unchanged

No scoring, lifecycle, historical-correction, weekly, four-week reporting, or category-policy rule was changed in Step 17.
