# Step 14 Implementation Notes — Frontend Foundation v0.1.0

## Frozen backend baseline

Frontend targets backend **v0.11.2 STABLE** and its 48-path OpenAPI contract. No backend schema or API changes are required for Step 14.

## Decisions carried forward

- Sadhana and Academic results stay separate everywhere.
- No combined balance score is introduced.
- Four-week reporting means exactly four adjacent complete organization weeks.
- Partial lifecycle weeks remain excluded from official weekly scoring.
- Daily Card rendering is dynamic from `activities[]` and `values[]`; no activity-name branching is introduced.
- Missing values remain distinguishable from intentional zero/False through backend `is_filled` semantics.
- FastAPI remains the source of truth for authentication, RBAC, lifecycle, scoring and historical rules.

## Integration strategy

The frontend uses a Next.js Backend-for-Frontend (BFF):

1. Browser sends same-origin requests to Next.js.
2. Next.js forwards requests server-side to FastAPI.
3. FastAPI JWT is stored in an HttpOnly cookie by Next.js and never exposed to browser JavaScript.
4. Role layouts verify the current user server-side and redirect cross-role navigation.

This intentionally avoids adding CORS middleware to the frozen backend and prevents LocalStorage-token coupling.

## Scope of this checkpoint

This checkpoint establishes the frontend architecture and live read integration. Detailed Daily Card editing controls and Admin mutation workflows are the next frontend phase; the integration seam they will use is already implemented.
