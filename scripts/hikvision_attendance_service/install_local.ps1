# Install Hikvision bridge to AppData and register Windows auto-start.
$ErrorActionPreference = "Stop"

$source = $PSScriptRoot
$target = Join-Path $env:LOCALAPPDATA "HikvisionAttendanceBridge"
$taskName = "HikvisionAttendanceBridge"

Write-Host "Installing to $target"

New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source "app") -Destination (Join-Path $target "app") -Recurse -Force
Copy-Item -Path (Join-Path $source "requirements.txt") -Destination (Join-Path $target "requirements.txt") -Force
Copy-Item -Path (Join-Path $source ".env") -Destination (Join-Path $target ".env") -Force -ErrorAction SilentlyContinue
if (Test-Path (Join-Path $source "hikvision_bridge.db")) {
    Copy-Item -Path (Join-Path $source "hikvision_bridge.db") -Destination (Join-Path $target "hikvision_bridge.db") -Force
}

@'
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8080
'@ | Set-Content -Path (Join-Path $target "run.ps1") -Encoding UTF8

Set-Location $target
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    .\.venv\Scripts\pip.exe install -r requirements.txt
}

$runScript = Join-Path $target "run.ps1"
$powershell = (Get-Command powershell.exe).Source
$action = New-ScheduledTaskAction -Execute $powershell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Installed and registered task: $taskName"
Write-Host "Starting service now..."
Start-ScheduledTask -TaskName $taskName
Write-Host "Done. Bridge runs from: $target"
