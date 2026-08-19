# Overtime as Time Off

## Overview

Approved overtime hours and fingerprint extra minutes (including early entry) are
converted into Time Off that the employee can use to leave early on another day.
No overtime is paid on the payslip.

## How hours are earned

### 1. Overtime request (existing approval flow)

Employee submits an overtime request → Manager → HR approval. On final HR
approval, the **actual overtime hours** (1:1, no multiplier) are added as an
Overtime Time Off allocation. The cost multipliers (1.5×, 2×, 2.5×) still apply
to the timesheet / analytic line for project costing but do **not** multiply the
Time Off hours.

If the request is refused or cancelled after approval, the allocation is
reversed (unless the employee already used some of the hours).

### 2. Fingerprint extra minutes

When an attendance record has a checkout:

- **Extra minutes** (checkout after scheduled end) still offset **same-day late
  minutes** first. This behaviour is unchanged.
- **Leftover extra** after offsetting late = `max(0, extra_minutes - late_minutes)`.
- **Early entry minutes** (check-in before scheduled start) are calculated
  separately.
- **Bankable minutes** = leftover extra + early entry.

Bankable minutes are automatically converted into an Overtime Time Off allocation
(one per attendance record, idempotent on recompute).

Skipped when:
- The day is an approved leave or public holiday.
- An HR-approved overtime request already covers the same employee and date (no
  double-banking).

### 3. Using the hours

The employee goes to **Time Off → New Request → Overtime** and requests hours
(same flow as Hourly Departure). After manager approval, the leave is validated
and the attendance system skips penalties for that period.

## What does NOT change

- Same-day late offset by extra minutes (unchanged formula).
- Hourly Departure: still 6 hours/month, allocated by cron, Article 11 caps.
- Overtime request workflow, project/task, timesheet, cost calculation.
- No overtime pay on the payslip.

## Configuration

**Settings → Time Off → Overtime Time Off**

- **Overtime Leave Type**: defaults to the "Overtime" type created by this module.

## Leave type

| Field | Value |
|---|---|
| Name | Overtime |
| Request unit | Hour |
| Requires allocation | Yes |
| Validation | Manager |
| Allocation validation | No validation |
| Is Hourly Departure | No |

## Technical

### Models modified

- `hr.leave.allocation` — new fields: `overtime_request_id`, `attendance_id`;
  new allocation origins `overtime_request`, `attendance_extra`.
- `hr.overtime.request` — `_on_approval_complete` extended to create allocation;
  `_on_approval_refused` reverses allocation.
- `hr.attendance` — new computed fields `early_entry_minutes`, `bankable_minutes`;
  `_bank_overtime_minutes()` creates/updates allocations on checkout.
- `hr.attendance.daily.status` — mirrors `early_entry_minutes`, `bankable_minutes`.
- `res.company` — `overtime_leave_type_id`.
- `res.config.settings` — exposed in settings view.
- `hr.overtime.leave.helper` — abstract model with shared allocation logic.
