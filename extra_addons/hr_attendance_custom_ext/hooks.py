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
