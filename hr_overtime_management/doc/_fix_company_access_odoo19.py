"""Add employee_company_id column and resync company_id on odoo19."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'hr_overtime_request' AND column_name = 'employee_company_id'
""")
if not cur.fetchone():
    cur.execute(
        'ALTER TABLE hr_overtime_request ADD COLUMN employee_company_id integer'
    )
    print('Added hr_overtime_request.employee_company_id')

cur.execute("""
    UPDATE hr_overtime_request r
    SET employee_company_id = e.company_id
    FROM hr_employee e
    WHERE r.employee_id = e.id
      AND (r.employee_company_id IS NULL OR r.employee_company_id IS DISTINCT FROM e.company_id)
""")
print(f'Synced employee_company_id on {cur.rowcount} row(s)')

cur.execute("""
    UPDATE hr_overtime_request r
    SET company_id = e.company_id
    FROM hr_employee e
    WHERE r.employee_id = e.id
      AND r.company_id IS DISTINCT FROM e.company_id
""")
print(f'Fixed company_id on {cur.rowcount} row(s)')

cur.execute("SELECT id FROM ir_model WHERE model = 'hr.overtime.request'")
model_id = cur.fetchone()[0]
for field_name, field_type, relation, store in [
    ('employee_company_id', 'many2one', 'res.company', True),
    ('company_id', 'many2one', 'res.company', True),
]:
    cur.execute(
        "SELECT id FROM ir_model_fields WHERE model_id = %s AND name = %s",
        (model_id, field_name),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE ir_model_fields SET store = %s, ttype = %s, relation = %s "
            "WHERE id = %s",
            (store, field_type, relation, row[0]),
        )
    else:
        print(f'Field {field_name} metadata already exists')

cur.execute(
    "UPDATE ir_module_module SET latest_version = '19.0.1.0.8' "
    "WHERE name = 'hr_overtime_management'"
)
print('Module version set to 19.0.1.0.8')
conn.close()
print('Done. Restart Odoo and hard-refresh (Ctrl+F5).')
