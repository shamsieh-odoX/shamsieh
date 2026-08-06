# -*- coding: utf-8 -*-
"""Re-apply Time Off Admin strip; keep Attendance Admin for integration bot."""

import logging

_logger = logging.getLogger(__name__)

ALLOWED_TIME_OFF_ADMIN_LOGINS = {
    'admin',
    'mohaned@shamsieh.com',
}


def migrate(cr, version):
    try:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr, SUPERUSER_ID, {})
    except Exception:
        _logger.exception('hr_holidays_custom_ext 19.0.1.4.3 migrate failed')
        return

    time_off_admin = env.ref('hr_holidays.group_hr_holidays_manager', raise_if_not_found=False)
    if not time_off_admin:
        return

    users = env['res.users'].sudo().search([
        ('share', '=', False),
        ('active', '=', True),
        ('group_ids', 'in', [time_off_admin.id]),
    ])
    for user in users:
        login = (user.login or '').strip().lower()
        if login in ALLOWED_TIME_OFF_ADMIN_LOGINS:
            continue
        user.write({'group_ids': [(3, time_off_admin.id)]})
        _logger.info('Removed Time Off Administrator from %s', login)
