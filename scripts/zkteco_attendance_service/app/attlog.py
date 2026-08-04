# -*- coding: utf-8 -*-
"""Parse ZKTeco ADMS ATTLOG payloads (standalone — no Odoo imports)."""

from __future__ import annotations

import logging
import re
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

_ATTLOG_LINE_RE = re.compile(
    r'^(?P<pin>\S+)\s+(?P<stamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'
    r'(?:\s+(?P<status>\d+))?(?:\s+(?P<verify>\d+))?',
)


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


def _punch_type(punch: Any) -> str:
    try:
        code = int(punch)
    except (TypeError, ValueError):
        return 'unknown'
    return ZK_PUNCH_TYPE_MAP.get(code, 'unknown')


def parse_attlog_body(body: str | bytes, *, device_tz: str | None = None, serial: str = '') -> list[dict[str, Any]]:
    if body is None:
        return []
    if isinstance(body, bytes):
        text = body.decode('utf-8', errors='ignore')
    else:
        text = str(body)
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return []

    events: list[dict[str, Any]] = []
    for index, raw_line in enumerate(text.split('\n')):
        line = raw_line.strip()
        if not line:
            continue
        event = _parse_attlog_line(line, index=index, device_tz=device_tz, serial=serial)
        if event:
            events.append(event)
    return events


def _parse_attlog_line(line: str, *, index: int, device_tz: str | None, serial: str) -> dict[str, Any] | None:
    if '\t' in line:
        parts = line.split('\t')
        pin = (parts[0] or '').strip()
        stamp = (parts[1] or '').strip() if len(parts) > 1 else ''
        status = parts[2].strip() if len(parts) > 2 and parts[2].strip() != '' else None
        verify = parts[3].strip() if len(parts) > 3 and parts[3].strip() != '' else None
    else:
        match = _ATTLOG_LINE_RE.match(line)
        if not match:
            kv = {}
            for token in re.split(r'[\t ]+', line):
                if '=' in token:
                    key, value = token.split('=', 1)
                    kv[key.strip().lower()] = value.strip()
            pin = kv.get('pin') or kv.get('userid') or kv.get('user_id') or ''
            stamp = kv.get('datetime') or kv.get('time') or kv.get('timestamp') or ''
            status = kv.get('status') or kv.get('inoutmode')
            verify = kv.get('verified') or kv.get('verify')
        else:
            pin = match.group('pin')
            stamp = match.group('stamp')
            status = match.group('status')
            verify = match.group('verify')

    if not pin or not stamp:
        return None

    try:
        local_dt = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None

    event_time = _to_utc_naive(local_dt, device_tz)
    punch_type = _punch_type(status)
    stamp_key = event_time.strftime('%Y%m%d%H%M%S')
    external_id = f'zk-adms-{serial or "nosn"}-{pin}-{stamp_key}-{index}'
    return {
        'external_id': external_id,
        'employee_id': str(pin).strip(),
        'employee_name': '',
        'event_time': event_time,
        'event_type': punch_type if punch_type in ZK_PUNCH_TYPE_MAP.values() else 'unknown',
        'authentication_method': 'fingerprint',
        'door': None,
        'raw_payload': {
            'user_id': pin,
            'timestamp': stamp,
            'punch': status,
            'status': status,
            'verify': verify,
            'punch_type': punch_type,
            'source': 'zkteco_adms',
            'serial': serial,
            'raw_line': line,
        },
    }
