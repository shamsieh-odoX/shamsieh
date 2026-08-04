# ZKTeco Attendance Bridge

Local poller for ZKTeco terminals (TCP/UDP port **4370**) when Odoo runs in the
cloud (Odoo.sh) and cannot open a socket to a private LAN IP.

## Setup

1. In Odoo → **Attendances → Configuration → Fingerprint Devices**, create a device:
   - **Name**: e.g. `ZKTeco Branch Device`
   - **API Type**: ZKTeco
   - **Office / Branch Label**: e.g. second office name
   - **Company**: `SHAMSIEH TECHNOLOGY SERVICES CO` (same company as Hikvision; employees are shared)
   - **Device IP / Port**: `192.178.1.40` / `4370`
   - **Password / Comm Key**: device communication password (usually `0`)
   - **Device Timezone**: `Asia/Amman`
   - **Auto Sync**: off on Odoo.sh (bridge pushes instead)
2. Note the device database **ID**.
3. On a PC on the same LAN as the terminal:

```bash
cd scripts/zkteco_attendance_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env
python -m app.main
```

Employee mapping uses the same fields as Hikvision (`biometric_device_user_id`,
`barcode` / Badge ID, `pin`, etc.). Set each employee’s device user ID to match
the ZKTeco user number.
