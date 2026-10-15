def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.website_shamsieh.hooks import (
        ensure_arabic_website_language,
        force_shamsieh_homepage,
        reload_website_ar_translations,
    )

    force_shamsieh_homepage(env)
    ensure_arabic_website_language(env)
    reload_website_ar_translations(env)
