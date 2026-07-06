# -*- coding: utf-8 -*-
"""Standalone Hikvision ISAPI client for access control terminals (DS-K1T series).

No Odoo imports — safe to use from scripts and tests outside the ORM.
"""

from __future__ import annotations

import json
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from requests.auth import HTTPDigestAuth
from requests.exceptions import RequestException, Timeout

from .hikvision_exceptions import (
    HikvisionAuthenticationError,
    HikvisionConnectionError,
    HikvisionEndpointNotFound,
    HikvisionParseError,
)

_logger = logging.getLogger('hr_attendance_custom_ext.hikvision')

CAPABILITY_ENDPOINTS = (
    '/ISAPI/System/deviceInfo',
    '/ISAPI/System/capabilities',
    '/ISAPI/AccessControl/capabilities?format=json',
    '/ISAPI/AccessControl/AcsEvent/capabilities?format=json',
    '/ISAPI/AccessControl/UserInfo/capabilities?format=json',
    '/ISAPI/AccessControl/UserInfo/Count?format=json',
    '/ISAPI/AccessControl/CardInfo/capabilities?format=json',
    '/ISAPI/AccessControl/CardInfo/Count?format=json',
)

USER_SEARCH_PATH = '/ISAPI/AccessControl/UserInfo/Search?format=json'
ACS_EVENT_PATH = '/ISAPI/AccessControl/AcsEvent?format=json'
DEVICE_INFO_PATH = '/ISAPI/System/deviceInfo'
ACS_FETCH_CHUNK_HOURS = 1
ACS_MAX_RESULTS = 50
ACS_MAX_PAGES = 200


def _local_tag(tag: str) -> str:
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def _iter_time_chunks(
    start_time: datetime,
    end_time: datetime,
    chunk_hours: int = ACS_FETCH_CHUNK_HOURS,
):
    """Split a UTC window into smaller chunks so device pagination can reach all events."""
    if start_time >= end_time:
        return
    chunk = timedelta(hours=chunk_hours)
    cursor = start_time
    while cursor < end_time:
        chunk_end = min(cursor + chunk, end_time)
        yield cursor, chunk_end
        cursor = chunk_end


def _acs_pagination_has_more(
    block: dict[str, Any],
    position: int,
    num_matches: int,
    max_results: int,
) -> bool:
    """DS-K1T firmware may omit responseStatusStrg=MORE even when more pages exist."""
    if num_matches == 0:
        return False
    status = (block.get('responseStatusStrg') or '').upper()
    if status == 'MORE':
        return True
    total = block.get('totalMatches')
    if total is not None and position + num_matches < int(total):
        return True
    return num_matches >= max_results


def _xml_text(root: ET.Element, name: str) -> str | None:
    for element in root.iter():
        if _local_tag(element.tag) == name and element.text:
            return element.text.strip()
    return None


def _to_utc_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_for_device(dt: datetime, tz_name: str | None = None) -> str:
    """Format datetime for Hikvision ISAPI (naive local time, no TZ offset)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = dt.astimezone().tzinfo
    else:
        tz = dt.astimezone().tzinfo
    return dt.astimezone(tz).replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%S')


class HikvisionClient:
    """HTTP Digest ISAPI client for Hikvision access control terminals."""

    def __init__(
        self,
        device_ip: str,
        username: str,
        password: str,
        port: int = 80,
        timeout: float = 15,
        verify_ssl: bool = False,
        use_https: bool = False,
    ):
        if not device_ip:
            raise ValueError('device_ip is required')
        if not username:
            raise ValueError('username is required')

        self.device_ip = device_ip
        self.port = port
        self.username = username
        self.password = password or ''
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._scheme = 'https' if use_https else 'http'
        self._session: requests.Session | None = None
        self._connected = False
        self._device_info: dict[str, Any] | None = None

    def _base_url(self) -> str:
        return f'{self._scheme}://{self.device_ip}:{self.port}'

    def _ensure_session(self) -> requests.Session:
        if self._session is None:
            session = requests.Session()
            session.auth = HTTPDigestAuth(self.username, self.password)
            session.verify = self.verify_ssl
            self._session = session
        return self._session

    def _request(
        self,
        method: str,
        path: str,
        *,
        required: bool = False,
        raise_on_404: bool = False,
        **kwargs: Any,
    ) -> requests.Response | None:
        url = urljoin(self._base_url(), path)
        session = self._ensure_session()
        _logger.info('Hikvision %s %s', method.upper(), path)

        try:
            response = session.request(method, url, timeout=self.timeout, **kwargs)
        except Timeout as exc:
            _logger.error('Hikvision timeout on %s %s', method.upper(), path)
            raise HikvisionConnectionError(f'Timeout on {path}') from exc
        except RequestException as exc:
            _logger.error('Hikvision connection error on %s %s: %s', method.upper(), path, exc)
            raise HikvisionConnectionError(f'Connection failed on {path}: {exc}') from exc

        if response.status_code in (401, 403):
            _logger.error(
                'Hikvision authentication failed on %s %s (HTTP %s)',
                method.upper(), path, response.status_code,
            )
            raise HikvisionAuthenticationError(
                f'Authentication failed on {path} (HTTP {response.status_code})'
            )

        if response.status_code == 404:
            _logger.warning('Hikvision endpoint not found: %s (HTTP 404)', path)
            if raise_on_404 or required:
                raise HikvisionEndpointNotFound(f'Endpoint not found: {path}')
            return None

        if not response.ok:
            body_snippet = (response.text or '').strip()[:1000]
            _logger.warning(
                'Hikvision unexpected status on %s %s: HTTP %s — %s',
                method.upper(), path, response.status_code, body_snippet,
            )
            if required:
                raise HikvisionConnectionError(
                    f'Unexpected HTTP {response.status_code} on {path}: {body_snippet}'
                )
            return response

        return response

    @staticmethod
    def _parse_xml(text: str) -> ET.Element:
        try:
            return ET.fromstring(text)
        except ET.ParseError as exc:
            raise HikvisionParseError(f'Invalid XML response: {exc}') from exc

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HikvisionParseError(f'Invalid JSON response: {exc}') from exc
        if not isinstance(data, dict):
            raise HikvisionParseError('JSON response root must be an object')
        return data

    def _response_json(self, response: requests.Response) -> dict[str, Any]:
        return self._parse_json(response.text)

    def connect(self) -> dict[str, Any]:
        """Initialize session and validate credentials via deviceInfo."""
        _logger.info('Connecting to Hikvision device %s:%s', self.device_ip, self.port)
        self._device_info = self.get_device_info()
        self._connected = True
        _logger.info(
            'Connected to Hikvision %s (%s)',
            self._device_info.get('model'),
            self._device_info.get('serial'),
        )
        return self._device_info

    def test_connection(self) -> dict[str, Any]:
        """Probe /ISAPI/System/deviceInfo and return parsed device metadata."""
        return self.get_device_info()

    def get_device_info(self) -> dict[str, Any]:
        response = self._request('GET', DEVICE_INFO_PATH, required=True)
        assert response is not None
        root = self._parse_xml(response.text)
        info = {
            'model': _xml_text(root, 'model'),
            'firmware': _xml_text(root, 'firmwareVersion'),
            'serial': _xml_text(root, 'serialNumber'),
            'deviceName': _xml_text(root, 'deviceName'),
            'manufacturer': _xml_text(root, 'manufacturer'),
            'deviceType': _xml_text(root, 'deviceType'),
            'macAddress': _xml_text(root, 'macAddress'),
        }
        _logger.info(
            'Device info: model=%s firmware=%s serial=%s',
            info.get('model'), info.get('firmware'), info.get('serial'),
        )
        return info

    def discover_capabilities(self) -> dict[str, Any]:
        """Probe common ISAPI endpoints; 404 responses are logged and skipped."""
        results: dict[str, Any] = {}
        for path in CAPABILITY_ENDPOINTS:
            response = self._request('GET', path)
            if response is None:
                results[path] = {'status': 404, 'supported': False}
                continue
            entry: dict[str, Any] = {
                'status': response.status_code,
                'supported': response.ok,
            }
            content_type = response.headers.get('Content-Type', '')
            body = response.text.strip()
            if response.ok and body:
                if 'json' in content_type or body.startswith('{'):
                    try:
                        entry['data'] = self._parse_json(body)
                    except HikvisionParseError:
                        entry['snippet'] = body[:500]
                else:
                    try:
                        root = self._parse_xml(body)
                        entry['root_tag'] = _local_tag(root.tag)
                    except HikvisionParseError:
                        entry['snippet'] = body[:500]
            results[path] = entry
            _logger.info('Capability probe %s -> HTTP %s', path, response.status_code)
        supported = [path for path, meta in results.items() if meta.get('supported')]
        _logger.info('Supported endpoints (%s): %s', len(supported), ', '.join(supported))
        return results

    def _post_search_page(
        self,
        path: str,
        cond_key: str,
        cond: dict[str, Any],
        *,
        required: bool = True,
    ) -> dict[str, Any]:
        response = self._request(
            'POST',
            path,
            required=required,
            raise_on_404=True,
            headers={'Content-Type': 'application/json'},
            json={cond_key: cond},
        )
        assert response is not None
        return self._response_json(response)

    def _paginate_search(
        self,
        path: str,
        cond_key: str,
        response_key: str,
        list_key: str,
        cond_extra: dict[str, Any] | None = None,
        max_results: int = 30,
        max_pages: int = 100,
        search_id: str | None = None,
    ) -> list[dict[str, Any]]:
        search_id = search_id or str(uuid.uuid4())
        position = 0
        collected: list[dict[str, Any]] = []
        pages = 0

        while pages < max_pages:
            cond: dict[str, Any] = {
                'searchID': search_id,
                'searchResultPosition': position,
                'maxResults': max_results,
            }
            if cond_extra:
                cond.update(cond_extra)

            payload = self._post_search_page(path, cond_key, cond)
            block = payload.get(response_key, {})
            if not isinstance(block, dict):
                raise HikvisionParseError(f'Expected object at {response_key}')

            items = block.get(list_key) or []
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                raise HikvisionParseError(f'Expected list at {response_key}.{list_key}')

            collected.extend(item for item in items if isinstance(item, dict))
            num_matches = int(block.get('numOfMatches') or len(items) or 0)
            status = (block.get('responseStatusStrg') or '').upper()
            pages += 1
            _logger.info(
                'Paginated %s page %s: got %s items (status=%s, total=%s)',
                path, pages, num_matches, status, block.get('totalMatches'),
            )

            if not _acs_pagination_has_more(block, position, num_matches, max_results):
                break
            position += num_matches

        return collected

    @staticmethod
    def normalize_user(raw: dict[str, Any]) -> dict[str, Any]:
        employee_id = (
            raw.get('employeeNo')
            or raw.get('employeeNoString')
            or raw.get('employeeID')
        )
        card_number = raw.get('cardNo')
        if not card_number and raw.get('numOfCard'):
            cards = raw.get('CardInfo') or raw.get('RightPlan')
            if isinstance(cards, list) and cards:
                card_number = cards[0].get('cardNo')
            elif isinstance(cards, dict):
                card_number = cards.get('cardNo')

        department = raw.get('belongGroup') or raw.get('department')
        if not department:
            extends = raw.get('PersonInfoExtends')
            if isinstance(extends, list) and extends:
                department = extends[0].get('value')

        return {
            'employee_id': str(employee_id) if employee_id is not None else '',
            'name': raw.get('name') or '',
            'card_number': str(card_number) if card_number else None,
            'department': department or None,
            'user_type': raw.get('userType'),
            'raw': raw,
        }

    def get_users(self) -> list[dict[str, Any]]:
        """Retrieve enrolled users via UserInfo/Search pagination."""
        _logger.info('Fetching Hikvision users from %s', USER_SEARCH_PATH)
        try:
            raw_users = self._paginate_search(
                USER_SEARCH_PATH,
                cond_key='UserInfoSearchCond',
                response_key='UserInfoSearch',
                list_key='UserInfo',
                max_results=100,
            )
        except HikvisionEndpointNotFound as exc:
            _logger.error('User search endpoint unavailable: %s', exc)
            raise

        users = [self.normalize_user(raw) for raw in raw_users]
        _logger.info('Downloaded %s Hikvision user(s)', len(users))
        return users

    @staticmethod
    def _attendance_source_from_verify(*values: str | None) -> str:
        text = ' '.join(v.lower() for v in values if v)
        if not text:
            return 'unknown'
        if 'face' in text:
            return 'face'
        if any(token in text for token in ('fp', 'finger', 'fingerprint')):
            return 'fingerprint'
        if 'card' in text:
            return 'card'
        if any(token in text for token in ('password', 'passwd', 'pw')):
            return 'password'
        return 'unknown'

    @staticmethod
    def _event_external_id(raw: dict[str, Any]) -> str:
        serial = raw.get('serialNo') or raw.get('serialno')
        if serial is not None:
            return str(serial)
        employee = raw.get('employeeNoString') or raw.get('employeeNo') or ''
        event_time = raw.get('time') or raw.get('dateTime') or ''
        return f'{event_time}-{employee}'

    @staticmethod
    def _event_type_label(raw: dict[str, Any]) -> str:
        if raw.get('attendanceStatus'):
            return str(raw['attendanceStatus'])
        major = raw.get('major')
        minor = raw.get('minor')
        if major is not None or minor is not None:
            return f'major:{major}/minor:{minor}'
        return raw.get('eventType') or 'unknown'

    @classmethod
    def normalize_event(cls, raw: dict[str, Any]) -> dict[str, Any]:
        verify_mode = (
            raw.get('currentVerifyMode')
            or raw.get('verifyMode')
            or raw.get('currentVerify')
            or ''
        )
        event_time = _to_utc_datetime(raw.get('time') or raw.get('dateTime'))
        employee = raw.get('employeeNoString') or raw.get('employeeNo') or ''
        return {
            'external_id': cls._event_external_id(raw),
            'device_user_id': str(employee) if employee != '' else '',
            'event_time': event_time,
            'event_type': cls._event_type_label(raw),
            'attendance_source': cls._attendance_source_from_verify(verify_mode),
            'raw': raw,
        }

    @classmethod
    def normalize_access_event(cls, raw: dict[str, Any]) -> dict[str, Any]:
        verify_mode = (
            raw.get('currentVerifyMode')
            or raw.get('verifyMode')
            or raw.get('currentVerify')
            or ''
        )
        door = raw.get('doorName') or raw.get('doorNo') or raw.get('doorID')
        if door is not None:
            door = str(door)
        return {
            'external_id': cls._event_external_id(raw),
            'employee_id': str(raw.get('employeeNoString') or raw.get('employeeNo') or ''),
            'employee_name': raw.get('name') or '',
            'event_time': _to_utc_datetime(raw.get('time') or raw.get('dateTime')),
            'event_type': cls._event_type_label(raw),
            'authentication_method': verify_mode or 'unknown',
            'door': door,
            'raw_payload': raw,
        }

    def _normalize_access_event(self, raw: dict[str, Any]) -> dict[str, Any]:
        return self.normalize_access_event(raw)

    def _acs_event_cond_variants(
        self,
        start_time: datetime,
        end_time: datetime,
        device_tz: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build AcsEventCond payloads; DS-K1T firmware is picky about timeType and major/minor."""
        window = {
            'startTime': _iso_for_device(start_time, device_tz),
            'endTime': _iso_for_device(end_time, device_tz),
            'timeType': 'local',
        }
        # DS-K1T firmware requires major/minor; a bare window always returns HTTP 400.
        return [
            {**window, 'major': 0, 'minor': 0},
            {**window, 'major': 5, 'minor': 0},
        ]

    @staticmethod
    def _event_dedupe_key(raw: dict[str, Any]) -> str:
        serial = raw.get('serialNo')
        if serial is not None:
            return f'serial:{serial}'
        employee = raw.get('employeeNoString') or raw.get('employeeNo') or ''
        event_time = raw.get('time') or raw.get('dateTime') or ''
        return f'{event_time}-{employee}'

    def _fetch_acs_events_once(self, cond_extra: dict[str, Any]) -> list[dict[str, Any]]:
        search_id = str(uuid.uuid4())
        position = 0
        max_results = ACS_MAX_RESULTS
        pages = 0
        collected: list[dict[str, Any]] = []
        while pages < ACS_MAX_PAGES:
            pages += 1
            cond: dict[str, Any] = {
                'searchID': search_id,
                'searchResultPosition': position,
                'maxResults': max_results,
                **cond_extra,
            }
            payload = self._post_search_page(ACS_EVENT_PATH, 'AcsEventCond', cond)
            block = payload.get('AcsEvent', {})
            if not isinstance(block, dict):
                raise HikvisionParseError('Expected object at AcsEvent')

            items = block.get('InfoList') or []
            if isinstance(items, dict):
                items = [items]
            collected.extend(item for item in items if isinstance(item, dict))

            num_matches = int(block.get('numOfMatches') or len(items) or 0)
            status = (block.get('responseStatusStrg') or '').upper()
            _logger.info(
                'AcsEvent page at position %s: %s item(s) (status=%s, total=%s)',
                position, num_matches, status, block.get('totalMatches'),
            )
            if not _acs_pagination_has_more(block, position, num_matches, max_results):
                break
            position += num_matches
        if pages >= ACS_MAX_PAGES:
            _logger.warning(
                'AcsEvent pagination stopped at max pages (%s); some events may be missing',
                ACS_MAX_PAGES,
            )
        return collected

    def _fetch_access_events_window(
        self,
        start_time: datetime,
        end_time: datetime,
        device_tz: str | None,
        seen_keys: set[str],
    ) -> tuple[list[dict[str, Any]], bool, Exception | None]:
        """Fetch one time window; returns (events, any_variant_ok, last_error)."""
        last_error: Exception | None = None
        any_variant_ok = False
        merged: list[dict[str, Any]] = []

        for cond_extra in self._acs_event_cond_variants(start_time, end_time, device_tz):
            try:
                _logger.info('Trying AcsEventCond variant: %s', cond_extra)
                raw_events = self._fetch_acs_events_once(cond_extra)
                any_variant_ok = True
                added = 0
                for raw in raw_events:
                    key = self._event_dedupe_key(raw)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    merged.append(self.normalize_access_event(raw))
                    added += 1
                _logger.info(
                    'Variant %s returned %s event(s), %s new after dedupe (total %s)',
                    cond_extra, len(raw_events), added, len(merged),
                )
            except HikvisionConnectionError as exc:
                last_error = exc
                _logger.warning('AcsEvent variant failed: %s', exc)
                continue

        return merged, any_variant_ok, last_error

    def get_access_events(
        self,
        start_time: datetime,
        end_time: datetime,
        device_tz: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch access control events for the given UTC-aware time window."""
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        _logger.info(
            'Fetching Hikvision access events from %s to %s '
            '(device tz=%s, device local: %s — %s)',
            start_time.isoformat(),
            end_time.isoformat(),
            device_tz or 'server',
            _iso_for_device(start_time, device_tz),
            _iso_for_device(end_time, device_tz),
        )

        span = end_time - start_time
        if span > timedelta(hours=ACS_FETCH_CHUNK_HOURS):
            chunks = list(_iter_time_chunks(start_time, end_time, ACS_FETCH_CHUNK_HOURS))
            _logger.info(
                'Splitting %s h window into %s chunk(s) of up to %s h',
                span.total_seconds() / 3600, len(chunks), ACS_FETCH_CHUNK_HOURS,
            )
        else:
            chunks = [(start_time, end_time)]

        seen_keys: set[str] = set()
        merged: list[dict[str, Any]] = []
        any_variant_ok = False
        last_error: Exception | None = None

        for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            if len(chunks) > 1:
                _logger.info(
                    'Fetching Hikvision chunk %s/%s: %s — %s (device local: %s — %s)',
                    index, len(chunks),
                    chunk_start.isoformat(), chunk_end.isoformat(),
                    _iso_for_device(chunk_start, device_tz),
                    _iso_for_device(chunk_end, device_tz),
                )
            chunk_events, chunk_ok, chunk_error = self._fetch_access_events_window(
                chunk_start, chunk_end, device_tz, seen_keys,
            )
            merged.extend(chunk_events)
            any_variant_ok = any_variant_ok or chunk_ok
            if chunk_error:
                last_error = chunk_error

        if merged:
            _logger.info('Downloaded %s Hikvision access event(s) across variants', len(merged))
            return merged

        if any_variant_ok:
            _logger.info('No Hikvision access events in the requested window')
            return []

        if last_error:
            raise last_error
        raise HikvisionConnectionError('Failed to fetch access events from device')
