# -*- coding: utf-8 -*-
"""Process Hikvision HTTP Listening pushes into hr.attendance (Option 2)."""

from __future__ import annotations

import logging
from typing import Any

from odoo import fields

from .hikvision import _to_utc_datetime
from .hikvision_connector import HikvisionConnector

_logger = logging.getLogger(__name__)

PUNCH_TYPE_MAP = {
    'checkin': 'check_in',
    'check_in': 'check_in',
    'checkout': 'check_out',
    'check_out': 'check_out',
    'breakin': 'break_in',
    'break_in': 'break_in',
    'breakout': 'break_out',
    'break_out': 'break_out',
}

DOOR_SYSTEM_SUB_EVENT_TYPES = frozenset({21, 22, 23, 24, '21', '22', '23', '24'})
FINGERPRINT_FAILED_SUB_EVENT_TYPES = frozenset({39, 151, '39', '151'})


def _sub_event_type(raw: dict[str, Any]) -> str:
    return str(raw.get('subEventType') or raw.get('minor') or '').strip()


def _employee_no(raw: dict[str, Any]) -> str:
    for key in ('employeeNoString', 'employeeNo', 'userNo'):
        value = str(raw.get(key) or '').strip()
        if value:
            return value
    return ''


def _normalize_punch_type(raw: dict[str, Any]) -> str | None:
    status = str(raw.get('attendanceStatus') or '').strip().lower()
    if status and status != 'undefined':
        compact = status.replace(' ', '').replace('-', '')
        mapped = PUNCH_TYPE_MAP.get(compact) or PUNCH_TYPE_MAP.get(status)
        if mapped:
            return mapped
    return None


def _external_log_id(raw: dict[str, Any]) -> str:
    serial = raw.get('serialNo')
    if serial is not None:
        return str(serial)
    verify = raw.get('verifyNo')
    date_time = raw.get('dateTime') or raw.get('time') or ''
    employee = _employee_no(raw)
    return f'{date_time}-{employee}-{verify}'


def classify_http_push(raw: dict[str, Any]) -> tuple[str, str]:
    """Return (action, reason) for an HTTP push payload."""
    sub_event = _sub_event_type(raw)
    if sub_event in DOOR_SYSTEM_SUB_EVENT_TYPES:
        return 'ignored', 'door/system event'
    try:
        if int(sub_event) in {21, 22, 23, 24}:
            return 'ignored', 'door/system event'
    except (TypeError, ValueError):
        pass

    if sub_event in FINGERPRINT_FAILED_SUB_EVENT_TYPES:
        return 'ignored', 'fingerprint failed'

    try:
        if int(sub_event) in {39, 151}:
            return 'ignored', 'fingerprint failed'
    except (TypeError, ValueError):
        pass

    employee_no = _employee_no(raw)
    if not employee_no:
        return 'ignored', 'missing employee number'

    punch_type = _normalize_punch_type(raw)
    if not punch_type:
        return 'ignored', 'unknown attendance status'

    event_time = _to_utc_datetime(raw.get('dateTime') or raw.get('time'))
    if not event_time:
        return 'error', 'missing event time'

    return 'process', punch_type


def process_http_push(device, raw_fields: dict[str, Any]) -> dict[str, Any]:
    """Process one Hikvision HTTP push for a fingerprint device record."""
    device.ensure_one()
    action, reason = classify_http_push(raw_fields)
    if action == 'ignored':
        _logger.info(
            'Hikvision HTTP push ignored for %s: %s (serialNo=%s)',
            device.name,
            reason,
            raw_fields.get('serialNo'),
        )
        return {'status': 'ignored', 'reason': reason}

    if action == 'error':
        _logger.warning(
            'Hikvision HTTP push error for %s: %s payload=%s',
            device.name,
            reason,
            raw_fields,
        )
        return {'status': 'error', 'reason': reason}

    punch_type = reason
    employee_no = _employee_no(raw_fields)
    connector = HikvisionConnector(device)
    employee = connector._resolve_employee(employee_no)
    if not employee:
        _logger.warning(
            'Hikvision HTTP push: no employee for device_user_id=%s device=%s',
            employee_no,
            device.name,
        )
        return {'status': 'employee_not_found', 'employee_no': employee_no}

    punch_time = _to_utc_datetime(
        raw_fields.get('dateTime') or raw_fields.get('time'),
    ) or fields.Datetime.now()
    external_id = _external_log_id(raw_fields)

    result = device.env['hr.employee'].sudo().hikvision_bridge_punch(
        employee.id,
        punch_type,
        fields.Datetime.to_string(punch_time),
        external_log_id=external_id,
        device_user_id=employee_no,
        attendance_source='fingerprint',
    )

    _logger.info(
        'Hikvision HTTP push processed device=%s employee=%s punch=%s status=%s attendance_id=%s',
        device.name,
        employee.id,
        punch_type,
        result.get('status'),
        result.get('attendance_id'),
    )

    return {
        'status': result.get('status', 'unknown'),
        'punch_type': punch_type,
        'attendance_id': result.get('attendance_id'),
        'employee_id': employee.id,
    }
