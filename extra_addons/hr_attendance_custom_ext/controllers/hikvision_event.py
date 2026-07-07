# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

from odoo.addons.hr_attendance_custom_ext.services.hikvision import _to_utc_datetime

_logger = logging.getLogger(__name__)

HTTP_LISTENING_RATE_LIMIT = 60
HTTP_LISTENING_RATE_WINDOW_SECONDS = 60

KNOWN_PAYLOAD_KEYS = frozenset({
    'eventType',
    'majorEventType',
    'subEventType',
    'serialNo',
    'verifyNo',
    'dateTime',
})


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

    def _parse_event_log(self):
        """Read multipart form and parse the event_log field as JSON."""
        form = request.httprequest.form
        event_log = form.get('event_log')
        if not event_log:
            _logger.warning(
                'Hikvision HTTP push missing event_log form field; form keys: %s',
                sorted(form.keys()),
            )
            return None
        try:
            parsed = json.loads(event_log)
        except (json.JSONDecodeError, TypeError) as exc:
            _logger.warning('Hikvision event_log JSON parse error: %s', exc)
            return None
        if not isinstance(parsed, dict):
            _logger.warning(
                'Hikvision event_log is not a JSON object: %r', type(parsed),
            )
            return None
        return parsed

    def _log_unknown_keys(self, device, payload):
        unknown = sorted(set(payload.keys()) - KNOWN_PAYLOAD_KEYS)
        if unknown:
            _logger.info(
                'Hikvision HTTP push from %s: unknown payload keys %s; '
                'full payload: %s',
                device.name,
                unknown,
                json.dumps(payload, default=str),
            )

    @staticmethod
    def _coerce_int(value):
        if value is None:
            return False
        try:
            return int(value)
        except (TypeError, ValueError):
            return False

    @classmethod
    def _external_id_from_payload(cls, payload):
        parts = []
        for key in ('serialNo', 'verifyNo', 'dateTime'):
            value = payload.get(key)
            if value is not None and str(value) != '':
                parts.append(str(value))
        if parts:
            return '-'.join(parts)
        return f'push-{fields.Datetime.now()}'

    @classmethod
    def _build_log_vals(cls, device, payload):
        event_time = _to_utc_datetime(payload.get('dateTime')) or fields.Datetime.now()
        return {
            'device_id': device.id,
            'external_id': cls._external_id_from_payload(payload),
            'serial_no': (
                str(payload['serialNo'])
                if payload.get('serialNo') is not None else False
            ),
            'verify_no': (
                str(payload['verifyNo'])
                if payload.get('verifyNo') is not None else False
            ),
            'event_type': (
                str(payload['eventType'])
                if payload.get('eventType') is not None else False
            ),
            'major': cls._coerce_int(payload.get('majorEventType')),
            'minor': cls._coerce_int(payload.get('subEventType')),
            'event_time': event_time,
            'raw_payload': payload,
            'state': 'draft',
        }

    def _record_payload(self, device, payload):
        Log = request.env['fingerprint.device.log'].sudo()
        vals = self._build_log_vals(device, payload)
        existing = Log.search([
            ('device_id', '=', device.id),
            ('external_id', '=', vals['external_id']),
        ], limit=1)
        if existing:
            _logger.info(
                'Hikvision HTTP push duplicate for %s external_id=%s',
                device.name, vals['external_id'],
            )
            return existing
        return Log.create(vals)

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

        payload = self._parse_event_log()
        if payload is not None:
            try:
                device = device.with_company(device.company_id)
                self._log_unknown_keys(device, payload)
                self._record_payload(device, payload)
                device.write({'http_listening_last_at': fields.Datetime.now()})
            except Exception:
                _logger.exception('Hikvision HTTP push record failed for %s', device.name)

        return self._json_response({'status': 'ok'})
