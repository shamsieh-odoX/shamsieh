# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'crm_lead' AND column_name = 'sector_legacy'
    """)
    if not cr.fetchone():
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    code_to_id = {
        sector.code: sector.id
        for sector in env['crm.lead.sector'].search([('code', '!=', False)])
    }
    for code, sector_id in code_to_id.items():
        cr.execute("""
            UPDATE crm_lead
            SET sector_id = %s
            WHERE sector_legacy = %s
        """, (sector_id, code))

    cr.execute("ALTER TABLE crm_lead DROP COLUMN IF EXISTS sector_legacy")
