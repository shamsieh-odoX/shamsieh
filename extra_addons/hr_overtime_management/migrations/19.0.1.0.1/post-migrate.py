from datetime import datetime, timedelta


def migrate(cr, version):
    """Convert legacy float start/end times to datetime fields."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'hr_overtime_request' AND column_name = 'start_time'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        SELECT id, date, start_time, end_time
        FROM hr_overtime_request
        WHERE start_time IS NOT NULL AND end_time IS NOT NULL AND date IS NOT NULL
    """)
    for row_id, work_date, start_time, end_time in cr.fetchall():
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
        cr.execute(
            """
            UPDATE hr_overtime_request
            SET start_datetime = %s, end_datetime = %s
            WHERE id = %s
            """,
            (start_dt, end_dt, row_id),
        )
