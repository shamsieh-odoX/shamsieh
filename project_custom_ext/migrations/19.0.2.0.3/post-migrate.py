# -*- coding: utf-8 -*-

from odoo.addons.project_custom_ext.hooks import _ensure_project_users_have_timesheet_access


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    _ensure_project_users_have_timesheet_access(env)
