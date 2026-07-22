"""Add company column and recompute overtime costs on odoo19."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
cur = conn.cursor()

cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'res_company' AND column_name = 'overtime_hours_per_month'
""")
if not cur.fetchone():
    cur.execute("ALTER TABLE res_company ADD COLUMN overtime_hours_per_month double precision DEFAULT 173.33")
    print('Added overtime_hours_per_month to res_company')

# Check admin employee wage / calendar
cur.execute("""
    SELECT e.id, e.name, v.wage, rc.hours_per_week
    FROM hr_employee e
    JOIN hr_version v ON v.id = e.version_id
    LEFT JOIN resource_calendar rc ON rc.id = v.resource_calendar_id
    WHERE e.name ILIKE '%admin%' OR e.id = 1
    LIMIT 3
""")
print('Employees:', cur.fetchall())

conn.commit()
conn.close()
print('DB column ready. Restart Odoo to reload Python code, then reopen the overtime request.')
