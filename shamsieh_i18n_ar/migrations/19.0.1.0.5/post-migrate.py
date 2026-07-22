# -*- coding: utf-8 -*-

from odoo.addons.shamsieh_i18n_ar.hooks import load_standard_ar_translations, _reload_custom_module_translations


def migrate(cr, version):
    from odoo.api import Environment
    env = Environment(cr, 1, {})
    load_standard_ar_translations(env)
    _reload_custom_module_translations(env)
