# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

from odoo.addons.hr_attendance_custom_ext.services.hikvision_connector import HikvisionConnector
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

        body = request.httprequest.get_data()
        content_type = request.httprequest.content_type or ''
        try:
            raw_payload = parse_hikvision_push_body(body, content_type)
        except ValueError as exc:
            _logger.warning('Hikvision HTTP push parse error for %s: %s', device.name, exc)
            return self._json_response({'status': 'error', 'message': str(exc)}, status=400)

        try:
            device = device.with_company(device.company_id)
            result = HikvisionConnector(device).ingest_push_event(
                raw_payload, process_immediately=True,
            )
        except Exception:
            _logger.exception('Hikvision HTTP push failed for %s', device.name)
            return self._json_response(
                {'status': 'error', 'message': 'Internal server error'},
                status=500,
            )

        return self._json_response({
            'status': 'ok',
            'action': result['action'],
            'external_id': result['external_id'],
            'reason': result['reason'],
        })
