# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrEmployeeFaceEnrollWizard(models.TransientModel):
    _name = 'hr.employee.face.enroll.wizard'
    _description = 'Enroll Employee Face Template'

    employee_id = fields.Many2one('hr.employee', required=True)
    company_id = fields.Many2one(related='employee_id.company_id')
    enrollment_image = fields.Binary(string='Enrollment Image', required=True, attachment=False)
    enrollment_image_filename = fields.Char()
    notes = fields.Text()

    def action_enroll(self):
        self.ensure_one()
        raise UserError(_(
            'Face enrollment provider is not installed or not configured. '
            'Install optional Python packages from requirements-face.txt and configure InsightFace.'
        ))
