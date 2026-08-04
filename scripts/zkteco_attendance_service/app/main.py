# -*- coding: utf-8 -*-
"""ZKTeco local poll bridge for Odoo.sh (F28 / port 4370).

Polls the device like Attendance Management, then pushes events to Odoo.
Close Attendance Management (or Disconnect) while this runs — both use port 4370.

Usage:
  python -m app.main
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import xmlrpc.client
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

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
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)
    file_handler = RotatingFileHandler(
        LOG_DIR / 'zkteco_poll.log',
        maxBytes=2_000_000,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


_setup_logging()
_logger = logging.getLogger('zkteco_bridge')


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


def push_events_to_odoo(events: list[dict[str, Any]]) -> dict:
    device_id = int(os.environ['ZKTECO_DEVICE_ID'])
    db, uid, key, models = odoo_models()
    serialized = [serialize_event(event) for event in events]
    _logger.info('Pushing %s poll event(s) to Odoo device %s', len(serialized), device_id)
    stats = models.execute_kw(
        db, uid, key,
        'fingerprint.device', 'ingest_external_attendance_events',
        [[device_id], serialized],
    )
    _logger.info('Odoo ingest stats: %s', stats)
    return stats


def poll_once() -> dict:
    from .zk_client import ZktecoClient

    lookback = float(os.getenv('LOOKBACK_HOURS', '24'))
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(hours=lookback)
    client = ZktecoClient(
        device_ip=os.environ.get('ZKTECO_IP', '192.168.1.40'),
        port=int(os.getenv('ZKTECO_PORT', '4370')),
        timeout=int(os.getenv('ZKTECO_TIMEOUT', '15')),
        password=int(os.getenv('ZKTECO_PASSWORD', '0')),
        force_udp=_env_bool('ZKTECO_FORCE_UDP', False),
    )
    _logger.info(
        'Polling ZK %s:%s (lookback %sh)...',
        client.device_ip, client.port, lookback,
    )
    events = client.get_attendance(
        date_from=date_from,
        date_to=date_to,
        device_tz=os.getenv('ZKTECO_TIMEZONE', 'Asia/Amman'),
    )
    _logger.info('Fetched %s attendance row(s) from device', len(events))
    return push_events_to_odoo(events)


def _poll_loop():
    interval = int(os.getenv('POLL_INTERVAL_SECONDS', '30'))
    # Run immediately on start, then every interval.
    while True:
        try:
            poll_once()
        except Exception as exc:
            _logger.error(
                'ZK poll error: %s — close Attendance Management if it is Connected',
                exc,
            )
        time.sleep(interval)


def _run_adms_listener():
    from fastapi import FastAPI, Request, Response
    import uvicorn
    from .attlog import parse_attlog_body

    app = FastAPI(title='ZKTeco ADMS Bridge')

    def _serial_from_request(request: Request) -> str:
        sn = request.query_params.get('SN') or request.query_params.get('sn') or ''
        if not sn:
            sn = request.headers.get('SN') or ''
        return sn.strip()

    @app.get('/')
    async def root():
        return {
            'service': 'zkteco_bridge',
            'mode': 'adms+poll' if _env_bool('ENABLE_POLL', False) else 'adms',
            'poll_enabled': _env_bool('ENABLE_POLL', False),
        }

    @app.api_route('/iclock', methods=['GET', 'POST'])
    @app.api_route('/iclock/', methods=['GET', 'POST'])
    async def iclock_root():
        return Response(content='OK', media_type='text/plain')

    @app.api_route('/iclock/cdata', methods=['GET', 'POST'])
    @app.api_route('/iclock/cdata/', methods=['GET', 'POST'])
    async def iclock_cdata(request: Request):
        serial = _serial_from_request(request)
        table = (request.query_params.get('table') or '').strip().upper()
        if request.method == 'GET':
            return Response(content='OK', media_type='text/plain')
        body = (await request.body()).decode('utf-8', errors='ignore')
        if table in ('ATTLOG', 'ATTLOGUE', '') or 'ATTLOG' in table:
            events = parse_attlog_body(
                body,
                device_tz=os.getenv('ZKTECO_TIMEZONE', 'Asia/Amman'),
                serial=serial or os.getenv('ZKTECO_SERIAL', ''),
            )
            if events:
                stats = push_events_to_odoo(events)
                return Response(
                    content=f'OK: {stats.get("stored", 0)}',
                    media_type='text/plain',
                )
        return Response(content='OK', media_type='text/plain')

    @app.api_route('/iclock/getrequest', methods=['GET', 'POST'])
    @app.api_route('/iclock/getrequest/', methods=['GET', 'POST'])
    async def iclock_getrequest():
        return Response(content='OK', media_type='text/plain')

    @app.api_route('/iclock/registry', methods=['GET', 'POST'])
    @app.api_route('/iclock/registry/', methods=['GET', 'POST'])
    async def iclock_registry():
        return Response(content='OK', media_type='text/plain')

    host = os.getenv('ADMS_LISTEN_HOST', '0.0.0.0')
    port = int(os.getenv('ADMS_LISTEN_PORT', '8088'))
    _logger.info('ADMS listener on http://%s:%s/iclock/', host, port)
    uvicorn.run(app, host=host, port=port, log_level='info')


def main():
    enable_poll = _env_bool('ENABLE_POLL', True)
    enable_adms = _env_bool('ENABLE_ADMS', False)

    if not enable_poll and not enable_adms:
        _logger.error('Enable ENABLE_POLL and/or ENABLE_ADMS in .env')
        raise SystemExit(1)

    if enable_poll and enable_adms:
        thread = threading.Thread(target=_poll_loop, name='zk-poll', daemon=True)
        thread.start()
        _logger.info('Poll loop started (background); ADMS listener in foreground')
        _run_adms_listener()
        return

    if enable_adms:
        _run_adms_listener()
        return

    _logger.info(
        'ZKTeco POLL mode — device %s:%s → Odoo every %ss. '
        'Close Attendance Management while this runs.',
        os.getenv('ZKTECO_IP', '192.168.1.40'),
        os.getenv('ZKTECO_PORT', '4370'),
        os.getenv('POLL_INTERVAL_SECONDS', '30'),
    )
    _poll_loop()


if __name__ == '__main__':
    main()
