# -*- coding: utf-8 -*-

from odoo import _, http
from odoo.exceptions import UserError
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

    @http.route('/hr_attendance_custom/systray_punch', type='jsonrpc', auth='user')
    def systray_punch(self, punch_type=False):
        employee = request.env.user.employee_id
        if not employee:
            return {'status': 'error', 'message': _('No employee linked to user.')}
        if punch_type not in {'check_in', 'break_in', 'break_out', 'check_out'}:
            return {'status': 'error', 'message': _('Invalid punch type.')}
        try:
            if punch_type == 'check_in':
                employee._validate_attendance_check_in()
            result = employee.action_systray_punch(punch_type)
            if result.get('status') in {'duplicate', 'no_open_attendance', 'not_on_break'}:
                messages = {
                    'duplicate': _('This punch was already recorded.'),
                    'no_open_attendance': _('You must check in before using this punch.'),
                    'not_on_break': _('You are not currently on break. Use Break Out to start a break first.'),
                }
                return {'status': 'error', 'message': messages[result['status']]}
        except UserError as exc:
            return {'status': 'error', 'message': str(exc)}
        return self._get_employee_info_response(employee)

    @http.route('/hr_attendance_custom/home_pin_check_in', type='jsonrpc', auth='user')
    def home_pin_check_in(self, pin_code=False):
        employee = request.env.user.employee_id
        if not employee:
            return {'status': 'error', 'message': _('No employee linked to user.')}
        try:
            employee._validate_single_daily_check_in()
            if employee._get_attendance_scheduled_location() != 'home':
                raise UserError(_('Home PIN check-in is only allowed on home schedule days.'))
            if not employee._verify_home_attendance_pin(pin_code):
                raise UserError(_('Invalid PIN code.'))
            attendance = employee.with_context(
                attendance_via_home_pin=True,
            )._attendance_action_change()
            attendance.write({
                'attendance_source': 'pin',
                'hikvision_punch_type': 'check_in',
            })
            employee.sudo().hikvision_presence_status = 'working'
        except UserError as exc:
            return {'status': 'error', 'message': str(exc)}
        return {
            'status': 'passed',
            'attendance_id': attendance.id,
            'message': _('OK'),
        }
