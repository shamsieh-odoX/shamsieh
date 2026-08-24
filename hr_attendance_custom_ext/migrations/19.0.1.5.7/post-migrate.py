"""Fix Studio compute typo on hr.payslip x_ssc_employer_share_report."""


SAFE_COMPUTE = """
for record in self:
    amount = 0.0
    for line in record.line_ids:
        name = line.name or ''
        code = (line.code or '').upper()
        if (
            'EMPLOYER' in code
            or 'Employer SSC' in name
            or 'حصة الشركة' in name
        ):
            amount = abs(line.total or 0.0)
            break
    record['x_ssc_employer_share_report'] = amount
""".strip()


def migrate(cr, version):
    cr.execute(
        """
        SELECT id, compute
          FROM ir_model_fields
         WHERE name = 'x_ssc_employer_share_report'
           AND model = 'hr.payslip'
        """
    )
    for field_id, compute in cr.fetchall():
        text = compute or ''
        if 'amountfor' in text or not text.strip():
            cr.execute(
                """
                UPDATE ir_model_fields
                   SET compute = %s
                 WHERE id = %s
                """,
                (SAFE_COMPUTE, field_id),
            )
