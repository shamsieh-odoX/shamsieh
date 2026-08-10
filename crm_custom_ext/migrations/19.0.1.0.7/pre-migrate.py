# -*- coding: utf-8 -*-
"""Link existing Scope of Work / Contract stages before data load to avoid duplicates."""


def migrate(cr, version):
    from odoo.api import Environment

    env = Environment(cr, 1, {})
    Stage = env['crm.stage'].with_context(active_test=False, lang='en_US')
    IMD = env['ir.model.data']

    mappings = [
        ('stage_shamsieh_scope_of_work', ['Scope of Work', 'Scope Of Work']),
        ('stage_shamsieh_contract', ['Contract']),
        ('stage_shamsieh_lost', ['Lost']),
    ]
    for xmlid_name, names in mappings:
        existing = IMD.search([
            ('module', '=', 'crm_custom_ext'),
            ('name', '=', xmlid_name),
        ], limit=1)
        if existing:
            continue
        stage = Stage.search([('name', 'in', names)], limit=1)
        if not stage:
            # Case-insensitive fallback
            for name in names:
                stage = Stage.search([('name', '=ilike', name)], limit=1)
                if stage:
                    break
        if stage:
            IMD.create({
                'module': 'crm_custom_ext',
                'name': xmlid_name,
                'model': 'crm.stage',
                'res_id': stage.id,
                'noupdate': True,
            })
