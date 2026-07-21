# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def _reload_ar_translations(env, module_name):
    lang = env['res.lang'].with_context(active_test=False).search(
        [('code', 'in', ['ar_001', 'ar'])], limit=1,
    )
    if not lang:
        return
    mod = env['ir.module.module'].search([('name', '=', module_name)], limit=1)
    if mod:
        mod._update_translations(filter_lang=[lang.code], overwrite=True)


def post_init_hook(env):
    """Best-effort backfill; never abort module install/upgrade."""
    try:
        Attendance = env['hr.attendance']
        if 'attendance_source' in Attendance._fields:
            mode_map = {
                'kiosk': 'kiosk',
                'systray': 'systray',
                'manual': 'manual',
                'technical': 'manual',
                'auto_check_out': 'manual',
            }
            for attendance in Attendance.search([('attendance_source', '=', False)]):
                source = mode_map.get(attendance.in_mode, 'manual')
                attendance.attendance_source = source

        Policy = env['fingerprint.attendance.policy']
        for company in env['res.company'].search([]):
            Policy.create_default_for_company(company)

        Device = env['fingerprint.device']
        hikvision_devices = Device.search([
            ('api_type', '=', 'hikvision'),
            ('active', '=', True),
        ])
        for device in hikvision_devices:
            patch = {}
            if not device.http_listening_enabled:
                patch['http_listening_enabled'] = True
            if not device.http_listening_token:
                patch['http_listening_token'] = Device._generate_http_listening_token()
            if not device.http_listening_allowed_ips and device.device_ip:
                patch['http_listening_allowed_ips'] = device.device_ip
            if device.http_listening_enabled and device.auto_sync:
                patch['auto_sync'] = False
            if patch:
                device.write(patch)

        _reload_ar_translations(env, 'hr_attendance_custom_ext')

        Log = env['fingerprint.device.log']
        logs_with_employee = Log.search([('employee_id', '!=', False)])
        for log in logs_with_employee:
            if log.employee_id and log.employee_name != log.employee_id.name:
                log.employee_name = log.employee_id.name
    except Exception:
        _logger.exception(
            'hr_attendance_custom_ext post_init_hook skipped due to error'
        )
