# -*- coding: utf-8 -*-
"""Restore Attendance rights for the integration bot and sync device IDs to barcode."""

import logging

_logger = logging.getLogger(__name__)

# Users that must keep Attendance Officer/Manager (local bridge + HR ops).
ATTENDANCE_ADMIN_LOGINS = {
    'admin',
    'mohaned@shamsieh.com',
    'm.saqer@shamsieh.com',
}


def migrate(cr, version):
    try:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr, SUPERUSER_ID, {})
    except Exception:
        _logger.exception('hr_attendance_custom_ext: cannot build env')
        return

    officer = env.ref('hr_attendance.group_hr_attendance_officer', raise_if_not_found=False)
    manager = env.ref('hr_attendance.group_hr_attendance_manager', raise_if_not_found=False)
    Users = env['res.users'].sudo()

    for login in ATTENDANCE_ADMIN_LOGINS:
        user = Users.search([('login', '=', login)], limit=1)
        if not user:
            continue
        commands = []
        if officer and officer not in user.group_ids:
            commands.append((4, officer.id))
        if manager and manager not in user.group_ids:
            commands.append((4, manager.id))
        if commands:
            user.write({'group_ids': commands})
            _logger.info('Restored Attendance Officer/Manager for %s', login)

    # Fill empty barcodes from biometric_device_user_id so bridge lookups work.
    employees = env['hr.employee'].sudo().search([
        ('biometric_device_user_id', '!=', False),
        '|',
        ('barcode', '=', False),
        ('barcode', '=', ''),
    ])
    for employee in employees:
        # Avoid unique barcode collisions.
        exists = env['hr.employee'].sudo().search_count([
            ('barcode', '=', employee.biometric_device_user_id),
            ('id', '!=', employee.id),
        ])
        if not exists:
            employee.barcode = employee.biometric_device_user_id
            _logger.info(
                'Set barcode=%s for employee %s from biometric_device_user_id',
                employee.barcode,
                employee.display_name,
            )
