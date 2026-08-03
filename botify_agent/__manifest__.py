{
    "name": "Botify Agent",
    "summary": "Embed a Botify AI agent that acts with each employee's own Odoo permissions",
    "description": """
Botify Agent
============

Embeds a Botify AI assistant in the Odoo backend and — crucially — makes it act
**as the employee using it**, not as a shared integration account.

Two endpoints do the work:

* ``/botify_agent/identity`` runs with ``auth="user"``, so it reads the current
  user from ``request.env.user`` on the server. It mints a short-lived signed
  assertion naming that user. The browser cannot influence the subject.

* ``/botify_agent/rpc`` accepts signed calls from Botify and executes them with
  ``with_user(uid)``, which returns a ``su=False`` environment. Odoo therefore
  applies that user's access rights, record rules and allowed companies to every
  read and write. No permission is copied into Botify, so none can go stale.
""",
    "version": "19.0.1.1.0",
    "category": "Productivity/Discuss",
    "license": "LGPL-3",
    "author": "Botify",
    "website": "https://botifyarabia.ai",
    "depends": ["base", "base_setup", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/res_config_settings_views.xml",
        "views/botify_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "botify_agent/static/src/js/botify_widget_loader.js",
            "botify_agent/static/src/js/botify_client_action.js",
            "botify_agent/static/src/xml/botify_client_action.xml",
        ],
    },
    "installable": True,
    "application": False,
}
