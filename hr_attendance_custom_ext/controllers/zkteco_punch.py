# -*- coding: utf-8 -*-
"""Real-time ZKTeco punch HTTP API (no sync / no lookback)."""

import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.hr_attendance_custom_ext.services.zkteco_punch import process_zkteco_punch

_logger = logging.getLogger(__name__)


class ZktecoPunchController(http.Controller):

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _token(self, path_token):
        auth = request.httprequest.headers.get('Authorization', '')
        if auth.lower().startswith('bearer '):
            return auth[7:].strip()
        header_token = request.httprequest.headers.get('X-ZKTeco-Token', '').strip()
        if header_token:
            return header_token
        return (path_token or '').strip()

    def _payload(self):
        data = {}
        try:
            body = request.httprequest.get_data(as_text=True) or ''
            if body.strip():
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    data.update(parsed)
        except Exception:
            _logger.debug('ZKTeco punch body is not JSON', exc_info=True)
        # Allow form / query overrides for simple clients
        for key in (
            'device_user_id', 'employee_no', 'user_id', 'pin',
            'punch_type', 'punch', 'event_time', 'punch_time', 'timestamp',
            'external_id',
        ):
            value = request.params.get(key)
            if value not in (None, ''):
                data[key] = value
        return data

    @http.route(
        ['/zkteco/punch/<string:token>', '/zkteco/punch/<string:token>/'],
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def zkteco_punch(self, token, **kwargs):
        token = self._token(token)
        Device = request.env['fingerprint.device'].sudo()
        device = Device._find_zkteco_punch_device(token)
        if not device:
            return self._json({'status': 'error', 'message': 'Not found'}, status=404)

        try:
            result = process_zkteco_punch(device.with_company(device.company_id), self._payload())
            status_code = 200
            if result.get('status') == 'error':
                status_code = 400
            elif result.get('status') == 'employee_not_found':
                status_code = 404
            return self._json(result, status=status_code)
        except Exception:
            _logger.exception('ZKTeco punch API failed for %s', device.name)
            return self._json({'status': 'error', 'message': 'processing failed'}, status=500)

    @http.route(
        ['/zkteco/punch/<string:token>', '/zkteco/punch/<string:token>/'],
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def zkteco_punch_help(self, token, **kwargs):
        """Simple discovery / health for the punch URL."""
        token = self._token(token)
        device = request.env['fingerprint.device'].sudo()._find_zkteco_punch_device(token)
        if not device:
            return self._json({'status': 'error', 'message': 'Not found'}, status=404)
        return self._json({
            'status': 'ok',
            'service': 'zkteco_punch_api',
            'device': device.name,
            'accepted_punch_types': ['check_in', 'check_out', 'break_out', 'break_in'],
            'post_example': {
                'device_user_id': '2',
                'punch_type': 'check_in',
                'event_time': '2026-08-04 09:00:00',
            },
        })
