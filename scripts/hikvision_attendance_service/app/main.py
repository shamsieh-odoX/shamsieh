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
from .hikvision_parser import AttendanceEvent, parse_event
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


logging.getLogger("uvicorn.access").addFilter(_SuppressDoorHeartbeatAccessLog())

settings = get_settings()
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
    if result == "employee-not-found":
        return 404
    return 200


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

    day_start, day_end = odoo.get_today_range_utc(employee, event.event_time)
    if odoo.has_attendance_for_day(employee["id"], day_start, day_end):
        logger.info(
            "Duplicate attendance for employee=%s day_range=(%s,%s)",
            employee["id"],
            day_start,
            day_end,
        )
        store.mark_processed(event.device_serial, event.event_id, event.employee_no, event.event_time.isoformat())
        return "duplicate-attendance"

    attendance_id = odoo.create_checkin(employee["id"], event.event_time.astimezone(timezone.utc))
    store.mark_processed(event.device_serial, event.event_id, event.employee_no, event.event_time.isoformat())
    logger.info(
        "Created attendance id=%s employee=%s event_id=%s",
        attendance_id,
        employee["id"],
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


@app.post("/hikvision/attendance")
async def hikvision_attendance(request: Request):
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    remote = request.client.host if request.client else "unknown"
    try:
        parsed = parse_event(body, content_type, received_at=datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Invalid Hikvision payload from %s: %s", remote, exc)
        return _api_response({"status": "error", "reason": "invalid-payload"}, 400)

    if not parsed.event and parsed.reason == "system-event":
        _note_system_event(remote)
        return _api_response(
            {"status": "error", "reason": parsed.reason},
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
        return _api_response(
            {"status": "error", "reason": parsed.reason},
            parsed.status_code,
        )

    try:
        result = process_event(parsed.event)
        return _api_response(
            {"status": "ok", "result": result},
            _result_status_code(result),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing failed, queueing for retry event_id=%s", parsed.event.event_id)
        store.enqueue_retry(_event_to_payload(parsed.event), str(exc), settings.retry_interval_seconds)
        return _api_response({"status": "queued", "reason": "odoo-unavailable"}, 503)


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
