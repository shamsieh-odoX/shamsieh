# -*- coding: utf-8 -*-

def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Remove seed predefined tasks — templates apply stages only by default.
    env['project.task.template.line'].search([('line_type', '=', 'task')]).unlink()
    projects = env['project.project'].search([])
    if projects:
        projects._compute_progress_and_hours()
        projects._compute_progress_range()
