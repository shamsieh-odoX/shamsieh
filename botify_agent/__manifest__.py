{
    "name": "Botify Agent",
    "summary": "The Botify AI agent inside Odoo, acting as each employee with their own Odoo permissions",
    "version": "19.0.3.0.2",
    "category": "Productivity",
    "license": "LGPL-3",
    "author": "Botify",
    "depends": ["base", "web", "mail", "bus"],
    "data": [
        "security/botify_security.xml",
        "security/ir.model.access.csv",
        "data/botify_method_data.xml",
        "data/botify_cron.xml",
        "views/botify_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "botify_agent/static/src/botify_service.js",
            "botify_agent/static/src/botify_action.xml",
        ],
    },
    "installable": True,
    "application": False,
}
