# Starts the whole AI YouTube Content Ecosystem stack locally, without Docker.
# Uses an isolated PostgreSQL (port 5433) and Redis (port 6380) installed via
# Scoop into this Windows user's profile — neither touches the machine's
# existing system PostgreSQL service (port 5432).
#
# First time on a machine: run setup-local.ps1 once (installs Scoop packages,
# initialises the cluster, creates the role/db, venv, migrations, superadmin).
#
# Usage: powershell -ExecutionPolicy Bypass -File start-local.ps1
# Stop everything: stop-local.ps1 (or just close the opened windows)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$env:PATH = "$env:USERPROFILE\scoop\apps\postgresql\current\bin;$env:USERPROFILE\scoop\shims;$env:PATH"

$pgData = "$env:USERPROFILE\scoop\persist\postgresql\data"
$pgLog = "$env:USERPROFILE\scoop\persist\postgresql\pg.log"

Write-Host "Starting PostgreSQL (port 5433)..." -ForegroundColor Cyan
$pgStatus = & pg_ctl -D $pgData status 2>&1
if ($LASTEXITCODE -ne 0) {
    pg_ctl -D $pgData -l $pgLog start
    Start-Sleep -Seconds 3
} else {
    Write-Host "  already running" -ForegroundColor DarkGray
}

Write-Host "Starting Redis (port 6380)..." -ForegroundColor Cyan
$redisRunning = redis-cli -p 6380 ping 2>$null
if ($redisRunning -ne "PONG") {
    Start-Process -FilePath "redis-server" -ArgumentList "--port 6380 --daemonize no --save `"`"" -WindowStyle Hidden `
        -RedirectStandardOutput "$env:USERPROFILE\scoop\persist\redis.log" `
        -RedirectStandardError "$env:USERPROFILE\scoop\persist\redis.err.log"
    Start-Sleep -Seconds 2
} else {
    Write-Host "  already running" -ForegroundColor DarkGray
}

Write-Host "Applying migrations..." -ForegroundColor Cyan
& "$root\backend\.venv\Scripts\python.exe" "$root\backend\manage.py" migrate --noinput | Select-Object -Last 3

Write-Host "Starting Django backend on :8000..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000"

Write-Host "Starting Celery worker (all queues) + beat..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python.exe -m celery -A config worker -Q q_script,q_voice,q_visual,q_render,q_upload,celery -l info --pool=solo"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python.exe -m celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler"

Write-Host "Starting React frontend on :5173..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev -- --host 0.0.0.0 --port 5173"

Write-Host ""
Write-Host "Done. Open http://localhost:5173 in your browser." -ForegroundColor Green
Write-Host "Superadmin login: admin@admin.com / admin123" -ForegroundColor Green
