# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

from odoo.addons.hr_attendance.controllers.main import HrAttendance


class HrAttendanceCustom(HrAttendance):

    @staticmethod
    def _get_user_attendance_data(employee):
        if employee:
            return employee._get_attendance_systray_user_data()
        return HrAttendance._get_user_attendance_data(employee)

    @http.route('/hr_attendance/systray_check_in_out', type='jsonrpc', auth='user')
    def systray_attendance(self, latitude=False, longitude=False):
        employee = request.env.user.employee_id
        geo_ip_response = self._get_geoip_response(
            mode='systray',
            latitude=latitude,
            longitude=longitude,
            device_tracking_enabled=employee.company_id.attendance_device_tracking,
        )
        employee.with_context(
            attendance_device_location=bool(latitude and longitude),
        )._attendance_action_change(geo_ip_response)
        return self._get_employee_info_response(employee)
