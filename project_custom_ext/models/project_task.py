# -*- coding: utf-8 -*-

from datetime import timedelta



from odoo import api, fields, models, _

from odoo.exceptions import UserError





class ProjectTask(models.Model):

    _inherit = 'project.task'



    can_move_stage = fields.Boolean(compute='_compute_can_move_stage')

    allocated_until = fields.Datetime(

        string='Allocated Until',

        help='Planned date and time when allocated work on this task should be completed.',

    )

    time_remaining_until = fields.Datetime(

        string='Time Remaining Until',

        compute='_compute_time_remaining_until',

        store=True,

    )



    def _compute_can_move_stage(self):

        can_move = self.env['project.custom.access.mixin']._can_move_task_stage()

        for task in self:

            task.can_move_stage = can_move



    @api.depends('allocated_until', 'date_deadline', 'remaining_hours', 'allocated_hours')

    def _compute_time_remaining_until(self):

        now = fields.Datetime.now()

        for task in self:

            if task.allocated_until:

                task.time_remaining_until = task.allocated_until

            elif task.date_deadline:

                task.time_remaining_until = task.date_deadline

            elif task.remaining_hours and task.remaining_hours > 0:

                task.time_remaining_until = now + timedelta(hours=task.remaining_hours)

            else:

                task.time_remaining_until = False



    @api.onchange('allocated_until')

    def _onchange_allocated_until(self):

        if self.allocated_until and not self.date_deadline:

            self.date_deadline = self.allocated_until



    def write(self, vals):

        if not self.env.su and {'stage_id', 'state'} & set(vals):

            if self.env['project.custom.access.mixin']._is_edit_only():

                raise UserError(
                    _('You cannot move tasks between stages with your current access level.')
                )

        return super().write(vals)


