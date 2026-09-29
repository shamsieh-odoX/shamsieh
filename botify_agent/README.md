# Botify Agent for Odoo 19

This addon embeds Botify's assistant in the Odoo backend. Operations are
granted by Botify for the logged-in Odoo user, then executed in that user's
Odoo environment so Odoo access rights, record rules, and company scope apply.

## Configure

After upgrading the addon, go to **Settings → Botify Agent** and configure:

- Enable the agent.
- Botify API URL and installation key supplied by Botify.
- Installation secret shared with Botify.
- The operation classes that Odoo should permit. Botify must permit them too;
  the employee's own Odoo rights still apply to each operation.
- Assign employees to the **Botify Agent user** group.

The installation key is intentionally not copied from the previous addon's
`installation_id`: that value identified a Botify connection, while this
version requires the new installation key. The upgrade preserves the API URL,
enabled setting, and shared secret where present.

## Protocol and operations

The browser loads Botify's widget and relays its signed grants to the
session-authenticated `/botify_agent/v1/*` routes. The addon checks the grant,
binds it to the current Odoo session and user, applies the local risk-class
settings, validates the requested operation, and executes without `sudo()`.
It records operation outcomes and Botify notifications in Odoo for audit and
delivery retry.

This release uses the Botify v1 operation-grant and event protocol. The Botify
installation must be configured for this protocol before enabling the addon.
