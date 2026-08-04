# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Recompute late minutes and sync presence after break semantic fix."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Employee = env['hr.employee']
    employees = Employee.search([])
    if hasattr(Employee, '_sync_hikvision_presence_from_last_punch'):
        employees._sync_hikvision_presence_from_last_punch()

    Attendance = env['hr.attendance']
    open_or_recent = Attendance.search([
        '|',
        ('check_out', '=', False),
        ('date', '>=', '2026-07-01'),
    ])
    if open_or_recent:
        open_or_recent._compute_attendance_status_fields()
