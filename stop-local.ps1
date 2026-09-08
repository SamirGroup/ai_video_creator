# Stops the isolated local PostgreSQL (5433) and Redis (6380) started by
# start-local.ps1. The Django/Vite dev servers run in their own visible
# PowerShell windows — just close those windows (or Ctrl+C in them).

$env:PATH = "$env:USERPROFILE\scoop\apps\postgresql\current\bin;$env:USERPROFILE\scoop\shims;$env:PATH"
$pgData = "$env:USERPROFILE\scoop\persist\postgresql\data"

Write-Host "Stopping PostgreSQL..." -ForegroundColor Cyan
pg_ctl -D $pgData stop -m fast

Write-Host "Stopping Redis..." -ForegroundColor Cyan
redis-cli -p 6380 shutdown nosave 2>$null

Write-Host "Done." -ForegroundColor Green
