# ZKTeco → Odoo poll bridge (F28)

Your F28 talks on port **4370** (same as Attendance Management). This service
downloads punches every 30 seconds and sends them to Odoo.

**Close / Disconnect Attendance Management** while the bridge runs — only one
program can use the device at a time.

## One-time setup

```powershell
cd C:\Users\ASUS\Desktop\odoo\scripts\zkteco_attendance_service
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
# .env already configured for this office
powershell -ExecutionPolicy Bypass -File .\install_windows_startup.ps1
Start-ScheduledTask -TaskName ZKTecoOdooPollBridge
```

## Manual start

```powershell
.\start_zkteco_poll.bat
```

## Logs

`logs\zkteco_poll.log`

Task Scheduler task: run `install_scheduled_task.ps1` as admin (optional).

Default install uses the **Startup folder** shortcut (no admin):
`install_windows_startup.ps1`

## Hikvision

Unchanged — separate service under `scripts/hikvision_attendance_service`.
