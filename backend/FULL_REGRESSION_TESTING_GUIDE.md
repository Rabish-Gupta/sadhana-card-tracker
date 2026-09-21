# Full Backend Regression Test — v0.11.2

Use this checkpoint instead of running individual smoke tests one-by-one.

## 1. Install and verify the package

```powershell
pip install -e ".[dev]"
pytest -q
python -m compileall -q app migrations scripts
alembic current
```

Expected unit/regression suite: `144 passed`.
Expected DB revision: `0003_lifecycle_fields (head)`.

## 2. Start the API

```powershell
uvicorn app.main:app --reload
```

Keep this terminal open.

## 3. Run the complete real-PostgreSQL regression suite

In a second terminal, from the same project directory:

```powershell
python scripts/full_backend_smoke_suite.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!"
```

This executes the authentication, configuration, Daily Card, deterministic scoring,
weekly evaluation, lifecycle scheduler, historical correction, and four-week monthly
report smoke tests in sequence. Each test uses disposable accounts/data and cleanup.

The Daily Card and scoring smoke tests perform same-day updates. If you run after the
organization's configured daily deadline, use:

```powershell
python scripts/full_backend_smoke_suite.py `
  --admin-email admin@sadhanatracker.com `
  --admin-password "AdminTest123!" `
  --skip-time-sensitive
```

The final expected line is:

```text
ALL SELECTED BACKEND SMOKE TESTS PASSED
```

## Decimal JSON contract

Precise `Decimal` values such as percentages and raw duration totals are serialized as
JSON strings by Pydantic, consistent with the existing Weekly/Daily APIs. Client code
should parse them as decimal/number values when it needs arithmetic.
