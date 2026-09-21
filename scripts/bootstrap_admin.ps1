param(
  [Parameter(Mandatory=$true)][string]$AdminEmail,
  [Parameter(Mandatory=$true)][string]$AdminFullName,
  [Parameter(Mandatory=$true)][string]$AdminPhone,
  [Parameter(Mandatory=$true)][string]$AdminPassword,
  [switch]$ResetPassword
)

$compose = @("compose", "--env-file", ".env.production", "-f", "deploy/docker-compose.yml")
$args = @(
  "exec", "backend", "python", "-m", "app.db.seed",
  "--admin-email", $AdminEmail,
  "--admin-full-name", $AdminFullName,
  "--admin-phone", $AdminPhone,
  "--admin-password", $AdminPassword
)
if ($ResetPassword) { $args += "--reset-admin-password" }

& docker @compose @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
