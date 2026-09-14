# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProductType(models.Model):
    _name = 'project.product.type'
    _description = 'Project Product Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    project_count = fields.Integer(compute='_compute_project_count')

    _name_uniq = models.Constraint(
        'unique(name)',
        'Product type name must be unique.',
    )

    def _compute_project_count(self):
        Project = self.env['project.project']
        for product_type in self:
            product_type.project_count = Project.search_count([
                ('product_type_id', '=', product_type.id),
            ])

    def action_open_projects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Projects'),
            'res_model': 'project.project',
            'view_mode': 'kanban,list,form',
            'domain': [('product_type_id', '=', self.id)],
            'context': {'default_product_type_id': self.id},
        }
