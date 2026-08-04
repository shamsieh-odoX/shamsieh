import psycopg2
conn = psycopg2.connect(host='127.0.0.1', port=5432, user='odoo', password='Shamsieh@dev2025', dbname='odoo19')
cur = conn.cursor()
cur.execute("""
    SELECT e.id, e.name, v.wage, rc.hours_per_week
    FROM hr_employee e
    JOIN hr_version v ON v.id = e.current_version_id
    LEFT JOIN resource_calendar rc ON rc.id = v.resource_calendar_id
    LIMIT 5
""")
for row in cur.fetchall():
    wage, hpw = row[2], row[3]
    hourly = wage * 12 / 52 / hpw if wage and hpw else (wage / 173.33 if wage else 0)
    total_2h = 2 * hourly * 1.5
    print(f'{row[1]}: wage={wage}, hours/week={hpw}, hourly={hourly:.2f}, total_2h_regular={total_2h:.2f}')
conn.commit()
conn.close()
