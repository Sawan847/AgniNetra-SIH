# =============================================================================
# AgniNetra AI — Windows PowerShell Development Setup
# Run: .\scripts\setup_dev.ps1
# =============================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "`n===== AgniNetra AI — Development Setup =====" -ForegroundColor Cyan

# ---- Check prerequisites ----
Write-Host "`n[1/7] Checking prerequisites..." -ForegroundColor Yellow

$missing = @()
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { $missing += "Docker Desktop" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $missing += "Python 3.11+" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += "Node.js 18+" }

if ($missing.Count -gt 0) {
    Write-Host "Missing prerequisites: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Please install them and re-run this script." -ForegroundColor Red
    exit 1
}

Write-Host "  Docker:  $(docker --version)" -ForegroundColor Green
Write-Host "  Python:  $(python --version)" -ForegroundColor Green
Write-Host "  Node.js: $(node --version)" -ForegroundColor Green

# ---- Create .env from template ----
Write-Host "`n[2/7] Setting up environment..." -ForegroundColor Yellow

$envFile = Join-Path $ProjectRoot ".env"
$envExample = Join-Path $ProjectRoot ".env.example"

if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host "  Created .env from .env.example" -ForegroundColor Green
    Write-Host "  IMPORTANT: Edit .env and set secure passwords before production use." -ForegroundColor Yellow
} else {
    Write-Host "  .env already exists, skipping." -ForegroundColor Green
}

# ---- Start database ----
Write-Host "`n[3/7] Starting PostgreSQL/PostGIS..." -ForegroundColor Yellow

Push-Location $ProjectRoot
docker compose up -d db
Start-Sleep -Seconds 5

$retries = 0
while ($retries -lt 15) {
    $health = docker inspect --format='{{.State.Health.Status}}' agnietra-db 2>$null
    if ($health -eq "healthy") { break }
    Write-Host "  Waiting for database to be healthy... ($retries)" -ForegroundColor Gray
    Start-Sleep -Seconds 2
    $retries++
}

if ($health -ne "healthy") {
    Write-Host "  Database failed to start. Check 'docker compose logs db'." -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "  Database is healthy." -ForegroundColor Green

# ---- Backend setup ----
Write-Host "`n[4/7] Setting up backend..." -ForegroundColor Yellow

$backendDir = Join-Path $ProjectRoot "backend"
$venvDir = Join-Path $backendDir ".venv"

if (-not (Test-Path $venvDir)) {
    python -m venv $venvDir
    Write-Host "  Created virtual environment." -ForegroundColor Green
}

& "$venvDir\Scripts\Activate.ps1"
pip install -r (Join-Path $backendDir "requirements.txt") --quiet
Write-Host "  Python dependencies installed." -ForegroundColor Green

# ---- Run Alembic migrations ----
Write-Host "`n[5/7] Running database migrations..." -ForegroundColor Yellow

Push-Location $backendDir
alembic upgrade head
Pop-Location
Write-Host "  Migrations applied." -ForegroundColor Green

# ---- Frontend setup ----
Write-Host "`n[6/7] Setting up frontend..." -ForegroundColor Yellow

$frontendDir = Join-Path $ProjectRoot "frontend"
Push-Location $frontendDir
npm install
Pop-Location
Write-Host "  Node dependencies installed." -ForegroundColor Green

# ---- Summary ----
Write-Host "`n[7/7] Setup complete!" -ForegroundColor Yellow
Pop-Location

Write-Host "`n===== Quick Start Commands =====" -ForegroundColor Cyan
Write-Host "  Start all:      docker compose up" -ForegroundColor White
Write-Host "  Start DB only:  docker compose up -d db" -ForegroundColor White
Write-Host "  Backend dev:    cd backend && ..\.venv\Scripts\Activate.ps1 && uvicorn app.main:app --reload" -ForegroundColor White
Write-Host "  Frontend dev:   cd frontend && npm run dev" -ForegroundColor White
Write-Host "  Backend tests:  cd backend && pytest ../tests/backend/ -v" -ForegroundColor White
Write-Host "  Frontend tests: cd frontend && npx vitest run" -ForegroundColor White
Write-Host ""
