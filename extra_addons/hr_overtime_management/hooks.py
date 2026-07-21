# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    try:
        env['res.company']._ensure_overtime_types_for_all_companies()
    except Exception:
        _logger.exception('hr_overtime_management: failed ensuring overtime types')
    try:
        _reload_ar_translations(env, 'hr_overtime_management')
    except Exception:
        _logger.exception('hr_overtime_management: failed reloading Arabic translations')


def _reload_ar_translations(env, module_name):
    lang = env['res.lang'].with_context(active_test=False).search(
        [('code', 'in', ['ar_001', 'ar'])], limit=1,
    )
    if not lang:
        return
    mod = env['ir.module.module'].search([('name', '=', module_name)], limit=1)
    if mod:
        mod._update_translations(filter_lang=[lang.code], overwrite=True)
