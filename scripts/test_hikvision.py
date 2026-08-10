#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone smoke test for the Hikvision ISAPI client.

No Odoo bootstrap and no database writes.

Usage:
    cd /path/to/shamsieh
    HIKVISION_IP=192.168.100.85 \\
    HIKVISION_USER=admin \\
    HIKVISION_PASSWORD='secret' \\
    .venv/bin/python scripts/test_hikvision.py

Optional:
    --hours 24       Event lookback window (default: 24)
    --limit 20       Max events to print (default: 20)
    --https          Use HTTPS instead of HTTP
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = REPO_ROOT / 'extra_addons' / 'hr_attendance_custom_ext'
sys.path.insert(0, str(MODULE_ROOT))

from services.hikvision import HikvisionClient  # noqa: E402
from services.hikvision_exceptions import HikvisionError  # noqa: E402


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _pretty(data) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    parser = argparse.ArgumentParser(description='Test Hikvision ISAPI client')
    parser.add_argument('--hours', type=int, default=24, help='Event lookback in hours')
    parser.add_argument('--limit', type=int, default=20, help='Max events to print')
    parser.add_argument('--https', action='store_true', help='Use HTTPS')
    args = parser.parse_args()

    device_ip = os.environ.get('HIKVISION_IP', '192.168.100.85')
    port = int(os.environ.get('HIKVISION_PORT', '80'))
    username = os.environ.get('HIKVISION_USER', 'admin')
    password = os.environ.get('HIKVISION_PASSWORD', '')
    verify_ssl = _env_bool('HIKVISION_VERIFY_SSL', False)

    if not password:
        print('ERROR: Set HIKVISION_PASSWORD in the environment.', file=sys.stderr)
        return 1

    client = HikvisionClient(
        device_ip=device_ip,
        port=port,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
        use_https=args.https,
    )

    try:
        print('=== 1. Connect / test_connection ===')
        device_info = client.connect()
        print(_pretty(device_info))

        print('\n=== 2. discover_capabilities ===')
        capabilities = client.discover_capabilities()
        supported = {
            path: meta for path, meta in capabilities.items() if meta.get('supported')
        }
        print(f'Supported endpoints: {len(supported)} / {len(capabilities)}')
        for path, meta in capabilities.items():
            status = meta.get('status')
            mark = 'OK' if meta.get('supported') else 'MISS'
            print(f'  [{mark}] HTTP {status} {path}')

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=args.hours)

        print(f'\n=== 3. get_access_events (last {args.hours}h, show first {args.limit}) ===')
        events = client.get_access_events(start_time, end_time)
        print(f'Total events fetched: {len(events)}')
        for event in events[: args.limit]:
            normalized = HikvisionClient.normalize_event(event['raw_payload'])
            print('-' * 60)
            print('Event:', _pretty({
                'external_id': event['external_id'],
                'employee_id': event['employee_id'],
                'employee_name': event['employee_name'],
                'event_time': event['event_time'],
                'event_type': event['event_type'],
                'authentication_method': event['authentication_method'],
                'door': event['door'],
            }))
            print('Normalized:', _pretty(normalized))

        print('\n=== 4. get_users ===')
        users = client.get_users()
        print(f'Total users fetched: {len(users)}')
        for user in users[:10]:
            print('-' * 60)
            print(_pretty({
                'employee_id': user['employee_id'],
                'name': user['name'],
                'card_number': user['card_number'],
                'department': user['department'],
                'user_type': user['user_type'],
            }))

        print('\nDone.')
        return 0

    except HikvisionError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
