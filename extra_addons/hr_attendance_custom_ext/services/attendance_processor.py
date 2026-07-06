# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import timedelta

from odoo import _, fields
from odoo.exceptions import UserError, ValidationError


class AttendanceProcessor:
    """Policy-driven draft log → hr.attendance processing."""

    def __init__(self, env):
        self.env = env

    def process_logs(self, logs):
        Log = logs.env['fingerprint.device.log']
        seeds = logs.filtered(lambda log: log.state == 'draft')
        if not seeds:
            return Log.browse()

        for log in seeds:
            if not log.device_user_id:
                log._mark_error(_('Missing device user ID'))
                continue
            if not log.event_time:
                log._mark_error(_('Invalid event time'))
                continue
            employee = log._resolve_employee()
            if not employee:
                log._mark_error(_('No employee mapped for device user ID'))
                continue
            log._check_duplicate()

        expanded = self._expand_employee_day_groups(
            seeds.filtered(lambda item: item.state == 'draft'),
        )
        processed = Log.browse()

        for log in expanded.filtered(lambda item: item.state == 'draft'):
            log._check_duplicate()

        remaining = expanded.filtered(lambda item: item.state == 'draft' and item.employee_id)
        groups = defaultdict(lambda: Log.browse())
        for log in remaining:
            policy = log.device_id._get_attendance_policy()
            local_date = log._event_local_date(log.employee_id)
            key = (log.employee_id.id, local_date, policy.id)
            groups[key] |= log

        for group_logs in groups.values():
            group_logs = group_logs.filtered(lambda item: item.state == 'draft')
            if not group_logs:
                continue
            policy = group_logs[0].device_id._get_attendance_policy()
            group_logs = self._collapse_scan_duplicates(group_logs, policy)
            group_logs = group_logs.filtered(lambda item: item.state == 'draft')
            if not group_logs:
                continue
            result = self._process_group(group_logs, policy)
            if result:
                processed |= group_logs.filtered(lambda item: item.state == 'processed')

        return processed

    def _expand_employee_day_groups(self, logs):
        Log = logs.env['fingerprint.device.log']
        expanded = Log.browse()
        for log in logs:
            if not log.employee_id or not log.event_time:
                continue
            local_date = log._event_local_date(log.employee_id)
            day_logs = Log.search([
                ('state', '=', 'draft'),
                ('employee_id', '=', log.employee_id.id),
            ])
            expanded |= day_logs.filtered(
                lambda item: item._event_local_date(item.employee_id) == local_date
            )
        return expanded

    def _collapse_scan_duplicates(self, logs, policy):
        logs = logs.sorted(key=lambda log: (log.event_time, log.id))
        window = timedelta(minutes=policy.duplicate_scan_window_minutes or 0)
        if not window:
            return logs

        kept = logs.browse()
        last_time = None
        for log in logs:
            if last_time and log.event_time and (log.event_time - last_time) < window:
                log._mark_duplicate(kept[-1].attendance_id if kept else None)
                continue
            kept |= log
            last_time = log.event_time
        return kept

    def _process_group(self, logs, policy):
        if policy.process_mode == 'alternating_in_out':
            return self._process_alternating(logs, policy)
        return self._process_first_last(logs, policy)

    def _process_first_last(self, logs, policy):
        Log = logs.env['fingerprint.device.log']
        logs = logs.sorted(key=lambda log: (log.event_time, log.id))
        employee = logs[0].employee_id
        device = logs[0].device_id
        local_date = logs[0]._event_local_date(employee)

        check_in_log = logs[0]
        check_out_log = False
        middle_logs = Log.browse()

        if len(logs) > 1:
            candidate_out = logs[-1]
            gap = candidate_out.event_time - check_in_log.event_time
            min_gap = timedelta(minutes=policy.minimum_checkout_gap_minutes or 0)
            if gap >= min_gap:
                check_out_log = candidate_out
                if policy.ignore_middle_scans and len(logs) > 2:
                    middle_logs = logs[1:-1]
            elif policy.ignore_middle_scans:
                middle_logs = logs[1:]

        check_in = check_in_log.event_time
        check_out = check_out_log.event_time if check_out_log else False

        if check_out and policy.max_shift_hours:
            max_delta = timedelta(hours=policy.max_shift_hours)
            if check_out - check_in > max_delta:
                check_out = check_in + max_delta

        attendance = self._upsert_attendance(
            employee, device, local_date, check_in, check_out,
            check_in_log.external_id, check_in_log.device_user_id, logs,
        )
        if not attendance:
            return False

        self._mark_processed(check_in_log, attendance, 'check_in')
        if check_out_log:
            self._mark_processed(check_out_log, attendance, 'check_out')
        for log in middle_logs:
            self._mark_processed(log, attendance, 'unknown')
        return attendance

    def _process_alternating(self, logs, policy):
        Log = logs.env['fingerprint.device.log']
        logs = logs.sorted(key=lambda log: (log.event_time, log.id))
        employee = logs[0].employee_id
        device = logs[0].device_id
        local_date = logs[0]._event_local_date(employee)
        Attendance = self.env['hr.attendance']

        existing = Attendance.search([
            ('employee_id', '=', employee.id),
            ('date', '=', local_date),
        ], order='check_in asc')
        if existing and not policy.allow_multiple_attendances_per_day:
            existing = existing[:1]
        elif not policy.allow_multiple_attendances_per_day:
            existing = Attendance.browse()

        open_attendance = existing.filtered(lambda att: not att.check_out)[:1]
        attendance_records = list(existing)
        last_attendance = attendance_records[-1] if attendance_records else False

        for log in logs:
            if open_attendance:
                gap = log.event_time - open_attendance.check_in
                min_gap = timedelta(minutes=policy.minimum_checkout_gap_minutes or 0)
                if gap < min_gap:
                    log._mark_duplicate(open_attendance)
                    continue
                attendance = self._write_checkout(open_attendance, log, policy)
                if not attendance:
                    return False
                self._mark_processed(log, attendance, 'check_out')
                open_attendance = False
                last_attendance = attendance
                continue

            if last_attendance and not policy.allow_multiple_attendances_per_day:
                log._mark_duplicate(last_attendance)
                continue

            attendance = self._create_checkin(employee, device, log)
            if not attendance:
                return False
            self._mark_processed(log, attendance, 'check_in')
            open_attendance = attendance
            last_attendance = attendance
            attendance_records.append(attendance)

        return attendance_records[-1] if attendance_records else False

    def _upsert_attendance(self, employee, device, local_date, check_in, check_out,
                           external_log_id, device_user_id, logs):
        Attendance = self.env['hr.attendance']
        attendance = Attendance.search([
            ('employee_id', '=', employee.id),
            ('date', '=', local_date),
        ], order='check_in asc', limit=1)

        vals = logs[0]._prepare_attendance_vals(
            employee, device, check_in, check_out, external_log_id, device_user_id,
        )
        try:
            if attendance:
                write_vals = {
                    'check_in': check_in,
                    'check_out': check_out or False,
                    'attendance_source': 'fingerprint',
                    'device_id': device.id,
                    'device_user_id': device_user_id,
                    'external_log_id': external_log_id,
                    'face_verified': False,
                }
                if check_out:
                    write_vals['out_mode'] = 'technical'
                attendance.write(write_vals)
            else:
                attendance = Attendance.create(vals)
        except (ValidationError, UserError) as exc:
            for log in logs:
                log._mark_error(str(exc))
            return False
        return attendance

    def _create_checkin(self, employee, device, log):
        try:
            return self.env['hr.attendance'].create(
                log._prepare_attendance_vals(
                    employee, device, log.event_time, False,
                    log.external_id, log.device_user_id,
                ),
            )
        except (ValidationError, UserError) as exc:
            log._mark_error(str(exc))
            return False

    def _write_checkout(self, attendance, log, policy):
        check_out = log.event_time
        if policy.max_shift_hours and attendance.check_in:
            max_delta = timedelta(hours=policy.max_shift_hours)
            if check_out - attendance.check_in > max_delta:
                check_out = attendance.check_in + max_delta
        try:
            attendance.write({
                'check_out': check_out,
                'attendance_source': 'fingerprint',
                'device_id': log.device_id.id,
                'device_user_id': log.device_user_id,
                'external_log_id': log.external_id,
                'face_verified': False,
                'out_mode': 'technical',
            })
        except (ValidationError, UserError) as exc:
            log._mark_error(str(exc))
            return False
        return attendance

    def _mark_processed(self, log, attendance, punch_type):
        now = fields.Datetime.now()
        log.write({
            'state': 'processed',
            'attendance_id': attendance.id,
            'employee_id': log.employee_id.id or attendance.employee_id.id,
            'employee_name': (log.employee_id or attendance.employee_id).name,
            'error_message': False,
            'punch_type': punch_type,
            'processed_at': now,
            'processed_by': log.env.user.id,
            'last_attempt_at': now,
            'attempt_count': log.attempt_count + 1,
        })
