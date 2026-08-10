# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo.api import Environment

    env = Environment(cr, 1, {})

    # Clear compiled web assets so light/dark CSS rebuilds for this module.
    env['ir.attachment'].sudo().search([
        ('url', '=like', '/web/assets/%'),
    ]).unlink()

    lang = env['res.lang'].with_context(active_test=False).search(
        [('code', 'in', ['ar_001', 'ar'])], limit=1,
    )
    mod = env['ir.module.module'].search([
        ('name', '=', 'shams_todo_groups'),
        ('state', '=', 'installed'),
    ], limit=1)
    if mod and lang:
        mod._update_translations(filter_lang=[lang.code], overwrite=True)
