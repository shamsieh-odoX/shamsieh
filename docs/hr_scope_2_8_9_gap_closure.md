# HR Scope §2, §8, §9 — Gap Closure Notes

## Remote face attendance (§9)

| Item | Status |
|------|--------|
| Remote face provider | **Implemented** using self-hosted **InsightFace** |
| Enrollment | HR wizard stores **embedding vectors** in `hr.employee.face.template` |
| Verification API | JSON-RPC `POST /hr_attendance_custom/face/check` with `selfie_image_base64` |
| Raw image storage | **Disabled by default** (`face_store_raw_images=False`) |
| Geo enforcement | **Implemented** when company `face_allowed_latitude`, `face_allowed_longitude`, and `face_geo_radius_meters` are configured |
| Real liveness / anti-spoof | **Future enhancement** — basic quality + single-face checks only |
| Mobile / web camera UI | **Frontend integration still needed** — API accepts base64 selfie via JSON-RPC |
| Development stub | `face_attendance_stub_enabled` — off by default; enable only for local testing |

## Optional Python dependencies

Install on the Odoo server venv:

```bash
pip install -r extra_addons/hr_attendance_custom_ext/requirements-face.txt
```

Packages: `insightface`, `onnxruntime`, `opencv-python-headless`, `numpy`, `pillow`.

InsightFace downloads models on **first use** to `~/.insightface/models` (not at Odoo startup).

## Production checklist

1. Install optional face dependencies on the server.
2. Settings → disable **Face Attendance Stub**.
3. Set match threshold (default `0.85`), geo reference point, and radius if required.
4. HR enrolls each employee via **Enroll Face Template**.
5. Enable **Remote Face Attendance Allowed** on each employee.
6. Mobile/web client captures selfie and calls JSON-RPC with authenticated Odoo user session.

## Fingerprint attendance (§8)

Hikvision ISAPI pull sync and HTTP Listening push are implemented in `hr_attendance_custom_ext`.

## Attendance calculations (§2)

Calendar-based late/early, daily status, and reports are implemented. Payroll, overtime, and leave integrations are out of scope.
