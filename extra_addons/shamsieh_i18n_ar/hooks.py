# -*- coding: utf-8 -*-

import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


def load_standard_ar_translations(env):
    """Load bundled Odoo 19 Arabic PO files for standard HR/Project modules."""
    from odoo.tools.translate import TranslationImporter

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
            importer.load_file(str(po_file), 'ar')
            loaded += 1
        except Exception:
            _logger.exception('shamsieh_i18n_ar: failed loading %s', po_file.name)
    if loaded:
        importer.save(overwrite=True)
        _logger.info('shamsieh_i18n_ar: loaded %s Arabic translation file(s)', loaded)


def post_init_hook(env):
    load_standard_ar_translations(env)
