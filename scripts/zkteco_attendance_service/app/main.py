# -*- coding: utf-8 -*-
"""Local ZKTeco ADMS HTTP listener + optional pyzk poll bridge.

Preferred mode (like Hikvision): the ZKTeco device pushes ATTLOG to this PC
over plain HTTP (/iclock/...), and we forward events into Odoo via XML-RPC.

Usage:
  pip install -r requirements.txt
  copy .env.example .env
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
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
import uvicorn

from .attlog import parse_attlog_body

SERVICE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(SERVICE_DIR / '.env')

logging.basicConfig(
    level=logging.DEBUG if os.getenv('VERBOSE_LOGGING', 'true').lower() == 'true' else logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
_logger = logging.getLogger('zkteco_bridge')

app = FastAPI(title='ZKTeco ADMS Bridge')


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _find_odoo_services_dir() -> Path | None:
    """Locate hr_attendance_custom_ext/services for optional pyzk poll mode."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        for candidate in (
            parent / 'extra_addons' / 'hr_attendance_custom_ext' / 'services',
            parent / 'hr_attendance_custom_ext' / 'services',
        ):
            if (candidate / 'zkteco.py').is_file():
                return candidate
    return None


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
    _logger.info('Pushing %s ADMS event(s) to Odoo device %s', len(serialized), device_id)
    stats = models.execute_kw(
        db, uid, key,
        'fingerprint.device', 'ingest_external_attendance_events',
        [[device_id], serialized],
    )
    _logger.info('Odoo ingest stats: %s', stats)
    return stats


def _serial_from_request(request: Request) -> str:
    sn = request.query_params.get('SN') or request.query_params.get('sn') or ''
    if not sn:
        sn = request.headers.get('SN') or ''
    return sn.strip()


@app.api_route('/iclock/cdata', methods=['GET', 'POST'])
@app.api_route('/iclock/cdata/', methods=['GET', 'POST'])
async def iclock_cdata(request: Request):
    serial = _serial_from_request(request)
    table = (request.query_params.get('table') or '').strip().upper()
    _logger.info('ADMS cdata SN=%r table=%r method=%s', serial, table, request.method)
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
            try:
                stats = push_events_to_odoo(events)
                return Response(
                    content=f'OK: {stats.get("stored", 0)}',
                    media_type='text/plain',
                )
            except Exception:
                _logger.exception('Failed to push ADMS events to Odoo')
                return Response(content='ERROR', media_type='text/plain', status_code=500)
    return Response(content='OK', media_type='text/plain')


@app.api_route('/iclock/getrequest', methods=['GET', 'POST'])
@app.api_route('/iclock/getrequest/', methods=['GET', 'POST'])
async def iclock_getrequest(request: Request):
    _logger.debug('ADMS getrequest SN=%r', _serial_from_request(request))
    return Response(content='OK', media_type='text/plain')


@app.api_route('/iclock/registry', methods=['GET', 'POST'])
@app.api_route('/iclock/registry/', methods=['GET', 'POST'])
async def iclock_registry(request: Request):
    _logger.debug('ADMS registry SN=%r', _serial_from_request(request))
    return Response(content='OK', media_type='text/plain')


@app.get('/')
async def root():
    return {
        'service': 'zkteco_adms_bridge',
        'adms_url_hint': f'http://<this-pc-lan-ip>:{os.getenv("ADMS_LISTEN_PORT", "8088")}/iclock/',
        'poll_enabled': _env_bool('ENABLE_POLL', False),
    }


def poll_once() -> dict:
    services = _find_odoo_services_dir()
    if not services:
        raise RuntimeError(
            'Cannot find hr_attendance_custom_ext/services for poll mode. '
            'Keep ENABLE_POLL=false and use ADMS push instead.'
        )
    if str(services) not in sys.path:
        sys.path.insert(0, str(services))
    from zkteco import ZktecoClient  # noqa: WPS433

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
    events = client.get_attendance(
        date_from=date_from,
        date_to=date_to,
        device_tz=os.getenv('ZKTECO_TIMEZONE', 'Asia/Amman'),
    )
    return push_events_to_odoo(events)


def _poll_loop():
    interval = int(os.getenv('POLL_INTERVAL_SECONDS', '60'))
    while True:
        try:
            poll_once()
        except Exception as exc:
            _logger.error('ZK poll error: %s', exc)
        time.sleep(interval)


def main():
    if _env_bool('ENABLE_POLL', False):
        thread = threading.Thread(target=_poll_loop, name='zk-poll', daemon=True)
        thread.start()
        _logger.info('Optional pyzk poll loop started')

    host = os.getenv('ADMS_LISTEN_HOST', '0.0.0.0')
    port = int(os.getenv('ADMS_LISTEN_PORT', '8088'))
    _logger.info(
        'ADMS HTTP listener on http://%s:%s/iclock/ — point the ZKTeco Cloud Server URL here',
        host, port,
    )
    uvicorn.run(app, host=host, port=port, log_level='info')


if __name__ == '__main__':
    main()
