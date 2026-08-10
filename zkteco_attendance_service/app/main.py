# -*- coding: utf-8 -*-
"""Local ZKTeco poll bridge for Odoo.sh / cloud Odoo.

Runs on a PC that can reach the ZKTeco terminal (LAN), pulls attendance with
pyzk, and pushes normalized events into Odoo via XML-RPC
``fingerprint.device.ingest_external_attendance_events``.

Usage:
  pip install -r requirements.txt
  copy .env.example .env  # fill values
  python -m app.main
"""

from __future__ import annotations

import logging
import os
import sys
import time
import xmlrpc.client
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
MODULE_SERVICES = ROOT / 'extra_addons' / 'hr_attendance_custom_ext' / 'services'
sys.path.insert(0, str(MODULE_SERVICES))

from zkteco import ZktecoClient  # noqa: E402
from zkteco_exceptions import ZktecoError  # noqa: E402

load_dotenv(Path(__file__).resolve().parent / '.env')

logging.basicConfig(
    level=logging.DEBUG if os.getenv('VERBOSE_LOGGING', 'true').lower() == 'true' else logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
_logger = logging.getLogger('zkteco_bridge')


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def odoo_models():
    url = os.environ['ODOO_URL'].rstrip('/')
    db = os.environ['ODOO_DB']
    user = os.environ['ODOO_BOT_USER']
    key = os.environ['ODOO_API_KEY']
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
    uid = common.authenticate(db, user, key, {})
    if not uid:
        raise RuntimeError('Odoo authentication failed')
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object', allow_none=True)
    return db, uid, key, models


def serialize_event(event: dict) -> dict:
    payload = dict(event)
    event_time = payload.get('event_time')
    if isinstance(event_time, datetime):
        payload['event_time'] = event_time.strftime('%Y-%m-%d %H:%M:%S')
    return payload


def poll_once(db, uid, key, models) -> dict:
    device_id = int(os.environ['ZKTECO_DEVICE_ID'])
    lookback = float(os.getenv('LOOKBACK_HOURS', '24'))
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(hours=lookback)
    client = ZktecoClient(
        device_ip=os.environ.get('ZKTECO_IP', '192.178.1.40'),
        port=int(os.getenv('ZKTECO_PORT', '4370')),
        timeout=int(os.getenv('ZKTECO_TIMEOUT', '15')),
        password=int(os.getenv('ZKTECO_PASSWORD', '0')),
        force_udp=_env_bool('ZKTECO_FORCE_UDP', False),
    )
    events = client.get_attendance(
        date_from=date_from,
        date_to=date_to,
        device_tz=os.getenv('ZKTECO_TIMEZONE', 'Asia/Amman'),
    )
    serialized = [serialize_event(event) for event in events]
    _logger.info('Fetched %s ZK attendance row(s); pushing to Odoo device %s', len(serialized), device_id)
    stats = models.execute_kw(
        db, uid, key,
        'fingerprint.device', 'ingest_external_attendance_events',
        [[device_id], serialized],
    )
    _logger.info('Odoo ingest stats: %s', stats)
    return stats


def main():
    interval = int(os.getenv('POLL_INTERVAL_SECONDS', '60'))
    db, uid, key, models = odoo_models()
    _logger.info('ZKTeco bridge started (interval=%ss)', interval)
    while True:
        try:
            poll_once(db, uid, key, models)
        except ZktecoError as exc:
            _logger.error('Device error: %s', exc)
        except Exception:
            _logger.exception('Bridge cycle failed')
        time.sleep(interval)


if __name__ == '__main__':
    main()
