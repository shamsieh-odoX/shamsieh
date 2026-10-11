# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import AccessError

_OWN = 'hr.group_hr_user,hr_employee_own_data.group_hr_own_data'

# Organizational / payroll / settings fields self-service users must not change.
_FORBIDDEN_OWN_DATA_FIELDS = frozenset({
    'department_id',
    'job_id',
    'parent_id',
    'coach_id',
    'company_id',
    'address_id',
    'employee_type',
    'user_id',
    'barcode',
    'pin',
    'wage',
    'contract_wage',
    'structure_type_id',
    'contract_type_id',
    'contract_date_start',
    'contract_date_end',
    'trial_date_end',
    'resource_calendar_id',
    'hr_responsible_id',
    'departure_reason_id',
    'departure_description',
    'departure_date',
    'category_ids',
    'version_id',
    'current_version_id',
})


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    legal_name = fields.Char(groups=_OWN)
    private_phone = fields.Char(groups=_OWN)
    private_email = fields.Char(groups=_OWN)
    lang = fields.Selection(groups=_OWN)
    place_of_birth = fields.Char(groups=_OWN)
    country_of_birth = fields.Many2one(groups=_OWN)
    birthday = fields.Date(groups=_OWN)
    birthday_public_display = fields.Boolean(groups=_OWN)
    permit_no = fields.Char(groups=_OWN)
    visa_no = fields.Char(groups=_OWN)
    visa_expire = fields.Date(groups=_OWN)
    work_permit_expiration_date = fields.Date(groups=_OWN)
    has_work_permit = fields.Binary(groups=_OWN)
    work_permit_name = fields.Char(groups=_OWN)
    certificate = fields.Selection(groups=_OWN)
    study_field = fields.Char(groups=_OWN)
    study_school = fields.Char(groups=_OWN)
    emergency_contact = fields.Char(groups=_OWN)
    emergency_phone = fields.Char(groups=_OWN)
    id_card = fields.Binary(groups=_OWN)
    driving_license = fields.Binary(groups=_OWN)
    private_car_plate = fields.Char(groups=_OWN)
    # Loaded on employee list / tags; needed so own-data users can open Employees.
    category_ids = fields.Many2many(groups=_OWN)

    def _is_own_data_only_user(self):
        user = self.env.user
        return (
            user.has_group('hr_employee_own_data.group_hr_own_data')
            and not user.has_group('hr.group_hr_user')
        )

    def write(self, vals):
        if self._is_own_data_only_user():
            if any(emp.user_id != self.env.user for emp in self):
                raise AccessError(_("You can only edit your own employee record."))
            forbidden = sorted(set(vals) & _FORBIDDEN_OWN_DATA_FIELDS)
            if forbidden:
                raise AccessError(_(
                    "You cannot change these fields on your employee record: %s. "
                    "Please contact HR.",
                    ', '.join(forbidden),
                ))
        return super().write(vals)
