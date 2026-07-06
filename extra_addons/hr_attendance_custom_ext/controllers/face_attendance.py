# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class FaceAttendanceController(http.Controller):

    @http.route('/hr_attendance_custom/face/check', type='jsonrpc', auth='user')
    def face_check(
        self,
        action_type='check_in',
        latitude=False,
        longitude=False,
        selfie_image_base64=False,
        external_token=False,
        device_info=False,
        employee_id=False,
    ):
        """Remote face attendance endpoint using InsightFace verification.

        TODO: Advanced liveness detection should be implemented later if required.
        """
        env = request.env
        employee = env.user.employee_id
        if employee_id:
            if not env.user.has_group('hr_attendance.group_hr_attendance_officer'):
                return {
                    'status': 'error',
                    'message': 'Not allowed to check attendance for another employee.',
                }
            employee = env['hr.employee'].browse(employee_id)
            if not employee or employee.company_id not in env.user.company_ids:
                return {'status': 'error', 'message': 'Employee not found.'}
        if not employee:
            return {'status': 'error', 'message': 'No employee linked to user.'}

        try:
            log = env['face.attendance.log'].sudo().create_face_check(
                employee=employee,
                action_type=action_type,
                latitude=latitude,
                longitude=longitude,
                selfie_image_base64=selfie_image_base64,
                external_token=external_token,
                device_info=device_info or request.httprequest.user_agent.string,
                ip_address=request.httprequest.remote_addr,
                user_agent=request.httprequest.user_agent.string,
            )
        except UserError as exc:
            return {'status': 'error', 'message': str(exc)}

        return {
            'status': log.verification_status,
            'log_id': log.id,
            'attendance_id': log.attendance_id.id if log.attendance_id else False,
            'confidence_score': log.confidence_score,
            'distance_meters': log.distance_meters,
            'message': log.error_message or 'OK',
        }
