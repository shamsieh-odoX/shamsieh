from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import html2plaintext


class ShamsTodoTask(models.Model):
    _name = 'shams.todo.task'
    _description = 'To-Do Task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date asc, priority desc, id desc'

    name = fields.Char(required=True, tracking=True)
    description = fields.Html()
    group_id = fields.Many2one(
        'shams.todo.group',
        string='Group',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        tracking=True,
        domain="[('id', 'in', member_user_ids)]",
    )
    member_user_ids = fields.Many2many(
        'res.users',
        related='group_id.member_ids',
        string='Group Members',
    )
    due_date = fields.Date(tracking=True)
    is_important = fields.Boolean(string='Important', default=False, tracking=True)
    my_day_date = fields.Date(
        string='My Day',
        help='When set to today, the task appears in My Day.',
    )
    # Values match Odoo's priority widget ('0'..'3'), same as project.task.
    priority = fields.Selection(
        selection=[
            ('0', 'Low'),
            ('1', 'Normal'),
            ('2', 'High'),
            ('3', 'Urgent'),
        ],
        string='Priority',
        default='1',
        required=True,
        tracking=True,
    )
    status = fields.Selection(
        selection=[
            ('todo', 'To Do'),
            ('in_progress', 'In Progress'),
            ('waiting_review', 'Waiting Review'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='todo',
        required=True,
        tracking=True,
    )
    created_by_id = fields.Many2one(
        'res.users',
        string='Created By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    completed_date = fields.Datetime(readonly=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='group_id.company_id',
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index', default=0)
    is_overdue = fields.Boolean(compute='_compute_is_overdue')
    is_done = fields.Boolean(
        string='Done',
        compute='_compute_is_done',
        inverse='_inverse_is_done',
        store=True,
    )

    @api.depends('status')
    def _compute_is_done(self):
        for task in self:
            task.is_done = task.status == 'done'

    def _inverse_is_done(self):
        for task in self:
            if task.is_done and task.status != 'done':
                task.status = 'done'
            elif not task.is_done and task.status == 'done':
                task.status = 'todo'

    def action_set_todo(self):
        self.write({'status': 'todo'})

    def action_set_in_progress(self):
        self.write({'status': 'in_progress'})

    def action_set_waiting_review(self):
        self.write({'status': 'waiting_review'})

    def action_set_done(self):
        self.write({'status': 'done'})

    def action_set_cancelled(self):
        self.write({'status': 'cancelled'})

    def action_assign_to_me(self):
        user = self.env.user
        for task in self:
            if task.group_id and user not in task.group_id.member_ids:
                raise ValidationError(_(
                    'You must be a member of the group "%(group)s" to assign this task to yourself.',
                    group=task.group_id.name,
                ))
            task.assigned_user_id = user

    def action_toggle_important(self):
        for task in self:
            task.is_important = not task.is_important
        return True

    def action_toggle_my_day(self):
        today = fields.Date.context_today(self)
        for task in self:
            task.my_day_date = False if task.my_day_date == today else today
        return True

    @api.model
    def _smart_list_domain(self, list_key, group_id=None):
        """Domain for Microsoft To Do–style smart lists and group lists."""
        user = self.env.user
        today = fields.Date.context_today(self)
        open_domain = [('status', 'not in', ('done', 'cancelled'))]
        if list_key == 'my_day':
            return open_domain + [('my_day_date', '=', today)]
        if list_key == 'important':
            return open_domain + [('is_important', '=', True)]
        if list_key == 'planned':
            return open_domain + [('due_date', '!=', False)]
        if list_key == 'assigned':
            return open_domain + [('assigned_user_id', '=', user.id)]
        if list_key == 'group' and group_id:
            return open_domain + [('group_id', '=', group_id)]
        return open_domain

    @api.model
    def get_todo_board(self, list_key='my_day', group_id=None, task_id=None):
        """Payload for the Shams To-Do client action (sidebar + tasks + detail)."""
        Group = self.env['shams.todo.group']
        user = self.env.user
        today = fields.Date.context_today(self)

        groups = Group.search([('member_ids', 'in', user.id)], order='name')
        domain = self._smart_list_domain(list_key, group_id=group_id)
        tasks = self.search(domain, order='is_done asc, due_date asc, priority desc, id desc', limit=200)

        def _task_row(task):
            return {
                'id': task.id,
                'name': task.name,
                'is_done': task.is_done,
                'is_important': task.is_important,
                'is_overdue': task.is_overdue,
                'due_date': task.due_date.isoformat() if task.due_date else False,
                'my_day_date': task.my_day_date.isoformat() if task.my_day_date else False,
                'in_my_day': task.my_day_date == today,
                'priority': task.priority,
                'status': task.status,
                'group_id': task.group_id.id,
                'group_name': task.group_id.name,
                'assigned_user_id': task.assigned_user_id.id if task.assigned_user_id else False,
                'assigned_user_name': task.assigned_user_id.name if task.assigned_user_id else False,
                'description_text': self._html_to_text(task.description),
                'assignable_members': [{
                    'id': member.id,
                    'name': member.name,
                } for member in task.group_id.member_ids.sorted('name')],
            }

        selected = False
        if task_id:
            selected_task = self.browse(task_id).exists()
            if selected_task:
                selected = _task_row(selected_task)

        titles = {
            'my_day': _('My Day'),
            'important': _('Important'),
            'planned': _('Planned'),
            'assigned': _('Assigned to me'),
            'group': False,
        }
        title = titles.get(list_key) or ''
        active_group = False
        if list_key == 'group' and group_id:
            active_group = groups.filtered(lambda g: g.id == group_id)[:1]
            title = active_group.name if active_group else _('Tasks')

        my_day_count = self.search_count(self._smart_list_domain('my_day'))
        important_count = self.search_count(self._smart_list_domain('important'))
        planned_count = self.search_count(self._smart_list_domain('planned'))
        assigned_count = self.search_count(self._smart_list_domain('assigned'))

        share_members = []
        share_candidates = []
        if active_group:
            share_members = [{
                'id': member.id,
                'name': member.name,
                'is_manager': member in active_group.manager_ids,
            } for member in active_group.member_ids.sorted('name')]
            # Internal users not already on the list (for “Assign / Share”).
            existing_ids = set(active_group.member_ids.ids)
            candidates = self.env['res.users'].search([
                ('share', '=', False),
                ('active', '=', True),
                ('id', 'not in', list(existing_ids) or [0]),
            ], order='name', limit=80)
            share_candidates = [{'id': u.id, 'name': u.name} for u in candidates]

        return {
            'today': today.isoformat(),
            'list_key': list_key,
            'group_id': group_id or False,
            'title': title,
            'current_user_id': user.id,
            'can_create_list': True,
            'can_share_list': bool(active_group and user.id in active_group.manager_ids.ids),
            'share_members': share_members,
            'share_candidates': share_candidates,
            'smart_lists': [
                {'key': 'my_day', 'label': _('My Day'), 'icon': 'sun', 'count': my_day_count},
                {'key': 'important', 'label': _('Important'), 'icon': 'star', 'count': important_count},
                {'key': 'planned', 'label': _('Planned'), 'icon': 'calendar', 'count': planned_count},
                {'key': 'assigned', 'label': _('Assigned to me'), 'icon': 'user', 'count': assigned_count},
            ],
            'groups': [{
                'id': g.id,
                'name': g.name,
                'count': self.search_count(self._smart_list_domain('group', group_id=g.id)),
                'color': g.color,
            } for g in groups],
            'tasks': [_task_row(t) for t in tasks],
            'selected_task': selected,
            'default_group_id': groups[:1].id if groups else False,
        }

    @api.model
    def _html_to_text(self, html_value):
        if not html_value:
            return ''
        return html2plaintext(html_value).strip()

    @api.model
    def create_todo_from_board(self, name, list_key='my_day', group_id=None):
        """Quick-add a task from the MS To Do–style board."""
        name = (name or '').strip()
        if not name:
            raise ValidationError(_('Task name is required.'))
        Group = self.env['shams.todo.group']
        user = self.env.user
        today = fields.Date.context_today(self)

        if not group_id:
            group_id = Group.get_or_create_personal_list().id
        group = Group.browse(group_id)
        if user.id not in group.member_ids.ids:
            raise ValidationError(_('You must be a member of the selected list.'))

        vals = {
            'name': name,
            'group_id': group.id,
            'assigned_user_id': user.id,
            'status': 'todo',
        }
        if list_key == 'my_day':
            vals['my_day_date'] = today
        elif list_key == 'important':
            vals['is_important'] = True
            vals['priority'] = '2'
        elif list_key == 'planned':
            vals['due_date'] = today
        task = self.create(vals)
        return self.get_todo_board(
            list_key=list_key,
            group_id=group_id if list_key == 'group' else None,
            task_id=task.id,
        )

    @api.model
    def update_todo_from_board(self, task_id, values):
        """Update selected fields from the board detail pane."""
        task = self.browse(task_id).exists()
        if not task:
            raise ValidationError(_('Task not found.'))
        allowed = {
            'name', 'is_done', 'is_important', 'due_date', 'priority',
            'my_day_date', 'description_text', 'status', 'assigned_user_id',
        }
        vals = {k: v for k, v in (values or {}).items() if k in allowed}
        if 'description_text' in vals:
            text = vals.pop('description_text') or ''
            vals['description'] = text
        if 'assigned_user_id' in vals and not vals['assigned_user_id']:
            vals['assigned_user_id'] = False
        if 'is_done' in vals and 'status' not in vals:
            vals['status'] = 'done' if vals['is_done'] else 'todo'
        task.write(vals)
        list_key = values.get('list_key') or 'my_day'
        group_id = values.get('group_id') or False
        return self.get_todo_board(list_key=list_key, group_id=group_id or None, task_id=task.id)

    @api.depends('due_date', 'status')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for task in self:
            task.is_overdue = bool(
                task.due_date
                and task.due_date < today
                and task.status not in ('done', 'cancelled')
            )

    @api.onchange('group_id')
    def _onchange_group_id(self):
        if not self.group_id:
            self.assigned_user_id = False
            return
        if self.assigned_user_id and self.assigned_user_id not in self.group_id.member_ids:
            self.assigned_user_id = False
        if not self.assigned_user_id and self.env.user in self.group_id.member_ids:
            self.assigned_user_id = self.env.user

    @api.constrains('assigned_user_id', 'group_id')
    def _check_assigned_user_is_member(self):
        for task in self:
            if not task.group_id or not task.assigned_user_id:
                continue
            if task.assigned_user_id not in task.group_id.member_ids:
                raise ValidationError(_(
                    'The assigned user must be a member of the group "%(group)s".',
                    group=task.group_id.name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        Group = self.env['shams.todo.group']
        for vals in vals_list:
            if not vals.get('created_by_id'):
                vals['created_by_id'] = user.id
            if not vals.get('assigned_user_id') and vals.get('group_id'):
                group = Group.browse(vals['group_id'])
                if user in group.member_ids:
                    vals['assigned_user_id'] = user.id
            if vals.get('status') == 'done' and not vals.get('completed_date'):
                vals['completed_date'] = fields.Datetime.now()
            if vals.get('is_important') and vals.get('priority', '1') in (False, '0', '1'):
                vals.setdefault('priority', '2')
        records = super().create(vals_list)
        partner = user.partner_id
        if partner:
            records.message_subscribe(partner_ids=partner.ids)
        return records

    def write(self, vals):
        if 'is_done' in vals and 'status' not in vals:
            vals['status'] = 'done' if vals['is_done'] else 'todo'
        if 'status' in vals:
            if vals['status'] == 'done':
                vals.setdefault('completed_date', fields.Datetime.now())
            elif vals['status'] != 'done':
                vals['completed_date'] = False
        if vals.get('is_important') is True and 'priority' not in vals:
            for task in self:
                if task.priority in ('0', '1'):
                    vals = dict(vals, priority='2')
                    break
        return super().write(vals)
