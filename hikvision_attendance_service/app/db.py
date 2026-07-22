from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_serial TEXT NOT NULL,
                event_id TEXT NOT NULL,
                employee_no TEXT,
                event_time TEXT,
                processed_at TEXT NOT NULL,
                UNIQUE(device_serial, event_id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS retry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                next_retry_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def is_processed(self, device_serial: str, event_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM processed_events WHERE device_serial = ? AND event_id = ? LIMIT 1",
            (device_serial, event_id),
        ).fetchone()
        return row is not None

    def mark_processed(
        self,
        device_serial: str,
        event_id: str,
        employee_no: str | None,
        event_time: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO processed_events(device_serial, event_id, employee_no, event_time, processed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_serial, event_id, employee_no, event_time, utcnow_iso()),
        )
        self.conn.commit()

    def enqueue_retry(self, payload: dict[str, Any], error: str, delay_seconds: int) -> None:
        next_retry = datetime.now(timezone.utc).timestamp() + delay_seconds
        self.conn.execute(
            """
            INSERT INTO retry_queue(payload_json, attempts, last_error, created_at, next_retry_at)
            VALUES (?, 0, ?, ?, ?)
            """,
            (
                json.dumps(payload),
                error,
                utcnow_iso(),
                datetime.fromtimestamp(next_retry, tz=timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def get_due_retry_events(self, limit: int = 100) -> list[sqlite3.Row]:
        now = utcnow_iso()
        cur = self.conn.execute(
            """
            SELECT id, payload_json, attempts
            FROM retry_queue
            WHERE next_retry_at <= ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (now, limit),
        )
        return list(cur.fetchall())

    def mark_retry_success(self, row_id: int) -> None:
        self.conn.execute("DELETE FROM retry_queue WHERE id = ?", (row_id,))
        self.conn.commit()

    def mark_retry_failure(self, row_id: int, attempts: int, error: str, delay_seconds: int) -> None:
        next_retry = datetime.now(timezone.utc).timestamp() + delay_seconds
        self.conn.execute(
            """
            UPDATE retry_queue
            SET attempts = ?, last_error = ?, next_retry_at = ?
            WHERE id = ?
            """,
            (
                attempts,
                error,
                datetime.fromtimestamp(next_retry, tz=timezone.utc).isoformat(),
                row_id,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
