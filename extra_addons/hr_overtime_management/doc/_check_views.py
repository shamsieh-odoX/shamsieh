import json
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
cur = conn.cursor()
for vid in (288, 1847, 2374, 2380):
    cur.execute("SELECT id, name, model, arch_db FROM ir_ui_view WHERE id=%s", (vid,))
    row = cur.fetchone()
    if row:
        arch = row[3]
        if isinstance(arch, dict):
            en = arch.get('en_US', list(arch.values())[0] if arch else '')
        else:
            en = str(arch)
        print(f"\n=== {row[0]} {row[1]} model={row[2]} ===")
        for line in en.split('\n'):
            if 'start' in line.lower() or 'end' in line.lower() or 'datetime' in line.lower():
                print(line.strip())
conn.close()
