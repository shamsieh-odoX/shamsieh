from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from typing import Any
from urllib.parse import parse_qs
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

ACS_FIELD_MARKERS = frozenset({
    "employeeNoString",
    "employeeNo",
    "serialNo",
    "major",
    "minor",
    "time",
    "dateTime",
    "currentVerifyMode",
})

FINGERPRINT_VERIFY_MODES = frozenset({"fp", "finger", "fingerprint"})
FINGERPRINT_SUCCESS_SUB_EVENT_TYPES = frozenset({1, 38, 75, 150, "1", "38", "75", "150"})
FINGERPRINT_FAILED_SUB_EVENT_TYPES = frozenset({39, 151, "39", "151"})
AUTH_VERIFY_MODES = frozenset({"fp", "finger", "fingerprint", "faceorfporcardorpw", "face", "card", "pw"})
DOOR_SYSTEM_SUB_EVENT_TYPES = frozenset({21, 22, 23, 24, "21", "22", "23", "24"})


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _unwrap_event_dict(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("AccessControllerEvent", "AcsEvent", "EventNotificationAlert"):
        nested = data.get(key)
        if isinstance(nested, dict):
            merged = _unwrap_event_dict(nested)
            # Keep useful wrapper fields (for example top-level dateTime) when Hikvision
            # puts event details inside AccessControllerEvent.
            for wrapper_key in (
                "dateTime",
                "time",
                "eventType",
                "eventState",
                "eventDescription",
                "ipAddress",
                "channelID",
            ):
                if wrapper_key in data and wrapper_key not in merged:
                    merged[wrapper_key] = data[wrapper_key]
            for attendance_key in (
                "attendanceStatus",
                "AttendanceStatus",
                "byAttendanceStatus",
                "statusValue",
                "label",
            ):
                if attendance_key in data and attendance_key not in merged:
                    merged[attendance_key] = data[attendance_key]
            return merged
    if ACS_FIELD_MARKERS.intersection(data):
        return data
    event_list = data.get("EventNotificationAlertList")
    if isinstance(event_list, list) and event_list:
        first = event_list[0]
        if isinstance(first, dict):
            return _unwrap_event_dict(first)
    return data


def _xml_to_dict(xml_body: bytes) -> dict[str, Any]:
    root = ET.fromstring(xml_body)
    data: dict[str, Any] = {}
    for node in root.iter():
        key = _strip_ns(node.tag)
        text = (node.text or "").strip()
        if text:
            data[key] = text
    return data


def _parse_json_fields(body: bytes) -> dict[str, Any]:
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return _unwrap_event_dict(data)


def _parse_form_fields(body: bytes) -> dict[str, Any]:
    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    for key in ("event_log", "AccessControllerEvent", "event", "EventNotificationAlert"):
        value = (parsed.get(key) or [""])[0]
        if not value:
            continue
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError(f"{key} must be a JSON object")
        return _unwrap_event_dict(data)
    raise ValueError("Missing event_log form field")


def _try_parse_part(payload: bytes) -> dict[str, Any] | None:
    if not payload or not payload.strip():
        return None
    stripped = payload.lstrip()
    if stripped.startswith(b"{"):
        try:
            return _parse_json_fields(payload)
        except (json.JSONDecodeError, ValueError):
            return None
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
        try:
            return _xml_to_dict(payload)
        except ET.ParseError:
            return None
    return None


def _part_priority(fields: dict[str, Any]) -> int:
    score = 0
    if _employee_no(fields):
        score += 100
    sub_event = _sub_event_value(fields)
    if sub_event in FINGERPRINT_SUCCESS_SUB_EVENT_TYPES:
        score += 50
    elif sub_event in FINGERPRINT_FAILED_SUB_EVENT_TYPES:
        score += 40
    elif sub_event in DOOR_SYSTEM_SUB_EVENT_TYPES:
        score += 1
    verify = _verify_mode(fields)
    if verify in FINGERPRINT_VERIFY_MODES or any(token in verify for token in ("finger", "fp")):
        score += 20
    return score


def _merge_event_parts(parts: list[dict[str, Any]]) -> dict[str, Any]:
    if not parts:
        return {}
    if len(parts) == 1:
        return parts[0]
    ranked = sorted(parts, key=_part_priority, reverse=True)
    merged = dict(ranked[0])
    for part in ranked[1:]:
        for key, value in part.items():
            if value in (None, ""):
                continue
            if key not in merged or merged[key] in (None, ""):
                merged[key] = value
    return merged


def _parse_multipart_fields(body: bytes, content_type: str) -> dict[str, Any]:
    headers = f"Content-Type: {content_type}\r\n\r\n".encode()
    msg = BytesParser(policy=policy.default).parsebytes(headers + body)
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True) or b""
        parsed = _try_parse_part(payload)
        if parsed:
            return parsed
        raise ValueError("Multipart wrapper without parseable payload")

    part_names: list[str] = []
    candidates: list[dict[str, Any]] = []
    for part in msg.iter_parts():
        payload = part.get_payload(decode=True) or b""
        name = (part.get_param("name", header="content-disposition") or "").strip()
        if name:
            part_names.append(name)
        parsed = _try_parse_part(payload)
        if parsed:
            candidates.append(_unwrap_event_dict(parsed))

    if candidates:
        return _merge_event_parts(candidates)
    raise ValueError(f"No parseable event part in multipart body (parts={part_names})")


def debug_multipart(body: bytes, content_type: str) -> list[dict[str, str]]:
    headers = f"Content-Type: {content_type}\r\n\r\n".encode()
    msg = BytesParser(policy=policy.default).parsebytes(headers + body)
    parts: list[dict[str, str]] = []
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True) or b""
        parts.append({
            "name": "",
            "content_type": msg.get_content_type(),
            "preview": payload[:400].decode("utf-8", errors="replace"),
        })
        return parts
    for part in msg.iter_parts():
        payload = part.get_payload(decode=True) or b""
        parts.append({
            "name": (part.get_param("name", header="content-disposition") or ""),
            "content_type": part.get_content_type(),
            "preview": payload[:400].decode("utf-8", errors="replace"),
        })
    return parts


def parse_fields(body: bytes, content_type: str) -> dict[str, Any]:
    if not body or not body.strip():
        raise ValueError("Empty request body")
    ct = (content_type or "").lower()
    if "multipart/" in ct:
        return _parse_multipart_fields(body, content_type)
    if "application/x-www-form-urlencoded" in ct:
        return _parse_form_fields(body)
    if "application/json" in ct or body.lstrip().startswith(b"{"):
        return _parse_json_fields(body)
    if body.lstrip().startswith(b"<?xml") or body.lstrip().startswith(b"<"):
        return _xml_to_dict(body)
    parsed = _try_parse_part(body)
    if parsed:
        return parsed
    raise ValueError("Unsupported payload format")


def _safe_parse_datetime(raw: str) -> datetime:
    value = str(raw).strip().replace("Z", "+00:00")
    if " " in value and "T" not in value:
        value = value.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _extract_event_time(fields: dict[str, Any], received_at: datetime | None) -> tuple[datetime, str]:
    for key in (
        "dateTime",
        "time",
        "localTime",
        "happenTime",
        "eventOccurTime",
        "eventTime",
        "UTC",
    ):
        raw = str(fields.get(key) or "").strip()
        if raw:
            return _safe_parse_datetime(raw), key
    fallback = received_at or datetime.now(timezone.utc)
    if fallback.tzinfo is None:
        fallback = fallback.replace(tzinfo=timezone.utc)
    return fallback, "received_at"


def _employee_no(fields: dict[str, Any]) -> str:
    for key in ("employeeNoString", "employeeNo", "userNo"):
        value = str(fields.get(key) or "").strip()
        if value:
            return value
    return ""


def _verify_mode(fields: dict[str, Any]) -> str:
    return str(
        fields.get("currentVerifyMode")
        or fields.get("verifyMode")
        or fields.get("currentVerify")
        or ""
    ).strip().lower()


def _sub_event_type(fields: dict[str, Any]) -> str:
    return str(fields.get("subEventType") or fields.get("minor") or "").strip()


def _sub_event_value(fields: dict[str, Any]) -> Any:
    return fields.get("subEventType", fields.get("minor"))


def _is_door_system_event(fields: dict[str, Any]) -> bool:
    if _employee_no(fields):
        return False
    sub_event = _sub_event_value(fields)
    if sub_event in DOOR_SYSTEM_SUB_EVENT_TYPES:
        return True
    verify = _verify_mode(fields)
    return verify == "invalid"


def _status_value(fields: dict[str, Any]) -> str:
    return str(fields.get("statusValue", fields.get("status", fields.get("result", "")))).strip().lower()


def _is_auth_related(fields: dict[str, Any]) -> bool:
    sub_event = _sub_event_value(fields)
    if sub_event in FINGERPRINT_SUCCESS_SUB_EVENT_TYPES | FINGERPRINT_FAILED_SUB_EVENT_TYPES:
        return True
    verify = _verify_mode(fields)
    if verify in AUTH_VERIFY_MODES or any(token in verify for token in ("finger", "fp", "face", "card", "pw")):
        return True
    return bool(_employee_no(fields))


def _is_fingerprint_failed(fields: dict[str, Any]) -> bool:
    sub_event = _sub_event_value(fields)
    if sub_event in FINGERPRINT_FAILED_SUB_EVENT_TYPES:
        return True
    if not _is_auth_related(fields):
        return False
    verify = _verify_mode(fields)
    if verify == "invalid" and _employee_no(fields):
        return True
    status = _status_value(fields)
    if status in ("failed", "fail", "false", "denied", "rejected"):
        return True
    if status in ("0",) and sub_event in FINGERPRINT_FAILED_SUB_EVENT_TYPES:
        return True
    if status in ("0",) and verify not in ("", "invalid") and not _employee_no(fields):
        return True
    return False


def _is_successful_fingerprint(fields: dict[str, Any]) -> bool:
    if _is_fingerprint_failed(fields):
        return False

    sub_event = _sub_event_value(fields)
    if sub_event in FINGERPRINT_SUCCESS_SUB_EVENT_TYPES and _employee_no(fields):
        return True

    if _employee_no(fields) and _status_value(fields) in ("1", "success", "ok", "true"):
        verify = _verify_mode(fields)
        if verify in AUTH_VERIFY_MODES or any(token in verify for token in ("finger", "fp", "face", "card")):
            return True

    verify = _verify_mode(fields)
    if verify in FINGERPRINT_VERIFY_MODES or any(token in verify for token in ("finger", "fp")):
        status = _status_value(fields)
        return status in ("success", "ok", "1", "true", "")

    event_tokens = " ".join(
        str(fields.get(key, "")).lower()
        for key in (
            "eventType",
            "subEventType",
            "majorEventType",
            "major",
            "minor",
            "description",
            "eventDescription",
            "attendanceStatus",
            "name",
        )
    )
    return any(token in event_tokens for token in ("finger", "fp", "biometric", "authenticated"))


@dataclass
class AttendanceEvent:
    employee_no: str
    event_time: datetime
    event_type: str
    sub_event_type: str
    device_serial: str
    event_id: str
    raw_fields: dict[str, Any]


@dataclass
class ParseResult:
    event: AttendanceEvent | None
    reason: str
    status_code: int


def parse_event(
    body: bytes,
    content_type: str,
    received_at: datetime | None = None,
) -> ParseResult:
    fields = parse_fields(body, content_type)
    sub_event = _sub_event_type(fields)
    employee_no = _employee_no(fields)
    if employee_no or sub_event not in {"", *map(str, DOOR_SYSTEM_SUB_EVENT_TYPES)}:
        logger.info(
            "Hikvision event subEventType=%s employee_no=%r verify=%r",
            sub_event,
            employee_no or None,
            _verify_mode(fields) or None,
        )

    if _is_door_system_event(fields):
        logger.debug("Ignored system/door event subEventType=%s", _sub_event_type(fields))
        return ParseResult(None, "system-event", 200)

    if _is_fingerprint_failed(fields):
        logger.info(
            "Fingerprint failed subEventType=%s verify=%s employee_no=%r statusValue=%s",
            _sub_event_type(fields),
            _verify_mode(fields),
            _employee_no(fields),
            fields.get("statusValue"),
        )
        return ParseResult(None, "fingerprint-failed", 200)

    employee_no = _employee_no(fields)
    if not employee_no:
        logger.info("Incomplete event: missing employee_no keys=%s", sorted(fields.keys()))
        return ParseResult(None, "missing-employee", 200)

    if not _is_successful_fingerprint(fields):
        logger.info(
            "Non-fingerprint event employee_no=%r verify=%r subEventType=%r",
            employee_no,
            _verify_mode(fields),
            _sub_event_type(fields),
        )
        return ParseResult(None, "not-fingerprint-event", 200)

    event_time, time_source = _extract_event_time(fields, received_at)
    if time_source == "received_at":
        logger.info(
            "Event missing device dateTime; using webhook receive time=%s employee_no=%s serialNo=%s",
            event_time.isoformat(),
            employee_no,
            fields.get("serialNo"),
        )
    else:
        logger.info(
            "Event time from %s=%s employee_no=%s serialNo=%s",
            time_source,
            event_time.isoformat(),
            employee_no,
            fields.get("serialNo"),
        )

    event_type = str(fields.get("eventType") or fields.get("majorEventType") or "").strip()
    sub_event_type = _sub_event_type(fields)
    device_serial = str(
        fields.get("serialNo")
        or fields.get("deviceSerialNo")
        or fields.get("devIndex")
        or "unknown-device"
    ).strip()
    event_id = str(fields.get("eventId") or fields.get("uuid") or fields.get("serialNo") or "").strip()
    if not event_id:
        fingerprint = f"{device_serial}|{employee_no}|{event_time.isoformat()}|{event_type}|{sub_event_type}".encode()
        event_id = hashlib.sha1(fingerprint).hexdigest()

    return ParseResult(
        AttendanceEvent(
            employee_no=employee_no,
            event_time=event_time,
            event_type=event_type,
            sub_event_type=sub_event_type,
            device_serial=device_serial or "unknown-device",
            event_id=event_id,
            raw_fields=fields,
        ),
        "parsed",
        200,
    )
