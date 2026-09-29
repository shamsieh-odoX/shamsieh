"""v1 (19.0.1.x) -> 19.0.2.0.0: drop v1's settings view before this version's views load.

It extends the settings form with v1 fields that no longer exist, so validating
the new settings view would fail; Odoo only removes it after the upgrade.
"""

V1_SETTINGS_VIEW = "res_config_settings_view_form_botify"


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_ui_view WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'botify_agent' AND model = 'ir.ui.view' AND name = %s
        )
        """,
        [V1_SETTINGS_VIEW],
    )
    cr.execute(
        "DELETE FROM ir_model_data WHERE module = 'botify_agent' AND model = 'ir.ui.view' AND name = %s",
        [V1_SETTINGS_VIEW],
    )
