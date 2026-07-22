# Hikvision -> Odoo Attendance Bridge (Local, No Docker)

Small FastAPI service that receives Hikvision attendance push events and creates `hr.attendance` check-ins in Odoo through XML-RPC.

## What it does

- POST `/hikvision/attendance` accepts Hikvision event push payloads (`multipart/*` with XML part, or plain XML body).
- Parses:
  - `employeeNoString`
  - `dateTime`
  - `eventType` / `subEventType`
- Processes only successful fingerprint/biometric verification events.
- Looks up `hr.employee` where `barcode == employeeNoString`.
- If employee not found: logs and returns `200` (so device does not retry forever).
- Prevents duplicate attendance creation per local day (employee/company timezone aware).
- Adds idempotency with local SQLite key `(device_serial, event_id)`.
- Adds retry queue in SQLite for transient Odoo failures; worker retries every 30 seconds.

## Files

- `app/main.py` FastAPI app and retry worker
- `app/hikvision_parser.py` multipart/XML parser + filter logic
- `app/odoo_client.py` XML-RPC calls
- `app/db.py` SQLite idempotency + retry queue
- `.env.example` required environment variables

## Run locally (Windows / PowerShell)

```powershell
cd C:\Users\ASUS\Desktop\odoo\scripts\hikvision_attendance_service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your real Odoo connection values.

Start service:

```powershell
$env:ODOO_URL="https://your-odoo-domain.com"
$env:ODOO_DB="your_db"
$env:ODOO_BOT_USER="bot@example.com"
$env:ODOO_API_KEY="your_api_key"
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

## Verify Odoo connection independently

Once server is running:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/odoo/ping
```

Expected response shape:

```json
{"status":"ok","odoo":{"version":"19.0+e","installed_modules":123}}
```

## Test webhook with sample Hikvision XML

Create `sample-event.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<EventNotificationAlert version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ipAddress>192.168.100.85</ipAddress>
  <portNo>80</portNo>
  <protocol>HTTP</protocol>
  <macAddress>ec:17:2f:aa:bb:cc</macAddress>
  <channelID>1</channelID>
  <dateTime>2026-07-07T09:22:11+03:00</dateTime>
  <activePostCount>1</activePostCount>
  <eventType>AccessControllerEvent</eventType>
  <eventState>active</eventState>
  <eventDescription>fingerprint authentication succeeded</eventDescription>
  <employeeNoString>10023</employeeNoString>
  <serialNo>1245789901</serialNo>
  <subEventType>verifyFingerprint</subEventType>
  <currentVerifyMode>fingerprint</currentVerifyMode>
  <status>success</status>
</EventNotificationAlert>
```

Send it:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8080/hikvision/attendance `
  -Method Post `
  -ContentType "application/xml" `
  -InFile .\sample-event.xml
```

You should get one of:
- `{"status":"ok","result":"created"}`
- `{"status":"ok","result":"duplicate-attendance"}`
- `{"status":"ok","result":"employee-not-found"}`
- `{"status":"queued","reason":"odoo-unavailable"}`

## Point Hikvision device to webhook

In the Hikvision terminal web UI, set event push URL to:

`http://<this-machine-ip>:8080/hikvision/attendance`

Use your LAN IP (not `127.0.0.1`) so the device at `192.168.100.85` can reach it.
