# ZKTeco Attendance Bridge (ADMS push — like Hikvision)

Runs on a PC on the same LAN as the ZKTeco terminal. The device pushes punches
over **HTTP** to `/iclock/...`; this bridge forwards them into Odoo (Odoo.sh).

Do **not** use Odoo **Sync Now** / **Test Connection** for ZKTeco on the cloud
(those need `pyzk` + direct LAN access, which Odoo.sh does not have).

## Setup

1. In Odoo → **Attendances → Configuration → Fingerprint Devices** (ZKTeco device):
   - **API Type**: ZKTeco
   - **ADMS / Cloud Push**: on
   - **ZKTeco Serial Number (SN)**: from the terminal (e.g. `SRN5244400238`)
   - **Auto Sync**: off
2. On a PC that can reach the terminal:

```bash
cd scripts/zkteco_attendance_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env (API key, device id, serial)
python -m app.main
```

3. On the ZKTeco device (or Attendance Management → Cloud / ADMS settings):
   - Server URL: `http://<PC-LAN-IP>:8088/iclock/`
   - Serial must match the Odoo field

4. Punch once — Odoo should show a new sync log / attendance within seconds.
   **Last ADMS Push** on the device form updates when the terminal talks to the bridge.

Employee mapping uses the same fields as Hikvision (`biometric_device_user_id`,
Badge ID, PIN, etc.).

## Note on HTTPS

Many ZK terminals only speak **HTTP** ADMS. Point them at this local bridge, not
directly at `https://….odoo.com/iclock/` unless your model supports HTTPS cloud.
