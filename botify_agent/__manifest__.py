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

* ``/botify_agent/grant`` mints a short-lived, single-use grant naming exactly
  one uid and one operation, in exchange for proof of possession of a
  per-session delegation credential minted alongside the identity assertion.

* ``/botify_agent/rpc`` accepts signed calls from Botify, requires a valid
  grant (protocol v2 — the shared secret alone can no longer name a uid) and
  executes them with ``with_user(uid)``, which returns a ``su=False``
  environment. Odoo therefore applies that user's access rights, record rules
  and allowed companies to every read and write. No permission is copied into
  Botify, so none can go stale.
""",
    "version": "19.0.2.1.3",  # ported from canonical integrations/odoo/botify_agent 18.0.2.0.1 onto the shamsieh Odoo 19 tree, preserving the org-specific backend floating-widget loader (static/src/js/botify_widget.js, NOT part of the canonical addon). 2.0.0 (BREAKING protocol change): /rpc now requires a signed per-operation grant (X-Botify-Grant) obtained from the new /botify_agent/grant endpoint using a per-user delegation credential minted by /identity — the shared secret alone can no longer name an acting uid, every RPC call consumes a single-use jti, and reads/writes/actions are policy-checked against a shared deny-by-default manifest. A Botify backend older than this rebuild cannot drive this addon version, and this addon version cannot serve a Botify backend older than the rebuild. Supersedes 19.0.1.2.2's inline field-guard regex (now centralized in models/botify_policy.py) and its bespoke HMAC-only /rpc auth (now grant-based). Also carries the Odoo-19-specific fix (found while porting this addon to this exact live Odoo 19 tenant, upstreamed into canonical): the nonce replay-guard's UNIQUE(jti) constraint is now created via a raw ALTER TABLE in init() instead of the pre-19 _sql_constraints list, which Odoo 19 silently ignores. 2.1.0: per-tenant classification of this database's own custom models (sanitize_tenant_model + the Odoo-side 'Allow assistant writes to custom models' switch, default off) — see docs/odoo/tenant-models.md.
    "botify_protocol_version": 2,
    "category": "Productivity/Discuss",
    "license": "LGPL-3",
    "author": "Botify",
    "website": "https://botifyarabia.ai",
    "depends": ["base", "base_setup", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/botify_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "botify_agent/static/src/js/botify_client_action.js",
            "botify_agent/static/src/xml/botify_client_action.xml",
            # shamsieh-specific: floating chat widget embedded in the Odoo backend
            # UI (not part of the canonical addon). See the file's own header
            # comment for why it is kept as an independent asset.
            "botify_agent/static/src/js/botify_widget.js",
        ],
    },
    "installable": True,
    "application": False,
}
