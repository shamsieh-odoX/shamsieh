"""Apply start_datetime/end_datetime schema migration on odoo19."""
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host='127.0.0.1', port=5432, user='odoo',
    password='Shamsieh@dev2025', dbname='odoo19',
)
conn.autocommit = False
cur = conn.cursor()

cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'hr_overtime_request'
    ORDER BY column_name
""")
cols = {r[0] for r in cur.fetchall()}
print('Before:', sorted(cols))

if 'start_datetime' not in cols:
    cur.execute("ALTER TABLE hr_overtime_request ADD COLUMN start_datetime timestamp WITHOUT TIME ZONE")
    print('Added start_datetime')

if 'end_datetime' not in cols:
    cur.execute("ALTER TABLE hr_overtime_request ADD COLUMN end_datetime timestamp WITHOUT TIME ZONE")
    print('Added end_datetime')

if 'start_time' in cols and 'end_time' in cols:
    cur.execute("""
        SELECT id, date, start_time, end_time
        FROM hr_overtime_request
        WHERE start_time IS NOT NULL AND end_time IS NOT NULL
    """)
    for row_id, work_date, start_time, end_time in cur.fetchall():
        if not work_date:
            continue
        start_hour = int(start_time)
        start_minute = int(round((start_time - start_hour) * 60))
        end_hour = int(end_time)
        end_minute = int(round((end_time - end_hour) * 60))
        start_dt = datetime.combine(work_date, datetime.min.time()).replace(
            hour=start_hour, minute=start_minute,
        )
        end_dt = datetime.combine(work_date, datetime.min.time()).replace(
            hour=end_hour, minute=end_minute,
        )
        if end_time <= start_time:
            end_dt += timedelta(days=1)
        cur.execute(
            "UPDATE hr_overtime_request SET start_datetime=%s, end_datetime=%s WHERE id=%s",
            (start_dt, end_dt, row_id),
        )
        if work_date:
            cur.execute(
                "UPDATE hr_overtime_request SET date=%s WHERE id=%s",
                (start_dt.date(), row_id),
            )
    print('Migrated float times to datetimes')

# Default any NULL datetimes so NOT NULL constraint won't fail on future ORM sync
cur.execute("""
    UPDATE hr_overtime_request
    SET start_datetime = COALESCE(start_datetime, (date + time '18:00')::timestamp),
        end_datetime = COALESCE(end_datetime, (date + time '21:00')::timestamp)
    WHERE start_datetime IS NULL OR end_datetime IS NULL
""")

if 'start_time' in cols:
    cur.execute("ALTER TABLE hr_overtime_request DROP COLUMN IF EXISTS start_time")
    print('Dropped start_time')

if 'end_time' in cols:
    cur.execute("ALTER TABLE hr_overtime_request DROP COLUMN IF EXISTS end_time")
    print('Dropped end_time')

cur.execute("""
    UPDATE ir_module_module
    SET latest_version = '19.0.1.0.1', state = 'installed'
    WHERE name = 'hr_overtime_management'
""")

conn.commit()

cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'hr_overtime_request'
    ORDER BY column_name
""")
print('After:', [r[0] for r in cur.fetchall()])
conn.close()
print('Done. Restart Odoo or refresh the page.')
