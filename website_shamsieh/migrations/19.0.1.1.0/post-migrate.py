def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.website_shamsieh.hooks import force_shamsieh_homepage

    force_shamsieh_homepage(env)
