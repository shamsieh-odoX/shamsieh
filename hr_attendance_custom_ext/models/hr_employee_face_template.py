# -*- coding: utf-8 -*-

import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployeeFaceTemplate(models.Model):
    _name = 'hr.employee.face.template'
    _description = 'Employee Face Template'
    _order = 'enrolled_at desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='employee_id.company_id',
        store=True,
        index=True,
    )
    embedding_json = fields.Text(
        string='Face Embedding (JSON)',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    provider = fields.Selection(
        selection=[('insightface', 'InsightFace')],
        required=True,
        default='insightface',
    )
    active = fields.Boolean(default=True, index=True)
    enrolled_at = fields.Datetime()
    enrolled_by = fields.Many2one('res.users')
    image_attachment_id = fields.Many2one('ir.attachment', ondelete='set null')
    notes = fields.Text()

    def get_embedding_vector(self):
        self.ensure_one()
        if not self.embedding_json:
            return None
        return json.loads(self.embedding_json)

    def set_embedding_vector(self, vector):
        self.ensure_one()
        self.embedding_json = json.dumps(vector)

    @api.model
    def get_active_for_employee(self, employee):
        if not employee:
            return self.browse()
        return self.search([
            ('employee_id', '=', employee.id),
            ('active', '=', True),
        ], limit=1)

    def deactivate_others_for_employee(self):
        for template in self:
            others = self.search([
                ('employee_id', '=', template.employee_id.id),
                ('active', '=', True),
                ('id', '!=', template.id),
            ])
            if others:
                others.write({'active': False})

    @api.constrains('active', 'employee_id')
    def _check_single_active_template(self):
        for template in self.filtered('active'):
            duplicates = self.search([
                ('employee_id', '=', template.employee_id.id),
                ('active', '=', True),
                ('id', '!=', template.id),
            ])
            if duplicates:
                raise ValidationError(_(
                    'Only one active face template is allowed per employee.'
                ))
