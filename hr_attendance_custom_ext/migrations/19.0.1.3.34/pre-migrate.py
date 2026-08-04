# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Late after 08:15 (15m grace), Asia/Amman tz, and sync break work state."""
    # Lateness cutoff: scheduled start + 15 minutes (08:00 + 15 => after 08:15).
    cr.execute("""
        UPDATE fingerprint_attendance_policy
           SET late_grace_minutes = 15
         WHERE COALESCE(late_grace_minutes, 0) = 0
    """)

    # Interpret working hours in Amman, not UTC.
    cr.execute("""
        UPDATE resource_calendar
           SET tz = 'Asia/Amman'
         WHERE COALESCE(tz, 'UTC') = 'UTC'
    """)
    cr.execute("""
        UPDATE resource_resource
           SET tz = 'Asia/Amman'
         WHERE COALESCE(tz, 'UTC') = 'UTC'
    """)
