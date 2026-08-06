# -*- coding: utf-8 -*-
"""Ensure Paid Time Off requires manager then officer/GM approval."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE hr_leave_type
           SET leave_validation_type = 'both'
         WHERE requires_allocation IS TRUE
           AND leave_validation_type IN ('no_validation', 'manager', 'hr')
           AND (
                name ILIKE '%paid%time%off%'
             OR name ILIKE '%legal%leave%'
             OR name ILIKE '%annual%'
             OR name ILIKE '%pto%'
           )
        """
    )
