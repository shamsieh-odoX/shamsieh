"""Re-apply homepage override after upgrade (clears Website Editor COW)."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.website_shamsieh.hooks import force_shamsieh_homepage

    force_shamsieh_homepage(env)
