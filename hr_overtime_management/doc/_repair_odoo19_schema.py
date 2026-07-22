"""Repair odoo19 schema for hr_overtime_management v19.0.1.0.3"""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = True
cur = conn.cursor()


def column_exists(table, column):
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cur.fetchone())


def add_column(table, column, coltype, default=None):
    if not column_exists(table, column):
        sql = f'ALTER TABLE "{table}" ADD COLUMN "{column}" {coltype}'
        if default is not None:
            sql += f' DEFAULT {default}'
        cur.execute(sql)
        print(f'Added {table}.{column}')


# --- res_company ---
add_column('res_company', 'overtime_hours_per_month', 'double precision', '173.33')
add_column('res_company', 'overtime_generate_analytic_line', 'boolean', 'true')
add_column('res_company', 'overtime_default_type_id', 'integer')
add_column('res_company', 'overtime_daily_hours_cap', 'double precision', '4.0')

# --- hr_overtime_request datetime columns ---
add_column('hr_overtime_request', 'start_datetime', 'timestamp without time zone')
add_column('hr_overtime_request', 'end_datetime', 'timestamp without time zone')

# Migrate from legacy float times if still present
if column_exists('hr_overtime_request', 'start_time'):
    cur.execute("""
        UPDATE hr_overtime_request
        SET start_datetime = COALESCE(
                start_datetime,
                (date + (start_time || ' hours')::interval)
            ),
            end_datetime = COALESCE(
                end_datetime,
                CASE WHEN end_time <= start_time
                    THEN (date + interval '1 day' + (end_time || ' hours')::interval)
                    ELSE (date + (end_time || ' hours')::interval)
                END
            )
        WHERE date IS NOT NULL AND start_time IS NOT NULL AND end_time IS NOT NULL
    """)
    cur.execute('ALTER TABLE hr_overtime_request DROP COLUMN IF EXISTS start_time')
    cur.execute('ALTER TABLE hr_overtime_request DROP COLUMN IF EXISTS end_time')
    print('Migrated and dropped legacy start_time/end_time')

# Fill NULL datetimes
cur.execute("""
    UPDATE hr_overtime_request
    SET start_datetime = COALESCE(start_datetime, NOW()),
        end_datetime = COALESCE(end_datetime, NOW() + interval '2 hours')
    WHERE start_datetime IS NULL OR end_datetime IS NULL
""")

# Set NOT NULL (safe after backfill)
cur.execute("""
    ALTER TABLE hr_overtime_request
    ALTER COLUMN start_datetime SET NOT NULL
""")
cur.execute("""
    ALTER TABLE hr_overtime_request
    ALTER COLUMN end_datetime SET NOT NULL
""")
print('Set NOT NULL on start_datetime/end_datetime')

# --- ir_model_fields: register overtime_hours_per_month if missing ---
cur.execute("SELECT id FROM ir_model WHERE model = 'res.company'")
model_id = cur.fetchone()
if model_id:
    cur.execute("""
        SELECT 1 FROM ir_model_fields
        WHERE model = 'res.company' AND name = 'overtime_hours_per_month'
    """)
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO ir_model_fields (
                name, model, model_id, field_description, ttype,
                state, readonly, required, selectable, store, copied,
                create_uid, write_uid, create_date, write_date
            ) VALUES (
                'overtime_hours_per_month', 'res.company', %s,
                '{"en_US": "Working Hours per Month"}', 'float',
                'base', false, false, true, true, true,
                1, 1, NOW(), NOW()
            )
        """, (model_id[0],))
        print('Registered ir_model_fields for overtime_hours_per_month')

# --- Fix module state ---
cur.execute("""
    UPDATE ir_module_module
    SET state = 'installed',
        latest_version = '19.0.1.0.3'
    WHERE name = 'hr_overtime_management'
""")
print('Module state reset to installed')

# Verify
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'res_company' AND column_name LIKE 'overtime%'
    ORDER BY 1
""")
print('res_company overtime columns:', [r[0] for r in cur.fetchall()])

cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'hr_overtime_request'
      AND column_name IN ('start_datetime', 'end_datetime', 'start_time', 'end_time')
    ORDER BY 1
""")
print('hr_overtime_request time columns:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT name, state, latest_version FROM ir_module_module WHERE name = 'hr_overtime_management'")
print('Module:', cur.fetchone())

conn.close()
print('\nDone. Restart Odoo server now.')
