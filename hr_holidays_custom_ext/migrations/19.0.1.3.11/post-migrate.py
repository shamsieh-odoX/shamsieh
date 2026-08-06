# -*- coding: utf-8 -*-
"""Keep Time Off / Attendance admin rights only for Ozlam (admin) and Mohaned (GM)."""

import logging

_logger = logging.getLogger(__name__)

# Logins allowed to keep Time Off Administrator.
# Attendance Administrator for the integration bot is restored by
# hr_attendance_custom_ext migrations (m.saqer@shamsieh.com).
ALLOWED_ADMIN_LOGINS = {
    'admin',  # Ozlam
    'mohaned@shamsieh.com',  # GM
}
# Still strip Attendance Admin from normal employees, but keep for IT bot too.
ALLOWED_ATTENDANCE_ADMIN_LOGINS = {
    'admin',
    'mohaned@shamsieh.com',
    'm.saqer@shamsieh.com',
}


def migrate(cr, version):
    env = None
    try:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr, SUPERUSER_ID, {})
    except Exception:
        _logger.exception('hr_holidays_custom_ext migrate: cannot build env')
        return

    time_off_admin = env.ref('hr_holidays.group_hr_holidays_manager', raise_if_not_found=False)
    attendance_admin = env.ref('hr_attendance.group_hr_attendance_manager', raise_if_not_found=False)
    if not time_off_admin and not attendance_admin:
        return

    users = env['res.users'].sudo().search([
        ('share', '=', False),
        ('active', '=', True),
    ])
    stripped = []
    for user in users:
        login = (user.login or '').strip().lower()
        commands = []
        if time_off_admin and time_off_admin in user.group_ids and login not in ALLOWED_ADMIN_LOGINS:
            commands.append((3, time_off_admin.id))
        if (
            attendance_admin
            and attendance_admin in user.group_ids
            and login not in ALLOWED_ATTENDANCE_ADMIN_LOGINS
        ):
            commands.append((3, attendance_admin.id))
        if commands:
            user.write({'group_ids': commands})
            stripped.append(user.login)

    if stripped:
        _logger.info(
            'hr_holidays_custom_ext: removed Time Off/Attendance Admin from: %s',
            ', '.join(stripped),
        )
