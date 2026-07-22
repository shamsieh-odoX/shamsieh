import psycopg2
conn = psycopg2.connect(host='127.0.0.1', port=5432, user='odoo', password='Shamsieh@dev2025', dbname='odoo19')
cur = conn.cursor()
cur.execute("""
    SELECT r.name, r.state, l.role, l.state, u.login
    FROM hr_overtime_request r
    JOIN hr_overtime_approval_line l ON l.request_id = r.id
    JOIN res_users u ON u.id = l.approver_id
    ORDER BY r.id, l.sequence
""")
for row in cur.fetchall():
    print(row)
conn.close()
