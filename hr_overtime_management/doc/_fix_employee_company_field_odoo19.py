"""Remove stale stored field metadata for employee_company_id on odoo19."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT id FROM ir_model WHERE model = 'hr.overtime.request'")
model_id = cur.fetchone()[0]

cur.execute("""
    UPDATE ir_model_fields
    SET store = false, column1 = NULL
    WHERE model_id = %s AND name = 'employee_company_id'
""", (model_id,))
print(f'Updated ir_model_fields.store=false for employee_company_id: {cur.rowcount} row(s)')

cur.execute("""
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'hr_overtime_request' AND column_name = 'employee_company_id'
""")
if cur.fetchone():
    cur.execute('ALTER TABLE hr_overtime_request DROP COLUMN employee_company_id')
    print('Dropped orphan column hr_overtime_request.employee_company_id')
else:
    print('No orphan column to drop')

cur.execute(
    "UPDATE ir_module_module SET latest_version = '19.0.1.0.7' "
    "WHERE name = 'hr_overtime_management'"
)
print('Module version set to 19.0.1.0.7')
conn.close()
print('Done. Restart Odoo and hard-refresh (Ctrl+F5).')
