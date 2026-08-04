# Optional: create a Scheduled Task (needs elevation / admin).
# Prefer install_windows_startup.ps1 (Startup folder) if Access Denied.
#
#   powershell -ExecutionPolicy Bypass -File .\install_scheduled_task.ps1

$ErrorActionPreference = 'Stop'
$ServiceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bat = Join-Path $ServiceDir 'start_zkteco_poll.bat'
$TaskName = 'ZKTecoOdooPollBridge'

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction -Execute $Bat -WorkingDirectory $ServiceDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description 'Poll ZKTeco F28 to Odoo' -Force | Out-Null
Write-Host "Task $TaskName registered."
