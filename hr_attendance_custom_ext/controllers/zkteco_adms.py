# -*- coding: utf-8 -*-
"""ZKTeco ADMS / iclock push endpoints (device → Odoo), Hikvision-style live sync."""

import logging

from odoo import fields, http
from odoo.http import request

from odoo.addons.hr_attendance_custom_ext.services.zkteco_adms import parse_attlog_body

_logger = logging.getLogger(__name__)


class ZktecoAdmsController(http.Controller):
    """Minimal ADMS server so ZKTeco can push attendance without Odoo Sync/pyzk."""

    def _plain(self, body='OK', status=200):
        return request.make_response(
            body,
            headers=[('Content-Type', 'text/plain; charset=utf-8')],
            status=status,
        )

    def _serial(self):
        params = request.httprequest.args
        return (
            params.get('SN')
            or params.get('sn')
            or request.httprequest.headers.get('SN')
            or ''
        ).strip()

    def _find_device(self, serial):
        Device = request.env['fingerprint.device'].sudo()
        return Device._find_zkteco_adms_device(serial)

    def _touch(self, device):
        device._touch_http_listening_last_at(force=True)

    @http.route(
        ['/iclock/cdata', '/iclock/cdata/'],
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
        save_session=False,
    )
    def iclock_cdata(self, **kwargs):
        serial = self._serial()
        device = self._find_device(serial)
        table = (request.httprequest.args.get('table') or '').strip().upper()
        _logger.info(
            'ZKTeco ADMS cdata SN=%r table=%r method=%s ip=%s',
            serial, table, request.httprequest.method, request.httprequest.remote_addr,
        )

        if not device:
            # Still ACK so devices keep retrying cleanly after SN is configured.
            _logger.warning('ZKTeco ADMS unknown serial %r', serial)
            return self._plain('OK')

        if request.httprequest.method == 'GET':
            self._touch(device)
            # Handshake / options poll.
            return self._plain('OK')

        body = request.httprequest.get_data(as_text=True) or ''
        if table in ('ATTLOG', 'ATTLOGUE', '') or 'ATTLOG' in table:
            events = parse_attlog_body(
                body,
                device_tz=device.device_timezone or 'Asia/Amman',
                serial=serial,
            )
            if events:
                # Convert datetimes for ORM ingest path.
                for event in events:
                    if event.get('event_time'):
                        event['event_time'] = fields.Datetime.to_string(event['event_time'])
                stats = device.ingest_external_attendance_events(events)
                _logger.info('ZKTeco ADMS ATTLOG SN=%s stats=%s', serial, stats)
                self._touch(device)
                # Friendlier status line for ADMS (not "Bridge ingest").
                device.write({
                    'last_sync_message': (
                        'ADMS push: fetched %(fetched)s | stored %(stored)s | '
                        'ignored %(ignored)s | duplicates %(duplicates)s | '
                        'unmapped %(unmapped)s | skipped %(skipped)s'
                    ) % stats,
                })
                return self._plain(f'OK: {stats.get("stored", 0)}')
            self._touch(device)
            return self._plain('OK')

        # OPERLOG / USER / options — acknowledge only.
        self._touch(device)
        return self._plain('OK')

    @http.route(
        ['/iclock/getrequest', '/iclock/getrequest/'],
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
        save_session=False,
    )
    def iclock_getrequest(self, **kwargs):
        serial = self._serial()
        device = self._find_device(serial)
        if device:
            self._touch(device)
        # No pending commands.
        return self._plain('OK')

    @http.route(
        ['/iclock/registry', '/iclock/registry/'],
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
        save_session=False,
    )
    def iclock_registry(self, **kwargs):
        serial = self._serial()
        device = self._find_device(serial)
        if device:
            self._touch(device)
        return self._plain('OK')
