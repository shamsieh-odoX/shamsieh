# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FingerprintDeviceLog(models.Model):
    _name = 'fingerprint.device.log'
    _description = 'Fingerprint Device Log'
    _order = 'punch_time desc, id desc'

    device_id = fields.Many2one(
        'fingerprint.device', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='device_id.company_id', store=True)
    external_id = fields.Char(required=True, index=True)
    device_user_id = fields.Char(required=True, index=True)
    employee_id = fields.Many2one('hr.employee', index=True)
    punch_time = fields.Datetime(required=True, index=True)
    punch_type = fields.Selection(
        selection=[
            ('check_in', 'Check In'),
            ('check_out', 'Check Out'),
            ('unknown', 'Unknown'),
        ],
        default='unknown',
        required=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('processed', 'Processed'),
            ('error', 'Error'),
            ('duplicate', 'Duplicate'),
        ],
        default='draft',
        required=True,
        index=True,
    )
    attendance_id = fields.Many2one('hr.attendance', ondelete='set null')
    error_message = fields.Text()

    _device_external_uniq = models.Constraint(
        'unique(device_id, external_id)',
        'Device log external ID must be unique per device.',
    )

    def _resolve_employee(self):
        self.ensure_one()
        if self.employee_id:
            return self.employee_id
        if not self.device_user_id:
            return self.env['hr.employee']
        employee = self.env['hr.employee'].search([
            ('biometric_device_user_id', '=', self.device_user_id),
            ('company_id', '=', self.device_id.company_id.id),
        ], limit=1)
        if employee:
            self.employee_id = employee.id
        return employee

    def _infer_punch_type(self, employee):
        self.ensure_one()
        if self.punch_type in ('check_in', 'check_out'):
            return self.punch_type
        if employee.attendance_state == 'checked_out':
            return 'check_in'
        return 'check_out'

    def _process_single_log(self):
        self.ensure_one()
        if self.state in ('processed', 'duplicate'):
            return self.attendance_id

        duplicate = self.search([
            ('device_id', '=', self.device_id.id),
            ('external_id', '=', self.external_id),
            ('id', '!=', self.id),
            ('state', '=', 'processed'),
        ], limit=1)
        if duplicate:
            self.write({
                'state': 'duplicate',
                'error_message': _('Duplicate of log %s', duplicate.id),
            })
            return False

        employee = self._resolve_employee()
        if not employee:
            self.write({
                'state': 'error',
                'error_message': _('No employee mapped for device user ID %s', self.device_user_id),
            })
            return False

        punch_type = self._infer_punch_type(employee)
        Attendance = self.env['hr.attendance']

        if punch_type == 'check_in':
            if employee.attendance_state == 'checked_in':
                open_att = employee.last_attendance_id
                self.write({
                    'state': 'processed',
                    'attendance_id': open_att.id,
                    'employee_id': employee.id,
                })
                return open_att

            attendance = Attendance.create({
                'employee_id': employee.id,
                'check_in': self.punch_time,
                'attendance_source': 'fingerprint',
                'device_id': self.device_id.id,
                'device_user_id': self.device_user_id,
                'external_log_id': self.external_id,
                'in_mode': 'technical',
            })
        else:
            open_attendance = Attendance.search([
                ('employee_id', '=', employee.id),
                ('check_out', '=', False),
            ], order='check_in desc', limit=1)
            if not open_attendance:
                self.write({
                    'state': 'error',
                    'error_message': _('No open attendance to check out for %s', employee.name),
                    'employee_id': employee.id,
                })
                return False
            open_attendance.write({
                'check_out': self.punch_time,
                'attendance_source': 'fingerprint',
                'device_id': self.device_id.id,
                'device_user_id': self.device_user_id,
                'external_log_id': self.external_id,
                'out_mode': 'technical',
            })
            attendance = open_attendance

        self.write({
            'state': 'processed',
            'attendance_id': attendance.id,
            'employee_id': employee.id,
            'punch_type': punch_type,
        })
        return attendance

    def _process_pending_logs(self):
        logs = self.search([('state', '=', 'draft')], order='punch_time asc')
        processed = self.browse()
        for log in logs:
            try:
                result = log._process_single_log()
                if result:
                    processed |= log
            except UserError as exc:
                log.write({'state': 'error', 'error_message': str(exc)})
        return processed

    @api.model
    def _cron_process_pending(self):
        return self.search([('state', '=', 'draft')])._process_pending_logs()
