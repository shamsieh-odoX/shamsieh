import json
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
cur = conn.cursor()

# Fix report template
cur.execute("SELECT arch_db FROM ir_ui_view WHERE id = 2380")
arch_db = cur.fetchone()[0]
new_map = {}
for lang, arch in arch_db.items():
    arch = arch.replace('doc.start_time', 'doc.start_datetime')
    arch = arch.replace('doc.end_time', 'doc.end_datetime')
    arch = arch.replace("t-options=\"{'widget': 'float_time'}\"", '')
    new_map[lang] = arch
cur.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = 2380", (json.dumps(new_map),))

# Clear ir.ui.view cache / registry signaling
cur.execute("DELETE FROM ir_attachment WHERE name LIKE 'web.assets%'")  # optional, skip aggressive

conn.commit()
conn.close()
print('Report view 2380 fixed.')
