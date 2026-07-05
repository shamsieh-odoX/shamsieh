# Shamsieh Technology Services Co.
# Odoo HR Module — Customization Scope by Table
# نطاق التخصيص حسب الجدول — وحدة الموارد البشرية في أودو

**Scope covered:** §2 Attendance Management / إدارة الدوام والحضور · §3 Fingerprint Device Integration / ربط جهاز البصمة · §4 Remote Face Attendance / بصمة الوجه للموظفين عن بُعد

**Verified against:** Odoo 19 standard codebase (`addons/hr`, `addons/hr_attendance`, `addons/resource`) and live database **`mydb_shamsieh`** (`ir_module_module`, `ir_model_fields`, `ir_model`).

**تم التحقق من:** كود أودو 19 القياسي وقاعدة البيانات الفعلية `mydb_shamsieh`.

> **Important finding:** `hr_attendance` is **not installed** on `mydb_shamsieh`. The `hr.attendance` model, its fields, views, crons, and security records are absent from the live DB until that standard module is installed. All attendance customizations below assume `hr_attendance` will be installed first.

**Proposed custom module (not yet in codebase):** `hr_attendance_custom_ext` — following the `extra_addons` convention used by `crm_custom_ext` and `project_custom_ext`.

**Total customization items:** 78

---

## 1. Installed Related Modules / الوحدات ذات الصلة

| Module | Type | State on `mydb_shamsieh` | Notes |
| ------ | ---- | ------------------------ | ----- |
| `hr` | Standard Odoo | **Installed** | Base Employees module |
| `hr_attendance` | Standard Odoo | **Not installed** | Required prerequisite — provides `hr.attendance`, kiosk, systray, crons |
| `resource` | Standard Odoo | **Installed** | Working calendars (`resource.calendar`) |
| `hr_presence` | Standard Odoo | Not installed | Optional — presence from login/attendance |
| Biometric / fingerprint module | — | **None** | No standard or custom module found |
| Face attendance module | — | **None** | No standard or custom module found |
| Custom HR module | — | **None** | `extra_addons` contains only `crm_custom_ext`, `project_custom_ext` |

| # | English | العربية |
| - | ------- | ------- |
| 1 | Install standard `hr_attendance` before any custom HR attendance work. | تثبيت وحدة `hr_attendance` القياسية قبل أي تخصيص للحضور. |
| 2 | Create new custom module `hr_attendance_custom_ext` (depends: `hr`, `hr_attendance`, `resource`). | إنشاء موديل مخصص جديد `hr_attendance_custom_ext` (يعتمد على: hr، hr_attendance، resource). |
| 3 | No third-party biometric/face Odoo module exists in repo or DB — integration must be built custom. | لا يوجد موديل بصمة/وجه جاهز في المستودع أو قاعدة البيانات — الربط يجب بناؤه مخصصاً. |
| 4 | Fingerprint device brand/model/API: **Needs confirmation** (HR scope doc §19 assumptions). | نوع/موديل/API جهاز البصمة: **يحتاج تأكيد** (افتراضات وثيقة النطاق §19). |
| 5 | Face recognition provider (on-device vs cloud API): **Needs confirmation**. | مزود التعرف على الوجه (محلي أو سحابي): **يحتاج تأكيد**. |

---

## hr.attendance (existing table — add columns)

**Model:** `hr.attendance` — **Standard Odoo** (`hr_attendance` addon).  
**Live DB:** Model not registered (module uninstalled). Fields verified from Odoo 19 source code.

### Field Analysis / تحليل الحقول

| Field | Exists in Odoo 19? | Action |
| ----- | ------------------ | ------ |
| `employee_id` | Yes | **Existing column to reuse** |
| `check_in` | Yes | **Existing column to reuse** |
| `check_out` | Yes | **Existing column to reuse** |
| `worked_hours` | Yes (computed, stored) | **Existing column to reuse** |
| `source` | No | **New column** — unified attendance source |
| `attendance_status` | No | **New column** — present / late / early_leave / absent / incomplete |
| `late_minutes` | No | **New column** (computed, stored) |
| `early_checkout_minutes` | No | **New column** (computed, stored) |
| `missing_checkout` | No | **New column** (Boolean, computed) |
| `device_id` | No | **New column** (Many2one → `fingerprint.device`) |
| `device_user_id` | No | **New column** (Char — raw device user ID) |
| `external_log_id` | No | **New column** (Char — link to import log) |
| `geo_latitude` / `geo_longitude` | Partial | **Existing columns to reuse:** `in_latitude`/`in_longitude`, `out_latitude`/`out_longitude` |
| `face_verified` | No | **New column** (Boolean) |

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing column to reuse:** `employee_id` — links attendance to employee. | **حقل موجود — إعادة استخدام:** `employee_id` — يربط الحضور بالموظف. |
| 2 | **Existing column to reuse:** `check_in` — actual check-in timestamp. | **حقل موجود — إعادة استخدام:** `check_in` — وقت الحضور الفعلي. |
| 3 | **Existing column to reuse:** `check_out` — actual check-out timestamp. | **حقل موجود — إعادة استخدام:** `check_out` — وقت الانصراف الفعلي. |
| 4 | **Existing column to reuse:** `worked_hours` — computed from check_in/check_out minus lunch. | **حقل موجود — إعادة استخدام:** `worked_hours` — محسوب من الدخول/الخروج ناقص الاستراحة. |
| 5 | **New column:** `attendance_source` (Selection: `fingerprint`, `face`, `manual`, `kiosk`, `systray`, `import`) — unified source per HR requirement; do not rely only on separate `in_mode`/`out_mode`. | **حقل جديد:** `attendance_source` (قائمة: بصمة، وجه، يدوي، كشك، شريط النظام، استيراد) — مصدر موحد حسب متطلبات الشركة. |
| 6 | **New column:** `attendance_status` (Selection: `present`, `late`, `early_leave`, `absent`, `incomplete`, `on_leave`) — daily status per §2.2. | **حقل جديد:** `attendance_status` — الحالة اليومية (حاضر، متأخر، انصراف مبكر، غائب، غير مكتمل، إجازة). |
| 7 | **New column:** `late_minutes` (Integer, computed, stored) — minutes after official 08:00 start. | **حقل جديد:** `late_minutes` — دقائق التأخير بعد 08:00. |
| 8 | **New column:** `early_checkout_minutes` (Integer, computed, stored) — minutes before official 16:00 end. | **حقل جديد:** `early_checkout_minutes` — دقائق الانصراف المبكر قبل 16:00. |
| 9 | **New column:** `missing_checkout` (Boolean, computed, stored) — True when `check_out` is empty past end-of-day tolerance. | **حقل جديد:** `missing_checkout` — صحيح عند غياب وقت الانصراف بعد نهاية اليوم. |
| 10 | **New column:** `device_id` (Many2one `fingerprint.device`) — which fingerprint terminal created the record. | **حقل جديد:** `device_id` — جهاز البصمة الذي أنشأ السجل. |
| 11 | **New column:** `device_user_id` (Char) — raw user ID from fingerprint device log. | **حقل جديد:** `device_user_id` — معرف المستخدم من جهاز البصمة. |
| 12 | **New column:** `external_log_id` (Char, indexed) — fingerprint or face log reference for duplicate prevention. | **حقل جديد:** `external_log_id` — مرجع السجل الخارجي لمنع التكرار. |
| 13 | **Existing columns to reuse for geolocation:** `in_latitude`/`in_longitude` (check-in), `out_latitude`/`out_longitude` (check-out). Do not add separate `geo_latitude`/`geo_longitude` unless explicitly required. | **حقول موجودة للموقع:** `in_latitude`/`in_longitude` و`out_latitude`/`out_longitude` — لا حاجة لحقول `geo_*` منفصلة إلا إذا طُلب ذلك صراحة. |
| 14 | **New column:** `face_verified` (Boolean) — True when attendance originated from successful face match. | **حقل جديد:** `face_verified` — صحيح عند نجاح مطابقة الوجه. |
| 15 | **Compute method:** `_compute_late_and_early_minutes()` — compare `check_in`/`check_out` (employee TZ) against `resource.calendar` expected start 08:00 and end 16:00. | **دالة حساب:** `_compute_late_and_early_minutes()` — مقارنة الأوقات بجدول الدوام 08:00–16:00. |
| 16 | **Compute method:** `_compute_attendance_status()` — derive status from lateness, absence, leave, missing checkout. | **دالة حساب:** `_compute_attendance_status()` — استنتاج الحالة اليومية. |
| 17 | **Compute method:** `_compute_missing_checkout()` — flag open records after scheduled end + tolerance. | **دالة حساب:** `_compute_missing_checkout()` — تحديد السجلات غير المكتملة. |
| 18 | **Constraint:** SQL unique on (`external_log_id`, `device_id`) where `external_log_id` is set — duplicate fingerprint/face log prevention. | **قيد:** فريد على (`external_log_id`, `device_id`) لمنع تكرار سجلات البصمة/الوجه. |
| 19 | **Constraint:** reuse standard `_check_validity` — no overlapping attendances, max one open check-in per employee. | **قيد:** إعادة استخدام `_check_validity` القياسي — منع التداخل وسجل مفتوح واحد. |
| 20 | **Server logic:** on create/write from fingerprint or face logs, set `attendance_source`, `device_id`, `external_log_id`, `face_verified` explicitly. | **منطق خادم:** عند الإنشاء من البصمة/الوجه، تعيين المصدر والجهاز والمرجع والتحقق من الوجه. |

---

## hr.employee (existing table — add columns)

**Model:** `hr.employee` — **Standard Odoo** (`hr` + `hr_attendance` extensions).  
**Live DB fields confirmed:** `barcode`, `pin`, `resource_calendar_id`. Attendance-specific fields absent because `hr_attendance` is uninstalled.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing column to reuse:** `barcode` — RFID/Badge ID for kiosk scanner (not fingerprint device user ID). | **حقل موجود:** `barcode` — رقم البطاقة/RFID للكشك وليس معرف جهاز البصمة. |
| 2 | **Existing column to reuse:** `pin` — kiosk PIN verification. | **حقل موجود:** `pin` — رمز PIN للكشك. |
| 3 | **Existing column to reuse:** `resource_calendar_id` (via `hr.version`) — employee working schedule; configure 08:00–16:00 here. | **حقل موجود:** `resource_calendar_id` — جدول الدوام؛ يُضبط 08:00–16:00 هنا. |
| 4 | **Existing column to reuse (after installing hr_attendance):** `attendance_manager_id`, `attendance_state`, `attendance_ids`. | **حقول موجودة بعد تثبيت hr_attendance:** `attendance_manager_id`, `attendance_state`, `attendance_ids`. |
| 5 | **New column:** `biometric_device_user_id` (Char, indexed) — maps employee to fingerprint device user ID. | **حقل جديد:** `biometric_device_user_id` — ربط الموظف بمعرف المستخدم في جهاز البصمة. |
| 6 | **New column:** `face_reference_id` (Char) — external face-enrollment reference/token ID (no raw image in Odoo if provider stores templates externally). | **حقل جديد:** `face_reference_id` — مرجع تسجيل الوجه الخارجي. |
| 7 | **New column:** `face_template_id` (Char or Binary attachment ref) — optional stored template ID; **Needs confirmation** whether templates stay on-device only. | **حقل جديد:** `face_template_id` — اختياري؛ **يحتاج تأكيد** إن كان القالب يبقى على الجهاز فقط. |
| 8 | **New column:** `attendance_required` (Boolean, default True) — employee must clock attendance daily. | **حقل جديد:** `attendance_required` — إلزامية تسجيل الحضور يومياً. |
| 9 | **New column:** `remote_attendance_allowed` (Boolean, default False) — allows face check-in/out for remote workers (§4). | **حقل جديد:** `remote_attendance_allowed` — السماح بالحضور بالوجه للموظفين عن بُعد. |
| 10 | **View customization:** add biometric mapping + face enrollment + remote flag fields on employee form (HR Officers group). | **تخصيص واجهة:** إضافة حقول الربط البيومتري والوجه وصلاحية الحضور عن بُعد في نموذج الموظف. |
| 11 | **Server logic:** validate `remote_attendance_allowed` before accepting face attendance API calls. | **منطق خادم:** التحقق من `remote_attendance_allowed` قبل قبول حضور الوجه. |

---

## resource.calendar + resource.calendar.attendance (existing tables — configure)

**Models:** **Standard Odoo** (`resource` addon). Used for official 08:00 AM – 04:00 PM schedule (HR scope §2.1).

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing table — configure:** company default `resource.calendar` with `resource.calendar.attendance` lines: Mon–Fri, `hour_from=8.0`, `hour_to=16.0`, `day_period=full_day`. | **جدول موجود — إعداد:** تقويم الشركة 08:00–16:00 أيام العمل حسب سياسة الشركة. |
| 2 | **Existing column to reuse:** `resource.calendar.attendance.hour_from` / `hour_to` — basis for late/early calculations. | **حقول موجودة:** `hour_from`/`hour_to` — أساس حساب التأخير والانصراف المبكر. |
| 3 | **Server logic:** late minutes = `check_in` (local TZ) minus calendar start; skip on public leave / employee time-off (**Needs confirmation** — `hr_holidays` not installed on `mydb_shamsieh`). | **منطق خادم:** حساب التأخير من جدول الدوام مع استثناء الإجازات (**يحتاج تأكيد** — hr_holidays غير مثبت). |
| 4 | **Seed data:** create Shamsieh standard 8h calendar and assign to all employees via `hr.version`. | **بيانات أولية:** إنشاء تقويم دوام شمسية القياسي وتعيينه للموظفين. |

---

## fingerprint.device (new table)

**Model:** `fingerprint.device` — **New custom model/table** (§3 Fingerprint Device Integration).

| # | English | العربية |
| - | ------- | ------- |
| 1 | **New model/table:** `fingerprint.device` — device configuration header. | **موديل/جدول جديد:** `fingerprint.device` — إعدادات جهاز البصمة. |
| 2 | **New column:** `name` (Char, required) — device label. | **حقل جديد:** `name` — اسم الجهاز. |
| 3 | **New column:** `company_id` (Many2one `res.company`, required). | **حقل جديد:** `company_id` — الشركة. |
| 4 | **New column:** `device_ip` (Char) — device IP/hostname. | **حقل جديد:** `device_ip` — عنوان IP. |
| 5 | **New column:** `device_port` (Integer) — connection port. | **حقل جديد:** `device_port` — منفذ الاتصال. |
| 6 | **New column:** `api_type` (Selection: `zkteco`, `hikvision`, `file_import`, `custom_api`) — **Needs confirmation** per installed hardware. | **حقل جديد:** `api_type` — نوع الربط (**يحتاج تأكيد** حسب الجهاز). |
| 7 | **New column:** `api_key` / `username` / `password` (Char, groups=Technical) — credentials. | **حقول جديدة:** بيانات اعتماد الاتصال (للمسؤول التقني فقط). |
| 8 | **New column:** `sync_status` (Selection: `idle`, `running`, `success`, `error`). | **حقل جديد:** `sync_status` — حالة المزامنة. |
| 9 | **New column:** `last_sync_at` (Datetime) — last successful/partial sync. | **حقل جديد:** `last_sync_at` — آخر مزامنة. |
| 10 | **New column:** `last_sync_message` (Text) — error/summary log. | **حقل جديد:** `last_sync_message` — رسالة/خطأ آخر مزامنة. |
| 11 | **New column:** `active` (Boolean). | **حقل جديد:** `active` — نشط/معطل. |
| 12 | **New column:** `auto_sync` (Boolean, default True) — enable cron sync. | **حقل جديد:** `auto_sync` — تفعيل المزامنة التلقائية. |
| 13 | **Server logic:** `action_sync_now()` — manual sync button on device form. | **منطق خادم:** `action_sync_now()` — زر مزامنة يدوية. |
| 14 | **View customization:** tree + form views under Attendances → Configuration → Fingerprint Devices. | **تخصيص واجهة:** عرض شجرة ونموذج تحت إعدادات الحضور → أجهزة البصمة. |

---

## fingerprint.device.log (new table)

**Model:** `fingerprint.device.log` — **New custom model/table** — raw import staging before `hr.attendance` creation.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **New model/table:** `fingerprint.device.log` — stores raw device punch events. | **موديل/جدول جديد:** `fingerprint.device.log` — سجلات اللقطات الخام من الجهاز. |
| 2 | **New column:** `device_id` (Many2one `fingerprint.device`, required). | **حقل جديد:** `device_id` — الجهاز المصدر. |
| 3 | **New column:** `external_id` (Char, required, indexed) — unique punch ID from device. | **حقل جديد:** `external_id` — معرف اللقطة الفريد من الجهاز. |
| 4 | **New column:** `device_user_id` (Char, required) — user ID on device. | **حقل جديد:** `device_user_id` — معرف المستخدم على الجهاز. |
| 5 | **New column:** `employee_id` (Many2one `hr.employee`) — resolved via `biometric_device_user_id` mapping. | **حقل جديد:** `employee_id` — الموظف بعد الربط. |
| 6 | **New column:** `punch_time` (Datetime, required) — event timestamp from device. | **حقل جديد:** `punch_time` — وقت اللقطة. |
| 7 | **New column:** `punch_type` (Selection: `check_in`, `check_out`, `unknown`). | **حقل جديد:** `punch_type` — نوع اللقطة (دخول/خروج). |
| 8 | **New column:** `state` (Selection: `draft`, `processed`, `error`, `duplicate`). | **حقل جديد:** `state` — حالة المعالجة. |
| 9 | **New column:** `attendance_id` (Many2one `hr.attendance`) — linked Odoo attendance after processing. | **حقل جديد:** `attendance_id` — سجل الحضور المرتبط. |
| 10 | **New column:** `error_message` (Text) — unmapped user, invalid time, etc. | **حقل جديد:** `error_message` — رسالة الخطأ. |
| 11 | **Constraint:** SQL unique (`device_id`, `external_id`) — duplicate log prevention. | **قيد:** فريد على (`device_id`, `external_id`) — منع تكرار السجلات. |
| 12 | **Server logic:** `_process_logs()` — map employee, determine in/out, create or update `hr.attendance`, set `attendance_source=fingerprint`. | **منطق خادم:** معالجة السجلات وإنشاء/تحديث `hr.attendance`. |
| 13 | **Server logic:** handle incomplete check-in/check-out — pair punches or flag `attendance_status=incomplete`. | **منطق خادم:** معالجة السجلات غير المكتملة وتحديد الحالة. |
| 14 | **View customization:** sync log tree view with filters: Error, Unmapped, Duplicate, Today. | **تخصيص واجهة:** عرض سجل المزامنة مع فلاتر الخطأ والتكرار واليوم. |

---

## face.attendance.log (new table)

**Model:** `face.attendance.log` — **New custom model/table** (§4 Remote Face Attendance).

| # | English | العربية |
| - | ------- | ------- |
| 1 | **New model/table:** `face.attendance.log` — audit trail for remote face check-in/out. | **موديل/جدول جديد:** `face.attendance.log` — سجل التحقق بالوجه عن بُعد. |
| 2 | **New column:** `employee_id` (Many2one `hr.employee`, required). | **حقل جديد:** `employee_id` — الموظف. |
| 3 | **New column:** `action_type` (Selection: `check_in`, `check_out`). | **حقل جديد:** `action_type` — دخول أو خروج. |
| 4 | **New column:** `verification_status` (Selection: `passed`, `failed`, `pending`). | **حقل جديد:** `verification_status` — نتيجة التحقق. |
| 5 | **New column:** `confidence_score` (Float) — match score from provider. | **حقل جديد:** `confidence_score` — نسبة الثقة. |
| 6 | **New column:** `attendance_source` (Selection, default `face`) — always `face` for this model. | **حقل جديد:** `attendance_source` — مصدر الحضور (وجه). |
| 7 | **New column:** `latitude` / `longitude` (Float) — geolocation at punch time. | **حقول جديدة:** `latitude`/`longitude` — الموقع الجغرافي. |
| 8 | **New column:** `ip_address` (Char), `user_agent` (Char) — fraud prevention metadata. | **حقول جديدة:** IP ومتصفح الجهاز لمنع الاحتيال. |
| 9 | **New column:** `face_reference_id` (Char) — token/reference used for match (no raw image stored unless policy requires). | **حقل جديد:** `face_reference_id` — مرجع القالب دون تخزين صورة إلا إذا طُلب. |
| 10 | **New column:** `attendance_id` (Many2one `hr.attendance`) — resulting attendance record. | **حقل جديد:** `attendance_id` — سجل الحضور الناتج. |
| 11 | **New column:** `external_token` (Char, indexed) — idempotency key for duplicate prevention. | **حقل جديد:** `external_token` — مفتاح منع التكرار. |
| 12 | **Server logic:** HTTP/JSON API endpoint — verify face (provider TBD), check `remote_attendance_allowed`, geolocation radius vs allowed zone, create `hr.attendance` with `face_verified=True`. | **منطق خادم:** واجهة API للتحقق بالوجه مع فحص الصلاحية والموقع وإنشاء الحضور. |
| 13 | **Server logic:** fraud prevention — reject if geolocation variance exceeds threshold or verification score below minimum (**threshold Needs confirmation**). | **منطق خادم:** منع الاحتيال — رفض عند تجاوز انحراف الموقع أو انخفاض نسبة الثقة (**العتبة تحتاج تأكيد**). |
| 14 | **View customization:** face attendance log tree/form for HR Officers. | **تخصيص واجهة:** عرض سجل حضور الوجه لمسؤولي الموارد البشرية. |

---

## res.company (existing table — add columns)

**Model:** `res.company` — **Standard Odoo**, extended by `hr_attendance` (kiosk settings).

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing columns to reuse (hr_attendance):** `attendance_kiosk_mode`, `attendance_device_tracking`, `auto_check_out`, `absence_management`. | **حقول موجودة:** إعدادات الكشك وتتبع الجهاز والخروج التلقائي وإدارة الغياب. |
| 2 | **New column:** `attendance_official_start` (Float, default 8.0) — company-wide expected start for late calc if not using calendar. | **حقل جديد:** `attendance_official_start` — وقت البداية الرسمي (08:00). |
| 3 | **New column:** `attendance_official_end` (Float, default 16.0) — expected end for early checkout calc. | **حقل جديد:** `attendance_official_end` — وقت النهاية الرسمي (16:00). |
| 4 | **New column:** `face_match_threshold` (Float) — minimum confidence score. | **حقل جديد:** `face_match_threshold` — الحد الأدنى لمطابقة الوجه. |
| 5 | **New column:** `face_geo_radius_meters` (Integer) — allowed distance from expected location. | **حقل جديد:** `face_geo_radius_meters` — نصف قطر الموقع المسموح بالمتر. |
| 6 | **View customization:** extend Attendance settings in `res.config.settings`. | **تخصيص واجهة:** توسيع إعدادات الحضور في إعدادات النظام. |

---

## ir.ui.view (HR attendance forms, tree views, search views, reports)

**Model:** `ir.ui.view` — **Standard Odoo** view records + custom inherits in `hr_attendance_custom_ext`.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **View customization:** extend `hr_attendance.view_attendance_tree` — add `attendance_source`, `attendance_status`, `late_minutes`, `early_checkout_minutes`, `missing_checkout`, `face_verified`. | **تخصيص واجهة:** توسيع عرض شجرة الحضور بالحقول الجديدة. |
| 2 | **View customization:** extend `hr_attendance.hr_attendance_view_form` — show source, status, device link, face verified, late/early minutes. | **تخصيص واجهة:** توسيع نموذج الحضور. |
| 3 | **View customization:** extend `hr_attendance.hr_attendance_view_filter` — new filters: Late, Early Checkout, Missing Checkout, Absent, By Source (fingerprint/face/manual). | **تخصيص واجهة:** فلاتر التأخير والانصراف المبكر والغياب والمصدر. |
| 4 | **View customization:** new search filter `attendance_source` group-by. | **تخصيص واجهة:** تجميع حسب مصدر الحضور. |
| 5 | **View customization:** Lateness Report — list/pivot on `hr.attendance` filtered `attendance_status=late`, group by employee/department/date. | **تخصيص واجهة:** تقرير التأخير — قائمة/محوري حسب الموظف/القسم/التاريخ. |
| 6 | **View customization:** Missing Attendance Report — employees with `attendance_required=True` and no `hr.attendance` on date (or status=absent). | **تخصيص واجهة:** تقرير الغياب/الحضور الناقص. |
| 7 | **View customization:** `fingerprint.device` + `fingerprint.device.log` tree/form/search views. | **تخصيص واجهة:** واجهات جهاز البصمة وسجل المزامنة. |
| 8 | **View customization:** `face.attendance.log` tree/form/search views. | **تخصيص واجهة:** واجهات سجل حضور الوجه. |
| 9 | **View customization:** employee form — biometric mapping, face enrollment, remote attendance flag. | **تخصيص واجهة:** نموذج الموظف — ربط البصمة وتسجيل الوجه. |
| 10 | **Existing views to reuse as base:** standard `hr_attendance` tree/form/search/pivot/graph (after module install). | **واجهات موجودة كأساس:** واجهات hr_attendance القياسية بعد التثبيت. |

---

## ir.cron (attendance sync jobs)

**Model:** `ir.cron` — **Standard Odoo** scheduled actions.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Scheduled action (existing to reuse):** `hr_attendance_check_out_cron` — auto check-out open records. | **إجراء مجدول موجود:** الخروج التلقائي للسجلات المفتوحة. |
| 2 | **Scheduled action (existing to reuse):** `hr_attendance_absence_cron` — technical absence records (extend for Shamsieh absence rules). | **إجراء مجدول موجود:** كشف الغياب — يحتاج توسيع لقواعد شمسية. |
| 3 | **Scheduled action (new):** `Fingerprint: Sync All Devices` — every 15 min, calls `fingerprint.device._cron_sync_all()`. | **إجراء مجدول جديد:** مزامنة جميع أجهزة البصمة كل 15 دقيقة. |
| 4 | **Scheduled action (new):** `Fingerprint: Process Pending Logs` — process `fingerprint.device.log` in `draft` state. | **إجراء مجدول جديد:** معالجة سجلات البصمة المعلقة. |
| 5 | **Scheduled action (new):** `Attendance: Recompute Late/Early Status` — nightly recompute `late_minutes`, `attendance_status` for open day. | **إجراء مجدول جديد:** إعادة حساب التأخير والحالة ليلاً. |
| 6 | **Scheduled action (new):** `Attendance: Flag Missing Checkouts` — end-of-day job for records without `check_out`. | **إجراء مجدول جديد:** تحديد سجلات الانصراف الناقص نهاية اليوم. |

---

## res.groups + ir.model.access.csv + ir.rule (security)

**Standard base (after hr_attendance install):** `group_hr_attendance_own_reader`, `group_hr_attendance_officer`, `group_hr_attendance_user`, `group_hr_attendance_manager`.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Security rule (existing to reuse):** Employee (`group_hr_attendance_own_reader`) — view own `hr.attendance` only (`employee_id.user_id = uid`). | **قاعدة موجودة:** الموظف — قراءة حضوره فقط. |
| 2 | **Security rule (existing to reuse):** Department Manager / Attendance Officer — view team attendance via `attendance_manager_id`. | **قاعدة موجودة:** مدير القسم/مسؤول الحضور — سجلات الفريق المُدار. |
| 3 | **Security rule (existing to reuse):** HR Officer (`group_hr_attendance_user`) — edit attendance and view all records. | **قاعدة موجودة:** مسؤول الموارد البشرية — تعديل الحضور وعرض كل السجلات. |
| 4 | **Security rule (existing to reuse):** HR Manager / Administrator (`group_hr_attendance_manager`) — full access. | **قاعدة موجودة:** مدير الموارد البشرية — وصول كامل. |
| 5 | **New group:** `group_fingerprint_device_manager` (Technical/Admin) — configure `fingerprint.device`, run manual sync. | **مجموعة جديدة:** مسؤول تقني — إعداد أجهزة البصمة والمزامنة اليدوية. |
| 6 | **ir.model.access.csv (new):** `fingerprint.device` — read/write for Technical; read-only for HR Manager. | **صلاحيات جديدة:** `fingerprint.device` — تقني (كامل)، مدير HR (قراءة). |
| 7 | **ir.model.access.csv (new):** `fingerprint.device.log` — HR Officer read/write; HR Manager full; Employee no access. | **صلاحيات جديدة:** `fingerprint.device.log` — مسؤول HR ومدير HR. |
| 8 | **ir.model.access.csv (new):** `face.attendance.log` — Employee read own; HR Officer read all; HR Manager full. | **صلاحيات جديدة:** `face.attendance.log` — الموظف يرى سجله، HR يرى الكل. |
| 9 | **Security rule (new):** `face.attendance.log` employee rule — `[('employee_id.user_id','=',uid)]` read only. | **قاعدة جديدة:** الموظف يرى سجلات الوجه الخاصة به فقط. |
| 10 | **Security rule (new):** `fingerprint.device` — company multi-company rule `[('company_id','in',company_ids)]`. | **قاعدة جديدة:** عزل الشركات لأجهزة البصمة. |

---

## Server logic (compute methods / automated actions / API)

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Server logic:** Calculate late arrival — if `check_in` (employee TZ) > calendar start (08:00), set `late_minutes`. | **منطق خادم:** حساب التأخير بعد 08:00. |
| 2 | **Server logic:** Calculate early checkout — if `check_out` < calendar end (16:00), set `early_checkout_minutes`. | **منطق خادم:** حساب الانصراف المبكر قبل 16:00. |
| 3 | **Server logic:** Detect absence — no `hr.attendance` for required employee on workday; set status `absent` (extend standard `_cron_absence_detection`). | **منطق خادم:** كشف الغياب عند عدم وجود حضور لموظف إلزامي. |
| 4 | **Server logic:** Prevent duplicate fingerprint logs — unique (`device_id`, `external_id`) on `fingerprint.device.log`. | **منطق خادم:** منع تكرار سجلات البصمة. |
| 5 | **Server logic:** Create/update `hr.attendance` from fingerprint logs — pair check_in/check_out punches per employee per day. | **منطق خادم:** إنشاء/تحديث الحضور من سجلات البصمة. |
| 6 | **Server logic:** Create/update `hr.attendance` from face verification — on `verification_status=passed`, call `employee._attendance_action_change()` with geo info. | **منطق خادم:** إنشاء/تحديث الحضور من التحقق بالوجه. |
| 7 | **Server logic:** Mark attendance source clearly — always populate `attendance_source` (fingerprint / face / manual / kiosk / systray). | **منطق خادم:** تعيين مصدر الحضور بوضوح في كل سجل. |
| 8 | **Server logic:** Sync fingerprint device manually (`action_sync_now`) and automatically (`ir.cron`). | **منطق خادم:** مزامنة البصمة يدوياً وتلقائياً. |
| 9 | **Server logic:** Validate incomplete check-in/check-out — flag `missing_checkout` or `attendance_status=incomplete`; notify HR Officer. | **منطق خادم:** التحقق من السجلات غير المكتملة وإشعار HR. |
| 10 | **Server logic:** Employee mapping — resolve `fingerprint.device.log.device_user_id` → `hr.employee.biometric_device_user_id`; log error if unmapped. | **منطق خادم:** ربط معرف الجهاز بالموظف أو تسجيل خطأ. |
| 11 | **Server logic:** Error handling on sync — set `sync_status=error`, store `last_sync_message`, do not rollback already-processed logs. | **منطق خادم:** معالجة أخطاء المزامنة دون التراجع عن السجلات المعالجة. |

---

## Missing Customization Summary / ملخص التخصيصات الناقصة

| Requirement | Existing? | Existing Model/Field | Missing Customization | Notes |
| ----------- | --------- | -------------------- | --------------------- | ----- |
| Install attendance module | Partial | `hr`, `resource` installed | Install standard `hr_attendance` | **Uninstalled** on `mydb_shamsieh` |
| Employee check-in/out records | No | — | `hr.attendance` (standard, after install) | Model absent from live DB today |
| Official hours 08:00–16:00 | Partial | `resource.calendar.attendance.hour_from/hour_to` | Configure Shamsieh calendar + assign to employees | Configuration, not new column |
| Late arrival after 08:00 | No | — | `late_minutes`, `_compute_late_and_early_minutes()` | Not in standard Odoo |
| Early checkout before 16:00 | No | — | `early_checkout_minutes` | Not in standard Odoo |
| Daily attendance status | Partial | `hr.employee.attendance_state` (checked in/out only) | `hr.attendance.attendance_status` | Employee-level state ≠ daily status |
| Absence detection | Partial | `hr.attendance._cron_absence_detection` (technical records) | Extend for Shamsieh rules + missing attendance report | Standard cron exists in code |
| Unified attendance source | Partial | `in_mode`, `out_mode` (separate in/out) | `attendance_source` field | HR PDF requires clear source label |
| Geolocation on attendance | Yes | `in_latitude`, `in_longitude`, `out_latitude`, `out_longitude` | Reuse; populate from face API | `geo_latitude`/`geo_longitude` not needed as separate fields |
| Face verification flag | No | — | `face_verified` on `hr.attendance` | Not in standard Odoo |
| Fingerprint device config | No | — | New model `fingerprint.device` | No module in repo/DB |
| Fingerprint raw logs | No | — | New model `fingerprint.device.log` | — |
| Employee ↔ device user mapping | Partial | `hr.employee.barcode` (RFID badge) | `biometric_device_user_id` | Barcode ≠ fingerprint user ID |
| Face enrollment reference | No | — | `face_reference_id`, optional `face_template_id` | Storage policy **Needs confirmation** |
| Remote attendance permission | No | — | `remote_attendance_allowed` on `hr.employee` | §4 requirement |
| Attendance required flag | No | — | `attendance_required` on `hr.employee` | — |
| Manual fingerprint sync button | No | — | `fingerprint.device.action_sync_now()` | — |
| Automatic fingerprint sync cron | No | — | New `ir.cron` on `fingerprint.device` | — |
| Duplicate log prevention | No | — | Unique constraint on `fingerprint.device.log` | — |
| Face attendance API + audit log | No | — | `face.attendance.log` + HTTP controller | — |
| Face fraud prevention (geo) | Partial | `base.geolocalize`, kiosk geo in `hr_attendance` | Custom radius check + confidence threshold on `res.company` | — |
| Lateness report | No | — | Custom search view + pivot/list action | Standard reporting is hours/overtime only |
| Missing attendance report | No | — | Custom report action | — |
| Attendance source filter | Partial | Filter on `in_mode` only | Filter/group on `attendance_source` | — |
| Fingerprint sync log view | No | — | Views on `fingerprint.device.log` | — |
| Face attendance log view | No | — | Views on `face.attendance.log` | — |
| Employee: view own attendance | Yes | `hr_attendance_rule_attendance_simple_user` | Install `hr_attendance` first | Rule exists in standard module code |
| Dept Manager: view team | Yes | `attendance_manager_id` + officer rule | Install + assign attendance managers | — |
| HR Officer: edit attendance & sync logs | Partial | Officer group on `hr.attendance` | Add access for new log models | — |
| HR Manager: full access | Yes | `group_hr_attendance_manager` | Install `hr_attendance` | — |
| Technical/Admin: device config | No | — | `group_fingerprint_device_manager` + access rules | — |
| Custom HR module in codebase | No | `crm_custom_ext`, `project_custom_ext` only | Create `hr_attendance_custom_ext` | Follows existing `extra_addons` pattern |
| Fingerprint hardware API | — | — | **Needs confirmation** | §19 assumption in HR scope doc |
| Face recognition provider | — | — | **Needs confirmation** | On-device vs cloud TBD |
| Time-off / public holidays in late calc | Partial | `resource.calendar.leaves` | Install `hr_holidays` if leave integration required | **Not installed** on `mydb_shamsieh` |

---

## Scope Alignment with HR Requirements Document (HR_Model.pdf)

| HR Doc Section | Requirement | Covered in this report |
| -------------- | ----------- | ---------------------- |
| §2.1 | Official hours 08:00–16:00 | `resource.calendar` configuration + late/early compute |
| §2.2 | Late arrival tracking & reporting | `late_minutes`, `attendance_status`, lateness report views |
| §2.2 | Filters: employee, department, date, company | Search view extensions |
| §8 | Fingerprint device integration | `fingerprint.device`, `fingerprint.device.log`, sync logic |
| §8 | Employee mapping, duplicate prevention, error handling | Constraints + server logic items |
| §9 | Remote face check-in/out | `face.attendance.log`, API, `remote_attendance_allowed` |
| §9 | Source marking (fingerprint / face / manual) | `attendance_source` field |
| §9 | Geolocation & fraud prevention | Reuse geo fields + `face_geo_radius_meters` |

---

*Document generated from codebase and database inspection. No implementation changes were made.*
