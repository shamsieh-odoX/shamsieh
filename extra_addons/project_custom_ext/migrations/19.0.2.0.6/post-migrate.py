# -*- coding: utf-8 -*-

def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['project.task.template.line']
    if 'line_type' in Line._fields:
        Line.search([('line_type', '=', 'task')]).unlink()
