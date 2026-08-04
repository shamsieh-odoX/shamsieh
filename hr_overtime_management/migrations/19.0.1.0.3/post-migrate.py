"""Recompute overtime costs after hourly cost logic update."""

def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'res_company' AND column_name = 'overtime_hours_per_month'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE res_company
            ADD COLUMN overtime_hours_per_month double precision DEFAULT 173.33
        """)

    # Force stored computed fields to refresh on next ORM read
    cr.execute("""
        UPDATE hr_overtime_request
        SET write_date = NOW()
        WHERE employee_id IS NOT NULL
    """)
