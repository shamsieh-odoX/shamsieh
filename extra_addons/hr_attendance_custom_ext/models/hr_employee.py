# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = ['hr.employee', 'attendance.calendar.mixin']
    _name = 'hr.employee'

    biometric_device_user_id = fields.Char(
        string='Biometric Device User ID',
        index=True,
        groups='hr_attendance.group_hr_attendance_officer',
        help='User ID on the fingerprint device; used to map device logs to this employee.',
    )
    face_reference_id = fields.Char(
        string='Face Reference ID',
        groups='hr_attendance.group_hr_attendance_officer',
        help='External face enrollment reference. Provider and storage policy need confirmation.',
    )
    face_template_id = fields.Char(
        string='Face Template ID',
        groups='hr_attendance.group_hr_attendance_officer',
        help='Optional template/token reference. Whether templates stay on-device only needs confirmation.',
    )
    attendance_required = fields.Boolean(
        string='Attendance Required',
        default=True,
        groups='hr_attendance.group_hr_attendance_officer',
    )
    remote_attendance_allowed = fields.Boolean(
        string='Remote Face Attendance Allowed',
        default=False,
        groups='hr_attendance.group_hr_attendance_officer',
        help='Allows remote check-in/out via face verification (§9).',
    )

    def write(self, vals):
        res = super().write(vals)
        if 'biometric_device_user_id' in vals:
            self._relink_fingerprint_logs()
        return res

    def _relink_fingerprint_logs(self):
        Log = self.env['fingerprint.device.log']
        for employee in self.filtered('biometric_device_user_id'):
            logs = Log.search([
                ('device_user_id', '=', employee.biometric_device_user_id),
                ('company_id', '=', employee.company_id.id),
                ('employee_id', '=', False),
                ('state', 'in', ('draft', 'error')),
            ])
            if not logs:
                continue
            logs.write({'employee_id': employee.id})
            logs.filtered(lambda log: log.state == 'error').write({
                'state': 'draft',
                'error_message': False,
            })

    def _attendance_action_change(self, geo_information=None):
        attendance = super()._attendance_action_change(geo_information=geo_information)
        if attendance and not attendance.attendance_source:
            mode_map = {
                'kiosk': 'kiosk',
                'systray': 'systray',
            }
            if self.attendance_state == 'checked_in':
                source = mode_map.get(attendance.in_mode, 'manual')
            else:
                source = mode_map.get(attendance.out_mode, 'manual')
            attendance.attendance_source = source
        return attendance
