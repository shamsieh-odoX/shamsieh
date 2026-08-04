"""Fix stale ir.ui.view records still referencing start_time/end_time."""
import json
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
cur = conn.cursor()

REPLACEMENTS = [
    ('name="start_time"', 'name="start_datetime"'),
    ("name='start_time'", "name='start_datetime'"),
    ('name="end_time"', 'name="end_datetime"'),
    ("name='end_time'", "name='end_datetime'"),
    (' widget="float_time"', ''),  # only on start/end which are now datetime
]

cur.execute("""
    SELECT id, name, arch_db
    FROM ir_ui_view
    WHERE model = 'hr.overtime.request'
       OR arch_db::text ILIKE '%start_time%'
       OR arch_db::text ILIKE '%end_time%'
""")
rows = cur.fetchall()
print(f'Found {len(rows)} view(s):')

for vid, name, arch_db in rows:
    if arch_db is None:
        continue
    if isinstance(arch_db, dict):
        arch_map = arch_db
    else:
        arch_map = json.loads(arch_db) if isinstance(arch_db, str) else arch_db

    changed = False
    new_map = {}
    for lang, arch in arch_map.items():
        new_arch = arch
        for old, new in REPLACEMENTS:
            if old in new_arch:
                new_arch = new_arch.replace(old, new)
        # targeted: remove float_time widget only from datetime field lines
        new_arch = new_arch.replace(
            'name="start_datetime" widget="float_time"',
            'name="start_datetime"',
        )
        new_arch = new_arch.replace(
            'name="end_datetime" widget="float_time"',
            'name="end_datetime"',
        )
        if new_arch != arch:
            changed = True
        new_map[lang] = new_arch

    has_old = any('start_time' in v or 'end_time' in v for v in new_map.values())
    print(f'  id={vid} name={name} changed={changed} still_has_old={has_old}')

    if changed or has_old:
        if has_old:
            for lang in new_map:
                for old, new in [
                    ('start_time', 'start_datetime'),
                    ('end_time', 'end_datetime'),
                ]:
                    new_map[lang] = new_map[lang].replace(f'name="{old}"', f'name="{new}"')
        cur.execute(
            "UPDATE ir_ui_view SET arch_db = %s, write_date = NOW() WHERE id = %s",
            (json.dumps(new_map), vid),
        )
        print(f'    -> updated view {vid}')

# Also fix QWeb report templates
cur.execute("""
    SELECT id, name, arch_db
    FROM ir_ui_view
    WHERE arch_db::text ILIKE '%start_time%'
       OR arch_db::text ILIKE '%end_time%'
""")
report_rows = cur.fetchall()
for vid, name, arch_db in report_rows:
    if vid in [r[0] for r in rows]:
        continue
    arch_map = arch_db if isinstance(arch_db, dict) else json.loads(arch_db)
    new_map = {}
    changed = False
    for lang, arch in arch_map.items():
        new_arch = arch.replace('doc.start_time', 'doc.start_datetime')
        new_arch = new_arch.replace('doc.end_time', 'doc.end_datetime')
        new_arch = new_arch.replace("{'widget': 'float_time'}", '')
        if new_arch != arch:
            changed = True
        new_map[lang] = new_arch
    if changed:
        cur.execute(
            "UPDATE ir_ui_view SET arch_db = %s, write_date = NOW() WHERE id = %s",
            (json.dumps(new_map), vid),
        )
        print(f'  -> updated report view {vid} ({name})')

# Mark module for view reload
cur.execute("""
    UPDATE ir_module_module SET state = 'to upgrade'
    WHERE name = 'hr_overtime_management'
""")

conn.commit()
conn.close()
print('Done. Hard-refresh browser (Ctrl+F5).')
