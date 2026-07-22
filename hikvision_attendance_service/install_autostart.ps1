# Run this script once as Administrator to start the bridge automatically at Windows logon.
$ErrorActionPreference = "Stop"

$taskName = "HikvisionAttendanceBridge"
$scriptPath = Join-Path $PSScriptRoot "run.ps1"
$powershell = (Get-Command powershell.exe).Source

$action = New-ScheduledTaskAction -Execute $powershell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Installed scheduled task: $taskName"
Write-Host "The bridge will start automatically when you log in to Windows."
Write-Host "To remove: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
