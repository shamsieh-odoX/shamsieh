# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'crm_lead' AND column_name = 'channel_legacy'
    """)
    if not cr.fetchone():
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Channel = env['crm.lead.channel'].sudo()
    code_to_id = {
        channel.code: channel.id
        for channel in Channel.search([('code', '!=', False)])
    }

    cr.execute("""
        SELECT id, channel_legacy, channel_other_legacy
        FROM crm_lead
        WHERE channel_legacy IS NOT NULL OR channel_other_legacy IS NOT NULL
    """)
    for lead_id, channel_code, channel_other in cr.fetchall():
        channel_id = False
        if channel_code == 'other':
            channel = Channel._get_or_create_by_name(channel_other or 'Other')
            channel_id = channel.id
        elif channel_code:
            channel_id = code_to_id.get(channel_code)
            if not channel_id:
                channel = Channel._get_or_create_by_name(channel_code.replace('_', ' ').title())
                channel_id = channel.id
        if channel_id:
            cr.execute(
                "UPDATE crm_lead SET channel_id = %s WHERE id = %s",
                (channel_id, lead_id),
            )

    cr.execute("ALTER TABLE crm_lead DROP COLUMN IF EXISTS channel_legacy")
    cr.execute("ALTER TABLE crm_lead DROP COLUMN IF EXISTS channel_other_legacy")
