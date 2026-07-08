from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from .config import get_settings
from .db import EventStore
from .hikvision_parser import (
    AttendanceEvent,
    debug_multipart,
    parse_event,
    parse_fields,
    _employee_no,
    _sub_event_type,
    _verify_mode,
)
from .odoo_client import OdooClient, OdooConfig, OdooError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("hikvision_bridge")


class _SuppressDoorHeartbeatAccessLog(logging.Filter):
    """Hide uvicorn access lines for ignored door/system webhooks (HTTP 204)."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return 'POST /hikvision/attendance HTTP/1.1" 204' not in message


settings = get_settings()
if settings.verbose_logging:
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger("app.hikvision_parser").setLevel(logging.DEBUG)
    logger.info("VERBOSE_LOGGING enabled — all requests and payloads will be logged")
else:
    logging.getLogger("uvicorn.access").addFilter(_SuppressDoorHeartbeatAccessLog())

store = EventStore(settings.sqlite_path)
odoo: OdooClient | None = None
_system_event_counts: dict[str, int] = {}
_system_event_last_summary: dict[str, float] = {}
SYSTEM_EVENT_SUMMARY_SECONDS = 60.0


def _note_system_event(remote: str) -> None:
    _system_event_counts[remote] = _system_event_counts.get(remote, 0) + 1
    now = time.monotonic()
    last = _system_event_last_summary.get(remote, 0.0)
    if now - last < SYSTEM_EVENT_SUMMARY_SECONDS:
        return
    count = _system_event_counts.pop(remote, 0)
    _system_event_last_summary[remote] = now
    if count:
        logger.info(
            "Ignored %s door/system event(s) from %s (subEventType 21-24; further logs suppressed for %ss)",
            count,
            remote,
            int(SYSTEM_EVENT_SUMMARY_SECONDS),
        )


def _event_to_payload(event: AttendanceEvent) -> dict[str, Any]:
    payload = asdict(event)
    payload["event_time"] = event.event_time.isoformat()
    return payload


def _payload_to_event(payload: dict[str, Any]) -> AttendanceEvent:
    return AttendanceEvent(
        employee_no=payload["employee_no"],
        event_time=datetime.fromisoformat(payload["event_time"]),
        event_type=payload.get("event_type", ""),
        sub_event_type=payload.get("sub_event_type", ""),
        device_serial=payload.get("device_serial", "unknown-device"),
        event_id=payload.get("event_id", ""),
        raw_fields=payload.get("raw_fields", {}),
    )


def _api_response(content: dict[str, Any], status_code: int = 200) -> JSONResponse | Response:
    if status_code == 204:
        return Response(status_code=204)
    return JSONResponse(status_code=status_code, content=content)


def _result_status_code(result: str) -> int:
    if result == "created":
        return 201
    return 200


def _device_response(content: dict[str, Any], status_code: int | None = None) -> JSONResponse:
    """Hikvision redelivers events unless the webhook returns HTTP 200/201."""
    code = status_code if status_code in (200, 201) else 200
    return JSONResponse(status_code=code, content=content)


def _connect_odoo() -> OdooClient | None:
    try:
        return OdooClient(
            OdooConfig(
                url=settings.odoo_url,
                db=settings.odoo_db,
                username=settings.odoo_bot_user,
                api_key=settings.odoo_api_key,
            )
        )
    except OdooError as exc:
        logger.error("Odoo connection failed: %s", exc)
        return None


def process_event(event: AttendanceEvent, *, from_retry: bool = False) -> str:
    if not odoo:
        raise OdooError("Odoo client not initialized")

    if store.is_processed(event.device_serial, event.event_id):
        logger.info(
            "Skip duplicate event_id=%s device=%s employee=%s",
            event.event_id,
            event.device_serial,
            event.employee_no,
        )
        return "duplicate-event"

    employee = odoo.find_employee_by_barcode(event.employee_no)
    if not employee:
        logger.warning("No employee found for barcode=%s", event.employee_no)
        store.mark_processed(event.device_serial, event.event_id, event.employee_no, event.event_time.isoformat())
        return "employee-not-found"
    attendance_status = str(event.raw_fields.get("attendanceStatus") or "").strip().lower()
    open_attendance = odoo.get_open_attendance(employee["id"])
    checkout_statuses = {"checkout", "check_out", "breakout", "break_out"}
    checkin_statuses = {"checkin", "check_in", "breakin", "break_in", "undefined", ""}

    if attendance_status in checkout_statuses:
        if not open_attendance:
            store.mark_processed(event.device_serial, event.event_id, event.employee_no, event.event_time.isoformat())
            logger.info(
                "No open attendance to close employee=%s status=%s event_id=%s",
                employee["id"],
                attendance_status or "unknown",
                event.event_id,
            )
            return "no-open-attendance"
        odoo.checkout_from_hikvision(
            int(open_attendance["id"]),
            event.event_time.astimezone(timezone.utc),
            event_id=event.event_id,
            employee_no=event.employee_no,
        )
        store.mark_processed(event.device_serial, event.event_id, event.employee_no, event.event_time.isoformat())
        logger.info(
            "Closed attendance id=%s employee=%s status=%s event_id=%s",
            open_attendance["id"],
            employee["id"],
            attendance_status,
            event.event_id,
        )
        return attendance_status

    if attendance_status in checkin_statuses and open_attendance:
        logger.info(
            "Duplicate open attendance for employee=%s open_id=%s status=%s",
            employee["id"],
            open_attendance["id"],
            attendance_status or "checkin",
        )
        store.mark_processed(event.device_serial, event.event_id, event.employee_no, event.event_time.isoformat())
        return "duplicate-attendance"

    attendance_id = odoo.create_checkin_from_hikvision(
        employee["id"],
        event.event_time.astimezone(timezone.utc),
        event_id=event.event_id,
        employee_no=event.employee_no,
    )
    store.mark_processed(event.device_serial, event.event_id, event.employee_no, event.event_time.isoformat())
    logger.info(
        "Created attendance id=%s employee=%s status=%s event_id=%s",
        attendance_id,
        employee["id"],
        attendance_status or "checkin",
        event.event_id,
    )
    return "created"


async def retry_worker() -> None:
    global odoo
    while True:
        await asyncio.sleep(settings.retry_interval_seconds)
        if not odoo:
            odoo = _connect_odoo()
        rows = store.get_due_retry_events()
        if not rows:
            continue
        for row in rows:
            payload = json.loads(row["payload_json"])
            event = _payload_to_event(payload)
            try:
                status = process_event(event, from_retry=True)
                store.mark_retry_success(row["id"])
                logger.info("Retry success row_id=%s result=%s", row["id"], status)
            except Exception as exc:  # noqa: BLE001
                attempts = row["attempts"] + 1
                store.mark_retry_failure(row["id"], attempts, str(exc), settings.retry_interval_seconds)
                logger.exception("Retry failed row_id=%s attempts=%s", row["id"], attempts)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global odoo
    odoo = _connect_odoo()
    task = asyncio.create_task(retry_worker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        store.close()


app = FastAPI(title="Hikvision Attendance Bridge", lifespan=lifespan)


@app.get("/hikvision/attendance")
async def hikvision_attendance_get():
    return {
        "status": "ok",
        "message": "Webhook is reachable. Hikvision must send POST events to this URL.",
    }


def _log_verbose_request(
    remote: str,
    body: bytes,
    content_type: str,
    fields: dict[str, Any],
    parsed_reason: str,
    status_code: int,
) -> None:
    logger.info(
        "VERBOSE POST remote=%s bytes=%s content_type=%r subEventType=%s employee_no=%r verify=%r -> %s HTTP %s",
        remote,
        len(body),
        content_type,
        _sub_event_type(fields),
        _employee_no(fields) or None,
        _verify_mode(fields) or None,
        parsed_reason,
        status_code,
    )
    logger.debug("VERBOSE parsed_fields=%s", fields)
    if "multipart/" in (content_type or "").lower():
        for part in debug_multipart(body, content_type):
            logger.info(
                "VERBOSE multipart part name=%r content_type=%r preview=%s",
                part.get("name"),
                part.get("content_type"),
                part.get("preview", "")[:800],
            )


@app.post("/hikvision/attendance")
async def hikvision_attendance(request: Request):
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    remote = request.client.host if request.client else "unknown"
    fields: dict[str, Any] = {}
    try:
        fields = parse_fields(body, content_type)
        parsed = parse_event(body, content_type, received_at=datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Invalid Hikvision payload from %s: %s", remote, exc)
        if settings.verbose_logging:
            logger.debug("VERBOSE invalid body preview=%r", body[:800])
        return _device_response({"status": "error", "reason": "invalid-payload"}, 200)

    if settings.verbose_logging:
        status_code = parsed.status_code if not parsed.event else _result_status_code("created")
        if not parsed.event:
            status_code = parsed.status_code
        _log_verbose_request(remote, body, content_type, fields, parsed.reason, status_code)

    if not parsed.event and parsed.reason == "system-event":
        if settings.verbose_logging:
            logger.info(
                "VERBOSE ignored door/system event subEventType=%s serialNo=%s from %s",
                _sub_event_type(fields),
                fields.get("serialNo"),
                remote,
            )
        else:
            _note_system_event(remote)
        return _device_response(
            {"status": "ignored", "reason": parsed.reason},
            parsed.status_code,
        )

    logger.info(
        "Received Hikvision POST bytes=%s content_type=%r remote=%s reason=%s",
        len(body),
        content_type,
        remote,
        parsed.reason if not parsed.event else "attendance",
    )

    if not parsed.event:
        return _device_response(
            {"status": "error", "reason": parsed.reason},
            parsed.status_code,
        )

    try:
        result = process_event(parsed.event)
        return _device_response(
            {"status": "ok", "result": result},
            _result_status_code(result),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing failed, queueing for retry event_id=%s", parsed.event.event_id)
        store.enqueue_retry(_event_to_payload(parsed.event), str(exc), settings.retry_interval_seconds)
        return _device_response({"status": "queued", "reason": "odoo-unavailable"}, 200)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/odoo/ping")
async def odoo_ping():
    global odoo
    if not odoo:
        odoo = _connect_odoo()
    if not odoo:
        return {"status": "error", "reason": "not-initialized"}
    try:
        data = odoo.ping()
        return {"status": "ok", "odoo": data}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": str(exc)}
