# -*- coding: utf-8 -*-

def migrate(cr, version):
    from odoo.api import Environment
    from odoo.addons.project_custom_ext.hooks import _reload_ar_translations
    env = Environment(cr, 1, {})
    _reload_ar_translations(env, 'project_custom_ext')
