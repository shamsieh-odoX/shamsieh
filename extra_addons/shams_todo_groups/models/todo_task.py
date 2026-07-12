from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ShamsTodoTask(models.Model):
    _name = 'shams.todo.task'
    _description = 'To-Do Task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date asc, priority desc, id desc'

    name = fields.Char(required=True, tracking=True)
    description = fields.Html(tracking=True)
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
    priority = fields.Selection(
        selection=[
            ('low', 'Low'),
            ('normal', 'Normal'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        string='Priority',
        default='normal',
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
        for vals in vals_list:
            if not vals.get('assigned_user_id'):
                vals['assigned_user_id'] = user.id
            if not vals.get('created_by_id'):
                vals['created_by_id'] = user.id
            if vals.get('status') == 'done' and not vals.get('completed_date'):
                vals['completed_date'] = fields.Datetime.now()
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
        return super().write(vals)
