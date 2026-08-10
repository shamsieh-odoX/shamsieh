# Part of Odoo. See LICENSE file for full copyright and licensing details.


def pre_init_hook(env):
    """Preserve legacy selection values before sector becomes a Many2one."""
    cr = env.cr
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


def post_init_hook(env):
    """Map preserved selection codes to the new sector records."""
    cr = env.cr
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'crm_lead' AND column_name = 'sector_legacy'
    """)
    if not cr.fetchone():
        return

    code_to_id = {
        sector.code: sector.id
        for sector in env['crm.lead.sector'].sudo().search([('code', '!=', False)])
    }
    for code, sector_id in code_to_id.items():
        cr.execute("""
            UPDATE crm_lead
            SET sector_id = %s
            WHERE sector_legacy = %s
        """, (sector_id, code))

    cr.execute("ALTER TABLE crm_lead DROP COLUMN IF EXISTS sector_legacy")
