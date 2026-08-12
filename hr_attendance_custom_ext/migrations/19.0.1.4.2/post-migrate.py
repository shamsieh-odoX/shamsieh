# -*- coding: utf-8 -*-
"""Migrate approved legacy remote-work requests to Time Off leaves."""

import logging

_logger = logging.getLogger(__name__)


def _table_exists(cr, table):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = %s
        """,
        (table,),
    )
    return bool(cr.fetchone())


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    try:
        from odoo import api, SUPERUSER_ID
    except Exception:
        _logger.exception('Unable to import Odoo migration environment')
        return

    if not _table_exists(cr, 'hr_remote_work_request'):
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    leave_type = env.ref(
        'hr_attendance_custom_ext.leave_type_remote_work',
        raise_if_not_found=False,
    )
    if not leave_type:
        _logger.warning('Remote Work leave type not found; skipping migration.')
        return

    date_from_col = 'date_from' if _column_exists(cr, 'hr_remote_work_request', 'date_from') else 'request_date'
    date_to_col = 'date_to' if _column_exists(cr, 'hr_remote_work_request', 'date_to') else 'request_date'

    query = f"""
        SELECT id, employee_id, company_id, {date_from_col} AS date_from, {date_to_col} AS date_to
          FROM hr_remote_work_request
         WHERE state = 'approved'
           AND employee_id IS NOT NULL
           AND {date_from_col} IS NOT NULL
           AND {date_to_col} IS NOT NULL
    """
    cr.execute(query)
    rows = cr.dictfetchall()
    if not rows:
        return

    Leave = env['hr.leave'].sudo()
    created_count = 0
    skipped_count = 0
    for row in rows:
        legacy_id = row['id']
        employee_id = row['employee_id']
        date_from = row['date_from']
        date_to = row['date_to']

        legacy_name = f'Remote Work (migrated #{legacy_id})'
        existing = Leave.search([
            ('name', '=', legacy_name),
            ('employee_id', '=', employee_id),
            ('holiday_status_id', '=', leave_type.id),
            ('request_date_from', '=', date_from),
            ('request_date_to', '=', date_to),
        ], limit=1)
        if existing:
            skipped_count += 1
            continue

        leave = Leave.create({
            'name': legacy_name,
            'employee_id': employee_id,
            'holiday_status_id': leave_type.id,
            'request_date_from': date_from,
            'request_date_to': date_to,
        })
        if leave.state not in ('validate', 'validate1'):
            leave.action_approve()
        if leave.state != 'validate':
            leave.action_validate()
        created_count += 1

    _logger.info(
        'Remote Work migration completed: created=%s skipped=%s',
        created_count,
        skipped_count,
    )
