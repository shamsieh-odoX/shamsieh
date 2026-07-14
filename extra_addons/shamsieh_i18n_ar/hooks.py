# -*- coding: utf-8 -*-

import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


def _get_arabic_lang_code(env):
    """Resolve the installed Arabic language code (ar_001 in Odoo 19)."""
    Lang = env['res.lang'].with_context(active_test=False)
    for code in ('ar_001', 'ar_SY', 'ar'):
        if Lang._lang_get(code):
            return code
    lang = Lang.search([('iso_code', '=', 'ar')], limit=1)
    return lang.code if lang else None


def load_standard_ar_translations(env):
    """Load bundled Odoo 19 Arabic PO files for standard HR/Project modules."""
    from odoo.tools.translate import TranslationImporter

    lang = _get_arabic_lang_code(env)
    if not lang:
        _logger.warning('shamsieh_i18n_ar: Arabic language is not installed (expected ar_001)')
        return

    po_dir = Path(__file__).resolve().parent / 'i18n' / 'standard'
    if not po_dir.is_dir():
        _logger.warning('shamsieh_i18n_ar: standard PO directory missing: %s', po_dir)
        return

    importer = TranslationImporter(env.cr)
    loaded = 0
    po_files = sorted(po_dir.glob('*.po'))
    overrides = po_dir / 'shamsieh_overrides.po'
    if overrides in po_files:
        po_files = [p for p in po_files if p != overrides] + [overrides]
    for po_file in po_files:
        try:
            importer.load_file(str(po_file), lang)
            loaded += 1
        except Exception:
            _logger.exception('shamsieh_i18n_ar: failed loading %s', po_file.name)
    if loaded:
        importer.save(overwrite=True)
        _logger.info(
            'shamsieh_i18n_ar: loaded %s Arabic translation file(s) for %s',
            loaded, lang,
        )


def post_init_hook(env):
    load_standard_ar_translations(env)
    _reload_custom_module_translations(env)


def _reload_custom_module_translations(env):
    lang = env['res.lang'].with_context(active_test=False).search(
        [('code', 'in', ['ar_001', 'ar'])], limit=1,
    )
    if not lang:
        return
    for module_name in (
        'hr_attendance_custom_ext',
        'hr_holidays_custom_ext',
        'hr_overtime_management',
        'hr_overtime_payroll',
        'project_custom_ext',
        'crm_custom_ext',
    ):
        mod = env['ir.module.module'].search([
            ('name', '=', module_name),
            ('state', '=', 'installed'),
        ], limit=1)
        if mod:
            mod._update_translations(filter_lang=[lang.code], overwrite=True)
