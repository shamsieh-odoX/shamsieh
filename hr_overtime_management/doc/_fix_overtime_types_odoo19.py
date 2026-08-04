"""Add overtime type category columns and company type links on odoo19."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'hr_overtime_type' AND column_name = 'category'
""")
if not cur.fetchone():
    cur.execute("""
        ALTER TABLE hr_overtime_type
        ADD COLUMN category VARCHAR
    """)
    print('Added hr_overtime_type.category')

cur.execute("""
    UPDATE hr_overtime_type SET category = 'regular'
    WHERE code = 'regular' AND (category IS NULL OR category = '')
""")
cur.execute("""
    UPDATE hr_overtime_type SET category = 'weekend'
    WHERE code = 'weekend' AND (category IS NULL OR category = '')
""")
cur.execute("""
    UPDATE hr_overtime_type SET category = 'day_off'
    WHERE code IN ('holiday', 'day_off') AND (category IS NULL OR category = '')
""")
cur.execute("""
    UPDATE hr_overtime_type SET category = 'regular'
    WHERE category IS NULL OR category = ''
""")
print('Updated overtime type categories')

for col in ('overtime_weekend_type_id', 'overtime_holiday_type_id'):
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'res_company' AND column_name = %s
    """, (col,))
    if not cur.fetchone():
        cur.execute(f"""
            ALTER TABLE res_company
            ADD COLUMN {col} INTEGER REFERENCES hr_overtime_type(id) ON DELETE SET NULL
        """)
        print(f'Added res_company.{col}')

cur.execute("""
    SELECT res_id FROM ir_model_data
    WHERE module = 'hr_overtime_management' AND name = 'overtime_type_weekend'
""")
weekend_row = cur.fetchone()
cur.execute("""
    SELECT res_id FROM ir_model_data
    WHERE module = 'hr_overtime_management' AND name = 'overtime_type_holiday'
""")
holiday_row = cur.fetchone()
if weekend_row:
    cur.execute("""
        UPDATE res_company SET overtime_weekend_type_id = %s
        WHERE overtime_weekend_type_id IS NULL
    """, (weekend_row[0],))
if holiday_row:
    cur.execute("""
        UPDATE res_company SET overtime_holiday_type_id = %s
        WHERE overtime_holiday_type_id IS NULL
    """, (holiday_row[0],))
print('Linked company weekend/day-off types')

cur.execute(
    "UPDATE ir_module_module SET latest_version = '19.0.1.3.0' "
    "WHERE name = 'hr_overtime_management'"
)
conn.close()
print('Done. Restart Odoo and upgrade HR Overtime Management.')
