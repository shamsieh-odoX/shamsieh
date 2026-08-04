# -*- coding: utf-8 -*-
"""Parse Hikvision HTTP Listening request bodies (JSON or multipart)."""

from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from typing import Any, Mapping

ACS_FIELD_MARKERS = frozenset({
    'employeeNoString',
    'employeeNo',
    'serialNo',
    'major',
    'minor',
    'time',
    'dateTime',
    'currentVerifyMode',
})

EVENT_FORM_FIELD_NAMES = (
    'event_log',
    'AccessControllerEvent',
    'event',
    'EventNotificationAlert',
)


def _unwrap_event_dict(data: dict[str, Any]) -> dict[str, Any]:
    for key in ('AccessControllerEvent', 'AcsEvent', 'EventNotificationAlert'):
        nested = data.get(key)
        if isinstance(nested, dict):
            merged = _unwrap_event_dict(nested)
            for wrapper_key in (
                'dateTime',
                'time',
                'eventType',
                'eventState',
                'eventDescription',
                'ipAddress',
                'channelID',
                'majorEventType',
                'subEventType',
            ):
                if wrapper_key in data and wrapper_key not in merged:
                    merged[wrapper_key] = data[wrapper_key]
            return merged
    if ACS_FIELD_MARKERS.intersection(data):
        return data
    event_list = data.get('EventNotificationAlertList')
    if isinstance(event_list, list) and event_list:
        first = event_list[0]
        if isinstance(first, dict):
            return _unwrap_event_dict(first)
    return data


def _parse_json_text(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise ValueError('Empty JSON text')
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError('Invalid JSON body') from exc
    if not isinstance(data, dict):
        raise ValueError('JSON body must be an object')
    return _unwrap_event_dict(data)


def _parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        raise ValueError('Empty request body')
    try:
        text = body.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('Invalid JSON body') from exc
    return _parse_json_text(text)


def _coerce_form_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if hasattr(value, 'read'):
        payload = value.read()
        if isinstance(payload, str):
            return payload.encode('utf-8')
        return payload or None
    text = str(value).strip()
    return text.encode('utf-8') if text else None


def _parse_multipart_body(body: bytes, content_type: str) -> dict[str, Any]:
    if not body:
        raise ValueError('Empty multipart body')
    headers = f'Content-Type: {content_type}\r\n\r\n'.encode()
    message = BytesParser(policy=policy.default).parsebytes(headers + body)
    if not message.is_multipart():
        payload = message.get_payload(decode=True) or b''
        return _parse_json_body(payload)

    candidates: list[dict[str, Any]] = []
    for part in message.iter_parts():
        part_payload = part.get_payload(decode=True) or b''
        if not part_payload.strip():
            continue
        part_type = (part.get_content_type() or '').lower()
        name = part.get_param('name', header='content-disposition') or ''
        if part_type in ('application/json', 'text/json', 'text/plain') or name in EVENT_FORM_FIELD_NAMES:
            try:
                candidates.append(_parse_json_body(part_payload))
            except ValueError:
                continue
    if not candidates:
        raise ValueError('No JSON event part found in multipart body')
    return candidates[0] if len(candidates) == 1 else _merge_event_candidates(candidates)


def _merge_event_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            100 if item.get('employeeNoString') or item.get('employeeNo') else 0,
            1 if item.get('serialNo') is not None else 0,
        ),
        reverse=True,
    )
    merged = dict(ranked[0])
    for part in ranked[1:]:
        for key, value in part.items():
            if value in (None, '') or key in merged:
                continue
            merged[key] = value
    return merged


def parse_hikvision_push_body(body: bytes, content_type: str = '') -> dict[str, Any]:
    """Return raw ACS event fields from an HTTP listening POST body."""
    content_type = (content_type or '').lower()
    if 'multipart/' in content_type:
        event = _parse_multipart_body(body, content_type)
    else:
        event = _parse_json_body(body)
    if not isinstance(event, dict) or not event:
        raise ValueError('Event payload is empty')
    return event


def parse_hikvision_push_form(
    form_data: Mapping[str, Any] | None,
    files: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse ACS fields when Werkzeug already consumed a multipart POST."""
    candidates: list[dict[str, Any]] = []
    sources: list[Mapping[str, Any]] = []
    if form_data:
        sources.append(form_data)
    if files:
        sources.append(files)

    for source in sources:
        for name in EVENT_FORM_FIELD_NAMES:
            if name not in source:
                continue
            payload = _coerce_form_bytes(source.get(name))
            if not payload:
                continue
            try:
                candidates.append(_parse_json_body(payload))
            except ValueError:
                continue
        for key, value in source.items():
            if key in EVENT_FORM_FIELD_NAMES:
                continue
            if isinstance(value, dict):
                unwrapped = _unwrap_event_dict(value)
                if ACS_FIELD_MARKERS.intersection(unwrapped):
                    candidates.append(unwrapped)
                continue
            payload = _coerce_form_bytes(value)
            if not payload or not payload.lstrip().startswith(b'{'):
                continue
            try:
                candidates.append(_parse_json_body(payload))
            except ValueError:
                continue

    if not candidates:
        raise ValueError('No event fields in parsed form data')
    if len(candidates) == 1:
        return candidates[0]
    return _merge_event_candidates(candidates)


def parse_hikvision_push_route_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Parse ACS fields passed as Odoo route keyword arguments."""
    for name in EVENT_FORM_FIELD_NAMES:
        if name not in kwargs:
            continue
        value = kwargs[name]
        if isinstance(value, dict):
            event = _unwrap_event_dict(value)
            if event:
                return event
        payload = _coerce_form_bytes(value)
        if payload:
            return _parse_json_body(payload)
    raise ValueError('No event fields in route kwargs')


def _read_raw_http_body(http_request) -> bytes:
    body = http_request.get_data(cache=True, as_text=False) or b''
    if body:
        return body
    body = http_request.get_data(cache=False, as_text=False) or b''
    if body:
        return body
    content_length = http_request.content_length or 0
    if content_length > 0:
        stream = http_request.environ.get('wsgi.input')
        if stream is not None:
            try:
                body = stream.read(content_length)
                if body:
                    return body
            except Exception:
                pass
    return b''


def request_has_event_form_data(
    http_request,
    route_kwargs: Mapping[str, Any] | None = None,
) -> bool:
    """Return True when parsed form/kwargs contain Hikvision event fields."""
    for source in (http_request.form, http_request.files):
        if not source:
            continue
        for name in EVENT_FORM_FIELD_NAMES:
            if name in source and _coerce_form_bytes(source.get(name)):
                return True
    if route_kwargs:
        for name in EVENT_FORM_FIELD_NAMES:
            if name in route_kwargs:
                return True
    return False


def extract_hikvision_push_from_request(
    http_request,
    route_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read ACS event fields from raw body or Werkzeug-parsed multipart form."""
    content_type = (http_request.content_type or '').lower()
    body = _read_raw_http_body(http_request)

    if body:
        return parse_hikvision_push_body(body, content_type)

    if http_request.form or http_request.files:
        return parse_hikvision_push_form(http_request.form, http_request.files)

    if route_kwargs:
        try:
            return parse_hikvision_push_route_kwargs(route_kwargs)
        except ValueError:
            pass

    if 'multipart/' in content_type:
        raise ValueError('Empty multipart body')
    raise ValueError('Empty request body')
