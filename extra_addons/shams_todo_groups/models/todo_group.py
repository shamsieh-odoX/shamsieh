from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ShamsTodoGroup(models.Model):
    _name = 'shams.todo.group'
    _description = 'To-Do Group'
    _order = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    member_ids = fields.Many2many(
        'res.users',
        'shams_todo_group_member_rel',
        'group_id',
        'user_id',
        string='Members',
    )
    manager_ids = fields.Many2many(
        'res.users',
        'shams_todo_group_manager_rel',
        'group_id',
        'user_id',
        string='Managers',
    )
    task_ids = fields.One2many(
        'shams.todo.task',
        'group_id',
        string='Tasks',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    member_count = fields.Integer(compute='_compute_counts')
    manager_count = fields.Integer(compute='_compute_counts')
    task_count = fields.Integer(compute='_compute_counts')
    color = fields.Integer(string='Color', default=0)

    @api.depends('member_ids', 'manager_ids', 'task_ids')
    def _compute_counts(self):
        for group in self:
            group.member_count = len(group.member_ids)
            group.manager_count = len(group.manager_ids)
            group.task_count = len(group.task_ids)

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        for vals in vals_list:
            member_commands = vals.get('member_ids') or []
            member_ids = {
                cmd[1]
                for cmd in member_commands
                if cmd[0] == 4
            }
            member_ids.update(
                user_id
                for cmd in member_commands
                if cmd[0] == 6
                for user_id in cmd[2]
            )
            if user.id not in member_ids:
                member_commands.append((4, user.id))
                vals['member_ids'] = member_commands
        return super().create(vals_list)

    def action_view_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'shams.todo.task',
            'view_mode': 'list,kanban,calendar,form',
            'domain': [('group_id', '=', self.id)],
            'context': {'default_group_id': self.id},
        }

    @api.constrains('manager_ids', 'member_ids')
    def _check_managers_are_members(self):
        for group in self:
            non_members = group.manager_ids - group.member_ids
            if non_members:
                raise ValidationError(_(
                    'Every manager must also be a member of the group "%(group)s". '
                    'The following users are managers but not members: %(users)s',
                    group=group.name,
                    users=', '.join(non_members.mapped('name')),
                ))
