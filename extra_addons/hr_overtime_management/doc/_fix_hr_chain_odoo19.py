"""Repair overtime requests missing an HR approval line."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
cur = conn.cursor()

# Find HR officer user (prefer overtime HR group, else admin)
cur.execute("""
    SELECT u.id, u.login
    FROM res_users u
    JOIN res_groups_users_rel g ON g.uid = u.id
    JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = g.gid
    WHERE d.module = 'hr_overtime_management' AND d.name = 'group_overtime_hr_officer'
    LIMIT 1
""")
row = cur.fetchone()
if not row:
    cur.execute("SELECT id, login FROM res_users WHERE login = 'admin' LIMIT 1")
    row = cur.fetchone()
hr_user_id, hr_login = row
print(f'HR approver: {hr_login} (id={hr_user_id})')

# Requests in approval flow without a pending/active HR line
cur.execute("""
    SELECT r.id, r.name, r.state
    FROM hr_overtime_request r
    WHERE r.state IN ('submitted', 'manager_approved', 'upper_manager_approved')
      AND NOT EXISTS (
          SELECT 1 FROM hr_overtime_approval_line l
          WHERE l.request_id = r.id AND l.role = 'hr'
      )
""")
broken = cur.fetchall()
print(f'Broken requests (no HR line): {len(broken)}')

for req_id, name, state in broken:
    cur.execute("SELECT COALESCE(MAX(sequence), 0) FROM hr_overtime_approval_line WHERE request_id = %s", (req_id,))
    max_seq = cur.fetchone()[0]
    # If last approved line exists, next HR line should be to_approve; else pending
    cur.execute("""
        SELECT COUNT(*) FROM hr_overtime_approval_line
        WHERE request_id = %s AND state = 'to_approve'
    """, (req_id,))
    has_active = cur.fetchone()[0]
    line_state = 'pending' if has_active else 'to_approve'
    cur.execute("""
        INSERT INTO hr_overtime_approval_line
            (request_id, sequence, role, approver_id, state, create_uid, write_uid, create_date, write_date)
        VALUES (%s, %s, 'hr', %s, %s, 1, 1, NOW(), NOW())
    """, (req_id, max_seq + 10, hr_user_id, line_state))
    print(f'  Added HR line to {name} ({state}), line_state={line_state}')

conn.commit()
conn.close()
print('Done. Restart Odoo or refresh, then approve the HR step.')
