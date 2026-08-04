# Installs ZKTeco poll into the current user's Windows Startup folder
# (no admin required). Runs at every logon.
#
#   powershell -ExecutionPolicy Bypass -File .\install_windows_startup.ps1

$ErrorActionPreference = 'Stop'
$ServiceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bat = Join-Path $ServiceDir 'start_zkteco_poll.bat'
$StartupDir = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDir 'ZKTeco Odoo Poll Bridge.lnk'

if (-not (Test-Path $Bat)) {
    throw "Missing start script: $Bat"
}

$Wsh = New-Object -ComObject WScript.Shell
$Shortcut = $Wsh.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Bat
$Shortcut.WorkingDirectory = $ServiceDir
$Shortcut.WindowStyle = 7  # minimized
$Shortcut.Description = 'Poll ZKTeco F28 and push attendance to Odoo'
$Shortcut.Save()

Write-Host "Startup shortcut created:"
Write-Host "  $ShortcutPath"
Write-Host ""
Write-Host "To start now (keep Attendance Management disconnected):"
Write-Host "  $Bat"
Write-Host "Logs: $ServiceDir\logs\zkteco_poll.log"
