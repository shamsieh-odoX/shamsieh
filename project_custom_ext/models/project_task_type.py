# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    is_closing_stage = fields.Boolean(
        string='Counts as Done',
        help='When enabled, tasks moved to this stage are treated as completed and increase the project progress %.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('fold') and 'is_closing_stage' not in vals:
                vals['is_closing_stage'] = True
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('fold'):
            vals.setdefault('is_closing_stage', True)
        return super().write(vals)
