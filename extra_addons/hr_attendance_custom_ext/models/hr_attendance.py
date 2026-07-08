# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    attendance_source = fields.Selection(
        selection=[
            ('fingerprint', 'Fingerprint'),
            ('face', 'Face'),
            ('pin', 'PIN'),
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
    policy_id = fields.Many2one(
        'fingerprint.attendance.policy',
        string='Attendance Policy',
        compute='_compute_policy_id',
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
    hikvision_punch_type = fields.Selection(
        selection=[
            ('check_in', 'Check In'),
            ('break_in', 'Break In'),
            ('break_out', 'Break Out'),
            ('check_out', 'Check Out'),
        ],
        string='Punch Type',
        tracking=True,
        index=True,
        help='Last punch recorded for this attendance day.',
    )
    hikvision_presence_status = fields.Selection(
        related='employee_id.hikvision_presence_status',
        string='Work State',
        readonly=True,
    )
    punch_log_ids = fields.One2many(
        'hr.attendance.punch.log',
        'attendance_id',
        string='Punch History',
    )

    _attendance_external_log_device_uniq = models.Constraint(
        'unique(device_id, external_log_id)',
        'External log ID must be unique per fingerprint device.',
    )

    @api.depends('employee_id', 'employee_id.company_id')
    def _compute_policy_id(self):
        Policy = self.env['fingerprint.attendance.policy']
        for attendance in self:
            if attendance.employee_id:
                attendance.policy_id = Policy.get_company_default(
                    attendance.employee_id.company_id,
                ).id
            else:
                attendance.policy_id = False

    def _get_attendance_policy(self):
        self.ensure_one()
        if self.policy_id:
            return self.policy_id
        if self.employee_id:
            return self.env['fingerprint.attendance.policy'].get_company_default(
                self.employee_id.company_id,
            )
        return self.env['fingerprint.attendance.policy']

    def _refresh_daily_status(self):
        # Daily status rows are technical artifacts generated from attendance writes.
        # They should not fail for regular users (kiosk, fingerprint bridge, employees).
        Status = self.env['hr.attendance.daily.status'].sudo()
        seen = set()
        for attendance in self:
            key = (attendance.employee_id.id, attendance.date)
            if attendance.employee_id and attendance.date and key not in seen:
                seen.add(key)
                Status._generate_for_employee_date(attendance.employee_id.sudo(), attendance.date)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_daily_status()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {'check_in', 'check_out', 'employee_id'} & set(vals):
            self._refresh_daily_status()
        return res

    def _defer_penalties_until_checkout(self):
        """Keep one open day record; compute late/early only after final checkout."""
        self.ensure_one()
        if self.check_out:
            return False
        if self.employee_id.hikvision_presence_status in ('working', 'on_break'):
            return True
        if self.punch_log_ids:
            return True
        return False

    @api.depends(
        'check_in',
        'check_out',
        'employee_id',
        'employee_id.resource_calendar_id',
        'employee_id.hikvision_presence_status',
        'policy_id',
        'punch_log_ids',
    )
    def _compute_attendance_status_fields(self):
        now = fields.Datetime.now()
        for attendance in self:
            attendance.late_minutes = 0
            attendance.early_checkout_minutes = 0
            attendance.missing_checkout = False
            attendance.attendance_status = 'present'

            if not attendance.employee_id or not attendance.check_in:
                continue

            if attendance._defer_penalties_until_checkout():
                continue

            employee = attendance.employee_id
            work_date = attendance.date
            skip, _reason = employee._should_skip_attendance_penalties(work_date)
            if skip:
                attendance.attendance_status = 'on_leave'
                continue

            policy = attendance._get_attendance_policy()
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
                raw_late = int(delta.total_seconds() // 60)
                grace = policy.late_grace_minutes or 0
                attendance.late_minutes = max(0, raw_late - grace)

            if attendance.check_out:
                check_out_local = employee._datetime_to_employee_local(attendance.check_out)
                sched_end_local = employee._datetime_to_employee_local(scheduled_end)
                if check_out_local and sched_end_local and check_out_local < sched_end_local:
                    delta = sched_end_local - check_out_local
                    raw_early = int(delta.total_seconds() // 60)
                    grace = policy.early_checkout_grace_minutes or 0
                    attendance.early_checkout_minutes = max(0, raw_early - grace)
            else:
                tolerance_minutes = policy.missing_checkout_tolerance_minutes
                if not tolerance_minutes:
                    tolerance_hours = employee.company_id.missing_checkout_tolerance_hours or 1.0
                    tolerance_minutes = int(tolerance_hours * 60)
                cutoff = scheduled_end + timedelta(minutes=tolerance_minutes)
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
        Activity = self.env['mail.activity']
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for attendance in incomplete:
            attendance.message_post(
                body='Missing checkout flagged after scheduled end of work day.',
                message_type='notification',
            )
            if activity_type and attendance.employee_id:
                existing = Activity.search([
                    ('res_model', '=', 'hr.attendance'),
                    ('res_id', '=', attendance.id),
                    ('summary', '=', 'Missing checkout'),
                ], limit=1)
                if not existing:
                    Activity.create({
                        'activity_type_id': activity_type.id,
                        'summary': 'Missing checkout',
                        'note': 'Employee has check-in without checkout past tolerance.',
                        'res_model_id': self.env['ir.model']._get('hr.attendance').id,
                        'res_id': attendance.id,
                        'user_id': self.env.ref('base.group_system').users[:1].id or self.env.user.id,
                    })
