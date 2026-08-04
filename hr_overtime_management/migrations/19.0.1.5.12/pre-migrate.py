"""Drop leftover unique(code, company_id) before schema sync.

Nullable company_id makes UNIQUE treat multiple shared templates as
duplicates in PostgreSQL, which crashes module upgrade/load.
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT conname
          FROM pg_constraint
         WHERE conrelid = 'hr_overtime_type'::regclass
           AND contype = 'u'
        """
    )
    for (conname,) in cr.fetchall():
        cr.execute(f'ALTER TABLE hr_overtime_type DROP CONSTRAINT IF EXISTS "{conname}"')

    # Known historical names if the catalog query above is empty on some dumps.
    for name in (
        'hr_overtime_type__code_company_uniq',
        'hr_overtime_type_code_company_uniq',
        'hr_overtime_type__code_company_uniq_constraint',
    ):
        cr.execute(f'ALTER TABLE hr_overtime_type DROP CONSTRAINT IF EXISTS "{name}"')
