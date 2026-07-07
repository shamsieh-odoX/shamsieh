$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found. Run: python -m venv .venv"
    exit 1
}

if (-not (Test-Path ".\.env")) {
    Write-Host ".env file not found. Copy .env.example to .env and configure Odoo.sh credentials."
    exit 1
}

& .\.venv\Scripts\Activate.ps1
Write-Host "Starting Hikvision Attendance Bridge on http://0.0.0.0:8080"
uvicorn app.main:app --host 0.0.0.0 --port 8080
