import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='postgres',
)
conn.autocommit = True
cur = conn.cursor()
cur.execute(
    "SELECT datname FROM pg_database WHERE datistemplate = false "
    "AND datname NOT IN ('postgres') ORDER BY datname"
)
dbs = [r[0] for r in cur.fetchall()]
print('Databases:', dbs)
for db in dbs:
    try:
        c2 = psycopg2.connect(
            host='127.0.0.1', port=5432, user='odoo',
            password='Shamsieh@dev2025', dbname=db,
        )
        cur2 = c2.cursor()
        cur2.execute(
            "SELECT state FROM ir_module_module WHERE name='hr_overtime_management'"
        )
        row = cur2.fetchone()
        if row:
            cur2.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='hr_overtime_request' ORDER BY column_name"
            )
            cols = [r[0] for r in cur2.fetchall()]
            print(f'{db}: module={row[0]}, columns={cols}')
        c2.close()
    except Exception as e:
        print(f'{db}: error {e}')
conn.close()
