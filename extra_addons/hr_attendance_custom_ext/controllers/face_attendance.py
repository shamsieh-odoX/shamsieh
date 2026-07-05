# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class FaceAttendanceController(http.Controller):

    @http.route('/hr_attendance_custom/face/check', type='jsonrpc', auth='user')
    def face_check(self, action_type='check_in', latitude=False, longitude=False):
        """Placeholder face attendance endpoint.

        TODO: Integrate real face recognition provider when confirmed.
        TODO: Add token/API-key auth for mobile clients if needed.
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'status': 'error', 'message': 'No employee linked to user.'}

        log = request.env['face.attendance.log'].sudo().create_face_check(
            employee=employee,
            action_type=action_type,
            latitude=latitude,
            longitude=longitude,
            ip_address=request.httprequest.remote_addr,
            user_agent=request.httprequest.user_agent.string,
        )
        return {
            'status': log.verification_status,
            'log_id': log.id,
            'attendance_id': log.attendance_id.id if log.attendance_id else False,
            'message': log.error_message or 'OK',
        }
