param(
  [Parameter(Mandatory=$true)][string]$AdminEmail,
  [Parameter(Mandatory=$true)][string]$AdminPassword,
  [string]$FrontendUrl = "http://localhost:3000",
  [string]$BackendUrl = "http://127.0.0.1:8000"
)

Write-Host "=== LIVE BACKEND CONTRACT ===" -ForegroundColor Cyan
Push-Location frontend
npm run contract:live -- --backend-url $BackendUrl
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

Write-Host "=== FRONTEND FULL SMOKE ===" -ForegroundColor Cyan
npm run smoke:full -- --admin-email $AdminEmail --admin-password $AdminPassword --url $FrontendUrl
$front = $LASTEXITCODE
Pop-Location
if ($front -ne 0) { exit $front }

Write-Host "=== BACKEND FULL SMOKE ===" -ForegroundColor Cyan
Push-Location backend
python scripts/full_backend_smoke_suite.py --admin-email $AdminEmail --admin-password $AdminPassword
$back = $LASTEXITCODE
Pop-Location
if ($back -ne 0) { exit $back }

Write-Host "ALL STEP 17 FULL-STACK RELEASE SMOKE TESTS PASSED" -ForegroundColor Green
