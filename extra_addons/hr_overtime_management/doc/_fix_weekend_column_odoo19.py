"""Add missing overtime_weekend_weekdays column and fix menu actions on odoo19."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'res_company' AND column_name = 'overtime_weekend_weekdays'
""")
if not cur.fetchone():
    cur.execute("""
        ALTER TABLE res_company
        ADD COLUMN overtime_weekend_weekdays VARCHAR DEFAULT '4,5'
    """)
    cur.execute("""
        UPDATE res_company
        SET overtime_weekend_weekdays = '4,5'
        WHERE overtime_weekend_weekdays IS NULL
    """)
    print('Added res_company.overtime_weekend_weekdays')
else:
    print('Column res_company.overtime_weekend_weekdays already exists')

# Point menus at server actions after XML id rename (safe if not yet upgraded).
for old_xmlid, new_xmlid in (
    ('action_hr_overtime_request', 'action_hr_overtime_open_my_requests'),
    ('action_hr_overtime_my_approvals', 'action_hr_overtime_open_my_approvals'),
):
    cur.execute("""
        SELECT res_id, model FROM ir_model_data
        WHERE module = 'hr_overtime_management' AND name = %s
    """, (old_xmlid,))
    row = cur.fetchone()
    if row:
        print(f'Keeping legacy xmlid {old_xmlid} -> {row[1]}({row[0]})')

cur.execute(
    "UPDATE ir_module_module SET latest_version = '19.0.1.2.0' "
    "WHERE name = 'hr_overtime_management'"
)
print('Module version set to 19.0.1.2.0')
conn.close()
print('Done. Restart Odoo, then Apps -> Upgrade HR Overtime Management.')
