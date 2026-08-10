# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    progress_percentage = fields.Float(
        string='Project Progress %',
        compute='_compute_progress_and_hours',
        store=True,
        readonly=True,
        aggregator='avg',
        digits=(16, 0),
        help='Completed tasks / total tasks × 100 (tasks in a closing stage count as done).',
    )
    progress_range = fields.Selection(
        selection=[
            ('0_20', '0% - 20%'),
            ('20_50', '20% - 50%'),
            ('50_80', '50% - 80%'),
            ('80_100', '80% - 100%'),
        ],
        string='Progress Range',
        compute='_compute_progress_range',
        store=True,
        readonly=True,
    )
    country_id = fields.Many2one('res.country', string='Country')
    sales_team_id = fields.Many2one('crm.team', string='Sales Team')
    estimated_hours = fields.Float(
        string='Estimated Hours',
        compute='_compute_progress_and_hours',
        store=True,
        readonly=True,
    )
    spent_hours = fields.Float(
        string='Spent Hours',
        compute='_compute_progress_and_hours',
        store=True,
        readonly=True,
    )
    remaining_hours = fields.Float(
        string='Remaining Hours',
        compute='_compute_progress_and_hours',
        store=True,
        readonly=True,
    )
    allocated_datetime = fields.Datetime(
        string='Allocated Until',
        help='Planned date and time when allocated work on this project should be completed.',
    )
    time_remaining_datetime = fields.Datetime(
        string='Time Remaining Until',
        compute='_compute_time_remaining_datetime',
        store=True,
    )
    task_template_id = fields.Many2one(
        'project.task.template',
        string='Task Template',
        copy=False,
        help='Select a template at project creation to auto-generate workflow stages (tasks are optional).',
    )
    template_applied = fields.Boolean(copy=False, readonly=True)

    @api.depends(
        'task_ids',
        'task_ids.stage_id',
        'task_ids.stage_id.is_closing_stage',
        'task_ids.allocated_hours',
        'task_ids.effective_hours',
        'task_ids.is_template',
    )
    def _compute_progress_and_hours(self):
        """Batch SQL aggregation — avoids per-project Python loops on large datasets."""
        if not self:
            return
        project_ids = self.ids
        Task = self.env['project.task']
        base_domain = [('project_id', 'in', project_ids), ('is_template', '=', False)]

        totals = {
            project.id: (count, allocated, spent)
            for project, count, allocated, spent in Task._read_group(
                base_domain,
                ['project_id'],
                ['__count', 'allocated_hours:sum', 'effective_hours:sum'],
            )
        }
        done_counts = {
            project.id: count
            for project, count in Task._read_group(
                base_domain + [('stage_id.is_closing_stage', '=', True)],
                ['project_id'],
                ['__count'],
            )
        }

        for project in self:
            total, estimated, spent = totals.get(project.id, (0, 0.0, 0.0))
            if total:
                closed = done_counts.get(project.id, 0)
                project.progress_percentage = round((closed / total) * 100.0)
            else:
                project.progress_percentage = 0.0
            project.estimated_hours = estimated or 0.0
            project.spent_hours = spent or 0.0
            project.remaining_hours = project.estimated_hours - project.spent_hours

    @api.depends('progress_percentage')
    def _compute_progress_range(self):
        for project in self:
            progress = project.progress_percentage or 0.0
            if progress < 20:
                project.progress_range = '0_20'
            elif progress < 50:
                project.progress_range = '20_50'
            elif progress < 80:
                project.progress_range = '50_80'
            else:
                project.progress_range = '80_100'

    @api.depends(
        'remaining_hours',
        'allocated_datetime',
        'task_ids.time_remaining_until',
        'task_ids.is_template',
    )
    def _compute_time_remaining_datetime(self):
        now = fields.Datetime.now()
        for project in self:
            open_tasks = project.task_ids.filtered(lambda t: not t.is_template)
            task_until = [dt for dt in open_tasks.mapped('time_remaining_until') if dt]
            if task_until:
                project.time_remaining_datetime = min(task_until)
            elif project.allocated_datetime:
                project.time_remaining_datetime = project.allocated_datetime
            elif project.remaining_hours > 0:
                project.time_remaining_datetime = now + timedelta(hours=project.remaining_hours)
            else:
                project.time_remaining_datetime = False

    @api.model_create_multi
    def create(self, vals_list):
        access = self.env['project.custom.access.mixin']
        if not access._can_create_project() and not self.env.su:
            raise UserError(_('You need Project Create/Move or Manager rights to create projects.'))
        projects = super().create(vals_list)
        projects._apply_task_template()
        return projects

    def write(self, vals):
        if 'task_template_id' in vals and any(p.template_applied for p in self):
            raise UserError(_('The task template cannot be changed after it has been applied.'))
        res = super().write(vals)
        if 'task_template_id' in vals:
            self.filtered(lambda p: not p.template_applied)._apply_task_template()
        return res

    def _apply_task_template(self):
        TaskType = self.env['project.task.type']
        for project in self:
            if not project.task_template_id or project.template_applied:
                continue
            template = project.task_template_id
            for stage_line in template.stage_ids.sorted('sequence'):
                TaskType.create({
                    'name': stage_line.name,
                    'sequence': stage_line.sequence,
                    'fold': stage_line.is_closing_stage,
                    'is_closing_stage': stage_line.is_closing_stage,
                    'project_ids': [(4, project.id)],
                })
            project.template_applied = True

    def unlink(self):
        """Remove project updates before delete (core leaves them and blocks unlink)."""
        self.write({'last_update_id': False})
        self.env['project.update'].search([('project_id', 'in', self.ids)]).unlink()
        return super().unlink()
