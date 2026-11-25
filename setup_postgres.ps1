# AutismCare: switch the local project from SQLite to PostgreSQL (SRS 2.4).
# Asks for the "postgres" password, creates the database and its user,
# writes .env, then creates the tables and loads the demo data.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $psql) { Write-Host "Couldn't find psql.exe under C:\Program Files\PostgreSQL." -ForegroundColor Red; exit 1 }
Write-Host "Using $psql"

if (Test-Path .env) {
    $answer = Read-Host ".env already exists. Overwrite it? (y/N)"
    if ($answer -ne "y") { Write-Host "Stopped. Nothing changed."; exit 0 }
}

$secure = Read-Host "Password for the 'postgres' superuser" -AsSecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

function Invoke-Psql([string]$sql) {
    $out = & $psql -U postgres -h localhost -w -tAc $sql 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $out" }
    return ($out | Out-String).Trim()
}

try {
    Invoke-Psql "SELECT 1" | Out-Null
} catch {
    Write-Host "Couldn't log in as postgres. Check the password and try again." -ForegroundColor Red
    Remove-Item Env:PGPASSWORD; exit 1
}

# Random credentials for the app (letters and digits only, safe in SQL and .env)
$appPassword = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
$secretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 50 | ForEach-Object { [char]$_ })

if ((Invoke-Psql "SELECT 1 FROM pg_roles WHERE rolname='autismcare_user'") -eq "1") {
    Invoke-Psql "ALTER USER autismcare_user WITH PASSWORD '$appPassword' CREATEDB" | Out-Null
    Write-Host "Updated existing database user autismcare_user."
} else {
    Invoke-Psql "CREATE USER autismcare_user WITH PASSWORD '$appPassword' CREATEDB" | Out-Null
    Write-Host "Created database user autismcare_user."
}
if ((Invoke-Psql "SELECT 1 FROM pg_database WHERE datname='autismcare'") -eq "1") {
    Write-Host "Database autismcare already exists. Keeping it."
} else {
    Invoke-Psql "CREATE DATABASE autismcare OWNER autismcare_user" | Out-Null
    Write-Host "Created database autismcare."
}
Remove-Item Env:PGPASSWORD

# The Wi-Fi address lets a phone on the same network open the site (mobile testing).
$lan = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^(127|169\.254)' } | Select-Object -First 1).IPAddress
$hosts = "localhost,127.0.0.1" + $(if ($lan) { ",$lan" } else { "" })

@"
DJANGO_SECRET_KEY=$secretKey
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=$hosts

DB_NAME=autismcare
DB_USER=autismcare_user
DB_PASSWORD=$appPassword
DB_HOST=localhost
DB_PORT=5432
"@ | Set-Content -Encoding ascii .env
Write-Host "Wrote .env"

$py = ".\venv\Scripts\python.exe"
& $py manage.py migrate
& $py manage.py seed
& $py manage.py seed_questions
Write-Host ""
Write-Host "Done. AutismCare now uses PostgreSQL." -ForegroundColor Green
Write-Host "Next: create your admin account with:  .\venv\Scripts\python.exe manage.py createsuperuser"
