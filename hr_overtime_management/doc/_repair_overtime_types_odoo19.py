"""Reactivate archived overtime types and provision missing per-company types."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("UPDATE hr_overtime_type SET active = true WHERE active = false")
print(f'Reactivated archived overtime types: {cur.rowcount}')

cur.execute("SELECT id FROM res_company ORDER BY id")
company_ids = [row[0] for row in cur.fetchall()]

defaults = {
    'regular': ('Regular Overtime', 'regular', 1.5, 1),
    'weekend': ('Weekend Overtime', 'weekend', 2.0, 2),
    'day_off': ('Day Off Overtime', 'holiday', 2.5, 3),
}
field_map = {
    'regular': 'overtime_default_type_id',
    'weekend': 'overtime_weekend_type_id',
    'day_off': 'overtime_holiday_type_id',
}

for company_id in company_ids:
    for category, (name, code, mult, seq) in defaults.items():
        cur.execute("""
            SELECT id FROM hr_overtime_type
            WHERE company_id = %s AND category = %s
            ORDER BY active DESC, id ASC LIMIT 1
        """, (company_id, category))
        row = cur.fetchone()
        if row:
            type_id = row[0]
            cur.execute(
                "UPDATE hr_overtime_type SET active = true, rate_multiplier = %s WHERE id = %s",
                (mult, type_id),
            )
        else:
            cur.execute("""
                INSERT INTO hr_overtime_type (name, code, category, rate_multiplier, sequence, company_id, active, create_uid, write_uid, create_date, write_date)
                VALUES (%s, %s, %s, %s, %s, %s, true, 1, 1, NOW(), NOW())
                RETURNING id
            """, (name, code, category, mult, seq, company_id))
            type_id = cur.fetchone()[0]
            print(f'Created {category} type id={type_id} for company {company_id}')
        col = field_map[category]
        cur.execute(f"UPDATE res_company SET {col} = %s WHERE id = %s", (type_id, company_id))

# Recompute overtime_type_id for open draft requests missing type
cur.execute("""
    SELECT r.id, r.start_datetime, r.employee_id, e.company_id
    FROM hr_overtime_request r
    JOIN hr_employee e ON e.id = r.employee_id
    WHERE r.overtime_type_id IS NULL OR r.state = 'draft'
""")
print('Done. Restart Odoo and upgrade hr_overtime_management.')
conn.close()
