# -*- coding: utf-8 -*-

from odoo import api, fields, models


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
        help='Optional external face enrollment reference.',
    )
    face_template_id = fields.Char(
        string='Face Template ID',
        groups='hr_attendance.group_hr_attendance_officer',
        help='Active internal face template reference.',
    )
    face_enrollment_status = fields.Selection(
        selection=[
            ('none', 'Not Enrolled'),
            ('enrolled', 'Enrolled'),
            ('reset', 'Reset'),
        ],
        string='Face Enrollment Status',
        default='none',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_enrolled_at = fields.Datetime(
        string='Face Enrolled At',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_enrolled_by = fields.Many2one(
        'res.users',
        string='Face Enrolled By',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_template_ids = fields.One2many(
        'hr.employee.face.template',
        'employee_id',
        string='Face Templates',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    active_face_template_id = fields.Many2one(
        'hr.employee.face.template',
        string='Active Face Template',
        compute='_compute_active_face_template_id',
        groups='hr_attendance.group_hr_attendance_officer',
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

    @api.depends('face_template_ids', 'face_template_ids.active')
    def _compute_active_face_template_id(self):
        Template = self.env['hr.employee.face.template']
        for employee in self:
            employee.active_face_template_id = Template.get_active_for_employee(employee)

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

    def action_open_face_enroll_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enroll Face Template',
            'res_model': 'hr.employee.face.enroll.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }

    def action_reset_face_enrollment(self):
        self.ensure_one()
        templates = self.face_template_ids.filtered('active')
        if templates:
            templates.write({'active': False})
        self.write({
            'face_enrollment_status': 'reset',
            'face_template_id': False,
            'face_enrolled_at': False,
            'face_enrolled_by': False,
        })
        return True

    def action_view_face_templates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Face Templates',
            'res_model': 'hr.employee.face.template',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

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
