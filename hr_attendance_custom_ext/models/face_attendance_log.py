# -*- coding: utf-8 -*-

import base64
import logging
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.face_provider import get_face_provider
from ..services.face_provider_insightface import (
    FaceProviderUnavailable,
    InsightFaceProvider,
    UNAVAILABLE_MESSAGE,
)

_logger = logging.getLogger(__name__)


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
    match_distance = fields.Float(string='Match Distance')
    distance_meters = fields.Float(string='Geo Distance (m)')
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    ip_address = fields.Char()
    user_agent = fields.Char()
    device_info = fields.Char()
    face_reference_id = fields.Char()
    provider = fields.Char()
    provider_response = fields.Json()
    selfie_image = fields.Binary(
        string='Selfie Image',
        attachment=True,
    )
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

    def _validate_work_location_rules(self):
        self.ensure_one()
        if self.action_type != 'check_in':
            return True
        location_type = self.employee_id._get_effective_work_location_type()
        if location_type == 'office':
            self.verification_status = 'failed'
            self.error_message = _('Office check-in requires geolocation. Use the attendance menu instead.')
            return False
        if location_type != 'home':
            self.verification_status = 'failed'
            self.error_message = _('Face verification is only required when working from home.')
            return False
        return True

    def _validate_single_daily_check_in(self):
        self.ensure_one()
        if self.action_type != 'check_in':
            return True
        try:
            self.employee_id._validate_single_daily_check_in()
        except UserError as exc:
            self.verification_status = 'failed'
            self.error_message = str(exc)
            return False
        return True

    def _get_active_template(self):
        self.ensure_one()
        return self.env['hr.employee.face.template'].get_active_for_employee(self.employee_id)

    def _validate_active_template(self):
        self.ensure_one()
        template = self._get_active_template()
        if not template or not template.get_embedding_vector():
            self.verification_status = 'failed'
            self.error_message = _('No active face template is enrolled for this employee.')
            return False
        return template

    def _run_verification_stub(self):
        self.ensure_one()
        company = self.employee_id.company_id
        if company.face_attendance_stub_enabled:
            self.verification_status = 'passed'
            self.confidence_score = 1.0
            self.provider = 'stub'
            return True
        self.verification_status = 'failed'
        self.error_message = UNAVAILABLE_MESSAGE
        return False

    def _run_verification(self, selfie_image_base64=False):
        """Run InsightFace verification against the active employee template."""
        self.ensure_one()
        company = self.employee_id.company_id
        if company.face_attendance_stub_enabled:
            return self._run_verification_stub()

        template = self._get_active_template()
        if not template or not template.get_embedding_vector():
            self.verification_status = 'failed'
            self.error_message = _('No active face template is enrolled for this employee.')
            return False

        if not selfie_image_base64:
            self.verification_status = 'failed'
            self.error_message = _('Selfie image is required for face verification.')
            return False

        try:
            provider = get_face_provider(company)
            if not provider.is_available():
                raise FaceProviderUnavailable(UNAVAILABLE_MESSAGE)
            selfie_bytes = InsightFaceProvider.decode_base64_image(selfie_image_base64)
            result = provider.verify_face(template.get_embedding_vector(), selfie_bytes)
        except FaceProviderUnavailable:
            self.verification_status = 'failed'
            self.error_message = UNAVAILABLE_MESSAGE
            return False
        except ValueError as exc:
            self.verification_status = 'failed'
            self.error_message = str(exc)
            return False

        self.provider = result.get('provider')
        self.provider_response = result.get('provider_response')
        self.confidence_score = result.get('confidence_score', 0.0)
        self.match_distance = result.get('distance', 0.0)

        threshold = company.face_match_threshold or 0.85
        if not result.get('passed'):
            self.verification_status = 'failed'
            self.error_message = result.get('failure_reason') or _('Face verification failed.')
            return False
        if self.confidence_score < threshold:
            self.verification_status = 'failed'
            self.error_message = _(
                'Face match confidence %(score).2f is below threshold %(threshold).2f.',
                score=self.confidence_score,
                threshold=threshold,
            )
            return False

        self.verification_status = 'passed'
        self.error_message = False
        return True

    def _apply_to_attendance(self):
        self.ensure_one()
        if self.verification_status != 'passed':
            return False

        geo = {}
        if self.latitude and self.longitude:
            geo = {
                'latitude': self.latitude,
                'longitude': self.longitude,
            }

        employee = self.employee_id
        if self.action_type == 'check_in' and employee.attendance_state == 'checked_out':
            attendance = employee.with_context(
                attendance_via_face=True,
            )._attendance_action_change(geo_information=geo or None)
        elif self.action_type == 'check_out' and employee.attendance_state == 'checked_in':
            attendance = employee.with_context(
                attendance_via_face=True,
            )._attendance_action_change(geo_information=geo or None)
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
            'hikvision_punch_type': 'check_in' if self.action_type == 'check_in' else 'check_out',
        })
        employee.sudo().hikvision_presence_status = (
            'working' if self.action_type == 'check_in' else 'checked_out'
        )
        self.attendance_id = attendance.id
        return attendance

    @api.model
    def _find_by_external_token(self, external_token):
        if not external_token:
            return self.browse()
        return self.search([('external_token', '=', external_token)], limit=1)

    @api.model
    def create_face_check(
        self,
        employee,
        action_type,
        latitude=False,
        longitude=False,
        ip_address=False,
        user_agent=False,
        face_reference_id=False,
        selfie_image_base64=False,
        external_token=False,
        device_info=False,
    ):
        """Public API used by controller to create and process a face check.

        TODO: Advanced liveness detection should be implemented later if required.
        """
        if external_token:
            existing = self._find_by_external_token(external_token)
            if existing:
                return existing

        log = self.create({
            'employee_id': employee.id,
            'action_type': action_type,
            'latitude': latitude,
            'longitude': longitude,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'device_info': device_info,
            'face_reference_id': face_reference_id or employee.face_reference_id,
            'selfie_image': selfie_image_base64 or False,
            'external_token': external_token or str(uuid.uuid4()),
        })
        log._validate_remote_allowed()
        if not log._validate_work_location_rules():
            return log
        if not log._validate_single_daily_check_in():
            return log
        company = employee.company_id
        if not company.face_attendance_stub_enabled and not log._validate_active_template():
            return log
        log._run_verification(selfie_image_base64=selfie_image_base64)
        if log.verification_status == 'passed':
            log._apply_to_attendance()
        return log
