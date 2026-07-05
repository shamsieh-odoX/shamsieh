# -*- coding: utf-8 -*-

import base64
import csv
import io
import logging
from datetime import timedelta

import requests
from requests.auth import HTTPDigestAuth

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HikvisionConnector:
    """Hikvision ISAPI connector — endpoints vary by device model.

    TODO: Confirm exact Hikvision model.
    TODO: Confirm device IP and port.
    TODO: Confirm whether device exposes ISAPI attendance/access event logs.
    TODO: Confirm whether event type identifies check-in/check-out or only access granted.
    TODO: Confirm whether employee number/device user ID maps to Odoo employee.
    """

    DEFAULT_EVENTS_PATH = '/ISAPI/AccessControl/AcsEvent'
    DEFAULT_TIMEOUT = 15

    def __init__(self, device):
        self.device = device

    def _base_url(self):
        port = self.device.device_port or 80
        return f'http://{self.device.device_ip}:{port}'

    def _auth(self):
        if self.device.username:
            return HTTPDigestAuth(self.device.username, self.device.password or '')
        return None

    def test_connection(self):
        self.device.ensure_one()
        if not self.device.device_ip:
            raise UserError(_('Device IP is required.'))
        if self.device.api_type == 'file_import':
            return True
        url = f'{self._base_url()}/ISAPI/System/deviceInfo'
        try:
            response = requests.get(
                url, auth=self._auth(), timeout=self.DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            raise UserError(_('Connection failed: %s', exc)) from exc

    def get_capabilities(self):
        return {
            'api_type': self.device.api_type,
            'events_path': self.DEFAULT_EVENTS_PATH,
            'note': 'Capabilities depend on Hikvision model — needs confirmation.',
        }

    def fetch_attendance_logs(self, date_from, date_to):
        if self.device.api_type == 'file_import':
            return self._fetch_from_csv_payload()
        if self.device.api_type == 'hikvision':
            return self._fetch_isapi_events(date_from, date_to)
        if self.device.api_type == 'zkteco':
            raise UserError(_('ZKTeco integration is not implemented yet.'))
        raise UserError(_('Unsupported API type: %s', self.device.api_type))

    def _fetch_isapi_events(self, date_from, date_to):
        """Placeholder ISAPI fetch — returns empty until device spec is confirmed."""
        _logger.info(
            'Hikvision ISAPI fetch placeholder for device %s (%s to %s). '
            'Configure exact endpoint after model confirmation.',
            self.device.name, date_from, date_to,
        )
        # TODO: Implement ISAPI XML/JSON parsing when device model is confirmed.
        return []

    def _fetch_from_csv_payload(self):
        if not self.device.import_file_data:
            return []
        raw = self.device.import_file_data
        if isinstance(raw, str):
            content = base64.b64decode(raw).decode('utf-8')
        else:
            content = base64.b64decode(raw).decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        return list(reader)

    @staticmethod
    def normalize_log(raw_log):
        """Map vendor payload to standard dict."""
        if isinstance(raw_log, dict):
            external_id = (
                raw_log.get('external_id')
                or raw_log.get('id')
                or raw_log.get('serialNo')
                or raw_log.get('employeeNoString')
            )
            device_user_id = (
                raw_log.get('device_user_id')
                or raw_log.get('employeeNo')
                or raw_log.get('employeeNoString')
                or raw_log.get('user_id')
            )
            punch_time = (
                raw_log.get('punch_time')
                or raw_log.get('time')
                or raw_log.get('dateTime')
            )
            punch_type = (
                raw_log.get('punch_type')
                or raw_log.get('type')
                or 'unknown'
            )
            return {
                'external_id': str(external_id) if external_id else False,
                'device_user_id': str(device_user_id) if device_user_id else False,
                'punch_time': punch_time,
                'punch_type': punch_type,
            }
        return {
            'external_id': False,
            'device_user_id': False,
            'punch_time': False,
            'punch_type': 'unknown',
        }

    def sync_device_logs(self, date_from=None, date_to=None):
        Log = self.device.env['fingerprint.device.log']
        date_to = date_to or fields.Datetime.now()
        date_from = date_from or (date_to - timedelta(hours=24))
        raw_logs = self.fetch_attendance_logs(date_from, date_to)
        created = Log.browse()
        for raw in raw_logs:
            normalized = self.normalize_log(raw)
            if not normalized.get('external_id'):
                continue
            existing = Log.search([
                ('device_id', '=', self.device.id),
                ('external_id', '=', normalized['external_id']),
            ], limit=1)
            if existing:
                continue
            punch_type = normalized.get('punch_type', 'unknown')
            if punch_type not in ('check_in', 'check_out'):
                punch_type = 'unknown'
            created |= Log.create({
                'device_id': self.device.id,
                'external_id': normalized['external_id'],
                'device_user_id': normalized.get('device_user_id'),
                'punch_time': normalized.get('punch_time') or fields.Datetime.now(),
                'punch_type': punch_type,
                'state': 'draft',
            })
        return created
