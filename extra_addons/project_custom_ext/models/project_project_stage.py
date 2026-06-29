# -*- coding: utf-8 -*-

from odoo import api, fields, models





class ProjectProjectStage(models.Model):

    _inherit = 'project.project.stage'



    is_closing_stage = fields.Boolean(

        string='Closing Stage',

        help='Marks this project stage as a closing/completed stage.',

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


