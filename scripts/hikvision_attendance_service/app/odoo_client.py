from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import xmlrpc.client


class OdooError(Exception):
    pass


@dataclass(frozen=True)
class OdooConfig:
    url: str
    db: str
    username: str
    api_key: str


class OdooClient:
    def __init__(self, cfg: OdooConfig) -> None:
        self.cfg = cfg
        self.common = xmlrpc.client.ServerProxy(f"{cfg.url}/xmlrpc/2/common", allow_none=True)
        self.models = xmlrpc.client.ServerProxy(f"{cfg.url}/xmlrpc/2/object", allow_none=True)
        self.uid = self.common.authenticate(cfg.db, cfg.username, cfg.api_key, {})
        if not self.uid:
            raise OdooError("Failed to authenticate to Odoo XML-RPC")

    def _execute(self, model: str, method: str, *args, **kwargs):
        try:
            return self.models.execute_kw(
                self.cfg.db,
                self.uid,
                self.cfg.api_key,
                model,
                method,
                list(args),
                kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise OdooError(str(exc)) from exc

    def ping(self) -> dict:
        version = self.common.version()
        modules_count = self._execute("ir.module.module", "search_count", [("state", "=", "installed")])
        return {"version": version.get("server_version"), "installed_modules": modules_count}

    def find_employee_by_barcode(self, employee_no: str) -> dict | None:
        records = self._execute(
            "hr.employee",
            "search_read",
            [("barcode", "=", employee_no)],
            fields=["id", "name", "company_id", "user_id"],
            limit=1,
        )
        return records[0] if records else None

    def _resolve_timezone(self, employee: dict) -> str:
        user_id = employee.get("user_id")
        if user_id:
            user_data = self._execute("res.users", "read", [user_id[0]], fields=["tz"])
            if user_data and user_data[0].get("tz"):
                return user_data[0]["tz"]
        company_id = employee.get("company_id")
        if company_id:
            company_data = self._execute(
                "res.company",
                "read",
                [company_id[0]],
                fields=["resource_calendar_id"],
            )
            if company_data and company_data[0].get("resource_calendar_id"):
                calendar_id = company_data[0]["resource_calendar_id"][0]
                calendar_data = self._execute("resource.calendar", "read", [calendar_id], fields=["tz"])
                if calendar_data and calendar_data[0].get("tz"):
                    return calendar_data[0]["tz"]
        return "UTC"

    def _zoneinfo(self, tz_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def get_today_range_utc(self, employee: dict, event_time: datetime) -> tuple[str, str]:
        tz_name = self._resolve_timezone(employee)
        local_tz = self._zoneinfo(tz_name)
        aware = event_time if event_time.tzinfo else event_time.replace(tzinfo=timezone.utc)
        local_dt = aware.astimezone(local_tz)
        local_day: date = local_dt.date()
        local_start = datetime.combine(local_day, time.min, tzinfo=local_tz)
        local_end = datetime.combine(local_day, time.max, tzinfo=local_tz)
        utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
        utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
        return (
            utc_start.strftime("%Y-%m-%d %H:%M:%S"),
            utc_end.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def has_attendance_for_day(self, employee_id: int, start_utc: str, end_utc: str) -> bool:
        count = self._execute(
            "hr.attendance",
            "search_count",
            [
                ("employee_id", "=", employee_id),
                ("check_in", ">=", start_utc),
                ("check_in", "<=", end_utc),
            ],
        )
        return bool(count)

    def create_checkin(self, employee_id: int, event_time: datetime) -> int:
        if event_time.tzinfo:
            check_in = event_time.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            check_in = event_time
        return self._execute(
            "hr.attendance",
            "create",
            [{
                "employee_id": employee_id,
                "check_in": check_in.strftime("%Y-%m-%d %H:%M:%S"),
            }],
        )
