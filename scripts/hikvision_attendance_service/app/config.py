from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    odoo_url: str
    odoo_db: str
    odoo_bot_user: str
    odoo_api_key: str
    sqlite_path: str = "hikvision_bridge.db"
    retry_interval_seconds: int = 30
    default_event_timezone: str = "UTC"
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        odoo_url=os.getenv("ODOO_URL", "").rstrip("/"),
        odoo_db=os.getenv("ODOO_DB", ""),
        odoo_bot_user=os.getenv("ODOO_BOT_USER", ""),
        odoo_api_key=os.getenv("ODOO_API_KEY", ""),
        sqlite_path=os.getenv("SQLITE_PATH", "hikvision_bridge.db"),
        retry_interval_seconds=int(os.getenv("RETRY_INTERVAL_SECONDS", "30")),
        default_event_timezone=os.getenv("DEFAULT_EVENT_TIMEZONE", "UTC"),
        listen_host=os.getenv("LISTEN_HOST", "0.0.0.0"),
        listen_port=int(os.getenv("LISTEN_PORT", "8080")),
    )
