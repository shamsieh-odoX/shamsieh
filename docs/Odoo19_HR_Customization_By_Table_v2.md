# Shamsieh Technology Services Co.
# Odoo HR Module — Customization Scope by Table
# نطاق التخصيص حسب الجدول — وحدة الموارد البشرية في أودو

**Scope covered:** §2 Attendance Management / إدارة الدوام والحضور · §8 Fingerprint Device Integration / ربط جهاز البصمة · §9 Remote Face Attendance / بصمة الوجه للموظفين عن بُعد

**Review basis:** Reviewed against the available Odoo 19 codebase (`addons/hr`, `addons/hr_attendance`, `addons/resource`) and database metadata on **`mydb_shamsieh`** where accessible (`ir_module_module`, `ir_model`, `ir_model_fields`).

**أساس المراجعة:** تمت المراجعة مقابل كود أودو 19 المتاح وبيانات قاعدة البيانات `mydb_shamsieh` حيث أمكن الوصول إليها.

> **Schedule note:** The 08:00–16:00 pattern reflects the current business requirement in the HR scope document. **Calculations should be based on each employee's `resource.calendar` (via `resource.calendar.attendance` lines), not hardcoded times.** Company-level defaults may be used only as a fallback when no employee calendar is assigned.
>
> **ملاحظة الدوام:** نمط 08:00–16:00 يعكس متطلب العمل الحالي. **يجب أن تستند الحسابات إلى `resource.calendar` لكل موظف، وليس أوقاتاً ثابتة في الكود.**

**Recommended custom module (not in codebase today):** `hr_attendance_custom_ext` — following the `extra_addons` convention used by `crm_custom_ext` and `project_custom_ext`.

**Total customization items:** 78

---

## 1. Installed Related Modules / الوحدات ذات الصلة

| Module | Type | State on `mydb_shamsieh` | Notes |
| ------ | ---- | ------------------------ | ----- |
| `hr` | Standard Odoo | Installed | Base Employees module |
| `hr_attendance` | Standard Odoo | Not installed | Prerequisite — provides `hr.attendance`, kiosk, systray, crons |
| `resource` | Standard Odoo | Installed | Working calendars (`resource.calendar`) |
| `hr_holidays` | Standard Odoo | Not installed | Required if leave/public holiday logic is included in lateness/absence |
| `hr_presence` | Standard Odoo | Not installed | Optional |
| Biometric / fingerprint module | — | None found | Recommended custom build |
| Face attendance module | — | None found | Recommended custom build |
| Custom HR module | — | None found | `extra_addons` contains `crm_custom_ext`, `project_custom_ext` only |

| # | English | العربية |
| - | ------- | ------- |
| 1 | Install standard `hr_attendance` before any custom HR attendance work. | تثبيت وحدة `hr_attendance` القياسية قبل أي تخصيص للحضور. |
| 2 | **Recommended custom module:** `hr_attendance_custom_ext` (depends: `hr`, `hr_attendance`, `resource`). | **موديل مخصص مقترح:** `hr_attendance_custom_ext` (يعتمد على: hr، hr_attendance، resource). |
| 3 | No third-party biometric/face Odoo module exists in the available repo or DB metadata — integration should be built as custom scope. | لا يوجد موديل بصمة/وجه جاهز — الربط مقترح كتخصيص مخصص. |
| 4 | Fingerprint device brand/model/API: **Needs confirmation**. | نوع/موديل/API جهاز البصمة: **يحتاج تأكيد**. |
| 5 | Face recognition provider (on-device vs cloud API): **Needs confirmation**. | مزود التعرف على الوجه: **يحتاج تأكيد**. |

---

## hr.attendance

**Model/Table:** `hr.attendance`  
**Type:** Existing standard Odoo table — available after installing `hr_attendance`  
**Current status:** Not registered in `mydb_shamsieh` (`hr_attendance` uninstalled). Standard fields reviewed in Odoo 19 source code (`addons/hr_attendance/models/hr_attendance.py`).  
**Existing reused fields:** `employee_id`, `check_in`, `check_out`, `worked_hours`, `in_mode`, `out_mode`, `in_latitude`, `in_longitude`, `out_latitude`, `out_longitude`, `in_location`, `out_location`  
**Recommended new fields:** `attendance_source`, `attendance_status`, `late_minutes`, `early_checkout_minutes`, `missing_checkout`, `device_id`, `device_user_id`, `external_log_id`, `face_verified`  
**Customization required:** Yes  
**Notes:** Do not add separate `geo_latitude`/`geo_longitude` if existing `in_*` / `out_*` geo fields are sufficient.

### Field Analysis / تحليل الحقول

| Field | Standard Odoo 19 support | Recommended action |
| ----- | ------------------------ | ------------------ |
| `employee_id` | Yes | **Existing column to reuse** |
| `check_in` | Yes | **Existing column to reuse** |
| `check_out` | Yes | **Existing column to reuse** |
| `worked_hours` | Yes (computed, stored) | **Existing column to reuse** |
| `source` | No | **Recommended custom column:** `attendance_source` |
| `attendance_status` | No | **Recommended custom column** |
| `late_minutes` | No | **Recommended custom column** (computed, stored) |
| `early_checkout_minutes` | No | **Recommended custom column** (computed, stored) |
| `missing_checkout` | No | **Recommended custom column** (Boolean, computed) |
| `device_id` | No | **Recommended custom column** (Many2one → `fingerprint.device`) |
| `device_user_id` | No | **Recommended custom column** |
| `external_log_id` | No | **Recommended custom column** |
| `geo_latitude` / `geo_longitude` | Partial | **Existing columns to reuse:** `in_latitude`/`in_longitude`, `out_latitude`/`out_longitude` |
| `face_verified` | No | **Recommended custom column** |

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing column to reuse:** `employee_id` — links attendance to employee. | **حقل موجود — إعادة استخدام:** `employee_id` — يربط الحضور بالموظف. |
| 2 | **Existing column to reuse:** `check_in` — actual check-in timestamp. | **حقل موجود — إعادة استخدام:** `check_in` — وقت الحضور الفعلي. |
| 3 | **Existing column to reuse:** `check_out` — actual check-out timestamp. | **حقل موجود — إعادة استخدام:** `check_out` — وقت الانصراف الفعلي. |
| 4 | **Existing column to reuse:** `worked_hours` — computed from check_in/check_out minus lunch. | **حقل موجود — إعادة استخدام:** `worked_hours` — محسوب من الدخول/الخروج ناقص الاستراحة. |
| 5 | **Recommended custom column:** `attendance_source` (Selection: `fingerprint`, `face`, `manual`, `kiosk`, `systray`, `import`) — unified source; do not rely only on separate `in_mode`/`out_mode`. | **حقل مخصص مقترح:** `attendance_source` — مصدر موحد للحضور. |
| 6 | **Recommended custom column:** `attendance_status` (Selection: `present`, `late`, `early_leave`, `absent`, `incomplete`, `on_leave`). | **حقل مخصص مقترح:** `attendance_status` — الحالة اليومية. |
| 7 | **Recommended custom column:** `late_minutes` — minutes after employee calendar start (business default 08:00 via `resource.calendar`). | **حقل مخصص مقترح:** `late_minutes` — دقائق التأخير بعد بداية جدول الدوام. |
| 8 | **Recommended custom column:** `early_checkout_minutes` — minutes before employee calendar end (business default 16:00 via `resource.calendar`). | **حقل مخصص مقترح:** `early_checkout_minutes` — دقائق الانصراف المبكر قبل نهاية جدول الدوام. |
| 9 | **Recommended custom column:** `missing_checkout` — True when `check_out` is empty past end-of-day tolerance. | **حقل مخصص مقترح:** `missing_checkout` — سجل انصراف ناقص. |
| 10 | **Recommended custom column:** `device_id` (Many2one `fingerprint.device`). | **حقل مخصص مقترح:** `device_id` — جهاز البصمة. |
| 11 | **Recommended custom column:** `device_user_id` — raw user ID from fingerprint device. | **حقل مخصص مقترح:** `device_user_id` — معرف المستخدم على الجهاز. |
| 12 | **Recommended custom column:** `external_log_id` — fingerprint/face log reference for duplicate prevention. | **حقل مخصص مقترح:** `external_log_id` — مرجع السجل الخارجي. |
| 13 | **Existing columns to reuse for geolocation:** `in_latitude`/`in_longitude`, `out_latitude`/`out_longitude`. | **حقول موجودة للموقع:** `in_*` / `out_*` — إعادة استخدام بدلاً من `geo_*` منفصلة. |
| 14 | **Recommended custom column:** `face_verified` — True when attendance originated from successful face match. | **حقل مخصص مقترح:** `face_verified` — تحقق الوجه. |
| 15 | **Recommended custom server logic:** `_compute_late_and_early_minutes()` — compare `check_in`/`check_out` (employee TZ) against `resource.calendar` expected hours. | **منطق خادم مخصص مقترح:** حساب التأخير والانصراف المبكر من `resource.calendar`. |
| 16 | **Recommended custom server logic:** `_compute_attendance_status()` — derive daily status. | **منطق خادم مخصص مقترح:** استنتاج الحالة اليومية. |
| 17 | **Recommended custom server logic:** `_compute_missing_checkout()` — flag open records after scheduled end + tolerance. | **منطق خادم مخصص مقترح:** تحديد السجلات غير المكتملة. |
| 18 | **Recommended custom constraint:** SQL unique on (`external_log_id`, `device_id`) where set — duplicate prevention. | **قيد مخصص مقترح:** منع تكرار السجلات الخارجية. |
| 19 | **Existing constraint to reuse:** standard `_check_validity` — no overlapping attendances, one open check-in per employee. | **قيد موجود — إعادة استخدام:** `_check_validity` القياسي. |
| 20 | **Recommended custom server logic:** on create/write from fingerprint or face logs, populate `attendance_source`, `device_id`, `external_log_id`, `face_verified`. | **منطق خادم مخصص مقترح:** تعيين المصدر والجهاز والمرجع عند الاستيراد. |

---

## hr.employee

**Model/Table:** `hr.employee`  
**Type:** Existing standard Odoo table  
**Current status:** Installed. Attendance-related fields from `hr_attendance` not present in DB metadata (module uninstalled). Reviewed fields on `mydb_shamsieh`: `barcode`, `pin`, `resource_calendar_id`.  
**Existing reused fields:** `barcode`, `pin`, `resource_calendar_id`; after `hr_attendance` install: `attendance_manager_id`, `attendance_state`, `attendance_ids` (standard)  
**Recommended new fields:** `biometric_device_user_id`, `face_reference_id`, `face_template_id`, `attendance_required`, `remote_attendance_allowed`  
**Customization required:** Yes  
**Notes:** `barcode` is RFID/kiosk badge ID — not fingerprint device user ID.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing column to reuse:** `barcode` — RFID/Badge ID for kiosk (not fingerprint device user ID). | **حقل موجود:** `barcode` — بطاقة RFID للكشك. |
| 2 | **Existing column to reuse:** `pin` — kiosk PIN verification. | **حقل موجود:** `pin` — رمز PIN للكشك. |
| 3 | **Existing column to reuse:** `resource_calendar_id` — employee working schedule; configure expected hours here (business default 08:00–16:00 as calendar lines, not hardcoded logic). | **حقل موجود:** `resource_calendar_id` — جدول الدوام لكل موظف. |
| 4 | **Existing columns to reuse after installing hr_attendance:** `attendance_manager_id`, `attendance_state`, `attendance_ids`. | **حقول قياسية بعد تثبيت hr_attendance:** مسؤول الحضور وحالة الحضور. |
| 5 | **Recommended custom column:** `biometric_device_user_id` — maps employee to fingerprint device user ID. | **حقل مخصص مقترح:** `biometric_device_user_id` — ربط معرف جهاز البصمة. |
| 6 | **Recommended custom column:** `face_reference_id` — external enrollment reference/token. | **حقل مخصص مقترح:** `face_reference_id` — مرجع تسجيل الوجه. |
| 7 | **Recommended custom column:** `face_template_id` — optional; **Needs confirmation** whether templates stay on-device only. | **حقل مخصص مقترح:** `face_template_id` — **يحتاج تأكيد** لمكان تخزين القالب. |
| 8 | **Recommended custom column:** `attendance_required` (Boolean, default True). | **حقل مخصص مقترح:** `attendance_required` — إلزامية الحضور. |
| 9 | **Recommended custom column:** `remote_attendance_allowed` (Boolean, default False) — face check-in/out for remote workers. | **حقل مخصص مقترح:** `remote_attendance_allowed` — حضور عن بُعد بالوجه. |
| 10 | **Recommended view customization:** employee form — biometric mapping, face enrollment, remote flag (HR Officers). | **تخصيص واجهة مقترح:** نموذج الموظف — حقول الربط والوجه. |
| 11 | **Recommended custom server logic:** validate `remote_attendance_allowed` before face attendance API calls. | **منطق خادم مخصص مقترح:** التحقق من صلاحية الحضور عن بُعد. |

---

## resource.calendar + resource.calendar.attendance

**Model/Table:** `resource.calendar`, `resource.calendar.attendance`  
**Type:** Existing standard Odoo tables  
**Current status:** Installed. `resource.calendar.attendance` fields present in DB metadata (`hour_from`, `hour_to`, etc.).  
**Existing reused fields:** `hour_from`, `hour_to`, `dayofweek`, `calendar_id`  
**Recommended new fields:** None — configuration and seed data  
**Customization required:** Yes (configuration)  
**Notes:** The 08:00–16:00 schedule is the current business requirement, but calculations should be based on `resource.calendar` instead of hardcoded times.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing table — configure:** company/employee `resource.calendar` with `resource.calendar.attendance` lines reflecting official hours (business default Mon–Fri 08:00–16:00). | **جدول موجود — إعداد:** ضبط جدول الدوام الرسمي عبر `resource.calendar`. |
| 2 | **Existing columns to reuse:** `hour_from` / `hour_to` — basis for late/early calculations. | **حقول موجودة:** `hour_from`/`hour_to` — أساس حساب التأخير والانصراف المبكر. |
| 3 | **Recommended custom server logic:** late minutes = `check_in` (local TZ) minus calendar start from employee `resource_calendar_id`; skip on approved leave if `hr_holidays` is installed (**Needs confirmation** — not installed on `mydb_shamsieh`). | **منطق خادم مخصص مقترح:** حساب التأخير من التقويم مع استثناء الإجازات (**يحتاج تأكيد**). |
| 4 | **Recommended seed data:** Shamsieh standard working-hours calendar assigned via `hr.version`. | **بيانات أولية مقترحة:** تقويم دوام قياسي وتعيينه للموظفين. |

---

## fingerprint.device

**Model/Table:** `fingerprint.device`  
**Type:** Recommended new custom model/table (§3 Fingerprint Device Integration)  
**Current status:** Not present in codebase or `mydb_shamsieh` metadata  
**Existing reused fields:** —  
**Recommended new fields:** `name`, `company_id`, `device_ip`, `device_port`, `api_type`, credentials, `sync_status`, `last_sync_at`, `last_sync_message`, `active`, `auto_sync`  
**Customization required:** Yes  
**Notes:** Device brand/model/API and connection method (**API / database / SDK / file import**) — **Needs confirmation**.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Recommended new custom model/table:** `fingerprint.device` — device configuration header. | **موديل/جدول مخصص جديد مقترح:** `fingerprint.device` — إعدادات الجهاز. |
| 2 | **Recommended custom column:** `name` (Char, required). | **حقل مخصص مقترح:** `name` — اسم الجهاز. |
| 3 | **Recommended custom column:** `company_id` (Many2one `res.company`, required). | **حقل مخصص مقترح:** `company_id` — الشركة. |
| 4 | **Recommended custom column:** `device_ip`, `device_port`. | **حقول مخصصة مقترحة:** IP والمنفذ. |
| 5 | **Recommended custom column:** `api_type` (Selection: `zkteco`, `hikvision`, `file_import`, `custom_api`) — **Needs confirmation**. | **حقل مخصص مقترح:** `api_type` — **يحتاج تأكيد**. |
| 6 | **Recommended custom column:** `api_key` / `username` / `password` (Technical group only). | **حقول مخصصة مقترحة:** بيانات الاعتماد للمسؤول التقني. |
| 7 | **Recommended custom column:** `sync_status`, `last_sync_at`, `last_sync_message`. | **حقول مخصصة مقترحة:** حالة وتاريخ ورسالة المزامنة. |
| 8 | **Recommended custom column:** `active`, `auto_sync`. | **حقول مخصصة مقترحة:** نشط والمزامنة التلقائية. |
| 9 | **Recommended custom server logic:** `action_sync_now()` — manual sync button. | **منطق خادم مخصص مقترح:** مزامنة يدوية. |
| 10 | **Recommended view customization:** tree + form under Attendances → Configuration → Fingerprint Devices. | **تخصيص واجهة مقترح:** شاشات إعداد الجهاز. |

---

## fingerprint.device.log

**Model/Table:** `fingerprint.device.log`  
**Type:** Recommended new custom model/table — raw import staging before `hr.attendance`  
**Current status:** Not present in codebase or DB metadata  
**Existing reused fields:** —  
**Recommended new fields:** `device_id`, `external_id`, `device_user_id`, `employee_id`, `punch_time`, `punch_type`, `state`, `attendance_id`, `error_message`  
**Customization required:** Yes  
**Notes:** Employee-to-device-user mapping must be prepared on `hr.employee.biometric_device_user_id`.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Recommended new custom model/table:** `fingerprint.device.log` — raw device punch events. | **موديل/جدول مخصص جديد مقترح:** سجلات اللقطات الخام. |
| 2 | **Recommended custom column:** `device_id`, `external_id`, `device_user_id`, `employee_id`. | **حقول مخصصة مقترحة:** الجهاز والمعرف الخارجي والموظف. |
| 3 | **Recommended custom column:** `punch_time`, `punch_type`, `state`. | **حقول مخصصة مقترحة:** الوقت والنوع والحالة. |
| 4 | **Recommended custom column:** `attendance_id`, `error_message`. | **حقول مخصصة مقترحة:** ربط الحضور ورسالة الخطأ. |
| 5 | **Recommended custom constraint:** unique (`device_id`, `external_id`) — duplicate prevention. | **قيد مخصص مقترح:** منع تكرار السجلات. |
| 6 | **Recommended custom server logic:** `_process_logs()` — map employee, create/update `hr.attendance`, set `attendance_source=fingerprint`. | **منطق خادم مخصص مقترح:** معالجة السجلات وإنشاء الحضور. |
| 7 | **Recommended custom server logic:** handle incomplete check-in/check-out — flag `attendance_status=incomplete`. | **منطق خادم مخصص مقترح:** معالجة السجلات غير المكتملة. |
| 8 | **Recommended view customization:** sync log tree with filters: Error, Unmapped, Duplicate, Today. | **تخصيص واجهة مقترح:** عرض سجل المزامنة مع فلاتر. |

---

## face.attendance.log

**Model/Table:** `face.attendance.log`  
**Type:** Recommended new custom model/table (§4 Remote Face Attendance)  
**Current status:** Not present in codebase or DB metadata  
**Existing reused fields:** —  
**Recommended new fields:** `employee_id`, `action_type`, `verification_status`, `confidence_score`, `latitude`, `longitude`, `ip_address`, `user_agent`, `face_reference_id`, `attendance_id`, `external_token`  
**Customization required:** Yes  

### Face Recognition Assumptions — Needs Confirmation / افتراضات التعرف على الوجه — تحتاج تأكيد

| Item | Status |
| ---- | ------ |
| Face recognition provider | **Needs confirmation** |
| Verification: local/on-device vs cloud API | **Needs confirmation** |
| Whether raw face images are stored | **Needs confirmation** |
| Whether only templates/tokens are stored | **Needs confirmation** |
| Confidence threshold | **Needs confirmation** |
| Geolocation radius | **Needs confirmation** |
| Fraud prevention rules | **Needs confirmation** |
| Legal/privacy approval for biometric data | **Needs confirmation** |

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Recommended new custom model/table:** `face.attendance.log` — audit trail for remote face check-in/out. | **موديل/جدول مخصص جديد مقترح:** سجل التحقق بالوجه عن بُعد. |
| 2 | **Recommended custom column:** `employee_id`, `action_type`, `verification_status`, `confidence_score`. | **حقول مخصصة مقترحة:** الموظف ونوع الإجراء ونتيجة التحقق. |
| 3 | **Recommended custom column:** `latitude`, `longitude`, `ip_address`, `user_agent` — fraud prevention metadata. | **حقول مخصصة مقترحة:** بيانات الموقع والجهاز. |
| 4 | **Recommended custom column:** `face_reference_id`, `attendance_id`, `external_token`. | **حقول مخصصة مقترحة:** مرجع الوجه والحضور ومفتاح منع التكرار. |
| 5 | **Recommended custom server logic:** HTTP/JSON API — verify face (**provider Needs confirmation**), check `remote_attendance_allowed`, geolocation rules, create `hr.attendance` with `face_verified=True`. | **منطق خادم مخصص مقترح:** واجهة API للتحقق بالوجه (**المزود يحتاج تأكيد**). |
| 6 | **Recommended custom server logic:** fraud prevention — reject on failed geo/confidence rules (**thresholds Needs confirmation**). | **منطق خادم مخصص مقترح:** منع الاحتيال (**العتبات تحتاج تأكيد**). |
| 7 | **Recommended view customization:** face attendance log tree/form for HR Officers. | **تخصيص واجهة مقترح:** عرض سجل حضور الوجه. |

---

## res.company

**Model/Table:** `res.company`  
**Type:** Existing standard Odoo table — extended by `hr_attendance` when installed  
**Current status:** Standard HR attendance company fields available in source code only until `hr_attendance` is installed  
**Existing reused fields (standard, after install):** `attendance_kiosk_mode`, `attendance_device_tracking`, `auto_check_out`, `absence_management`  
**Recommended new fields:** `face_match_threshold`, `face_geo_radius_meters` (optional company-level defaults; calendar remains primary for schedule)  
**Customization required:** Yes (partial)  
**Notes:** Avoid company-level `attendance_official_start/end` as primary logic — prefer `resource.calendar`. Optional fallback fields only if client confirms.

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing columns to reuse (after hr_attendance install):** kiosk, device tracking, auto check-out, absence management settings. | **حقول قياسية بعد التثبيت:** إعدادات الكشك والتتبع والغياب. |
| 2 | **Recommended custom column:** `face_match_threshold` — default minimum confidence (**Needs confirmation**). | **حقل مخصص مقترح:** عتبة مطابقة الوجه (**يحتاج تأكيد**). |
| 3 | **Recommended custom column:** `face_geo_radius_meters` — allowed geo variance (**Needs confirmation**). | **حقل مخصص مقترح:** نصف قطر الموقع (**يحتاج تأكيد**). |
| 4 | **Recommended view customization:** extend Attendance settings in `res.config.settings`. | **تخصيص واجهة مقترح:** إعدادات الحضور في إعدادات النظام. |

---

## ir.ui.view (HR attendance forms, tree views, search views, reports)

**Model/Table:** `ir.ui.view`  
**Type:** Existing standard Odoo table — custom inherits recommended in `hr_attendance_custom_ext`  
**Current status:** Standard `hr_attendance` views not in DB until module installed  
**Customization required:** Yes  

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Recommended view customization:** extend `hr_attendance.view_attendance_tree` — add custom attendance fields. | **تخصيص واجهة مقترح:** توسيع شجرة الحضور. |
| 2 | **Recommended view customization:** extend `hr_attendance.hr_attendance_view_form`. | **تخصيص واجهة مقترح:** توسيع نموذج الحضور. |
| 3 | **Recommended view customization:** extend `hr_attendance.hr_attendance_view_filter` — Late, Early Checkout, Missing Checkout, Absent, By Source. | **تخصيص واجهة مقترح:** فلاتر التأخير والغياب والمصدر. |
| 4 | **Recommended view customization:** Lateness Report — pivot/list on `attendance_status=late`. | **تخصيص واجهة مقترح:** تقرير التأخير. |
| 5 | **Recommended view customization:** Missing Attendance Report. | **تخصيص واجهة مقترح:** تقرير الغياب/الحضور الناقص. |
| 6 | **Recommended view customization:** `fingerprint.device` and `fingerprint.device.log` views. | **تخصيص واجهة مقترح:** واجهات البصمة وسجل المزامنة. |
| 7 | **Recommended view customization:** `face.attendance.log` views. | **تخصيص واجهة مقترح:** واجهات سجل الوجه. |
| 8 | **Existing views to reuse as base:** standard `hr_attendance` tree/form/search/pivot/graph after install. | **واجهات قياسية كأساس:** بعد تثبيت hr_attendance. |

---

## ir.cron (attendance sync jobs)

**Model/Table:** `ir.cron`  
**Type:** Existing standard Odoo table  
**Current status:** Standard attendance crons defined in `hr_attendance` source; not in DB until installed  
**Customization required:** Yes (extend + add)  

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing scheduled action to reuse:** `hr_attendance_check_out_cron` — auto check-out (standard, after install). | **إجراء مجدول قياسي:** الخروج التلقائي. |
| 2 | **Existing scheduled action to reuse:** `hr_attendance_absence_cron` — extend for Shamsieh absence rules. | **إجراء مجدول قياسي:** كشف الغياب — يحتاج توسيع. |
| 3 | **Recommended custom scheduled action:** `Fingerprint: Sync All Devices` — periodic device sync. | **إجراء مجدول مخصص مقترح:** مزامنة أجهزة البصمة. |
| 4 | **Recommended custom scheduled action:** `Fingerprint: Process Pending Logs`. | **إجراء مجدول مخصص مقترح:** معالجة سجلات البصمة المعلقة. |
| 5 | **Recommended custom scheduled action:** `Attendance: Recompute Late/Early Status` — nightly from `resource.calendar`. | **إجراء مجدول مخصص مقترح:** إعادة حساب التأخير ليلاً. |
| 6 | **Recommended custom scheduled action:** `Attendance: Flag Missing Checkouts`. | **إجراء مجدول مخصص مقترح:** تحديد انصراف ناقص نهاية اليوم. |

---

## res.groups + ir.model.access.csv + ir.rule (security)

**Model/Table:** `res.groups`, `ir.model.access`, `ir.rule`  
**Type:** Existing standard Odoo — extensions recommended  
**Current status:** Standard `hr_attendance` security in source code; not in DB until installed  
**Customization required:** Yes  

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Existing security rule to reuse:** Employee — read own `hr.attendance` (`group_hr_attendance_own_reader`). | **قاعدة قياسية:** الموظف — حضوره فقط. |
| 2 | **Existing security rule to reuse:** Department Manager / Attendance Officer — team via `attendance_manager_id`. | **قاعدة قياسية:** مدير القسم — فريقه. |
| 3 | **Existing security rule to reuse:** HR Officer — all attendances read/write. | **قاعدة قياسية:** مسؤول HR — كل الحضور. |
| 4 | **Existing security rule to reuse:** HR Manager — full access. | **قاعدة قياسية:** مدير HR — وصول كامل. |
| 5 | **Recommended custom security group:** `group_fingerprint_device_manager` — Technical/Admin device configuration. | **مجموعة مخصصة مقترحة:** مسؤول تقني لأجهزة البصمة. |
| 6 | **Recommended custom access rules:** `fingerprint.device`, `fingerprint.device.log`, `face.attendance.log`. | **صلاحيات مخصصة مقترحة:** وصول النماذج الجديدة. |
| 7 | **Recommended custom record rules:** employee read-own on `face.attendance.log`; company isolation on `fingerprint.device`. | **قواعد سجلات مخصصة مقترحة:** عزل البيانات حسب الدور والشركة. |

---

## Server Logic (compute methods / automated actions / API)

| # | English | العربية |
| - | ------- | ------- |
| 1 | **Recommended custom server logic:** Calculate late arrival from employee `resource.calendar` start (not hardcoded 08:00). | **منطق خادم مخصص مقترح:** حساب التأخير من `resource.calendar`. |
| 2 | **Recommended custom server logic:** Calculate early checkout from employee `resource.calendar` end (not hardcoded 16:00). | **منطق خادم مخصص مقترح:** حساب الانصراف المبكر من التقويم. |
| 3 | **Recommended custom server logic:** Detect absence — extend standard `_cron_absence_detection` for Shamsieh rules. | **منطق خادم مخصص مقترح:** كشف الغياب. |
| 4 | **Recommended custom server logic:** Prevent duplicate fingerprint logs. | **منطق خادم مخصص مقترح:** منع تكرار سجلات البصمة. |
| 5 | **Recommended custom server logic:** Create/update `hr.attendance` from fingerprint logs. | **منطق خادم مخصص مقترح:** إنشاء الحضور من البصمة. |
| 6 | **Recommended custom server logic:** Create/update `hr.attendance` from face verification. | **منطق خادم مخصص مقترح:** إنشاء الحضور من الوجه. |
| 7 | **Recommended custom server logic:** Always populate `attendance_source`. | **منطق خادم مخصص مقترح:** تعيين مصدر الحضور. |
| 8 | **Recommended custom server logic:** Manual and automatic fingerprint sync. | **منطق خادم مخصص مقترح:** مزامنة البصمة يدوياً وتلقائياً. |
| 9 | **Recommended custom server logic:** Validate incomplete records; notify HR Officer. | **منطق خادم مخصص مقترح:** التحقق من السجلات الناقصة وإشعار HR. |
| 10 | **Recommended custom server logic:** Employee mapping `device_user_id` → `biometric_device_user_id`. | **منطق خادم مخصص مقترح:** ربط معرف الجهاز بالموظف. |
| 11 | **Recommended custom server logic:** Sync error handling without rolling back processed logs. | **منطق خادم مخصص مقترح:** معالجة أخطاء المزامنة. |

---

## Automated Processes / العمليات الآلية

| # | Process | Type | Existing/Recommended | Notes |
| - | ------- | ---- | -------------------- | ----- |
| 1 | Late arrival calculation | Compute / cron | Recommended custom | Based on `resource.calendar`, not hardcoded times |
| 2 | Early checkout calculation | Compute / cron | Recommended custom | Based on `resource.calendar` end time |
| 3 | Missing checkout detection | Compute / cron | Recommended custom | End-of-day flag on open records |
| 4 | Absence detection | Scheduled action | Existing standard + recommended extension | `hr_attendance_absence_cron` after install |
| 5 | Fingerprint device sync | Scheduled action + button | Recommended custom | Interval **Needs confirmation** |
| 6 | Fingerprint log processing | Scheduled action | Recommended custom | `fingerprint.device.log` draft → processed |
| 7 | Duplicate log prevention | Constraint + server logic | Recommended custom | Unique `device_id` + `external_id` |
| 8 | Face attendance verification | API + server logic | Recommended custom | Provider and thresholds **Needs confirmation** |
| 9 | Attendance source tagging | Server logic on create | Recommended custom | `attendance_source` on every record |
| 10 | Nightly recomputation | Scheduled action | Recommended custom | Late/status refresh for prior day |
| 11 | HR notification for incomplete records | Server logic / mail | Recommended custom | Notify attendance manager or HR Officer |

---

## Views Affected / الواجهات المتأثرة

| # | View | Type | Existing/Recommended | Notes |
| - | ---- | ---- | -------------------- | ----- |
| 1 | `hr.attendance` tree view | List | Existing + recommended inherit | Add status, source, late minutes |
| 2 | `hr.attendance` form view | Form | Existing + recommended inherit | Device link, face verified, geo |
| 3 | `hr.attendance` search view | Search | Existing + recommended inherit | Late, absent, source filters |
| 4 | `hr.employee` form view | Form | Existing + recommended inherit | Biometric mapping, remote flag |
| 5 | Attendance dashboard / reporting | Pivot / graph | Existing + recommended extend | Standard pivot after install |
| 6 | Lateness report | Action + list/pivot | Recommended custom | Filter `attendance_status=late` |
| 7 | Missing attendance report | Action + list | Recommended custom | Required employees without punch |
| 8 | Fingerprint device configuration | Form + tree | Recommended custom | New model views |
| 9 | Fingerprint sync log views | Tree + search | Recommended custom | Error/unmapped filters |
| 10 | Face attendance log views | Tree + form | Recommended custom | HR Officer access |
| 11 | HR attendance settings | `res.config.settings` | Existing + recommended inherit | Face thresholds if confirmed |

---

## Dependencies & Risks / التبعيات والمخاطر

| # | English | العربية |
| - | ------- | ------- |
| 1 | `hr_attendance` must be installed before any attendance customization. | يجب تثبيت `hr_attendance` قبل أي تخصيص للحضور. |
| 2 | `hr_holidays` may be required if leave/public holiday logic is included in lateness or absence rules. | قد يُطلب `hr_holidays` إذا شمل النطاق الإجازات والعطل الرسمية. |
| 3 | Fingerprint device brand, model, and API must be confirmed before integration design is finalized. | يجب تأكيد نوع وموديل وAPI جهاز البصمة قبل اعتماد التصميم. |
| 4 | Device connection method must be confirmed: API, database, SDK, or file import. | يجب تأكيد طريقة الاتصال: API أو قاعدة بيانات أو SDK أو استيراد ملف. |
| 5 | Employee-to-device-user mapping must be prepared and maintained on `hr.employee`. | يجب إعداد وصيانة ربط الموظف بمعرف الجهاز. |
| 6 | Face recognition provider must be confirmed (on-device vs cloud). | يجب تأكيد مزود التعرف على الوجه (محلي أو سحابي). |
| 7 | Geolocation and privacy policy must be approved before enabling remote face attendance. | يجب اعتماد سياسة الموقع والخصوصية قبل تفعيل حضور الوجه عن بُعد. |
| 8 | Storing face images or biometric templates may require legal/privacy approval. | تخزين صور الوجه أو القوالب البيومترية قد يتطلب موافقة قانونية/خصوصية. |
| 9 | Payroll impact is out of scope unless explicitly confirmed by the client. | أثر الرواتب خارج النطاق ما لم يُؤكد صراحة من العميل. |
| 10 | Payroll, leave balance, and overtime rules are not covered in this document unless added to scope. | الرواتب وأرصدة الإجازات والعمل الإضافي غير مشمولة إلا بإضافتها للنطاق. |

---

## Database / Code Evidence Checked

**Database reviewed:** `mydb_shamsieh` (PostgreSQL, read-only queries on 2026-07-05).  
**Code reviewed:** `addons/hr_attendance/models/hr_attendance.py`, `addons/hr_attendance/models/hr_employee.py`, `addons/hr_attendance/security/hr_attendance_security.xml`, `addons/resource/models/resource_calendar_attendance.py`.

### Query 1 — Installed modules

```sql
SELECT name, state
FROM ir_module_module
WHERE name IN ('hr', 'hr_attendance', 'resource', 'hr_holidays')
ORDER BY name;
```

**Result:**

| name | state |
| ---- | ----- |
| hr | installed |
| hr_attendance | uninstalled |
| hr_holidays | uninstalled |
| resource | installed |

### Query 2 — Attendance / biometric / face models

```sql
SELECT model, name
FROM ir_model
WHERE model ILIKE '%attendance%'
   OR model ILIKE '%finger%'
   OR model ILIKE '%biometric%'
   OR model ILIKE '%face%'
ORDER BY model;
```

**Result:**

| model | name |
| ----- | ---- |
| resource.calendar.attendance | Work Detail |

*Note: `hr.attendance` not returned — consistent with `hr_attendance` uninstalled.*

### Query 3 — Relevant fields (excerpt)

```sql
SELECT m.model, f.name, f.ttype, f.field_description
FROM ir_model_fields f
JOIN ir_model m ON f.model_id = m.id
WHERE m.model IN ('hr.employee', 'hr.attendance')
   OR m.model ILIKE '%attendance%'
   OR m.model ILIKE '%finger%'
   OR m.model ILIKE '%biometric%'
   OR m.model ILIKE '%face%'
ORDER BY m.model, f.name;
```

**Result (attendance-relevant excerpt):**

| model | name | ttype |
| ----- | ---- | ----- |
| hr.employee | barcode | char |
| hr.employee | pin | char |
| hr.employee | resource_calendar_id | many2one |
| resource.calendar.attendance | hour_from | float |
| resource.calendar.attendance | hour_to | float |

*Full query returned 212 rows for `hr.employee` and `resource.calendar.attendance`. No `hr.attendance` rows. No fingerprint/face/biometric models or fields.*

**Standard `hr.attendance` fields (code evidence — `addons/hr_attendance/models/hr_attendance.py`):** `employee_id`, `check_in`, `check_out`, `worked_hours`, `in_mode`, `out_mode`, `in_latitude`, `in_longitude`, `out_latitude`, `out_longitude` — present in source; not in DB until `hr_attendance` installed.

---

## Missing Customization Summary / ملخص التخصيصات الناقصة

| Requirement | Status | Existing Standard Support | Recommended Customization | Dependency / Confirmation Needed | Notes |
| ----------- | ------ | ------------------------- | ------------------------- | -------------------------------- | ----- |
| Install attendance module | Gap | `hr`, `resource` installed | Install `hr_attendance` | `hr_attendance` install | Uninstalled on `mydb_shamsieh` |
| Employee check-in/out records | Gap | — | Standard `hr.attendance` after install | `hr_attendance` | Model absent from DB today |
| Official working hours | Partial | `resource.calendar.attendance` | Configure calendar per employee | Client workweek policy | Use calendar, not hardcoded logic |
| Late arrival tracking | Gap | — | `late_minutes` + compute from calendar | `hr_attendance`, calendar config | Not in standard Odoo |
| Early checkout tracking | Gap | — | `early_checkout_minutes` | `hr_attendance`, calendar config | Not in standard Odoo |
| Daily attendance status | Partial | `hr.employee.attendance_state` (in/out only) | `attendance_status` on `hr.attendance` | `hr_attendance` + custom module | Different semantics |
| Absence detection | Partial | `_cron_absence_detection` in source | Extend rules + missing report | `hr_attendance` install | Standard cron not in DB yet |
| Unified attendance source | Partial | `in_mode`, `out_mode` | `attendance_source` field | Custom module | HR scope requires clear label |
| Geolocation on attendance | Available | `in_*` / `out_*` lat/long in source | Reuse; populate from face API | `hr_attendance` install | No separate `geo_*` needed |
| Face verification flag | Gap | — | `face_verified` column | Custom module | — |
| Fingerprint device config | Gap | — | `fingerprint.device` model | Device API confirmation | — |
| Fingerprint raw logs | Gap | — | `fingerprint.device.log` model | Device API + mapping | — |
| Employee ↔ device mapping | Partial | `barcode` (RFID) | `biometric_device_user_id` | HR data preparation | Different identifier |
| Face enrollment | Gap | — | `face_reference_id`, optional `face_template_id` | Provider + privacy approval | **Needs confirmation** |
| Remote attendance permission | Gap | — | `remote_attendance_allowed` | Custom module | §4 requirement |
| Attendance required flag | Gap | — | `attendance_required` | Custom module | — |
| Manual fingerprint sync | Gap | — | `action_sync_now()` | Custom module + device API | — |
| Automatic fingerprint sync | Gap | — | Custom `ir.cron` | Device API + interval confirmation | — |
| Duplicate log prevention | Gap | — | Unique constraint on sync log | Custom module | — |
| Face attendance API + audit | Gap | — | `face.attendance.log` + controller | Provider confirmation | — |
| Face fraud prevention | Partial | `base.geolocalize`, kiosk geo | Radius + confidence rules | Privacy + threshold confirmation | **Needs confirmation** |
| Lateness report | Gap | Standard hours/overtime pivot only | Custom report action | Custom module | — |
| Missing attendance report | Gap | — | Custom report action | Custom module | — |
| Attendance source filter | Partial | `in_mode` filter in source | `attendance_source` filter | Custom module | — |
| Fingerprint sync log view | Gap | — | Custom views | Custom module | — |
| Face attendance log view | Gap | — | Custom views | Custom module | — |
| Employee: own attendance | Available | Standard security in source | Install `hr_attendance` | Module install | Not in DB until installed |
| Dept Manager: team attendance | Available | `attendance_manager_id` + officer rule | Install + assign managers | `hr_attendance` | — |
| HR Officer: edit + sync logs | Partial | Officer on `hr.attendance` in source | Access for new log models | Custom module | — |
| HR Manager: full access | Available | `group_hr_attendance_manager` in source | Install `hr_attendance` | Module install | — |
| Technical: device config | Gap | — | `group_fingerprint_device_manager` | Custom module | — |
| Custom HR module | Gap | `crm_custom_ext`, `project_custom_ext` | `hr_attendance_custom_ext` | Development | Not started |
| Payroll impact | Out of scope | — | — | Client confirmation | Unless added to scope |

---

## Scope Alignment with HR Requirements Document (HR_Model.pdf)

| HR Doc Section | Requirement | Addressed in this document |
| -------------- | ----------- | -------------------------- |
| §2.1 | Official hours 08:00–16:00 | `resource.calendar` configuration; calculations from calendar not hardcoded times |
| §2.2 | Late arrival tracking & reporting | Recommended `late_minutes`, `attendance_status`, lateness report |
| §2.2 | Filters: employee, department, date, company | Recommended search view extensions |
| §8 | Fingerprint device integration | Recommended `fingerprint.device`, `fingerprint.device.log`, sync logic |
| §8 | Mapping, duplicate prevention, error handling | Recommended constraints + server logic |
| §9 | Remote face check-in/out | Recommended `face.attendance.log`, API, `remote_attendance_allowed` |
| §9 | Source marking (fingerprint / face / manual) | Recommended `attendance_source` |
| §9 | Geolocation & fraud prevention | Reuse geo fields + confirmed thresholds |

---

*Document version 2 — refined for client review. Reviewed against available Odoo 19 codebase and `mydb_shamsieh` database metadata. No implementation changes were made.*
