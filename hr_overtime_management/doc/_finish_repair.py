import psycopg2
conn = psycopg2.connect(host='127.0.0.1', port=5432, user='odoo', password='Shamsieh@dev2025', dbname='odoo19')
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    UPDATE ir_module_module
    SET state = 'installed', latest_version = '19.0.1.0.3'
    WHERE name = 'hr_overtime_management'
""")
cur.execute("SELECT name, state, latest_version FROM ir_module_module WHERE name = 'hr_overtime_management'")
print('Module:', cur.fetchone())
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'res_company' AND column_name = 'overtime_hours_per_month'
""")
print('Column exists:', cur.fetchone())
conn.close()
