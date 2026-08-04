# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Enable HTTP listening on existing Hikvision devices and backfill Odoo employee names."""
    cr.execute("""
        UPDATE fingerprint_device
        SET http_listening_enabled = TRUE
        WHERE api_type = 'hikvision'
          AND active = TRUE
          AND http_listening_enabled = FALSE
    """)
    cr.execute("""
        UPDATE fingerprint_device_log AS log
        SET employee_name = emp.name
        FROM hr_employee AS emp
        WHERE log.employee_id = emp.id
          AND (log.employee_name IS NULL OR log.employee_name != emp.name)
    """)
