"""Remove stale Botify settings views before the replacement XML is validated."""


def migrate(cr, version):
    # Previous Botify builds used both external IDs for inherited settings
    # views. Their saved architectures refer to fields such as botify_base_url,
    # which no longer exist in the replacement settings model. Drop those
    # records before loading the new view with the same canonical external ID.
    for name in ("res_config_settings_view_form_botify", "res_config_settings_view_form"):
        cr.execute(
            "SELECT res_id FROM ir_model_data "
            "WHERE module = %s AND name = %s AND model = 'ir.ui.view'",
            ["botify_agent", name],
        )
        for (view_id,) in cr.fetchall():
            cr.execute("DELETE FROM ir_ui_view WHERE id = %s", [view_id])
        cr.execute(
            "DELETE FROM ir_model_data "
            "WHERE module = %s AND name = %s AND model = 'ir.ui.view'",
            ["botify_agent", name],
        )
