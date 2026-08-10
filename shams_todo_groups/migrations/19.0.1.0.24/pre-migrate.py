"""Self-contained: migration scripts cannot import the addon package."""


def migrate(cr, version):
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
