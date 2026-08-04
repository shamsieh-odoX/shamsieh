from odoo import api, fields, models


# Bilingual labels keyed by language (avoids depending on loaded .po code terms).
_DASH_LABELS = {
    'name': {
        'en': 'Group Dashboard',
        'ar': 'لوحة معلومات المجموعات',
    },
    'title': {
        'en': 'Group To-Do Overview',
        'ar': 'نظرة عامة على مهام المجموعات',
    },
    'subtitle': {
        'en': 'Track shared team tasks across your groups at a glance.',
        'ar': 'تتبع مهام الفريق المشتركة عبر مجموعاتك بنظرة سريعة.',
    },
    'open_tasks': {
        'en': 'Open Tasks',
        'ar': 'المهام المفتوحة',
    },
    'open_tasks_hint': {
        'en': 'Active group tasks you can access',
        'ar': 'مهام المجموعات النشطة التي يمكنك الوصول إليها',
    },
    'my_tasks': {
        'en': 'Assigned to Me',
        'ar': 'مُعيَّنة لي',
    },
    'my_tasks_hint': {
        'en': 'Open tasks waiting on you',
        'ar': 'مهام مفتوحة بانتظارك',
    },
    'overdue': {
        'en': 'Overdue',
        'ar': 'متأخرة',
    },
    'overdue_hint': {
        'en': 'Past due and still open',
        'ar': 'متأخرة وما زالت مفتوحة',
    },
    'completed': {
        'en': 'Completed',
        'ar': 'مكتملة',
    },
    'completed_hint': {
        'en': 'Finished group tasks',
        'ar': 'مهام المجموعات المنجزة',
    },
    'by_group': {
        'en': 'Tasks by Group',
        'ar': 'المهام حسب المجموعة',
    },
    'by_group_hint': {
        'en': 'Open pivot analysis',
        'ar': 'فتح تحليل المحور',
    },
    'my_section': {
        'en': 'My Assigned Tasks',
        'ar': 'مهامي المُعيَّنة',
    },
    'view_all': {
        'en': 'View all',
        'ar': 'عرض الكل',
    },
    'tasks': {
        'en': 'Tasks',
        'ar': 'المهام',
    },
}


def _dash_label(env, key):
    lang = (env.lang or 'en_US').lower()
    locale = 'ar' if lang.startswith('ar') else 'en'
    entry = _DASH_LABELS[key]
    return entry.get(locale) or entry['en']


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
            dashboard.name = _dash_label(self.env, 'name')
            dashboard.title_label = _dash_label(self.env, 'title')
            dashboard.subtitle_label = _dash_label(self.env, 'subtitle')
            dashboard.open_tasks_label = _dash_label(self.env, 'open_tasks')
            dashboard.open_tasks_hint = _dash_label(self.env, 'open_tasks_hint')
            dashboard.my_tasks_label = _dash_label(self.env, 'my_tasks')
            dashboard.my_tasks_hint = _dash_label(self.env, 'my_tasks_hint')
            dashboard.overdue_label = _dash_label(self.env, 'overdue')
            dashboard.overdue_hint = _dash_label(self.env, 'overdue_hint')
            dashboard.completed_label = _dash_label(self.env, 'completed')
            dashboard.completed_hint = _dash_label(self.env, 'completed_hint')
            dashboard.by_group_label = _dash_label(self.env, 'by_group')
            dashboard.by_group_hint = _dash_label(self.env, 'by_group_hint')
            dashboard.my_section_label = _dash_label(self.env, 'my_section')
            dashboard.view_all_label = _dash_label(self.env, 'view_all')

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
            name=_dash_label(self.env, 'open_tasks'),
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
        ], name=_dash_label(self.env, 'overdue'))

    def action_view_done_tasks(self):
        return self._get_task_action(
            [('status', '=', 'done')],
            name=_dash_label(self.env, 'completed'),
        )

    def action_view_tasks_by_group(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _dash_label(self.env, 'by_group'),
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
            'name': name or _dash_label(self.env, 'tasks'),
            'res_model': 'shams.todo.task',
            'view_mode': 'list,kanban,calendar,form',
            'domain': domain,
        }

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': _dash_label(self.env, 'name'),
            'res_model': 'shams.todo.dashboard',
            'view_mode': 'form',
            'res_id': dashboard.id,
            'target': 'current',
            'path': 'group-dashboard',
        }
