import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
cur = conn.cursor()

cur.execute(
    "SELECT name, state, latest_version FROM ir_module_module "
    "WHERE name='hr_overtime_management'"
)
print('Module:', cur.fetchone())

cur.execute("""
    SELECT d.name, m.name::text, array_agg(g.name ORDER BY g.name)
    FROM ir_ui_menu m
    JOIN ir_model_data d ON d.model = 'ir.ui.menu' AND d.res_id = m.id
        AND d.module = 'hr_overtime_management'
    LEFT JOIN ir_ui_menu_group_rel mgr ON mgr.menu_id = m.id
    LEFT JOIN res_groups g ON g.id = mgr.gid
    GROUP BY d.name, m.name, m.sequence
    ORDER BY m.sequence
""")
print('\nOvertime menus (xmlid, name, groups):')
for row in cur.fetchall():
    print(' ', row)

cur.execute("""
    SELECT im.model, g.name, a.perm_read, a.perm_write, a.perm_create, a.perm_unlink
    FROM ir_model_access a
    JOIN ir_model im ON im.id = a.model_id
    JOIN res_groups g ON g.id = a.group_id
    WHERE im.model LIKE 'hr.overtime%'
    ORDER BY im.model, g.name
""")
print('\nModel access:')
for row in cur.fetchall():
    print(' ', row)

cur.execute("""
    SELECT u.login,
           EXISTS (
               SELECT 1 FROM res_groups_users_rel r
               JOIN ir_model_data gd ON gd.model='res.groups' AND gd.res_id=r.gid
               WHERE r.uid=u.id AND gd.module='base' AND gd.name='group_user'
           ) AS internal,
           EXISTS (
               SELECT 1 FROM res_groups_users_rel r
               JOIN ir_model_data gd ON gd.model='res.groups' AND gd.res_id=r.gid
               WHERE r.uid=u.id AND gd.module='hr_overtime_management'
                   AND gd.name='group_overtime_user'
           ) AS ot_user,
           EXISTS (
               SELECT 1 FROM res_groups_users_rel r
               JOIN ir_model_data gd ON gd.model='res.groups' AND gd.res_id=r.gid
               WHERE r.uid=u.id AND gd.module='hr_overtime_management'
                   AND gd.name='group_overtime_admin'
           ) AS ot_admin,
           e.id AS employee_id
    FROM res_users u
    LEFT JOIN hr_employee e ON e.user_id = u.id
    WHERE u.active AND NOT u.share
    ORDER BY u.id
    LIMIT 20
""")
print('\nActive internal users:')
for row in cur.fetchall():
    print(' ', row)

conn.close()
