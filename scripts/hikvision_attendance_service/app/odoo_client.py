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

    def _attendance_field_names(self) -> set[str]:
        if not hasattr(self, "_attendance_fields_cache"):
            fields_map = self._execute("hr.attendance", "fields_get", [], attributes=["type"])
            self._attendance_fields_cache = set(fields_map.keys())
        return self._attendance_fields_cache

    def _employee_field_names(self) -> set[str]:
        if not hasattr(self, "_employee_fields_cache"):
            fields_map = self._execute("hr.employee", "fields_get", [], attributes=["type"])
            self._employee_fields_cache = set(fields_map.keys())
        return self._employee_fields_cache

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

    def get_open_attendance(self, employee_id: int) -> dict | None:
        records = self._execute(
            "hr.attendance",
            "search_read",
            [
                ("employee_id", "=", employee_id),
                ("check_out", "=", False),
            ],
            fields=["id", "check_in", "check_out"],
            order="check_in desc",
            limit=1,
        )
        return records[0] if records else None

    def _build_source_vals(
        self,
        *,
        event_id: str,
        employee_no: str,
        for_check_in: bool,
        punch_type: str | None = None,
    ) -> dict:
        field_names = self._attendance_field_names()
        vals: dict[str, str] = {}
        if "attendance_source" in field_names:
            vals["attendance_source"] = "fingerprint"
        if "external_log_id" in field_names:
            vals["external_log_id"] = event_id
        if "device_user_id" in field_names:
            vals["device_user_id"] = employee_no
        if punch_type and "hikvision_punch_type" in field_names:
            vals["hikvision_punch_type"] = punch_type
        if for_check_in and "in_mode" in field_names:
            vals["in_mode"] = "technical"
        if not for_check_in and "out_mode" in field_names:
            vals["out_mode"] = "technical"
        return vals

    def set_hikvision_presence_status(self, employee_id: int, presence_status: str) -> None:
        field_names = self._employee_field_names()
        if "hikvision_presence_status" not in field_names:
            return
        self._execute(
            "hr.employee",
            "write",
            [employee_id],
            {"hikvision_presence_status": presence_status},
        )

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

    def process_hikvision_punch(
        self,
        employee_id: int,
        punch_type: str,
        event_time: datetime,
        *,
        event_id: str,
        employee_no: str,
    ) -> dict:
        if event_time.tzinfo:
            punch_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            punch_time = event_time
        punch_time_str = punch_time.strftime("%Y-%m-%d %H:%M:%S")
        if "hikvision_presence_status" not in self._employee_field_names():
            raise OdooError("Upgrade hr_attendance_custom_ext on Odoo before using break punches.")
        return self._execute(
            "hr.employee",
            "hikvision_bridge_punch",
            employee_id,
            punch_type,
            punch_time_str,
            external_log_id=event_id,
            device_user_id=employee_no,
            attendance_source="fingerprint",
        )
