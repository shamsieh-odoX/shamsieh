# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models

from ..services.attendance_processor import AttendanceProcessor

_logger = logging.getLogger(__name__)


class FingerprintDeviceLog(models.Model):
    _name = 'fingerprint.device.log'
    _description = 'Fingerprint Device Log'
    _order = 'event_time desc, id desc'

    device_id = fields.Many2one(
        'fingerprint.device', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='device_id.company_id', store=True)
    external_id = fields.Char(required=True, index=True)
    serial_no = fields.Char(index=True)
    verify_no = fields.Char(index=True)
    device_user_id = fields.Char(index=True)
    employee_name = fields.Char(
        string='Stored Employee Name',
        help='Odoo employee name at sync time (not the device scanner label).',
    )
    display_employee_name = fields.Char(
        string='Employee Name',
        compute='_compute_display_employee_name',
        store=True,
    )
    employee_id = fields.Many2one('hr.employee', index=True)
    event_time = fields.Datetime(required=True, index=True)
    event_type = fields.Char(index=True)
    major = fields.Integer()
    minor = fields.Integer()
    authentication_method = fields.Char()
    raw_payload = fields.Json()
    request_headers = fields.Json()
    request_content_type = fields.Char()
    request_query_params = fields.Json()
    request_form = fields.Json()
    request_files = fields.Json()
    raw_request_body = fields.Text()
    raw_request_body_size = fields.Integer()
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('processed', 'Processed'),
            ('error', 'Error'),
            ('duplicate', 'Duplicate'),
            ('ignored', 'Ignored'),
        ],
        default='draft',
        required=True,
        index=True,
    )
    attendance_id = fields.Many2one('hr.attendance', ondelete='set null')
    error_message = fields.Text()
    processed_at = fields.Datetime(readonly=True)
    processed_by = fields.Many2one('res.users', readonly=True)
    attempt_count = fields.Integer(default=0)
    last_attempt_at = fields.Datetime(readonly=True)

    punch_time = fields.Datetime(related='event_time', store=True, string='Punch Time')
    punch_type = fields.Selection(
        selection=[
            ('check_in', 'Check In'),
            ('check_out', 'Check Out'),
            ('unknown', 'Unknown'),
        ],
        default='unknown',
    )

    _device_external_uniq = models.Constraint(
        'unique(device_id, external_id)',
        'Device log external ID must be unique per device.',
    )

    @api.depends('employee_id', 'employee_id.name', 'employee_name')
    def _compute_display_employee_name(self):
        for log in self:
            if log.employee_id:
                log.display_employee_name = log.employee_id.name
            else:
                log.display_employee_name = log.employee_name or ''

    @api.model
    def _attendance_log_domain(self):
        """Logs shown in sync UI: attendance scans only (check-in/out or pending draft)."""
        return [
            ('state', 'not in', ('ignored', 'duplicate')),
            '|',
            ('punch_type', 'in', ('check_in', 'check_out')),
            ('state', '=', 'draft'),
        ]

    def _employee_timezone(self, employee):
        return (
            employee.tz
            or employee.company_id.resource_calendar_id.tz
            or self.env.user.tz
            or 'UTC'
        )

    def _event_local_date(self, employee):
        self.ensure_one()
        if not self.event_time:
            return False
        return fields.Datetime.context_timestamp(
            self.with_context(tz=self._employee_timezone(employee)),
            self.event_time,
        ).date()

    def _resolve_employee(self):
        self.ensure_one()
        if self.employee_id:
            return self.employee_id
        if not self.device_user_id:
            return self.env['hr.employee']
        payload = self.raw_payload or {}
        device_user_id = str(self.device_user_id).strip()
        domain = [
            ('biometric_device_user_id', '=', device_user_id),
            ('company_id', '=', self.device_id.company_id.id),
        ]
        _logger.info(
            'Attendance processor mapping log_id=%s external_id=%s parsed_payload=%s '
            'extracted_identifier=%r lookup_field=%s domain=%s compared_value=%r',
            self.id,
            self.external_id,
            json.dumps(payload, default=str),
            device_user_id,
            'biometric_device_user_id',
            domain,
            device_user_id,
        )
        count = self.env['hr.employee'].search_count(domain)
        _logger.info(
            'Attendance processor mapping log_id=%s result_count=%s',
            self.id,
            count,
        )
        employee = self.env['hr.employee'].search(domain, limit=1)
        if employee:
            _logger.info(
                'Attendance processor mapping log_id=%s succeeded employee_id=%s employee_name=%r',
                self.id,
                employee.id,
                employee.name,
            )
            self.write({
                'employee_id': employee.id,
                'employee_name': employee.name,
            })
        else:
            employees = self.env['hr.employee'].search([
                ('company_id', '=', self.device_id.company_id.id),
            ])
            compared = [
                {
                    'id': emp.id,
                    'name': emp.name,
                    'biometric_device_user_id': emp.biometric_device_user_id or '',
                }
                for emp in employees
            ]
            _logger.info(
                'Attendance processor mapping log_id=%s no match for identifier=%r. '
                'Company employee biometric values=%s',
                self.id,
                device_user_id,
                compared,
            )
        return employee

    def _mark_error(self, message):
        now = fields.Datetime.now()
        self.write({
            'state': 'error',
            'error_message': message,
            'last_attempt_at': now,
            'attempt_count': self.attempt_count + 1,
        })

    def _mark_duplicate(self, attendance=None):
        self.ensure_one()
        vals = {
            'state': 'duplicate',
            'error_message': False,
            'processed_at': fields.Datetime.now(),
            'processed_by': self.env.user.id,
            'last_attempt_at': fields.Datetime.now(),
            'attempt_count': self.attempt_count + 1,
        }
        if attendance:
            vals['attendance_id'] = attendance.id
        self.write(vals)
        return attendance

    def _check_duplicate(self):
        self.ensure_one()
        if self.state in ('processed', 'duplicate', 'ignored'):
            return self.attendance_id

        sibling = self.search([
            ('device_id', '=', self.device_id.id),
            ('external_id', '=', self.external_id),
            ('id', '!=', self.id),
            ('state', 'in', ('processed', 'duplicate')),
        ], limit=1)
        if sibling:
            return self._mark_duplicate(sibling.attendance_id)

        attendance = self.env['hr.attendance'].search([
            ('device_id', '=', self.device_id.id),
            ('external_log_id', '=', self.external_id),
        ], limit=1)
        if attendance:
            return self._mark_duplicate(attendance)
        return False

    def _prepare_attendance_vals(self, employee, device, check_in, check_out, external_log_id, device_user_id):
        vals = {
            'employee_id': employee.id,
            'check_in': check_in,
            'attendance_source': 'fingerprint',
            'device_id': device.id,
            'device_user_id': device_user_id,
            'external_log_id': external_log_id,
            'face_verified': False,
            'in_mode': 'technical',
        }
        if check_out:
            vals['check_out'] = check_out
            vals['out_mode'] = 'technical'
        return vals

    def _process_pending_logs(self):
        """Process draft logs into hr.attendance using attendance policy."""
        processor = AttendanceProcessor(self.env)
        return processor.process_logs(self)

    def action_process_selected(self):
        self._process_pending_logs()
        return True

    def action_reset_to_draft(self):
        resettable = self.filtered(lambda log: log.state in ('error', 'ignored'))
        resettable.write({
            'state': 'draft',
            'error_message': False,
            'attendance_id': False,
            'processed_at': False,
            'processed_by': False,
        })
        return True

    @api.model
    def _cron_process_pending(self):
        devices = self.env['fingerprint.device'].search([('active', '=', True)])
        logs = self.search([
            ('state', '=', 'draft'),
            ('device_id', 'in', devices.ids),
        ])
        return logs._process_pending_logs()

    @api.model
    def _cron_purge_raw_payload(self):
        Policy = self.env['fingerprint.attendance.policy']
        for company in self.env['res.company'].search([]):
            policy = Policy.get_company_default(company)
            days = policy.raw_payload_retention_days or 0
            if days <= 0:
                continue
            cutoff = fields.Datetime.now() - timedelta(days=days)
            old_logs = self.search([
                ('company_id', '=', company.id),
                ('create_date', '<', cutoff),
                ('raw_payload', '!=', False),
            ])
            old_logs.write({'raw_payload': False})
