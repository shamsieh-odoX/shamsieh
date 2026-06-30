# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute("""
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_name = 'crm_lead' AND column_name = 'sector'
    """)
    row = cr.fetchone()
    if not row or row[0] not in ('varchar', 'bpchar'):
        return
    cr.execute("""
        ALTER TABLE crm_lead
        ADD COLUMN IF NOT EXISTS sector_legacy varchar
    """)
    cr.execute("""
        UPDATE crm_lead
        SET sector_legacy = sector
        WHERE sector IS NOT NULL AND sector_legacy IS NULL
    """)
