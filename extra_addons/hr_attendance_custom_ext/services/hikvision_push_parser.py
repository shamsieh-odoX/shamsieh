# -*- coding: utf-8 -*-
"""Parse Hikvision HTTP Listening request bodies (JSON or multipart)."""

from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from typing import Any

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


def _parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        raise ValueError('Empty request body')
    try:
        data = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid JSON body') from exc
    if not isinstance(data, dict):
        raise ValueError('JSON body must be an object')
    return _unwrap_event_dict(data)


def _parse_multipart_body(body: bytes, content_type: str) -> dict[str, Any]:
    if not body:
        raise ValueError('Empty multipart body')
    headers = f'Content-Type: {content_type}\r\n\r\n'.encode()
    message = BytesParser(policy=policy.default).parsebytes(headers + body)
    if not message.is_multipart():
        payload = message.get_payload(decode=True) or b''
        return _parse_json_body(payload)

    for part in message.iter_parts():
        part_payload = part.get_payload(decode=True) or b''
        if not part_payload.strip():
            continue
        part_type = (part.get_content_type() or '').lower()
        if part_type in ('application/json', 'text/json', 'text/plain'):
            try:
                return _parse_json_body(part_payload)
            except ValueError:
                continue
        name = part.get_param('name', header='content-disposition') or ''
        if name in ('AccessControllerEvent', 'event_log', 'event'):
            return _parse_json_body(part_payload)
    raise ValueError('No JSON event part found in multipart body')


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
