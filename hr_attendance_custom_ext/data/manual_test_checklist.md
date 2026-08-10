# Phases 4–11 implementation checklist and Phase 11 design pointer.

See [hikvision_http_listening_design.md](../../../docs/hikvision_http_listening_design.md) for optional real-time push (not implemented).

## Phase 4 — Policy engine

- [ ] Default attendance policy exists per company (Configuration → Attendance Policies)
- [ ] Device can override policy via `policy_id`
- [ ] first_last: 3 scans → check_in, unknown middle, check_out
- [ ] Duplicate scans within window marked duplicate
- [ ] Checkout gap enforced

## Phase 5 — Calculations

- [ ] late_minutes uses resource.calendar (not hardcoded)
- [ ] Policy grace minutes suppress late/early flags
- [ ] missing_checkout uses policy tolerance minutes

## Phase 6 — Daily status

- [ ] Cron generates yesterday's daily status
- [ ] Absent on workday with no attendance
- [ ] Present/late copied from hr.attendance

## Phase 7 — Reports

- [ ] Lateness / Missing / Source / Department / Fingerprint logs reports open

## Phase 8 — UI & security

- [ ] Device smart buttons: Draft, Error, Processed
- [ ] Log error_message visible; raw_payload debug-only
- [ ] Employees cannot read device logs

## Phase 9 — Notifications

- [ ] Sync failure creates HR activity
- [ ] Unmapped events create HR activity
- [ ] Missing checkout creates activity

## Phase 10 — Hardening

- [ ] Sync retry and checkpoint fields on device
- [ ] Log audit fields populated on process
- [ ] Reprocess Errors button works
- [ ] Raw payload purge cron
