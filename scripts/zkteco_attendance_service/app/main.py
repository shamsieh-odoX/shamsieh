# -*- coding: utf-8 -*-
"""ZKTeco live-capture → real-time Odoo punch API.

Each fingerprint hit is POSTed immediately to /zkteco/punch/<token>.
Punch types: check_in, check_out, break_out, break_in.
No Sync Now / no lookback sync.

Close Attendance Management while this runs (exclusive port 4370).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from .zk_client import ZK_PUNCH_TYPE_MAP, ZktecoClient, _punch_type

SERVICE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(SERVICE_DIR / '.env')

LOG_DIR = SERVICE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _setup_logging():
    level = logging.DEBUG if _env_bool('VERBOSE_LOGGING', True) else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    root.handlers.clear()
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)
    file_handler = RotatingFileHandler(
        LOG_DIR / 'zkteco_live.log',
        maxBytes=2_000_000,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


_setup_logging()
_logger = logging.getLogger('zkteco_live')


def _stamp(dt) -> str:
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def post_punch(punch_url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        punch_url,
        data=data,
        method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            try:
                return json.loads(body)
            except Exception:
                return {'status': 'ok', 'raw': body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {'status': 'error', 'message': body or str(exc)}
        parsed['_http_status'] = exc.code
        return parsed


def live_loop():
    punch_url = (os.environ.get('ZKTECO_PUNCH_URL') or '').strip()
    if not punch_url:
        raise RuntimeError(
            'ZKTECO_PUNCH_URL missing in .env — copy Punch API URL from Odoo device form'
        )

    client = ZktecoClient(
        device_ip=os.environ.get('ZKTECO_IP', '192.168.1.40'),
        port=int(os.getenv('ZKTECO_PORT', '4370')),
        timeout=int(os.getenv('ZKTECO_TIMEOUT', '15')),
        password=int(os.getenv('ZKTECO_PASSWORD', '0')),
        force_udp=_env_bool('ZKTECO_FORCE_UDP', False),
    )

    _logger.info(
        'LIVE capture %s:%s → Odoo punch API (close Attendance Management)',
        client.device_ip, client.port,
    )

    while True:
        conn = None
        try:
            zk = client._build_zk()
            conn = zk.connect()
            _logger.info('Connected — waiting for real-time punches...')
            for attendance in conn.live_capture():
                if attendance is None:
                    continue
                user_id = str(getattr(attendance, 'user_id', '') or '').strip()
                if not user_id:
                    continue
                punch = getattr(attendance, 'punch', None)
                status = getattr(attendance, 'status', None)
                stamp = getattr(attendance, 'timestamp', None)
                punch_type = _punch_type(punch, status)
                if punch_type not in ZK_PUNCH_TYPE_MAP.values():
                    punch_type = 'check_in'
                event_time = _stamp(stamp)
                uid = getattr(attendance, 'uid', None)
                external_id = (
                    f'zk-live-{user_id}-'
                    f'{event_time.replace(" ", "").replace(":", "")}-'
                    f'{uid}-{punch_type}'
                )
                payload = {
                    'device_user_id': user_id,
                    'punch_type': punch_type,
                    'event_time': event_time,
                    'external_id': external_id,
                }
                _logger.info('Punch: %s', payload)
                result = post_punch(punch_url, payload)
                _logger.info('Odoo: %s', result)
        except Exception as exc:
            _logger.error('Live error: %s — retry in 5s', exc)
            time.sleep(5)
        finally:
            if conn is not None:
                try:
                    conn.end_live_capture = True
                except Exception:
                    pass
                try:
                    conn.disconnect()
                except Exception:
                    pass


def main():
    live_loop()


if __name__ == '__main__':
    main()
