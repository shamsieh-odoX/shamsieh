# ZKTeco → Odoo real-time punch API

No Sync Now. The bridge keeps a live connection to the F28 and POSTs each punch
immediately to Odoo:

`POST /zkteco/punch/<token>`  
JSON: `{ "device_user_id": "2", "punch_type": "check_in", "event_time": "..." }`

Allowed `punch_type`: `check_in`, `check_out`, `break_out`, `break_in`.

## Setup

1. Upgrade `hr_attendance_custom_ext` on Odoo.sh.
2. Open the ZKTeco device → copy **Punch API URL**.
3. Put it in `.env` as `ZKTECO_PUNCH_URL=...`
4. **Disconnect Attendance Management**.
5. Run:

```powershell
cd scripts\zkteco_attendance_service
.\.venv\Scripts\activate
python -m app.main
```

Or use `start_zkteco_poll.bat` (same entrypoint; now live mode).
Windows Startup shortcut still works.

## Hikvision

Unchanged.
