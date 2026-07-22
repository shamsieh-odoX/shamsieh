# -*- coding: utf-8 -*-

def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    from odoo.addons.project_custom_ext.hooks import _mark_closing_stages, _override_spreadsheet_dashboard

    env = api.Environment(cr, SUPERUSER_ID, {})
    _mark_closing_stages(env)
    _override_spreadsheet_dashboard(env)
