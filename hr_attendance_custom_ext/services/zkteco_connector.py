# -*- coding: utf-8 -*-
"""Odoo bridge for fingerprint.device api_type='zkteco' (TCP pull via pyzk)."""

from __future__ import annotations

import logging

from odoo import _
from odoo.exceptions import UserError

from .hikvision_connector import HikvisionConnector
from .zkteco import ZktecoClient
from .zkteco_exceptions import ZktecoDependencyError, ZktecoError

_logger = logging.getLogger(__name__)


class ZktecoConnector(HikvisionConnector):
    """Reuse shared ingest/sync; override transport for ZKTeco devices."""

    DEFAULT_PORT = 4370

    def _zkteco_password(self) -> int:
        raw = (self.device.password or self.device.api_key or '0').strip() or '0'
        try:
            return int(raw)
        except ValueError as exc:
            raise UserError(_(
                'ZKTeco communication password must be numeric (device Comm Key). '
                'Got: %s', raw,
            )) from exc

    def _zkteco_client(self) -> ZktecoClient:
        self.device.ensure_one()
        if not self.device.device_ip:
            raise UserError(_('Device IP is required.'))
        timeout = self.device.connection_timeout or self.DEFAULT_TIMEOUT
        return ZktecoClient(
            device_ip=self.device.device_ip,
            port=self.device.device_port or self.DEFAULT_PORT,
            timeout=timeout,
            password=self._zkteco_password(),
            force_udp=bool(getattr(self.device, 'zkteco_force_udp', False)),
            ommit_ping=True,
        )

    def test_connection(self):
        self.device.ensure_one()
        try:
            info = self._zkteco_client().test_connection()
            _logger.info('ZKTeco connection OK for %s: %s', self.device.name, info)
            return info or True
        except ZktecoDependencyError as exc:
            raise UserError(str(exc)) from exc
        except ZktecoError as exc:
            raise UserError(_('ZKTeco connection failed: %s', exc)) from exc

    def fetch_attendance_logs(self, date_from, date_to):
        self.device.ensure_one()
        try:
            return self._zkteco_client().get_attendance(
                date_from=date_from,
                date_to=date_to,
                device_tz=self._device_timezone(),
            )
        except ZktecoDependencyError as exc:
            raise UserError(str(exc)) from exc
        except ZktecoError as exc:
            raise UserError(_('Failed to fetch ZKTeco attendance: %s', exc)) from exc

    def _fetch_with_retry(self, fetch_fn):
        retries = max(0, (self.device.sync_retry_count or 0))
        last_exc = None
        for attempt in range(retries + 1):
            try:
                return fetch_fn()
            except UserError as exc:
                last_exc = exc
                _logger.warning(
                    'ZKTeco fetch attempt %s/%s failed for %s: %s',
                    attempt + 1, retries + 1, self.device.name, exc,
                )
            except ZktecoError as exc:
                last_exc = UserError(_('Failed to fetch device events: %s', exc))
                _logger.warning(
                    'ZKTeco fetch attempt %s/%s failed for %s: %s',
                    attempt + 1, retries + 1, self.device.name, exc,
                )
        raise last_exc or UserError(_('Failed to fetch ZKTeco device events.'))


def get_device_connector(device):
    """Factory: return the connector for a fingerprint.device record."""
    device.ensure_one()
    if device.api_type == 'zkteco':
        return ZktecoConnector(device)
    return HikvisionConnector(device)
