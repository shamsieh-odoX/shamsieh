# -*- coding: utf-8 -*-
"""Parse ZKTeco ADMS / iclock ATTLOG payloads (no Odoo imports)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

try:
    from .zkteco import ZK_PUNCH_TYPE_MAP, _punch_type, _to_utc_naive
except ImportError:  # standalone bridge path
    from zkteco import ZK_PUNCH_TYPE_MAP, _punch_type, _to_utc_naive

_ATTLOG_LINE_RE = re.compile(
    r'^(?P<pin>\S+)\s+(?P<stamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'
    r'(?:\s+(?P<status>\d+))?(?:\s+(?P<verify>\d+))?',
)


def parse_attlog_body(body: str | bytes, *, device_tz: str | None = None, serial: str = '') -> list[dict[str, Any]]:
    """Parse ATTLOG body into normalized attendance events."""
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
    # Format A: tab-separated PIN, datetime, status, verify, ...
    if '\t' in line:
        parts = line.split('\t')
        pin = (parts[0] or '').strip()
        stamp = (parts[1] or '').strip() if len(parts) > 1 else ''
        status = parts[2].strip() if len(parts) > 2 and parts[2].strip() != '' else None
        verify = parts[3].strip() if len(parts) > 3 and parts[3].strip() != '' else None
    else:
        match = _ATTLOG_LINE_RE.match(line)
        if not match:
            # Format B: PIN=... DateTime=... Status=...
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
    raw_payload = {
        'user_id': pin,
        'timestamp': stamp,
        'punch': status,
        'status': status,
        'verify': verify,
        'punch_type': punch_type,
        'source': 'zkteco_adms',
        'serial': serial,
        'raw_line': line,
    }
    return {
        'external_id': external_id,
        'employee_id': str(pin).strip(),
        'employee_name': '',
        'event_time': event_time,
        'event_type': punch_type if punch_type in ZK_PUNCH_TYPE_MAP.values() else 'unknown',
        'authentication_method': 'fingerprint',
        'door': None,
        'raw_payload': raw_payload,
    }
