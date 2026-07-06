# -*- coding: utf-8 -*-

def post_init_hook(env):
    """Backfill attendance_source and create default attendance policies."""
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
        if patch:
            device.write(patch)

    Log = env['fingerprint.device.log']
    logs_with_employee = Log.search([('employee_id', '!=', False)])
    for log in logs_with_employee:
        if log.employee_id and log.employee_name != log.employee_id.name:
            log.employee_name = log.employee_id.name
