# -*- coding: utf-8 -*-
"""Real-time ZKTeco punch API (check_in / check_out / break_out / break_in)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from odoo import fields

from .hikvision_connector import HikvisionConnector

_logger = logging.getLogger(__name__)

ALLOWED_PUNCH_TYPES = frozenset({
    'check_in',
    'check_out',
    'break_out',
    'break_in',
})

PUNCH_ALIASES = {
    'checkin': 'check_in',
    'check_in': 'check_in',
    'in': 'check_in',
    '0': 'check_in',
    'checkout': 'check_out',
    'check_out': 'check_out',
    'out': 'check_out',
    '1': 'check_out',
    'breakout': 'break_out',
    'break_out': 'break_out',
    'break_start': 'break_out',
    '2': 'break_out',
    'breakin': 'break_in',
    'break_in': 'break_in',
    'break_end': 'break_in',
    '3': 'break_in',
}


def normalize_punch_type(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower().replace(' ', '').replace('-', '_')
    return PUNCH_ALIASES.get(raw)


def parse_event_time(value: Any, device_tz: str | None = None) -> datetime:
    """Parse event time; naive strings are treated as device-local then converted to UTC-naive."""
    if not value:
        return fields.Datetime.now()
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace('T', ' ')
        if text.endswith('Z'):
            text = text[:-1]
        try:
            dt = datetime.strptime(text[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return fields.Datetime.now()
    if dt.tzinfo is not None:
        return dt.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
    tz_name = device_tz or 'Asia/Amman'
    try:
        local = dt.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        local = dt.replace(tzinfo=ZoneInfo('UTC'))
    return local.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)


def process_zkteco_punch(device, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply one real-time punch for a ZKTeco fingerprint.device."""
    device.ensure_one()
    payload = payload or {}

    device_user_id = str(
        payload.get('device_user_id')
        or payload.get('employee_no')
        or payload.get('user_id')
        or payload.get('pin')
        or ''
    ).strip()
    if not device_user_id:
        return {'status': 'error', 'message': 'device_user_id is required'}

    punch_type = normalize_punch_type(payload.get('punch_type') or payload.get('punch'))
    if not punch_type or punch_type not in ALLOWED_PUNCH_TYPES:
        return {
            'status': 'error',
            'message': 'punch_type must be check_in, check_out, break_out, or break_in',
        }

    punch_time = parse_event_time(
        payload.get('event_time') or payload.get('punch_time') or payload.get('timestamp'),
        device_tz=device.device_timezone or 'Asia/Amman',
    )
    external_id = str(
        payload.get('external_id')
        or f"zk-api-{device.id}-{device_user_id}-{punch_time.strftime('%Y%m%d%H%M%S')}-{punch_type}"
    )

    connector = HikvisionConnector(device)
    employee = connector._resolve_employee(device_user_id)
    if not employee:
        _logger.warning(
            'ZKTeco punch API: no employee for device_user_id=%s device=%s',
            device_user_id, device.name,
        )
        return {'status': 'employee_not_found', 'device_user_id': device_user_id}

    result = device.env['hr.employee'].sudo().hikvision_bridge_punch(
        employee.id,
        punch_type,
        fields.Datetime.to_string(punch_time),
        external_log_id=external_id,
        device_user_id=device_user_id,
        attendance_source='fingerprint',
    )

    device.write({
        'http_listening_last_at': fields.Datetime.now(),
        'last_sync_at': fields.Datetime.now(),
        'last_sync_message': (
            f'Real-time punch: {punch_type} user={device_user_id} '
            f'status={result.get("status")}'
        ),
        'sync_status': 'success',
    })

    _logger.info(
        'ZKTeco punch API device=%s employee=%s punch=%s status=%s',
        device.name, employee.id, punch_type, result.get('status'),
    )
    return {
        'status': result.get('status', 'unknown'),
        'punch_type': punch_type,
        'attendance_id': result.get('attendance_id'),
        'employee_id': employee.id,
        'device_user_id': device_user_id,
        'event_time': fields.Datetime.to_string(punch_time),
    }
