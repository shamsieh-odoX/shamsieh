# -*- coding: utf-8 -*-

def post_init_hook(env):
    """Backfill attendance_source from in_mode on existing records."""
    Attendance = env['hr.attendance']
    if 'attendance_source' not in Attendance._fields:
        return
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
