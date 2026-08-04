import psycopg2
from datetime import datetime

conn = psycopg2.connect(host='127.0.0.1', port=5432, user='odoo', password='Shamsieh@dev2025', dbname='odoo19')
cur = conn.cursor()
cur.execute('SELECT id, name, code, category, rate_multiplier, company_id, active FROM hr_overtime_type ORDER BY id')
print('=== hr_overtime_type ===')
for r in cur.fetchall():
    print(r)
cur.execute('SELECT id, name, overtime_default_type_id, overtime_weekend_type_id, overtime_holiday_type_id, overtime_weekend_weekdays FROM res_company ORDER BY id')
print('=== res_company ===')
for r in cur.fetchall():
    print(r)
cur.execute("SELECT id, name, company_id FROM hr_employee WHERE id IN (2, 3)")
print('=== employees ===')
for r in cur.fetchall():
    print(r)
cur.execute("SELECT id, name, overtime_type_id, start_datetime, employee_id FROM hr_overtime_request WHERE name='OT/2026/07/00023'")
print('=== request ===')
for r in cur.fetchall():
    print(r)
    if r[3]:
        dt = r[3]
        print('  weekday:', dt.weekday() if hasattr(dt, 'weekday') else 'n/a')
conn.close()
