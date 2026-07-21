"""Early cleanup for stale To-Do asset registrations."""


def _purge_stale_todo_assets(cr):
    """Remove leftover asset defs/attachments that still reference deleted SCSS.

    Production kept compiling web.assets_web_dark with the old dark SCSS
    (invalid '#' comments) via ir.asset / ir.attachment overrides even after
    those files were removed from git.
    """
    cr.execute(
        """
        DELETE FROM ir_asset
        WHERE path ILIKE '%shams_todo_groups%'
           OR path ILIKE '%shams_todo_done_checkmark%'
           OR name ILIKE '%shams_todo%'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_attachment
        WHERE url ILIKE '%shams_todo_groups%/scss/%'
           OR url ILIKE '%shams_todo_done_checkmark%'
           OR url ILIKE '/web/assets/%'
           OR name ILIKE 'web.assets_web_dark%'
           OR name ILIKE 'web.assets_backend%'
        """
    )


def pre_init_hook(env):
    # Odoo 19 passes env (install only). Upgrades use migrations/pre-migrate.py.
    _purge_stale_todo_assets(env.cr)
