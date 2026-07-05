# -*- coding: utf-8 -*-

import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FaceAttendanceLog(models.Model):
    _name = 'face.attendance.log'
    _description = 'Face Attendance Log'
    _order = 'create_date desc, id desc'

    employee_id = fields.Many2one('hr.employee', required=True, index=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True)
    action_type = fields.Selection(
        selection=[('check_in', 'Check In'), ('check_out', 'Check Out')],
        required=True,
    )
    verification_status = fields.Selection(
        selection=[
            ('passed', 'Passed'),
            ('failed', 'Failed'),
            ('pending', 'Pending'),
        ],
        default='pending',
        required=True,
        index=True,
    )
    confidence_score = fields.Float()
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    ip_address = fields.Char()
    user_agent = fields.Char()
    face_reference_id = fields.Char()
    attendance_id = fields.Many2one('hr.attendance', ondelete='set null')
    external_token = fields.Char(index=True, copy=False, default=lambda self: str(uuid.uuid4()))
    error_message = fields.Text()

    _external_token_uniq = models.Constraint(
        'unique(external_token)',
        'External token must be unique.',
    )

    def _validate_remote_allowed(self):
        self.ensure_one()
        if not self.employee_id.remote_attendance_allowed:
            raise UserError(_('Remote face attendance is not allowed for this employee.'))

    def _run_verification_stub(self):
        """Placeholder verification until provider is confirmed.

        TODO: Face recognition provider needs confirmation.
        TODO: Local/on-device vs cloud verification needs confirmation.
        TODO: Raw image/template storage needs legal/privacy confirmation.
        TODO: Confidence threshold needs confirmation.
        TODO: Geolocation radius needs confirmation.
        TODO: Fraud prevention rules need confirmation.
        """
        self.ensure_one()
        company = self.employee_id.company_id
        if company.face_attendance_stub_enabled:
            self.verification_status = 'passed'
            self.confidence_score = 1.0
            return True
        self.verification_status = 'failed'
        self.error_message = _(
            'Face provider not configured. Enable stub on company for development only.'
        )
        return False

    def _apply_to_attendance(self):
        self.ensure_one()
        if self.verification_status != 'passed':
            return False

        geo = {}
        if self.latitude and self.longitude:
            geo = {
                'latitude': self.latitude,
                'longitude': self.longitude,
                'mode': 'face',
            }

        employee = self.employee_id
        if self.action_type == 'check_in' and employee.attendance_state == 'checked_out':
            attendance = employee._attendance_action_change(geo_information=geo or None)
        elif self.action_type == 'check_out' and employee.attendance_state == 'checked_in':
            attendance = employee._attendance_action_change(geo_information=geo or None)
        else:
            action = self.action_type
            state = employee.attendance_state
            raise UserError(
                _('Cannot perform %(action)s while employee is %(state)s.', action=action, state=state)
            )

        attendance.write({
            'attendance_source': 'face',
            'face_verified': True,
            'external_log_id': self.external_token,
        })
        self.attendance_id = attendance.id
        return attendance

    @api.model
    def create_face_check(self, employee, action_type, latitude=False, longitude=False,
                          ip_address=False, user_agent=False, face_reference_id=False):
        """Public API used by controller to create and process a face check."""
        log = self.create({
            'employee_id': employee.id,
            'action_type': action_type,
            'latitude': latitude,
            'longitude': longitude,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'face_reference_id': face_reference_id or employee.face_reference_id,
        })
        log._validate_remote_allowed()
        log._run_verification_stub()
        if log.verification_status == 'passed':
            log._apply_to_attendance()
        return log
