"""Drop fragile unique constraints that break upgrades on dirty production data."""


_DROP_CONSTRAINTS = (
    'hr_attendance__attendance_external_log_device_uniq',
    'fingerprint_device_log__device_external_uniq',
)


def migrate(cr, version):
    for name in _DROP_CONSTRAINTS:
        cr.execute(
            """
            SELECT quote_ident(n.nspname || '.' || t.relname), quote_ident(c.conname)
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE c.conname = %s
            """,
            (name,),
        )
        row = cr.fetchone()
        if not row:
            # Fallback: match by table + contype unique containing external
            continue
        cr.execute(f'ALTER TABLE {row[0]} DROP CONSTRAINT IF EXISTS {row[1]}')

    # Also drop any unique on those columns regardless of historical naming.
    cr.execute(
        """
        SELECT quote_ident(t.relname), quote_ident(c.conname)
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_attribute a1 ON a1.attrelid = t.oid AND a1.attnum = ANY (c.conkey)
         WHERE t.relname IN ('hr_attendance', 'fingerprint_device_log')
           AND c.contype = 'u'
           AND a1.attname IN ('external_log_id', 'external_id')
        """
    )
    for table_sql, con_sql in cr.fetchall():
        cr.execute(f'ALTER TABLE {table_sql} DROP CONSTRAINT IF EXISTS {con_sql}')
