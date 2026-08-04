# -*- coding: utf-8 -*-
"""Standalone ZKTeco TCP client (pyzk) for the local poll bridge."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

_logger = logging.getLogger(__name__)

ZK_PUNCH_TYPE_MAP = {
    0: 'check_in',
    1: 'check_out',
    2: 'break_out',
    3: 'break_in',
    4: 'check_in',
    5: 'check_out',
}


class ZktecoError(Exception):
    pass


class ZktecoConnectionError(ZktecoError):
    pass


class ZktecoDependencyError(ZktecoError):
    pass


def _import_zk():
    try:
        from zk import ZK  # noqa: WPS433
    except ImportError as exc:
        raise ZktecoDependencyError(
            'The Python package "pyzk" is required. Install with: pip install pyzk'
        ) from exc
    return ZK


def _to_utc_naive(dt: datetime, device_tz: str | None) -> datetime:
    if dt is None:
        return datetime.utcnow()
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    tz_name = device_tz or 'UTC'
    try:
        local = dt.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        _logger.warning('Invalid ZK device timezone %r; treating as UTC', tz_name)
        local = dt.replace(tzinfo=timezone.utc)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _punch_type(punch: Any, status: Any = None) -> str:
    try:
        code = int(punch)
    except (TypeError, ValueError):
        code = None
    if code is None:
        try:
            code = int(status)
        except (TypeError, ValueError):
            code = None
    if code is None:
        return 'unknown'
    return ZK_PUNCH_TYPE_MAP.get(code, 'unknown')


class ZktecoClient:
    def __init__(
        self,
        device_ip: str,
        port: int = 4370,
        timeout: int = 15,
        password: int = 0,
        force_udp: bool = False,
        ommit_ping: bool = True,
    ):
        if not device_ip:
            raise ZktecoConnectionError('Device IP is required.')
        self.device_ip = device_ip
        self.port = port or 4370
        self.timeout = timeout or 15
        self.password = int(password or 0)
        self.force_udp = bool(force_udp)
        self.ommit_ping = bool(ommit_ping)

    def _build_zk(self):
        ZK = _import_zk()
        return ZK(
            self.device_ip,
            port=self.port,
            timeout=self.timeout,
            password=self.password,
            force_udp=self.force_udp,
            ommit_ping=self.ommit_ping,
        )

    def get_attendance(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        device_tz: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = None
        try:
            zk = self._build_zk()
            conn = zk.connect()
            try:
                conn.disable_device()
            except Exception:
                _logger.debug('ZK disable_device skipped for %s', self.device_ip)
            rows = conn.get_attendance() or []
            try:
                conn.enable_device()
            except Exception:
                _logger.debug('ZK enable_device skipped for %s', self.device_ip)
        except ZktecoError:
            raise
        except Exception as exc:
            raise ZktecoConnectionError(str(exc)) from exc
        finally:
            if conn is not None:
                try:
                    conn.disconnect()
                except Exception:
                    pass

        events: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            event = self.normalize_attendance_row(row, index=index, device_tz=device_tz)
            event_time = event.get('event_time')
            if date_from and event_time and event_time < date_from:
                continue
            if date_to and event_time and event_time > date_to:
                continue
            events.append(event)
        events.sort(key=lambda item: item.get('event_time') or datetime.min)
        return events

    @classmethod
    def normalize_attendance_row(
        cls,
        row: Any,
        *,
        index: int = 0,
        device_tz: str | None = None,
    ) -> dict[str, Any]:
        user_id = str(getattr(row, 'user_id', '') or '').strip()
        timestamp = getattr(row, 'timestamp', None)
        punch = getattr(row, 'punch', None)
        status = getattr(row, 'status', None)
        uid = getattr(row, 'uid', None)
        event_time = _to_utc_naive(timestamp, device_tz) if isinstance(timestamp, datetime) else None
        punch_type = _punch_type(punch, status)
        stamp = event_time.strftime('%Y%m%d%H%M%S') if event_time else 'unknown'
        external_id = f'zk-{user_id}-{stamp}-{uid if uid is not None else index}'
        return {
            'external_id': external_id,
            'employee_id': user_id,
            'employee_name': '',
            'event_time': event_time,
            'event_type': punch_type,
            'authentication_method': 'fingerprint',
            'door': None,
            'raw_payload': {
                'user_id': user_id,
                'uid': uid,
                'timestamp': timestamp.isoformat(sep=' ') if isinstance(timestamp, datetime) else timestamp,
                'punch': punch,
                'status': status,
                'punch_type': punch_type,
                'source': 'zkteco_poll',
            },
        }
