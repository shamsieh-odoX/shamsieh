# -*- coding: utf-8 -*-
from odoo import fields, models

from .own_data_access import own_data_has_field_access

# Officers keep full access; own-data users also see Personal / Work private fields.
_OWN = 'hr.group_hr_user,hr_employee_own_data.group_hr_own_data'


class HrVersion(models.Model):
    _inherit = 'hr.version'

    def _has_field_access(self, field, operation):
        forced = own_data_has_field_access(self, field, operation)
        if forced is not None:
            return forced
        return super()._has_field_access(field, operation)

    # Odoo auto-writes these whenever any version field is saved.
    last_modified_uid = fields.Many2one(groups=_OWN)
    last_modified_date = fields.Datetime(groups=_OWN)

    country_id = fields.Many2one(groups=_OWN)
    identification_id = fields.Char(groups=_OWN)
    ssnid = fields.Char(groups=_OWN)
    passport_id = fields.Char(groups=_OWN)
    passport_expiration_date = fields.Date(groups=_OWN)
    sex = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ], groups=_OWN)
    private_street = fields.Char(groups=_OWN)
    private_street2 = fields.Char(groups=_OWN)
    private_city = fields.Char(groups=_OWN)
    allowed_country_state_ids = fields.Many2many(groups=_OWN)
    private_state_id = fields.Many2one(groups=_OWN)
    private_zip = fields.Char(groups=_OWN)
    private_country_id = fields.Many2one(groups=_OWN)
    distance_home_work = fields.Integer(groups=_OWN)
    km_home_work = fields.Integer(groups=_OWN)
    distance_home_work_unit = fields.Selection(groups=_OWN)
    marital = fields.Selection(groups=_OWN)
    spouse_complete_name = fields.Char(groups=_OWN)
    spouse_birthdate = fields.Date(groups=_OWN)
    children = fields.Integer(groups=_OWN)
    has_job = fields.Selection(
        [('yes', 'Yes'), ('no', 'No')],
        string='Spouse Works',
        groups=_OWN,
        tracking=True,
    )
