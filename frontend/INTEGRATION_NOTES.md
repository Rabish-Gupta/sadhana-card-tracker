# Integration Notes — v0.4.0

## Contract baseline

Frontend v0.4.0 is tied to backend v0.11.2. `contracts/backend-openapi.json` contains all 48 FastAPI paths and is canonically identical to the backend OpenAPI generated from the release package.

Use two checks:

```powershell
npm run contract
npm run contract:live -- --backend-url http://127.0.0.1:8000
```

The first checks the frozen snapshot invariants; the second verifies the actually running backend has not drifted.

## BFF boundary

Browser requests go only to Next.js `/api/*`. FastAPI JWTs are stored in an HttpOnly cookie. The generic BFF proxy intentionally blocks `auth/login` and `auth/logout` so browser code cannot bypass the dedicated session endpoints.

BFF requests have a configurable timeout and return `x-request-id` for correlation. Mutation bodies are capped by `BFF_MAX_BODY_BYTES`.

## Error mapping

- FastAPI response errors are passed through with status/body.
- Backend connection failures become HTTP 502.
- Backend timeouts become HTTP 504.
- Browser API errors preserve the BFF request ID for diagnostics.

## Production cookies

When `NODE_ENV=production`, the auth cookie is `Secure`, HttpOnly, SameSite=Lax and high priority. Public production deployment therefore requires HTTPS.

## No duplicated domain logic

Scoring, weekly aggregation, lifecycle transitions, historical corrections and four-week report semantics remain backend-authoritative. The frontend renders contracts and submits user/Admin intent; it does not independently recompute those rules.
