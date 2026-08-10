# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProjectTaskTemplate(models.Model):
    _name = 'project.task.template'
    _description = 'Project Stage Template'
    _order = 'name, id'

    name = fields.Char(required=True, translate=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    stage_ids = fields.One2many(
        'project.task.template.line',
        'template_id',
        string='Stages',
        copy=True,
    )
    stage_line_count = fields.Integer(compute='_compute_stage_line_count')

    @api.depends('stage_ids')
    def _compute_stage_line_count(self):
        for template in self:
            template.stage_line_count = len(template.stage_ids)

    def action_add_standard_stages(self):
        """Add the default workflow stages if the template has none yet."""
        self.ensure_one()
        if self.stage_ids:
            raise UserError(_('This template already has stages. Edit them in the list or remove them first.'))
        standard = [
            ('To Do', 10, False),
            ('In Progress', 20, False),
            ('Waiting', 30, False),
            ('Review', 40, False),
            ('Done', 50, True),
        ]
        self.env['project.task.template.line'].create([
            {
                'template_id': self.id,
                'name': name,
                'sequence': seq,
                'is_closing_stage': closing,
            }
            for name, seq, closing in standard
        ])
        return True


class ProjectTaskTemplateLine(models.Model):
    _name = 'project.task.template.line'
    _description = 'Project Stage Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one('project.task.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    is_closing_stage = fields.Boolean(
        string='Counts as Done',
        help='When enabled, tasks in this stage count as completed for the project progress % (e.g. Done or Completed).',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('template_id') and self.env.context.get('default_template_id'):
                vals['template_id'] = self.env.context['default_template_id']
        return super().create(vals_list)
