from odoo import _, api, fields, models


class ShamsTodoDashboard(models.TransientModel):
    _name = 'shams.todo.dashboard'
    _description = 'Group Dashboard'
    _rec_name = 'name'

    name = fields.Char(compute='_compute_labels')
    total_task_count = fields.Integer(compute='_compute_counts')
    my_task_count = fields.Integer(compute='_compute_counts')
    overdue_task_count = fields.Integer(compute='_compute_counts')
    done_task_count = fields.Integer(compute='_compute_counts')
    my_task_ids = fields.Many2many(
        'shams.todo.task',
        compute='_compute_my_task_ids',
        string='My Assigned Tasks',
    )

    # Translated UI labels (view text nodes are unreliable for button spans).
    title_label = fields.Char(compute='_compute_labels')
    subtitle_label = fields.Char(compute='_compute_labels')
    open_tasks_label = fields.Char(compute='_compute_labels')
    open_tasks_hint = fields.Char(compute='_compute_labels')
    my_tasks_label = fields.Char(compute='_compute_labels')
    my_tasks_hint = fields.Char(compute='_compute_labels')
    overdue_label = fields.Char(compute='_compute_labels')
    overdue_hint = fields.Char(compute='_compute_labels')
    completed_label = fields.Char(compute='_compute_labels')
    completed_hint = fields.Char(compute='_compute_labels')
    by_group_label = fields.Char(compute='_compute_labels')
    by_group_hint = fields.Char(compute='_compute_labels')
    my_section_label = fields.Char(compute='_compute_labels')
    view_all_label = fields.Char(compute='_compute_labels')

    @api.depends_context('lang')
    def _compute_labels(self):
        for dashboard in self:
            dashboard.name = _('Group Dashboard')
            dashboard.title_label = _('Group To-Do Overview')
            dashboard.subtitle_label = _(
                'Track shared team tasks across your groups at a glance.'
            )
            dashboard.open_tasks_label = _('Open Tasks')
            dashboard.open_tasks_hint = _('Active group tasks you can access')
            dashboard.my_tasks_label = _('Assigned to Me')
            dashboard.my_tasks_hint = _('Open tasks waiting on you')
            dashboard.overdue_label = _('Overdue')
            dashboard.overdue_hint = _('Past due and still open')
            dashboard.completed_label = _('Completed')
            dashboard.completed_hint = _('Finished group tasks')
            dashboard.by_group_label = _('Tasks by Group')
            dashboard.by_group_hint = _('Open pivot analysis')
            dashboard.my_section_label = _('My Assigned Tasks')
            dashboard.view_all_label = _('View all')

    @api.depends_context('uid')
    def _compute_my_task_ids(self):
        Task = self.env['shams.todo.task']
        for dashboard in self:
            dashboard.my_task_ids = Task.search([
                ('assigned_user_id', '=', self.env.uid),
                ('status', 'not in', ['done', 'cancelled']),
            ], order='due_date asc, priority desc, id desc')

    @api.depends_context('uid')
    def _compute_counts(self):
        Task = self.env['shams.todo.task']
        user = self.env.user
        today = fields.Date.context_today(self)
        open_domain = [('status', 'not in', ['done', 'cancelled'])]
        for dashboard in self:
            dashboard.total_task_count = Task.search_count(open_domain)
            dashboard.my_task_count = Task.search_count(
                open_domain + [('assigned_user_id', '=', user.id)],
            )
            dashboard.overdue_task_count = Task.search_count([
                ('due_date', '<', today),
                ('status', 'not in', ['done', 'cancelled']),
            ])
            dashboard.done_task_count = Task.search_count([
                ('status', '=', 'done'),
            ])

    def action_view_all_tasks(self):
        return self._get_task_action(
            [('status', 'not in', ['done', 'cancelled'])],
            name=_('Open Tasks'),
        )

    def action_view_my_tasks(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'shams_todo_groups.shams_todo_task_action_my_tasks',
        )

    def action_view_overdue_tasks(self):
        today = fields.Date.context_today(self)
        return self._get_task_action([
            ('due_date', '<', today),
            ('status', 'not in', ['done', 'cancelled']),
        ], name=_('Overdue'))

    def action_view_done_tasks(self):
        return self._get_task_action(
            [('status', '=', 'done')],
            name=_('Completed'),
        )

    def action_view_tasks_by_group(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tasks by Group'),
            'res_model': 'shams.todo.task',
            'view_mode': 'pivot,list,kanban,calendar,form',
            'context': {
                'pivot_measures': ['__count'],
                'search_default_group_by_group': 1,
            },
        }

    def _get_task_action(self, domain, name=None):
        return {
            'type': 'ir.actions.act_window',
            'name': name or _('Tasks'),
            'res_model': 'shams.todo.task',
            'view_mode': 'list,kanban,calendar,form',
            'domain': domain,
        }

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Group Dashboard'),
            'res_model': 'shams.todo.dashboard',
            'view_mode': 'form',
            'res_id': dashboard.id,
            'target': 'current',
            'path': 'group-dashboard',
        }
