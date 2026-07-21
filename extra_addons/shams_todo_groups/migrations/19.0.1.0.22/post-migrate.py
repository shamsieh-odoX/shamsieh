"""Clear stale web asset bundles after CSS path change (scss -> css).

Odoo keeps falling back to a cached dark bundle that still contains the old
invalid `# Kept for backward` line from shams_todo.dark.scss. Deleting the
compiled attachments forces a clean recompile on next request.
"""


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_attachment
        WHERE url LIKE '/web/assets/%'
           OR name LIKE 'web.assets_web_dark%'
           OR name LIKE 'web.assets_backend%'
        """
    )
