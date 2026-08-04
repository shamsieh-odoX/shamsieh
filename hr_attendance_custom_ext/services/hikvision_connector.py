# -*- coding: utf-8 -*-

import base64
import csv
import io
import json
import logging
from datetime import timedelta, timezone

from odoo import _, fields
from odoo.exceptions import UserError

from .hikvision import HikvisionClient
from .hikvision_exceptions import HikvisionError

_logger = logging.getLogger(__name__)

INVALID_AUTH_METHODS = frozenset({'invalid'})

DOOR_SYSTEM_EVENT_LABELS = (
    'door locked',
    'door unlocked',
    'exit button pressed',
    'exit button released',
    'remote login',
    'remote logout',
    'network recovered',
    'network disconnected',
)

DOOR_SYSTEM_MINOR_CODES = frozenset({21, 22, 23, 24})

SUCCESSFUL_EVENT_TYPE_TOKENS = ('authenticated', 'fingerprint', 'face')
SUCCESSFUL_VERIFY_MODE_TOKENS = ('fp', 'face', 'card', 'pw', 'finger', 'password', 'passwd')


def _raw_payload(event):
    return event.get('raw_payload') or {}


def _device_user_id(event):
    raw = _raw_payload(event)
    return (
        event.get('employee_id')
        or raw.get('employeeNoString')
        or raw.get('employeeNo')
        or ''
    ).strip()


def _verify_mode(event):
    raw = _raw_payload(event)
    return (
        raw.get('currentVerifyMode')
        or raw.get('verifyMode')
        or raw.get('currentVerify')
        or event.get('authentication_method')
        or ''
    ).strip().lower()


def _event_text_blobs(event):
    raw = _raw_payload(event)
    parts = [
        event.get('event_type') or '',
        event.get('authentication_method') or '',
        raw.get('eventDescription') or '',
        raw.get('eventType') or '',
        raw.get('attendanceStatus') or '',
        raw.get('name') or '',
    ]
    return ' '.join(str(part) for part in parts if part).lower()


def is_door_system_event(event):
    """Return True for door/system events and events without employeeNoString."""
    if not _device_user_id(event):
        return True

    text = _event_text_blobs(event)
    if any(label in text for label in DOOR_SYSTEM_EVENT_LABELS):
        return True

    minor = _raw_payload(event).get('minor')
    if minor is not None:
        try:
            if int(minor) in DOOR_SYSTEM_MINOR_CODES:
                return True
        except (TypeError, ValueError):
            pass
    return False


def is_successful_authentication(event):
    """Return True when authentication looks successful (not door/system)."""
    text = _event_text_blobs(event)
    if any(token in text for token in SUCCESSFUL_EVENT_TYPE_TOKENS):
        return True

    verify = _verify_mode(event)
    if verify and verify not in INVALID_AUTH_METHODS:
        if any(token in verify for token in SUCCESSFUL_VERIFY_MODE_TOKENS):
            return True

    # Employee present and not a door/system event.
    return bool(_device_user_id(event)) and not is_door_system_event(event)


def is_attendance_relevant_event(event):
    """Return True when event should be stored as draft (attendance-relevant)."""
    if not _device_user_id(event):
        return False

    if not event.get('event_time'):
        return False

    auth = (event.get('authentication_method') or '').strip().lower()
    verify = _verify_mode(event)
    if auth in INVALID_AUTH_METHODS or verify == 'invalid':
        return False

    if is_door_system_event(event):
        return False

    return is_successful_authentication(event)


def should_store_ignored_event(event):
    """Return True when a non-relevant event should still be persisted as ignored."""
    if not _device_user_id(event):
        return True
    if is_door_system_event(event):
        return True
    auth = (event.get('authentication_method') or '').strip().lower()
    if auth in INVALID_AUTH_METHODS:
        return True
    verify = _verify_mode(event)
    if verify == 'invalid':
        return True
    return False


def event_debug_fields(event):
    """Normalize event fields for sync debug logging."""
    raw = _raw_payload(event)
    event_time = event.get('event_time')
    if hasattr(event_time, 'isoformat'):
        event_time = event_time.isoformat()
    return {
        'serialNo': raw.get('serialNo'),
        'employeeNoString': _device_user_id(event) or raw.get('employeeNoString'),
        'name': event.get('employee_name') or raw.get('name'),
        'event_time': event_time,
        'event_type': event.get('event_type'),
        'major': raw.get('major'),
        'minor': raw.get('minor'),
        'currentVerifyMode': (
            raw.get('currentVerifyMode')
            or raw.get('verifyMode')
            or raw.get('currentVerify')
        ),
        'authentication_method': event.get('authentication_method'),
    }


def classify_sync_event(event, *, store_ignored_events=False):
    """Return (action, reason) where action is stored|ignored|skipped."""
    if not event.get('external_id'):
        return 'skipped', 'missing external_id'

    if not _device_user_id(event):
        if store_ignored_events:
            return 'ignored', 'no employeeNoString'
        return 'skipped', 'no employeeNoString'

    if not event.get('event_time'):
        if store_ignored_events:
            return 'ignored', 'missing event_time'
        return 'skipped', 'missing event_time'

    auth = (event.get('authentication_method') or '').strip().lower()
    verify = _verify_mode(event)
    if auth in INVALID_AUTH_METHODS or verify == 'invalid':
        if store_ignored_events:
            return 'ignored', 'invalid authentication'
        return 'skipped', 'invalid authentication'

    if is_door_system_event(event):
        if store_ignored_events:
            return 'ignored', 'door/system event'
        return 'skipped', 'door/system event'

    if is_attendance_relevant_event(event):
        return 'stored', 'attendance-relevant'

    if store_ignored_events:
        return 'ignored', 'not attendance-relevant'
    return 'skipped', 'not attendance-relevant'


class HikvisionConnector:
    """Odoo bridge for fingerprint.device sync (Hikvision ISAPI + CSV import)."""

    DEFAULT_TIMEOUT = 15

    def __init__(self, device):
        self.device = device

    def _hikvision_client(self):
        self.device.ensure_one()
        if not self.device.device_ip:
            raise UserError(_('Device IP is required.'))
        if not self.device.username:
            raise UserError(_('Device username is required.'))
        timeout = self.device.connection_timeout or self.DEFAULT_TIMEOUT
        return HikvisionClient(
            device_ip=self.device.device_ip,
            port=self.device.device_port or 80,
            username=self.device.username,
            password=self.device.password or '',
            timeout=timeout,
            verify_ssl=False,
        )

    def _fetch_with_retry(self, fetch_fn):
        retries = max(0, (self.device.sync_retry_count or 0))
        last_exc = None
        for attempt in range(retries + 1):
            try:
                return fetch_fn()
            except HikvisionError as exc:
                last_exc = exc
                _logger.warning(
                    'Hikvision fetch attempt %s/%s failed for %s: %s',
                    attempt + 1, retries + 1, self.device.name, exc,
                )
        raise UserError(_('Failed to fetch device events: %s', last_exc)) from last_exc

    def test_connection(self):
        self.device.ensure_one()
        if self.device.api_type == 'file_import':
            return True
        if self.device.api_type != 'hikvision':
            raise UserError(_('Test connection is only implemented for Hikvision devices.'))
        try:
            client = self._hikvision_client()
            return client.test_connection()
        except HikvisionError as exc:
            raise UserError(_('Connection failed: %s', exc)) from exc

    def get_capabilities(self):
        if self.device.api_type != 'hikvision':
            return {'api_type': self.device.api_type}
        try:
            client = self._hikvision_client()
            return client.discover_capabilities()
        except HikvisionError as exc:
            raise UserError(_('Capability discovery failed: %s', exc)) from exc

    def fetch_attendance_logs(self, date_from, date_to):
        if self.device.api_type == 'file_import':
            return self._fetch_from_csv_payload()
        if self.device.api_type == 'hikvision':
            return self._fetch_hikvision_events(date_from, date_to)
        if self.device.api_type == 'zkteco':
            # Dispatched via get_device_connector() → ZktecoConnector.
            raise UserError(_(
                'ZKTeco fetch was routed to the Hikvision connector. '
                'Use get_device_connector(device) instead.'
            ))
        raise UserError(_('Unsupported API type: %s', self.device.api_type))

    def _device_timezone(self):
        self.device.ensure_one()
        return (
            self.device.device_timezone
            or self.device.company_id.resource_calendar_id.tz
            or self.device.env.user.tz
            or 'UTC'
        )

    def _fetch_hikvision_events(self, date_from, date_to):
        client = self._hikvision_client()
        device_tz = self._device_timezone()
        return client.get_access_events(date_from, date_to, device_tz=device_tz)

    def _fetch_from_csv_payload(self):
        if not self.device.import_file_data:
            return []
        raw = self.device.import_file_data
        content = base64.b64decode(raw).decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        events = []
        for row in reader:
            events.append({
                'external_id': row.get('external_id'),
                'employee_id': row.get('device_user_id'),
                'employee_name': '',
                'event_time': row.get('punch_time'),
                'event_type': row.get('punch_type') or 'unknown',
                'authentication_method': 'fingerprint',
                'door': None,
                'raw_payload': dict(row),
            })
        return events

    def _event_to_log_vals(self, event, employee=None):
        raw = event.get('raw_payload') or {}
        event_time = event.get('event_time')
        if hasattr(event_time, 'tzinfo') and event_time.tzinfo is not None:
            event_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)

        device_user_id = (event.get('employee_id') or '').strip()
        event_type = event.get('event_type') or 'unknown'
        punch_type = event_type if event_type in ('check_in', 'check_out') else 'unknown'
        vals = {
            'device_id': self.device.id,
            'external_id': str(event.get('external_id')),
            'serial_no': str(raw.get('serialNo')) if raw.get('serialNo') is not None else False,
            'device_user_id': device_user_id or False,
            'event_time': event_time or fields.Datetime.now(),
            'event_type': event_type,
            'major': int(raw['major']) if raw.get('major') is not None else False,
            'minor': int(raw['minor']) if raw.get('minor') is not None else False,
            'authentication_method': event.get('authentication_method') or False,
            'raw_payload': raw,
            'punch_type': punch_type,
        }
        if employee:
            vals['employee_id'] = employee.id
            vals['employee_name'] = employee.name
        return vals

    def _log_employee_lookup_inputs(self, event):
        raw = event.get('raw_payload') or {}
        _logger.info(
            'Hikvision mapping input %s: employeeNoString=%r name=%r serialNo=%r '
            'verifyNo=%r currentVerifyMode=%r',
            self.device.name,
            raw.get('employeeNoString') or raw.get('employeeNo'),
            raw.get('name'),
            raw.get('serialNo'),
            raw.get('verifyNo'),
            raw.get('currentVerifyMode') or raw.get('verifyMode') or raw.get('currentVerify'),
        )

    def _resolve_employee(self, device_user_id):
        Employee = self.device.env['hr.employee']
        employee, matched_field = Employee.resolve_by_device_user_id(
            device_user_id,
            self.device.company_id,
        )
        if employee and matched_field:
            _logger.info(
                'Hikvision mapping %s: device_user_id=%r -> employee_id=%s '
                'employee_name=%r via %s',
                self.device.name,
                Employee._normalize_device_user_id(device_user_id),
                employee.id,
                employee.name,
                matched_field,
            )
        return employee

    @staticmethod
    def _relink_existing_log(existing, employee):
        if not employee or existing.employee_id:
            return
        vals = {
            'employee_id': employee.id,
            'employee_name': employee.name,
        }
        if existing.state == 'error':
            vals['state'] = 'draft'
            vals['error_message'] = False
        existing.write(vals)

    @staticmethod
    def _newest_event_time(events):
        times = []
        for event in events:
            event_time = event.get('event_time')
            if not event_time:
                continue
            if isinstance(event_time, str):
                event_time = fields.Datetime.to_datetime(event_time)
            if hasattr(event_time, 'tzinfo') and event_time.tzinfo:
                event_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)
            times.append(event_time)
        return max(times) if times else None

    def _update_checkpoint_from_event(self, event):
        raw = event.get('raw_payload') or {}
        serial = raw.get('serialNo')
        event_time = event.get('event_time')
        if not event_time:
            return
        if isinstance(event_time, str):
            event_time = fields.Datetime.to_datetime(event_time)
        if hasattr(event_time, 'tzinfo') and event_time.tzinfo:
            event_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)
        checkpoint_vals = {'last_sync_checkpoint': event_time}
        if serial is not None:
            checkpoint_vals['last_successful_event_serial'] = str(serial)
        if (
            not self.device.last_sync_checkpoint
            or event_time >= self.device.last_sync_checkpoint
        ):
            self.device.write(checkpoint_vals)

    def _ingest_normalized_event(self, event, *, process_immediately=False):
        """Store one normalized event; return (log, action, reason)."""
        Log = self.device.env['fingerprint.device.log']
        external_id = event.get('external_id')
        debug = event_debug_fields(event)
        store_ignored = self.device.store_ignored_events

        if not external_id:
            _logger.info(
                'Hikvision ingest %s skipped: %s | reason=%s',
                self.device.name, debug, 'missing external_id',
            )
            return Log.browse(), 'skipped', 'missing external_id'

        external_id = str(external_id)
        existing = Log.search([
            ('device_id', '=', self.device.id),
            ('external_id', '=', external_id),
        ], limit=1)
        if existing:
            device_user_id = _device_user_id(event)
            if device_user_id:
                self._log_employee_lookup_inputs(event)
                employee = self._resolve_employee(device_user_id)
                self._relink_existing_log(existing, employee)
            _logger.info(
                'Hikvision ingest %s duplicate: %s | reason=%s',
                self.device.name, debug, 'duplicate external_id',
            )
            return existing, 'duplicate', 'duplicate external_id'

        if self.device.api_type == 'file_import':
            action, reason = (
                ('stored', 'file import')
                if _device_user_id(event) else ('skipped', 'no device_user_id')
            )
        else:
            action, reason = classify_sync_event(
                event, store_ignored_events=store_ignored,
            )

        _logger.info(
            'Hikvision ingest %s event %s: %s | reason=%s',
            self.device.name, action, debug, reason,
        )

        log = Log.browse()
        if action == 'stored':
            device_user_id = _device_user_id(event)
            _logger.info(
                'Hikvision mapping parsed payload %s: %s',
                self.device.name,
                json.dumps(event.get('raw_payload') or {}, default=str),
            )
            self._log_employee_lookup_inputs(event)
            employee = self._resolve_employee(device_user_id)
            log = Log.create({
                **self._event_to_log_vals(event, employee=employee),
                'state': 'draft',
            })
            if process_immediately and log:
                log._process_pending_logs()
        elif action == 'ignored':
            log = Log.create({
                **self._event_to_log_vals(event),
                'state': 'ignored',
            })

        self._update_checkpoint_from_event(event)
        return log, action, reason

    def ingest_push_event(self, raw_payload, *, process_immediately=True):
        """Ingest a single HTTP push event from Hikvision HTTP Listening."""
        event = HikvisionClient.normalize_access_event(raw_payload)
        log, action, reason = self._ingest_normalized_event(
            event, process_immediately=process_immediately,
        )
        self.device.write({'http_listening_last_at': fields.Datetime.now()})
        return {
            'log': log,
            'action': action,
            'reason': reason,
            'external_id': str(event.get('external_id') or ''),
        }

    def sync_device_logs(self, date_from=None, date_to=None):
        Log = self.device.env['fingerprint.device.log']
        date_to = date_to or fields.Datetime.now()
        lookback = self.device.sync_lookback_hours or 24
        lookback_from = date_to - timedelta(hours=lookback)
        narrowed = False
        if self.device.last_sync_checkpoint and self.device.last_sync_checkpoint < date_to:
            date_from = max(lookback_from, self.device.last_sync_checkpoint - timedelta(minutes=5))
            narrowed = date_from > lookback_from
        else:
            date_from = date_from or lookback_from

        stats = {
            'fetched': 0,
            'stored': 0,
            'ignored': 0,
            'duplicates': 0,
            'unmapped': 0,
            'skipped': 0,
        }
        created = Log.browse()

        try:
            events = self._fetch_with_retry(
                lambda: self.fetch_attendance_logs(date_from, date_to),
            )
            if not events and narrowed:
                _logger.info(
                    'Hikvision sync %s: no events in narrowed window (%s — %s); '
                    'retrying full lookback (%s h)',
                    self.device.name, date_from, date_to, lookback,
                )
                events = self._fetch_with_retry(
                    lambda: self.fetch_attendance_logs(lookback_from, date_to),
                )
                date_from = lookback_from
        except HikvisionError as exc:
            _logger.error('Hikvision fetch failed for %s: %s', self.device.name, exc)
            raise UserError(_('Failed to fetch device events: %s', exc)) from exc
        except UserError:
            raise

        stats['fetched'] = len(events)
        newest_event_time = self._newest_event_time(events)
        if (
            events
            and newest_event_time
            and (date_to - newest_event_time) > timedelta(minutes=10)
            and date_from > lookback_from
        ):
            _logger.warning(
                'Hikvision sync %s: newest fetched event %s is more than 10 min before '
                'sync end %s; refetching full lookback (%s h)',
                self.device.name, newest_event_time, date_to, lookback,
            )
            events = self._fetch_with_retry(
                lambda: self.fetch_attendance_logs(lookback_from, date_to),
            )
            date_from = lookback_from
            stats['fetched'] = len(events)

        _logger.info(
            'Hikvision sync %s: fetched %s event(s) from %s to %s',
            self.device.name, stats['fetched'], date_from, date_to,
        )

        for event in events:
            log, action, _ = self._ingest_normalized_event(event)
            if action == 'stored':
                stats['stored'] += 1
                created |= log
                if log and not log.employee_id:
                    stats['unmapped'] += 1
            elif action == 'ignored':
                stats['ignored'] += 1
                created |= log
            elif action == 'duplicate':
                stats['duplicates'] += 1
            else:
                stats['skipped'] += 1

        _logger.info(
            'Hikvision sync %s complete: fetched=%s stored=%s ignored=%s '
            'duplicates=%s unmapped=%s skipped=%s',
            self.device.name,
            stats['fetched'],
            stats['stored'],
            stats['ignored'],
            stats['duplicates'],
            stats['unmapped'],
            stats['skipped'],
        )
        return created, stats
