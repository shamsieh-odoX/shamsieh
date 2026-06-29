# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectUpdate(models.Model):
    _inherit = 'project.update'

    project_id = fields.Many2one(
        ondelete='cascade',
    )
