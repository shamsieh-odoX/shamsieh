"""Validate overtime employee access for real users on odoo19."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
cur = conn.cursor()

cur.execute("""
    SELECT u.login, e.id AS employee_id, e.name AS employee_name,
           EXISTS (
               SELECT 1 FROM res_groups_implied_rel ig
               JOIN ir_model_data gd ON gd.model='res.groups' AND gd.res_id=ig.gid
               JOIN ir_model_data gc ON gc.model='res.groups' AND gc.res_id=ig.hid
               WHERE gd.module='base' AND gd.name='group_user'
                 AND gc.module='hr_overtime_management' AND gc.name='group_overtime_user'
           ) AS implied_ok,
           EXISTS (
               SELECT 1 FROM ir_ui_menu_group_rel mgr
               JOIN ir_model_data md ON md.model='ir.ui.menu' AND md.res_id=mgr.menu_id
               JOIN ir_model_data gd ON gd.model='res.groups' AND gd.res_id=mgr.gid
               WHERE md.module='hr_overtime_management' AND md.name='menu_hr_overtime_root'
                 AND gd.module='base' AND gd.name='group_user'
           ) AS menu_ok
    FROM res_users u
    LEFT JOIN hr_employee e ON e.user_id = u.id
    WHERE u.active AND NOT u.share
    ORDER BY u.id
""")
print('User access validation (implied group + menu for internal users):')
print(f"{'login':<25} {'employee':<8} {'can use overtime':<18}")
for login, emp_id, emp_name, implied_ok, menu_ok in cur.fetchall():
    if emp_id:
        status = 'YES' if implied_ok and menu_ok else 'CHECK'
    else:
        status = 'no employee record'
    print(f'{login:<25} {str(emp_id or "-"):<8} {status}')

cur.execute(
    "SELECT latest_version FROM ir_module_module WHERE name='hr_overtime_management'"
)
print('\nModule version:', cur.fetchone()[0])
conn.close()
