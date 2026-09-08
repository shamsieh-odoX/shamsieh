# -*- coding: utf-8 -*-
"""Ensure Shamsieh paid-break calendar uses 8 paid hours/day."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    try:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr, SUPERUSER_ID, {})
    except Exception:
        _logger.exception('hr_attendance_custom_ext: cannot build env')
        return

    calendar = env.ref(
        'hr_attendance_custom_ext.resource_calendar_shamsieh_standard',
        raise_if_not_found=False,
    )
    if not calendar:
        return

    if calendar.hours_per_day != 8.0:
        calendar.write({'hours_per_day': 8.0})
        _logger.info(
            'Updated %s hours_per_day to 8.0 for paid-break policy',
            calendar.display_name,
        )
