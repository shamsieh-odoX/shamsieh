from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _m2m_ids_from_commands(commands):
    """Extract user ids from typical Many2many create/write commands."""
    ids = set()
    for cmd in commands or []:
        if not cmd:
            continue
        if cmd[0] == 4:
            ids.add(cmd[1])
        elif cmd[0] == 6:
            ids.update(cmd[2] or [])
        elif cmd[0] == 5:
            ids.clear()
    return ids


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
            member_commands = list(vals.get('member_ids') or [])
            manager_commands = list(vals.get('manager_ids') or [])

            member_ids = _m2m_ids_from_commands(member_commands)
            manager_ids = _m2m_ids_from_commands(manager_commands)

            # Creator must be able to manage the group they create.
            if user.id not in manager_ids:
                manager_commands.append((4, user.id))
                manager_ids.add(user.id)
                vals['manager_ids'] = manager_commands

            # Managers must also be members (constraint + record-rule read).
            missing_members = (manager_ids | {user.id}) - member_ids
            for user_id in missing_members:
                member_commands.append((4, user_id))
            if missing_members or user.id not in member_ids:
                vals['member_ids'] = member_commands
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if 'manager_ids' in vals:
            for group in self:
                missing = group.manager_ids - group.member_ids
                if missing:
                    super(ShamsTodoGroup, group).write({
                        'member_ids': [(4, user.id) for user in missing],
                    })
        return result

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

    @api.model
    def get_or_create_personal_list(self):
        """Ensure the current user has a personal Tasks list for smart-list quick-add."""
        user = self.env.user
        personal = self.search([
            ('name', '=', 'Tasks'),
            ('member_ids', 'in', user.id),
            ('manager_ids', 'in', user.id),
        ], limit=1)
        if personal:
            return personal
        return self.create({
            'name': 'Tasks',
            'description': _('Personal task list'),
            'member_ids': [(6, 0, [user.id])],
            'manager_ids': [(6, 0, [user.id])],
        })

    @api.model
    def create_list_from_board(self, name):
        """Create a new sidebar list (group) from the To-Do board."""
        name = (name or '').strip()
        if not name:
            raise ValidationError(_('List name is required.'))
        group = self.create({'name': name})
        return {
            'id': group.id,
            'name': group.name,
            'count': 0,
            'color': group.color,
        }

    def add_member_from_board(self, user_id):
        """Share a list with another user so tasks can be assigned to them."""
        self.ensure_one()
        user = self.env.user
        if user.id not in self.manager_ids.ids and not user.has_group(
            'shams_todo_groups.group_todo_management'
        ):
            raise ValidationError(_('Only list managers can share this list.'))
        partner_user = self.env['res.users'].browse(int(user_id)).exists()
        if not partner_user or partner_user.share:
            raise ValidationError(_('Select a valid internal user to share with.'))
        self.write({'member_ids': [(4, partner_user.id)]})
        return True

    def remove_member_from_board(self, user_id):
        """Remove a member from a shared list."""
        self.ensure_one()
        user = self.env.user
        if user.id not in self.manager_ids.ids and not user.has_group(
            'shams_todo_groups.group_todo_management'
        ):
            raise ValidationError(_('Only list managers can change list members.'))
        member_id = int(user_id)
        if member_id in self.manager_ids.ids and len(self.manager_ids) <= 1:
            raise ValidationError(_('Keep at least one manager on the list.'))
        commands = [(3, member_id)]
        if member_id in self.manager_ids.ids:
            commands = [(3, member_id)]  # member remove
            self.write({
                'manager_ids': [(3, member_id)],
                'member_ids': [(3, member_id)],
            })
        else:
            self.write({'member_ids': commands})
        return True

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
