"""Apply employee self-service access on odoo19 without full module upgrade."""
import json
import os
import psycopg2

MODULE = 'hr_overtime_management'
VERSION = '19.0.1.0.5'
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def xmlid(cur, name, module=MODULE, model=None):
    sql = "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s"
    params = [module, name]
    if model:
        sql += " AND model = %s"
        params.append(model)
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f'Missing xmlid {module}.{name}')
    return row[0]


def ensure_implied_group(cur, parent_xmlid, child_xmlid, parent_module='base'):
    parent_id = xmlid(cur, parent_xmlid, module=parent_module, model='res.groups')
    child_id = xmlid(cur, child_xmlid, model='res.groups')
    cur.execute("""
        INSERT INTO res_groups_implied_rel (gid, hid)
        SELECT %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM res_groups_implied_rel WHERE gid = %s AND hid = %s
        )
    """, (parent_id, child_id, parent_id, child_id))
    print(f'Implied group: {parent_module}.{parent_xmlid} -> {MODULE}.{child_xmlid}')


def ensure_access(cur, name, model_name, group_xmlid, perms, group_module='base'):
    model_id = xmlid(cur, f'model_{model_name.replace(".", "_")}', module=MODULE, model='ir.model')
    group_id = xmlid(cur, group_xmlid, module=group_module, model='res.groups')
    cur.execute("SELECT id FROM ir_model_access WHERE name = %s", (name,))
    row = cur.fetchone()
    perm_read, perm_write, perm_create, perm_unlink = perms
    if row:
        cur.execute("""
            UPDATE ir_model_access
            SET model_id = %s, group_id = %s,
                perm_read = %s, perm_write = %s, perm_create = %s, perm_unlink = %s
            WHERE id = %s
        """, (model_id, group_id, perm_read, perm_write, perm_create, perm_unlink, row[0]))
        print(f'Updated access {name}')
    else:
        cur.execute("""
            INSERT INTO ir_model_access
                (name, model_id, group_id, perm_read, perm_write, perm_create, perm_unlink, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, true)
            RETURNING id
        """, (name, model_id, group_id, perm_read, perm_write, perm_create, perm_unlink))
        access_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES (%s, %s, 'ir.model.access', %s, false)
            ON CONFLICT DO NOTHING
        """, (MODULE, name, access_id))
        print(f'Created access {name}')


def update_rule_groups(cur, rule_xmlid, group_xmlid, group_module='base'):
    rule_id = xmlid(cur, rule_xmlid, model='ir.rule')
    group_id = xmlid(cur, group_xmlid, module=group_module, model='res.groups')
    cur.execute("""
        DELETE FROM rule_group_rel WHERE rule_group_id = %s
    """, (rule_id,))
    cur.execute("""
        INSERT INTO rule_group_rel (rule_group_id, group_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (rule_id, group_id))
    print(f'Rule {rule_xmlid} -> {group_module}.{group_xmlid}')


def update_menu(cur):
    menu_id = xmlid(cur, 'menu_hr_overtime_root', model='ir.ui.menu')
    group_user_id = xmlid(cur, 'group_user', module='base', model='res.groups')
    hr_root_id = xmlid(cur, 'menu_hr_root', module='hr', model='ir.ui.menu')

    cur.execute("""
        UPDATE ir_ui_menu
        SET parent_id = NULL, sequence = 226
        WHERE id = %s
    """, (menu_id,))
    cur.execute("DELETE FROM ir_ui_menu_group_rel WHERE menu_id = %s", (menu_id,))
    cur.execute(
        "INSERT INTO ir_ui_menu_group_rel (menu_id, gid) VALUES (%s, %s)",
        (menu_id, group_user_id),
    )

    # Ensure "My Overtime" parent submenu exists
    cur.execute("SELECT id FROM ir_model_data WHERE module = %s AND name = %s", (MODULE, 'menu_hr_overtime_my_requests'))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO ir_ui_menu (name, parent_id, sequence, active)
            VALUES ('{"en_US": "My Overtime"}', %s, 1, true)
            RETURNING id
        """, (menu_id,))
        my_parent_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES (%s, 'menu_hr_overtime_my_requests', 'ir.ui.menu', %s, false)
        """, (MODULE, my_parent_id))
    else:
        my_parent_id = xmlid(cur, 'menu_hr_overtime_my_requests', model='ir.ui.menu')
        cur.execute("UPDATE ir_ui_menu SET parent_id = %s, sequence = 1 WHERE id = %s", (menu_id, my_parent_id))

    requests_menu_id = xmlid(cur, 'menu_hr_overtime_requests', model='ir.ui.menu')
    cur.execute(
        "UPDATE ir_ui_menu SET parent_id = %s, sequence = 10 WHERE id = %s",
        (my_parent_id, requests_menu_id),
    )
    print(f'Overtime menu {menu_id}: top-level, groups=base.group_user (was under hr {hr_root_id})')


def extract_view_archs(xml_text):
    record_pattern = re.compile(
        r'<record\s+id="([^"]+)"\s+model="ir\.ui\.view">(.*?)</record>',
        re.DOTALL,
    )
    start_marker = '<field name="arch" type="xml">'
    archs = {}
    for xmlid, body in record_pattern.findall(xml_text):
        if start_marker not in body:
            continue
        start = body.index(start_marker) + len(start_marker)
        end = body.rindex('</field>')
        archs[xmlid] = body[start:end].strip()
    return archs


def update_views_from_files(cur):
    import re
    views_path = os.path.join(ADDON_DIR, 'views', 'hr_overtime_request_views.xml')
    with open(views_path, encoding='utf-8') as f:
        archs = extract_view_archs(f.read())
    for xmlid_name, arch in archs.items():
        view_id = xmlid(cur, xmlid_name, model='ir.ui.view')
        arch_db = json.dumps({'en_US': arch})
        view_type = re.match(r'<(\w+)', arch).group(1)
        cur.execute(
            "UPDATE ir_ui_view SET arch_db = %s::jsonb, type = %s WHERE id = %s",
            (arch_db, view_type, view_id),
        )
        print(f'Updated view {xmlid_name}')


def main():
    conn = psycopg2.connect(
        host='127.0.0.1', port=5432, user='odoo',
        password='Shamsieh@dev2025', dbname='odoo19',
    )
    conn.autocommit = True
    cur = conn.cursor()

    ensure_implied_group(cur, 'group_user', 'group_overtime_user')

    for name, model, perms in [
        ('access_hr_overtime_type_employee', 'hr.overtime.type', (True, False, False, False)),
        ('access_hr_overtime_request_employee', 'hr.overtime.request', (True, True, True, True)),
        ('access_hr_overtime_approval_line_employee', 'hr.overtime.approval.line', (True, False, False, False)),
        ('access_hr_overtime_refuse_wizard_employee', 'hr.overtime.refuse.wizard', (True, True, True, False)),
    ]:
        ensure_access(cur, name, model, 'group_user', perms)

    for rule_xmlid in [
        'hr_overtime_request_rule_employee_read',
        'hr_overtime_request_rule_employee_write_draft',
    ]:
        update_rule_groups(cur, rule_xmlid, 'group_user')

    # Create cancel/reset rules if missing (from v19.0.1.0.4)
    for rule_xmlid, rule_name, domain in [
        ('hr_overtime_request_rule_employee_cancel', 'Overtime Request: employee cancel submitted',
         "[('employee_id.user_id', '=', user.id), ('state', '=', 'submitted')]"),
        ('hr_overtime_request_rule_employee_reset', 'Overtime Request: employee reset refused/cancelled',
         "[('employee_id.user_id', '=', user.id), ('state', 'in', ('cancel', 'refused'))]"),
    ]:
        cur.execute("SELECT id FROM ir_model_data WHERE module = %s AND name = %s", (MODULE, rule_xmlid))
        if cur.fetchone():
            update_rule_groups(cur, rule_xmlid, 'group_user')
            continue
        model_id = xmlid(cur, 'model_hr_overtime_request', model='ir.model')
        group_id = xmlid(cur, 'group_user', module='base', model='res.groups')
        cur.execute("""
            INSERT INTO ir_rule (name, model_id, domain_force, active, perm_read, perm_write, perm_create, perm_unlink)
            VALUES (%s, %s, %s, true, false, true, false, false)
            RETURNING id
        """, (rule_name, model_id, domain))
        rule_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES (%s, %s, 'ir.rule', %s, true)
        """, (MODULE, rule_xmlid, rule_id))
        cur.execute(
            "INSERT INTO rule_group_rel (rule_group_id, group_id) VALUES (%s, %s)",
            (rule_id, group_id),
        )
        print(f'Created rule {rule_xmlid}')

    update_menu(cur)
    update_views_from_files(cur)

    cur.execute(
        "UPDATE ir_module_module SET latest_version = %s, state = 'installed' WHERE name = %s",
        (VERSION, MODULE),
    )
    print(f'Module version set to {VERSION}')
    conn.close()
    print('Done. Restart Odoo and hard-refresh the browser (Ctrl+F5).')


if __name__ == '__main__':
    main()
