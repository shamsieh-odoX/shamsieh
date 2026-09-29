"""Migrate the Shamsieh protocol-v2 addon to the Botify v1 operation relay."""


def _delete_xml_record(cr, module, name, table):
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s AND model = %s",
        [module, name, table],
    )
    rows = cr.fetchall()
    for (record_id,) in rows:
        cr.execute(f"DELETE FROM {table} WHERE id = %s", [record_id])
    cr.execute(
        "DELETE FROM ir_model_data WHERE module = %s AND name = %s AND model = %s",
        [module, name, table],
    )


def _copy_parameter(cr, source, target):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [source])
    row = cr.fetchone()
    if not row:
        return
    cr.execute("SELECT 1 FROM ir_config_parameter WHERE key = %s", [target])
    if not cr.fetchone():
        cr.execute(
            "INSERT INTO ir_config_parameter (key, value) VALUES (%s, %s)",
            [target, row[0]],
        )


def migrate(cr, version):
    # The old inherited settings view references fields removed by this addon.
    _delete_xml_record(cr, "botify_agent", "res_config_settings_view_form_botify", "ir_ui_view")

    # The former Assistant client action and menu are replaced by the remote
    # Botify widget service and the administration menus in botify_views.xml.
    _delete_xml_record(cr, "botify_agent", "menu_botify_assistant", "ir_ui_menu")
    _delete_xml_record(cr, "botify_agent", "action_botify_assistant", "ir_act_client")

    # Keep endpoint configuration and the shared signing secret. The old
    # installation_id was a Botify connection UUID; it is not the new Botify
    # installation key and must be configured separately after the upgrade.
    _copy_parameter(cr, "botify_agent.base_url", "botify_agent.api_url")
    _copy_parameter(cr, "botify_agent.shared_secret", "botify_agent.secret")
