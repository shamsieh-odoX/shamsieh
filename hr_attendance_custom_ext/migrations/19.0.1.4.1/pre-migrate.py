# -*- coding: utf-8 -*-
"""Rename request_date to date_from and add date_to for period-based WFH requests."""

import logging

_logger = logging.getLogger(__name__)


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
    table = 'hr_remote_work_request'
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = %s
        """,
        (table,),
    )
    if not cr.fetchone():
        return

    if _column_exists(cr, table, 'request_date') and not _column_exists(cr, table, 'date_from'):
        cr.execute(f'ALTER TABLE {table} RENAME COLUMN request_date TO date_from')
        _logger.info('Renamed hr_remote_work_request.request_date to date_from')

    if not _column_exists(cr, table, 'date_to'):
        cr.execute(f'ALTER TABLE {table} ADD COLUMN date_to date')
        _logger.info('Added hr_remote_work_request.date_to')

    if _column_exists(cr, table, 'date_from') and _column_exists(cr, table, 'date_to'):
        cr.execute(
            f"""
            UPDATE {table}
               SET date_to = date_from
             WHERE date_to IS NULL
               AND date_from IS NOT NULL
            """
        )
