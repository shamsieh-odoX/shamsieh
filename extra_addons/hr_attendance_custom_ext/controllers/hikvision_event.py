# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

from odoo.addons.hr_attendance_custom_ext.services.hikvision_http_push import (
    process_http_push,
)
from odoo.addons.hr_attendance_custom_ext.services.hikvision_push_parser import (
    parse_hikvision_push_body,
)

_logger = logging.getLogger(__name__)

HTTP_LISTENING_RATE_LIMIT = 60
HTTP_LISTENING_RATE_WINDOW_SECONDS = 60


class HikvisionEventController(http.Controller):

    def _json_response(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _client_ip(self):
        forwarded = request.httprequest.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.httprequest.remote_addr

    def _resolve_token(self, path_token):
        auth_header = request.httprequest.headers.get('Authorization', '')
        if auth_header.lower().startswith('bearer '):
            return auth_header[7:].strip()
        return path_token

    def _find_device(self, token):
        Device = request.env['fingerprint.device'].sudo()
        return Device._find_http_listening_device(token)

    def _is_rate_limited(self, device):
        Log = request.env['fingerprint.device.log'].sudo()
        window_start = fields.Datetime.now() - timedelta(
            seconds=HTTP_LISTENING_RATE_WINDOW_SECONDS,
        )
        recent_count = Log.search_count([
            ('device_id', '=', device.id),
            ('create_date', '>=', window_start),
        ])
        return recent_count >= HTTP_LISTENING_RATE_LIMIT

    def _parse_push_payload(self):
        http_request = request.httprequest
        body = http_request.get_data(cache=True, as_text=False) or b''
        content_type = http_request.content_type or ''
        try:
            return parse_hikvision_push_body(body, content_type)
        except ValueError as exc:
            _logger.warning(
                'Hikvision HTTP push parse failed: %s content_type=%r bytes=%s',
                exc,
                content_type,
                len(body),
            )
            return None

    @http.route(
        '/hikvision/event/<string:token>',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def hikvision_event(self, token, **kwargs):
        token = self._resolve_token(token)
        device = self._find_device(token)
        if not device:
            return self._json_response({'status': 'error', 'message': 'Not found'}, status=404)

        client_ip = self._client_ip()
        if not device._is_ip_allowed(client_ip):
            _logger.warning(
                'Hikvision HTTP push rejected for %s: IP %s not allowed',
                device.name, client_ip,
            )
            return self._json_response({'status': 'error', 'message': 'Forbidden'}, status=403)

        if self._is_rate_limited(device):
            return self._json_response({'status': 'error', 'message': 'Rate limit exceeded'}, status=429)

        raw_fields = self._parse_push_payload()
        if raw_fields is None:
            device.sudo().write({'http_listening_last_at': fields.Datetime.now()})
            return self._json_response({'status': 'ok', 'reason': 'unparsed payload'})

        try:
            device = device.with_company(device.company_id)
            result = process_http_push(device, raw_fields)
            device.sudo().write({'http_listening_last_at': fields.Datetime.now()})
            if result.get('status') == 'error':
                return self._json_response(result, status=400)
            return self._json_response({'status': 'ok', **result})
        except Exception:
            _logger.exception('Hikvision HTTP push failed for %s', device.name)
            return self._json_response({'status': 'error', 'message': 'processing failed'}, status=500)
