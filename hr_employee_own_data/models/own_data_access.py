# -*- coding: utf-8 -*-
"""Shared field-access helper for Manage own data users."""


def own_data_has_field_access(recordset, field, operation):
    """Return True/False to force access, or None to use the normal ACL."""
    if operation != 'read' or recordset.env.su:
        return None
    if not recordset.env.user.has_group('hr_employee_own_data.group_hr_own_data'):
        return None
    # Do not expose relational fields whose comodel the user cannot read
    # (e.g. sign.request) — that causes a secondary AccessError.
    if field.relational and field.comodel_name:
        if field.comodel_name not in recordset.env:
            return False
        if not recordset.env[field.comodel_name].has_access('read'):
            return False
    return True
