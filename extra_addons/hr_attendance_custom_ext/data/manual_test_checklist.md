# Manual test checklist — HR Attendance Custom Extension (§2, §8, §9)

1. [ ] Employee scans fingerprint on Hikvision device (or import CSV via File Import device).
2. [ ] Device log is imported into `fingerprint.device.log` (state = draft).
3. [ ] Device user ID maps to `hr.employee.biometric_device_user_id`.
4. [ ] `hr.attendance` record is created with correct check_in/check_out.
5. [ ] Duplicate scan with same `external_id` is not duplicated (state = duplicate).
6. [ ] Late minutes are calculated from employee `resource.calendar` (not hardcoded 08:00).
7. [ ] Early checkout minutes are calculated from employee `resource.calendar`.
8. [ ] Missing checkout is flagged when check_out is empty past tolerance.
9. [ ] Attendance source shows `fingerprint` on synced records.
10. [ ] Sync errors are logged clearly on device (`last_sync_message`) and log (`error_message`).

### Face attendance (stub)

11. [ ] Enable **Face Attendance Stub** in Settings → Attendances → Shamsieh Custom Attendance (development only).
12. [ ] Employee has `remote_attendance_allowed` = True.
13. [ ] Call JSON-RPC `/hr_attendance_custom/face/check` — log created, attendance updated, source = face.
