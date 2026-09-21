# Step 15 Implementation Notes — Devotee Frontend v0.2.0

## Integration boundary

The stable backend v0.11.2 remains the source of truth. The frontend uses the verified Step 14 BFF architecture:

`Browser → Next.js /api/* → FastAPI /api/v1/* → PostgreSQL`

No new backend route or schema was invented for Step 15.

## Dynamic Daily Card

The editor renders `DailyCardPublic.activities[]` and each activity's `values[]`. It selects the control from `input_type`, not from an activity name/code. This allows Admin-created/configured activities to remain compatible with the UI.

Only changed fields are PATCHed to `/cards/today`. The returned backend card replaces local state after every successful Update, so completion and deterministic daily scores are always backend-derived.

### Missing vs zero/false

- Clear to N/A → `is_filled=false` and no typed value.
- Numeric `0` → `is_filled=true`, `numeric_value=0`.
- Boolean No → `is_filled=true`, `boolean_value=false`.

This matches the backend validation contract exactly.

## Finalization

The frontend never offers a Submit/finalize action. It shows Update only while `DailyCardPublic.editable=true`. Auto-finalization remains a backend scheduler responsibility.

## Chanting

No Chanting-specific scoring/completion rule is duplicated in frontend code. Rounds and completion-time fields are rendered from backend field metadata; after Update the backend decides whether the activity is complete and how it scores. This prevents rule drift.

## Reports

Weekly and four-week screens consume persisted evaluation/report APIs. The browser does not recompute historical scores. Standards are displayed as analysis, not extra marks.

The four-week page explicitly states that the project monthly report is four adjacent complete organization weeks, even when the period crosses a calendar month boundary.

## Bhima lifecycle

The initial Yudhishthira Bhima choice is represented by `EmploymentStatus | null`. Neither Working nor Not Working is preselected when no prior/pending choice exists. This preserves the project's explicit-choice policy.

Yudhishthira can make or revise the choice before the promotion boundary; the backend determines the effective week. Existing Bhima devotees can request Working ↔ Not Working changes; the backend enforces next-week activation.
