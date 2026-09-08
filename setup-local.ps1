# One-time local setup (Windows, no Docker). Run once, then use start-local.ps1.
#
#   powershell -ExecutionPolicy Bypass -File setup-local.ps1
#
# What it does:
#   1. Installs Scoop (user-level, no admin) + postgresql, redis, ffmpeg if missing.
#   2. Initialises an isolated PostgreSQL cluster on port 5433 (does not touch a
#      system PostgreSQL on 5432) and creates the ai_youtuber role/database.
#      The role gets CREATEDB so pytest-django can create its test databases.
#   3. Creates backend/.venv (Python 3.14 or 3.11), installs requirements.
#   4. Runs migrations and seeds the dev superadmin (admin@admin.com / admin123).
#   5. Installs frontend npm dependencies.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$scoop = "$env:USERPROFILE\scoop"
$env:PATH = "$scoop\apps\postgresql\current\bin;$scoop\shims;$env:PATH"

if (-not (Test-Path "$scoop\shims\scoop.ps1")) {
    Write-Host "Installing Scoop..." -ForegroundColor Cyan
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
    Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
}
foreach ($pkg in @("postgresql", "redis", "ffmpeg")) {
    if (-not (Test-Path "$scoop\apps\$pkg")) {
        Write-Host "scoop install $pkg" -ForegroundColor Cyan
        scoop install $pkg
    }
}

$pgData = "$scoop\persist\postgresql\data"
$pgLog = "$scoop\persist\postgresql\pg.log"
$pgPort = 5433

if (-not (Test-Path "$pgData\PG_VERSION")) {
    Write-Host "Initialising PostgreSQL cluster at $pgData (port $pgPort)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Split-Path $pgData) | Out-Null
    $pwFile = "$env:TEMP\pg_superuser_pw.txt"
    Set-Content -Path $pwFile -Value "postgres" -Encoding ascii
    initdb -D $pgData -U postgres --pwfile=$pwFile -E UTF8 -A scram-sha-256 | Out-Null
    Remove-Item $pwFile -Force
    Add-Content -Path "$pgData\postgresql.conf" -Value "`nport = $pgPort`nlisten_addresses = 'localhost'`n"
}

$status = & pg_ctl -D $pgData status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Starting PostgreSQL..." -ForegroundColor Cyan
    pg_ctl -D $pgData -l $pgLog -o "-p $pgPort" start
    Start-Sleep -Seconds 4
}

$env:PGPASSWORD = "postgres"
$roleExists = & psql -h localhost -p $pgPort -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='ai_youtuber'"
if ($roleExists -ne "1") {
    Write-Host "Creating role ai_youtuber (CREATEDB for pytest)..." -ForegroundColor Cyan
    psql -h localhost -p $pgPort -U postgres -c "CREATE ROLE ai_youtuber LOGIN PASSWORD 'changeme' CREATEDB;"
}
$dbExists = & psql -h localhost -p $pgPort -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='ai_youtuber'"
if ($dbExists -ne "1") {
    psql -h localhost -p $pgPort -U postgres -c "CREATE DATABASE ai_youtuber OWNER ai_youtuber;"
}
Remove-Item Env:PGPASSWORD

Write-Host "Starting Redis (port 6380)..." -ForegroundColor Cyan
$pong = redis-cli -p 6380 ping 2>$null
if ($pong -ne "PONG") {
    Start-Process -FilePath "redis-server" -ArgumentList "--port 6380 --save `"`"" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

$venvPy = "$root\backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating backend venv..." -ForegroundColor Cyan
    $py = "py"
    & $py -3.14 -m venv "$root\backend\.venv"
    if ($LASTEXITCODE -ne 0) { & $py -3.11 -m venv "$root\backend\.venv" }
}
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r "$root\backend\requirements.txt"
if (Test-Path "$root\backend\requirements-dev.txt") { & $venvPy -m pip install --quiet -r "$root\backend\requirements-dev.txt" }

if (-not (Test-Path "$root\backend\.env")) {
    Copy-Item "$root\backend\.env.example" "$root\backend\.env"
    Write-Host "Created backend/.env from .env.example — edit secrets as needed." -ForegroundColor Yellow
}

Push-Location "$root\backend"
& $venvPy manage.py migrate
& $venvPy manage.py shell -c "from accounts.models import User, Role, UserRole; u,_=User.objects.get_or_create(email='admin@admin.com', defaults={'is_email_verified': True, 'is_staff': True, 'is_superuser': True}); u.set_password('admin123'); u.is_staff=True; u.is_superuser=True; u.save(); r,_=Role.objects.get_or_create(code='admin', defaults={'name':'Admin'}); UserRole.objects.get_or_create(user=u, role=r); print('superadmin ready')"
Pop-Location

if (Test-Path "$root\frontend\package.json") {
    Push-Location "$root\frontend"
    if (-not (Test-Path "node_modules")) { npm ci }
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete. Next: powershell -ExecutionPolicy Bypass -File start-local.ps1" -ForegroundColor Green
