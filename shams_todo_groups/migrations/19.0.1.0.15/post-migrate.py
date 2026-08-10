# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo.api import Environment

    env = Environment(cr, 1, {})
    lang = env['res.lang'].with_context(active_test=False).search(
        [('code', 'in', ['ar_001', 'ar'])], limit=1,
    )
    if not lang:
        return
    mod = env['ir.module.module'].search([
        ('name', '=', 'shams_todo_groups'),
        ('state', '=', 'installed'),
    ], limit=1)
    if mod:
        mod._update_translations(filter_lang=[lang.code], overwrite=True)
