# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HrExceptionalHoliday(models.Model):
    _name = 'hr.exceptional.holiday'
    _description = 'Exceptional Public Holiday Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'hr.approval.chain.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(string='Holiday Name', required=True, tracking=True)
    reference = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Requested By',
        required=True,
        tracking=True,
        default=lambda self: self.env.user.employee_id,
    )
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    calendar_id = fields.Many2one(
        'resource.calendar',
        string='Working Hours',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Leave empty to apply to all working schedules in the company.',
    )
    date_from = fields.Datetime(string='Start Date', required=True, tracking=True)
    date_to = fields.Datetime(string='End Date', required=True, tracking=True)
    reason = fields.Text(string='Reason', tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('manager_approved', 'Manager Approved'),
            ('upper_manager_approved', 'Upper Manager Approved'),
            ('hr_approved', 'Approved'),
            ('refused', 'Refused'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    calendar_leave_id = fields.Many2one(
        'resource.calendar.leaves',
        string='Public Holiday',
        copy=False,
        readonly=True,
    )
    approval_line_ids = fields.One2many(
        'hr.exceptional.holiday.approval.line',
        'request_id',
        string='Approval History',
        copy=False,
    )
    approval_line_count = fields.Integer(compute='_compute_approval_line_count')
    current_approver_id = fields.Many2one(
        'res.users',
        string='Current Approver',
        compute='_compute_current_approver_id',
        store=True,
    )
    can_submit_request = fields.Boolean(compute='_compute_request_permissions')
    can_approve_request = fields.Boolean(compute='_compute_request_permissions')
    can_refuse_request = fields.Boolean(compute='_compute_request_permissions')
    can_cancel_request = fields.Boolean(compute='_compute_request_permissions')
    can_reset_request = fields.Boolean(compute='_compute_request_permissions')

    @api.depends('approval_line_ids')
    def _compute_approval_line_count(self):
        for record in self:
            record.approval_line_count = len(record.approval_line_ids)

    @api.depends('approval_line_ids.state', 'approval_line_ids.approver_id')
    def _compute_current_approver_id(self):
        for record in self:
            active_line = record.sudo().approval_line_ids.filtered(
                lambda line: line.state == 'to_approve'
            )[:1]
            record.current_approver_id = active_line.approver_id

    @api.depends(
        'state',
        'employee_id',
        'employee_id.user_id',
        'approval_line_ids.state',
        'approval_line_ids.approver_id',
        'approval_line_ids.role',
    )
    def _compute_request_permissions(self):
        user = self.env.user
        is_hr_manager = user.has_group('hr_holidays.group_hr_holidays_manager')
        for record in self:
            is_owner = record.employee_id.user_id == user
            active_line = record._get_active_approval_line()
            can_approve = bool(active_line) and record._can_user_approve_line(active_line)
            record.can_submit_request = (
                (is_owner or is_hr_manager) and record.state == 'draft'
            )
            record.can_approve_request = can_approve
            record.can_refuse_request = can_approve
            record.can_cancel_request = (
                (is_owner or is_hr_manager)
                and record.state in ('draft', 'submitted', 'manager_approved', 'upper_manager_approved')
            )
            record.can_reset_request = (
                (is_owner or is_hr_manager) and record.state in ('cancel', 'refused')
            )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_to < record.date_from:
                raise ValidationError(_('The end date must be on or after the start date.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = (
                    self.env['ir.sequence'].next_by_code('hr.exceptional.holiday') or _('New')
                )
        return super().create(vals_list)

    def write(self, vals):
        protected = {'name', 'employee_id', 'company_id', 'calendar_id', 'date_from', 'date_to', 'reason'}
        if not self.env.su and protected.intersection(vals):
            for record in self:
                if record.state != 'draft' and not self.env.user.has_group(
                    'hr_holidays.group_hr_holidays_manager'
                ):
                    raise AccessError(_('Only draft requests can be edited.'))
        return super().write(vals)

    def _approval_line_model(self):
        return 'hr.exceptional.holiday.approval.line'

    def _approval_line_inverse_field(self):
        return 'request_id'

    def _approval_hr_group_xmlid(self):
        return 'hr_holidays.group_hr_holidays_manager'

    def _build_holiday_approval_chain(self, employee):
        return self._get_approval_chain_service().build_manager_hr_chain(
            employee,
            hr_group_xmlid=self._approval_hr_group_xmlid(),
        )

    def _schedule_approval_activity(self, line):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        request = self.sudo()
        request.activity_schedule(
            activity_type_id=activity_type.id,
            user_id=line.approver_id.id,
            summary=_('Exceptional holiday approval'),
            note=_('Exceptional holiday %(ref)s requires your approval.', ref=request.reference),
        )

    def _clear_approval_activities(self):
        self.sudo().activity_ids.unlink()

    def _on_approval_complete(self):
        CalendarLeave = self.env['resource.calendar.leaves'].sudo()
        for record in self:
            if record.calendar_leave_id:
                continue
            calendar_leave = CalendarLeave.create({
                'name': record.name,
                'date_from': record.date_from,
                'date_to': record.date_to,
                'calendar_id': record.calendar_id.id,
                'company_id': record.company_id.id,
                'resource_id': False,
                'time_type': 'leave',
                'exceptional_holiday_id': record.id,
            })
            record.calendar_leave_id = calendar_leave
            record.message_post(
                body=_('Public holiday created and is now active for attendance and overtime.'),
            )

    def _on_approval_refused(self, line, reason):
        self.sudo().message_post(
            body=_('Request refused by %(user)s: %(reason)s', user=self.env.user.name, reason=reason),
            subtype_xmlid='mail.mt_comment',
        )

    def _remove_calendar_leave(self):
        for record in self:
            if record.calendar_leave_id:
                record.calendar_leave_id.sudo().unlink()
                record.calendar_leave_id = False

    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft requests can be submitted.'))
            if not record.employee_id:
                raise UserError(_('A requester must be set before submitting.'))
            chain = record._resolve_approval_chain(
                record.employee_id,
                chain_builder=record._build_holiday_approval_chain,
                hr_group_xmlid=record._approval_hr_group_xmlid(),
            )
            if not chain:
                raise UserError(_('No approval chain could be resolved for this requester.'))
            if chain[-1][0] != 'hr':
                raise UserError(_(
                    'No Time Off manager is configured for final approval. '
                    'Assign at least one user to the Time Off Administrator group.'
                ))
            record._unlink_approval_lines()
            record._create_approval_lines_from_chain(chain)
            record.sudo().write({'state': 'submitted'})
            first_line = record._get_active_approval_line()
            if first_line:
                record._schedule_approval_activity(first_line)
            record.message_post(body=_('Exceptional holiday request submitted for approval.'))
        return True

    def action_cancel(self):
        for record in self:
            if record.state == 'hr_approved':
                raise UserError(_('Approved requests cannot be cancelled.'))
            record._clear_approval_activities()
            record._unlink_approval_lines()
            record._remove_calendar_leave()
            record.state = 'cancel'
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state not in ('cancel', 'refused'):
                raise UserError(_('Only cancelled or refused requests can be reset to draft.'))
            record._unlink_approval_lines()
            record._remove_calendar_leave()
            record.state = 'draft'
        return True

    def action_approve(self):
        return self.action_approve_current()

    def action_refuse(self):
        return self.action_open_refuse_wizard()

    def action_open_refuse_wizard(self):
        self.ensure_one()
        line = self.sudo()._get_active_approval_line()
        if not line:
            raise UserError(_('No pending approval step found.'))
        if not self._can_user_approve_line(line):
            raise AccessError(_('You are not allowed to refuse this request.'))
        return {
            'name': _('Refuse Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.exceptional.holiday.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_holiday_request_id': self.id,
                'default_approval_line_id': line.id,
            },
        }

    def action_view_approval_lines(self):
        self.ensure_one()
        return {
            'name': _('Approval History'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.exceptional.holiday.approval.line',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'context': {'default_request_id': self.id},
        }

    def action_view_calendar_leave(self):
        self.ensure_one()
        if not self.calendar_leave_id:
            raise UserError(_('No public holiday record is linked yet.'))
        return {
            'name': _('Public Holiday'),
            'type': 'ir.actions.act_window',
            'res_model': 'resource.calendar.leaves',
            'view_mode': 'form',
            'res_id': self.calendar_leave_id.id,
        }
