# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    attendance_source = fields.Selection(
        selection=[
            ('fingerprint', 'Fingerprint'),
            ('face', 'Face'),
            ('manual', 'Manual'),
            ('kiosk', 'Kiosk'),
            ('systray', 'Systray'),
            ('import', 'Import'),
        ],
        string='Attendance Source',
        tracking=True,
        index=True,
    )
    attendance_status = fields.Selection(
        selection=[
            ('present', 'Present'),
            ('late', 'Late'),
            ('early_leave', 'Early Leave'),
            ('absent', 'Absent'),
            ('incomplete', 'Incomplete'),
            ('on_leave', 'On Leave'),
        ],
        string='Attendance Status',
        compute='_compute_attendance_status_fields',
        store=True,
        index=True,
    )
    late_minutes = fields.Integer(
        string='Late Minutes',
        compute='_compute_attendance_status_fields',
        store=True,
    )
    early_checkout_minutes = fields.Integer(
        string='Early Checkout Minutes',
        compute='_compute_attendance_status_fields',
        store=True,
    )
    missing_checkout = fields.Boolean(
        string='Missing Checkout',
        compute='_compute_attendance_status_fields',
        store=True,
    )
    device_id = fields.Many2one(
        'fingerprint.device',
        string='Fingerprint Device',
        ondelete='set null',
        index=True,
    )
    device_user_id = fields.Char(string='Device User ID', index=True)
    external_log_id = fields.Char(string='External Log ID', index=True)
    face_verified = fields.Boolean(string='Face Verified')

    _attendance_external_log_device_uniq = models.Constraint(
        'unique(device_id, external_log_id)',
        'External log ID must be unique per fingerprint device.',
    )

    @api.depends('check_in', 'check_out', 'employee_id', 'employee_id.resource_calendar_id')
    def _compute_attendance_status_fields(self):
        now = fields.Datetime.now()
        for attendance in self:
            attendance.late_minutes = 0
            attendance.early_checkout_minutes = 0
            attendance.missing_checkout = False
            attendance.attendance_status = 'present'

            if not attendance.employee_id or not attendance.check_in:
                continue

            employee = attendance.employee_id
            work_date = attendance.date
            scheduled_start, scheduled_end = employee._get_work_day_bounds(work_date)

            if not scheduled_start:
                if not attendance.check_out:
                    attendance.missing_checkout = True
                    attendance.attendance_status = 'incomplete'
                continue

            check_in_local = employee._datetime_to_employee_local(attendance.check_in)
            sched_start_local = employee._datetime_to_employee_local(scheduled_start)
            if check_in_local and sched_start_local and check_in_local > sched_start_local:
                delta = check_in_local - sched_start_local
                attendance.late_minutes = int(delta.total_seconds() // 60)

            if attendance.check_out:
                check_out_local = employee._datetime_to_employee_local(attendance.check_out)
                sched_end_local = employee._datetime_to_employee_local(scheduled_end)
                if check_out_local and sched_end_local and check_out_local < sched_end_local:
                    delta = sched_end_local - check_out_local
                    attendance.early_checkout_minutes = int(delta.total_seconds() // 60)
            else:
                tolerance_hours = attendance.employee_id.company_id.missing_checkout_tolerance_hours
                cutoff = scheduled_end + timedelta(hours=tolerance_hours)
                if now > cutoff:
                    attendance.missing_checkout = True

            if attendance.missing_checkout or not attendance.check_out:
                attendance.attendance_status = 'incomplete'
            elif attendance.late_minutes > 0 and attendance.early_checkout_minutes > 0:
                attendance.attendance_status = 'early_leave'
            elif attendance.late_minutes > 0:
                attendance.attendance_status = 'late'
            elif attendance.early_checkout_minutes > 0:
                attendance.attendance_status = 'early_leave'
            else:
                attendance.attendance_status = 'present'

    @api.model
    def _cron_recompute_status(self):
        today = fields.Date.today()
        attendances = self.search([
            ('date', '>=', today - timedelta(days=7)),
            ('date', '<=', today),
        ])
        attendances._compute_attendance_status_fields()

    @api.model
    def _cron_flag_missing_checkouts(self):
        open_attendances = self.search([('check_out', '=', False)])
        open_attendances._compute_attendance_status_fields()
        incomplete = open_attendances.filtered(lambda a: a.missing_checkout)
        if incomplete:
            for attendance in incomplete:
                attendance.message_post(
                    body='Missing checkout flagged after scheduled end of work day.',
                    message_type='notification',
                )
