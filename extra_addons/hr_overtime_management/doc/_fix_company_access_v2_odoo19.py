"""Sync employee_company_id as integer and fix overtime actions on odoo19."""
import json
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    UPDATE hr_overtime_request r
    SET employee_company_id = e.company_id,
        company_id = e.company_id
    FROM hr_employee e
    WHERE r.employee_id = e.id
      AND (
            r.employee_company_id IS DISTINCT FROM e.company_id
         OR r.company_id IS DISTINCT FROM e.company_id
      )
""")
print(f'Resynced company fields on {cur.rowcount} overtime row(s)')

cur.execute("SELECT id FROM ir_model WHERE model = 'hr.overtime.request'")
model_id = cur.fetchone()[0]
cur.execute("""
    UPDATE ir_model_fields
    SET ttype = 'integer', relation = NULL, store = true
    WHERE model_id = %s AND name = 'employee_company_id'
""", (model_id,))
print(f'Updated employee_company_id field metadata: {cur.rowcount} row(s)')

# Point menus at server actions (xml ids recreated on upgrade; patch if still window)
for menu_xmlid, action_xmlid in [
    ('menu_hr_overtime_requests', 'action_hr_overtime_request'),
    ('menu_hr_overtime_my_approvals', 'action_hr_overtime_my_approvals'),
]:
    cur.execute(
        "SELECT res_id FROM ir_model_data WHERE module='hr_overtime_management' AND name=%s AND model='ir.actions.server'",
        (action_xmlid,),
    )
    row = cur.fetchone()
    if not row:
        print(f'Skip menu patch for {action_xmlid} (not installed yet)')
        continue
    action_id = row[0]
    cur.execute(
        "SELECT res_id FROM ir_model_data WHERE module='hr_overtime_management' AND name=%s AND model='ir.ui.menu'",
        (menu_xmlid,),
    )
    menu_row = cur.fetchone()
    if menu_row:
        cur.execute(
            "UPDATE ir_ui_menu SET action = %s WHERE id = %s",
            (f'ir.actions.server,{action_id}', menu_row[0]),
        )
        print(f'Patched menu {menu_xmlid} -> server action {action_id}')

cur.execute(
    "UPDATE ir_module_module SET latest_version = '19.0.1.0.9' WHERE name = 'hr_overtime_management'"
)
conn.close()
print('Done. Restart Odoo and hard-refresh (Ctrl+F5).')
