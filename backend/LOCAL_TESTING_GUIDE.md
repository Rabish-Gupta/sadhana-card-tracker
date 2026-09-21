# Local Testing Guide — Sadhana Card Tracker Backend

This checkpoint validates the database foundation before authentication or daily-card APIs are added.

## Recommended route: Windows + native PostgreSQL (no Docker)

### 1. Install prerequisites

Install:

- Python 3.11 or newer
- PostgreSQL 16 (or compatible newer release)
- pgAdmin 4 and PostgreSQL command-line tools

During PostgreSQL installation, remember the password for the `postgres` user. The examples below use `postgres` as that password. If you choose a different password, put that password in `.env` instead.

Keep the default PostgreSQL port `5432` unless it is already in use.

### 2. Extract the project

Extract the backend ZIP to a simple path, for example:

`C:\Projects\sadhana-card-tracker-backend`

Open **PowerShell** in that exact folder. A simple way is to open the folder in File Explorer, click the address bar, type `powershell`, and press Enter.

Verify that the current folder contains:

- `pyproject.toml`
- `alembic.ini`
- `app`
- `migrations`
- `tests`

Run:

```powershell
Get-Location
Get-ChildItem
```

### 3. Create the Python virtual environment

In the backend folder:

```powershell
py -3.11 -m venv .venv
```

If `py -3.11` is unavailable, use:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks the script for this terminal session, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Confirm:

```powershell
python --version
```

### 4. Install the backend and test dependencies

Still in the backend folder:

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### 5. Create `.env`

In the backend folder:

```powershell
Copy-Item .env.example .env
```

Open `.env` in Notepad:

```powershell
notepad .env
```

For a PostgreSQL user named `postgres`, password `postgres`, database `sadhana_tracker`, and port `5432`, use:

```env
APP_NAME=Sadhana Card Tracker API
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sadhana_tracker
SQL_ECHO=false
```

If your PostgreSQL password is different, replace the second `postgres` with your actual password.

### 6. Create the PostgreSQL database

#### Easiest: pgAdmin 4

Open pgAdmin 4.

1. Connect to your local PostgreSQL server.
2. Expand `Servers` → your PostgreSQL server.
3. Right-click `Databases`.
4. Choose `Create` → `Database...`.
5. Database name: `sadhana_tracker`.
6. Owner: `postgres`.
7. Save.

Do not manually create any project tables.

### 7. Run code-only tests first

Back in PowerShell, inside the backend folder with `.venv` active:

```powershell
pytest -q
```

Expected for the current Step 11 checkpoint:

```text
98 passed
```

Then:

```powershell
python -m compileall -q app migrations scripts
```

No output/error means success.

Generate PostgreSQL migration SQL without changing the database:

```powershell
alembic upgrade head --sql > migration_preview.sql
```

This creates `migration_preview.sql` for inspection.

### 8. Run the real PostgreSQL migration

```powershell
alembic upgrade head
```

Expected final Alembic revision:

```powershell
alembic current
```

It should show:

`0003_lifecycle_fields (head)`

### 9. Inspect the database in pgAdmin

In pgAdmin, refresh:

`Databases` → `sadhana_tracker` → `Schemas` → `public` → `Tables`

You should see the 19 application tables plus `alembic_version`.

Important examples:

- `organizations`
- `organization_setting_versions`
- `users`
- `devotee_categories`
- `activities`
- `category_activity_configs`
- `daily_cards`
- `weekly_evaluations`
- `audit_logs`

Open `Tools` → `Query Tool` for the `sadhana_tracker` database and run:

```sql
SELECT version_num FROM alembic_version;

SELECT extname
FROM pg_extension
WHERE extname IN ('citext', 'pgcrypto')
ORDER BY extname;
```

The migration revision should be `0003_lifecycle_fields`; both extensions should be returned.

### 10. Seed the baseline configuration

Authentication is implemented. For this disposable development database, bootstrap or reuse the Admin with a plaintext command-line password that the seeder immediately Argon2-hashes before storage:

```powershell
python -m app.db.seed --admin-email admin@sadhanatracker.com --admin-full-name "Test Admin" --admin-phone "+910000000000" --admin-password "AdminTest123!"
```

Use a stronger secret and secure secret-management practices outside local development.

### 11. Verify the seed

In pgAdmin Query Tool:

```sql
SELECT COUNT(*) AS categories FROM devotee_categories;
SELECT COUNT(*) AS activities FROM activities;
SELECT COUNT(*) AS activity_fields FROM activity_fields;
SELECT COUNT(*) AS scoring_rules FROM scoring_rules;
SELECT COUNT(*) AS scoring_rule_versions FROM scoring_rule_versions;
SELECT COUNT(*) AS standards FROM standards;
SELECT COUNT(*) AS standard_versions FROM standard_versions;
SELECT COUNT(*) AS category_configs FROM category_activity_configs;
```

Expected baseline counts:

- devotee categories: 6
- activities: 12
- activity fields: 12
- scoring rules: 11
- scoring rule versions: 11
- standards: 11
- standard versions: 11
- category activity configurations: 72

Verify every initial devotee category has 12 activity configurations:

```sql
SELECT dc.code, COUNT(cac.id) AS config_count
FROM devotee_categories dc
LEFT JOIN category_activity_configs cac ON cac.category_id = dc.id
GROUP BY dc.code
ORDER BY dc.code;
```

Every row should show `12`.

### 12. Test seed idempotency

Run the exact same seed command a second time:

```powershell
python -m app.db.seed --admin-email admin@sadhanatracker.com --admin-full-name "Test Admin" --admin-phone "+910000000000" --admin-password "AdminTest123!"
```

Then repeat the count queries. They must remain exactly the same. No duplicates should be created.

### 13. Inspect important seeded rules

Chanting:

```sql
SELECT sr.name, srv.max_score, srv.configuration
FROM scoring_rules sr
JOIN scoring_rule_versions srv ON srv.scoring_rule_id = sr.id
JOIN activities a ON a.id = sr.activity_id
WHERE a.code = 'CHANTING';
```

Day Rest:

```sql
SELECT srv.configuration
FROM scoring_rules sr
JOIN scoring_rule_versions srv ON srv.scoring_rule_id = sr.id
JOIN activities a ON a.id = sr.activity_id
WHERE a.code = 'DAY_REST';
```

The Day Rest configuration must show that exactly `45` minutes falls in the `<= 45` band worth `50` marks.

### 14. Run the FastAPI health endpoint

In PowerShell:

```powershell
uvicorn app.main:app --reload
```

Keep that terminal open.

Open a browser and visit:

`http://127.0.0.1:8000/health`

Expected:

```json
{"status":"ok"}
```

FastAPI docs are available at:

`http://127.0.0.1:8000/docs`

At this stage the docs include authentication, Admin configuration, and devotee Daily Card endpoints.

Stop the server with `Ctrl+C`.

### 15. Test migration rollback on this disposable database

Only do this before you put meaningful development data into the database.

```powershell
alembic downgrade base
```

Refresh `public` → `Tables` in pgAdmin. The application tables should be gone. Database-wide extensions may remain intentionally.

Recreate the schema:

```powershell
alembic upgrade head
```

Seed it again:

```powershell
python -m app.db.seed --admin-email admin@sadhanatracker.com --admin-full-name "Test Admin" --admin-phone "+910000000000" --admin-password "AdminTest123!"
```

If migration → seed → duplicate seed → downgrade → upgrade → seed all succeed, the database foundation has passed the checkpoint.

## Common errors

### `password authentication failed for user "postgres"`

The password in `.env` does not match the password selected during PostgreSQL installation. Correct `DATABASE_URL`.

### `database "sadhana_tracker" does not exist`

Create the database in pgAdmin first.

### `connection refused` / `[WinError 10061]`

The PostgreSQL Windows service is not running. Open Windows Services and start the service named similar to `postgresql-x64-16`.

### port `5432` already in use

You may already have PostgreSQL running, which is fine, or another program owns the port. Use the installed PostgreSQL server or configure another port and update `.env` accordingly.

### `alembic` is not recognized

Activate `.venv` and run `pip install -e ".[dev]"` again. You can also use:

```powershell
python -m alembic upgrade head
```

### PowerShell refuses to activate `.venv`

Use the temporary process-only command shown in Step 3. It does not permanently change the machine's execution policy.

## Checkpoint pass criteria

Do not begin the next feature phase until all of these pass:

- `pytest -q` → 88 passed
- Python compilation → no errors
- PostgreSQL database connection works
- `alembic upgrade head` succeeds
- revision is `0002_org_setting_versions`
- expected tables/extensions exist
- baseline seed succeeds
- second seed creates no duplicates
- seeded rules/standards match the approved specification
- `/health` returns HTTP 200 with `{"status":"ok"}`
- disposable downgrade and re-upgrade succeed


## Windows timezone data

The project depends on Python's IANA timezone database for organization-local calculations such as `Asia/Kolkata`. The runtime dependency `tzdata` is included in `pyproject.toml`, so a normal `pip install -e ".[dev]"` installs it automatically. If an older environment was created before v0.3.2, run `python -m pip install tzdata` once and rerun the tests.

## v0.4.2 password-seed safety

Use `--admin-password`, not a copied hash:

```powershell
python -m app.db.seed --admin-email admin@sadhanatracker.com --admin-full-name "Test Admin" --admin-phone "+910000000000" --admin-password "AdminTest123!"
```

The plaintext value exists only in the local process/command invocation; PostgreSQL receives only the generated Argon2 hash. To repair an older placeholder hash, add `--reset-admin-password`.
