# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HrRemoteWorkRequest(models.Model):
    _name = 'hr.remote.work.request'
    _description = 'Remote Work Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        default=lambda self: self.env.user.employee_id,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    department_id = fields.Many2one(
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )
    manager_id = fields.Many2one(
        'res.users',
        string='Manager',
        tracking=True,
        compute='_compute_manager_id',
        store=True,
        readonly=False,
    )
    request_date = fields.Date(
        string='Remote Work Date',
        required=True,
        tracking=True,
        default=fields.Date.context_today,
    )
    reason = fields.Text(
        string='Reason',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('manager_approved', 'Manager Approved'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    manager_approval_date = fields.Datetime(
        string='Manager Approval Date',
        readonly=True,
        copy=False,
    )
    hr_approval_date = fields.Datetime(
        string='HR Approval Date',
        readonly=True,
        copy=False,
    )
    refuse_reason = fields.Text(
        string='Refusal Reason',
        readonly=True,
        copy=False,
    )
    can_submit = fields.Boolean(compute='_compute_approval_permissions')
    can_manager_approve = fields.Boolean(compute='_compute_approval_permissions')
    can_hr_approve = fields.Boolean(compute='_compute_approval_permissions')
    can_refuse = fields.Boolean(compute='_compute_approval_permissions')
    can_cancel = fields.Boolean(compute='_compute_approval_permissions')

    @api.depends('state', 'employee_id', 'manager_id')
    def _compute_approval_permissions(self):
        user = self.env.user
        is_officer = user.has_group('hr_attendance.group_hr_attendance_officer')
        for request in self:
            is_requester = request.employee_id.user_id == user
            is_manager = request.manager_id == user
            request.can_submit = request.state == 'draft' and (is_requester or is_officer)
            request.can_manager_approve = request.state == 'submitted' and (is_manager or is_officer)
            request.can_hr_approve = request.state == 'manager_approved' and is_officer
            request.can_refuse = request.state in ('submitted', 'manager_approved') and (
                (request.state == 'submitted' and (is_manager or is_officer))
                or (request.state == 'manager_approved' and is_officer)
            )
            request.can_cancel = request.state in ('draft', 'submitted', 'manager_approved') and (
                is_requester or is_officer
            )

    @api.depends('employee_id', 'employee_id.leave_manager_id', 'employee_id.parent_id')
    def _compute_manager_id(self):
        for request in self:
            employee = request.employee_id
            if not employee:
                request.manager_id = False
                continue
            if employee.leave_manager_id:
                request.manager_id = employee.leave_manager_id
            elif employee.parent_id and employee.parent_id.user_id:
                request.manager_id = employee.parent_id.user_id
            else:
                request.manager_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hr.remote.work.request',
                ) or _('New')
        return super().create(vals_list)

    @api.constrains('request_date', 'state')
    def _check_request_date(self):
        today = fields.Date.context_today(self)
        for request in self:
            if not request.request_date or request.request_date >= today:
                continue
            if request.state in ('approved', 'refused', 'cancelled'):
                continue
            raise ValidationError(_(
                'Remote work requests cannot be created for past dates.'
            ))

    @api.constrains('employee_id', 'request_date', 'state')
    def _check_duplicate_request(self):
        for request in self.filtered(lambda r: r.state not in ('refused', 'cancelled')):
            duplicate = self.search([
                ('id', '!=', request.id),
                ('employee_id', '=', request.employee_id.id),
                ('request_date', '=', request.request_date),
                ('state', 'not in', ('refused', 'cancelled')),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'A remote work request already exists for %(employee)s on %(day)s.',
                    employee=request.employee_id.name,
                    day=request.request_date,
                ))

    def _check_company_feature_enabled(self):
        self.ensure_one()
        if not self.company_id.remote_work_requests_enabled:
            raise UserError(_(
                'Remote work requests are disabled for %(company)s.',
                company=self.company_id.name,
            ))

    def _check_requester(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group('hr_attendance.group_hr_attendance_officer'):
            return
        employee = self.employee_id
        if employee.user_id == user:
            return
        raise AccessError(_('You can only manage your own remote work requests.'))

    def _check_manager_approver(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group('hr_attendance.group_hr_attendance_officer'):
            return
        if self.manager_id and self.manager_id == user:
            return
        raise AccessError(_('Only the employee\'s manager can approve this step.'))

    def _check_hr_approver(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_attendance.group_hr_attendance_officer'):
            raise AccessError(_('Only an attendance officer can give the final approval.'))

    def action_submit(self):
        today = fields.Date.context_today(self)
        for request in self:
            request._check_company_feature_enabled()
            request._check_requester()
            if request.request_date < today:
                raise UserError(_('Remote work requests cannot be submitted for past dates.'))
            if not request.reason or not request.reason.strip():
                raise UserError(_('A reason is required for remote work requests.'))
            if not request.manager_id:
                raise UserError(_(
                    'No manager is configured for %(employee)s. '
                    'Set a Time Off Approver on the employee record.',
                    employee=request.employee_id.name,
                ))
            request.write({'state': 'submitted'})
            request.message_post(
                body=_('Remote work request submitted for %(day)s.', day=request.request_date),
                partner_ids=request.manager_id.partner_id.ids,
            )
        return True

    def action_manager_approve(self):
        for request in self:
            request._check_manager_approver()
            if request.state != 'submitted':
                raise UserError(_('Only submitted requests can be approved by the manager.'))
            request.write({
                'state': 'manager_approved',
                'manager_approval_date': fields.Datetime.now(),
            })
            officers = self.env.ref('hr_attendance.group_hr_attendance_officer').users
            if officers:
                request.message_post(
                    body=_('Manager approved. Pending HR approval.'),
                    partner_ids=officers.partner_id.ids,
                )
        return True

    def action_hr_approve(self):
        for request in self:
            request._check_hr_approver()
            if request.state != 'manager_approved':
                raise UserError(_('Only manager-approved requests can be approved by HR.'))
            request.write({
                'state': 'approved',
                'hr_approval_date': fields.Datetime.now(),
            })
            if request.employee_id.user_id:
                request.message_post(
                    body=_('Your remote work request for %(day)s has been approved.', day=request.request_date),
                    partner_ids=request.employee_id.user_id.partner_id.ids,
                )
        return True

    def action_cancel(self):
        for request in self:
            request._check_requester()
            if request.state in ('approved', 'refused'):
                raise UserError(_('Approved or refused requests cannot be cancelled.'))
            request.write({'state': 'cancelled'})
        return True

    def action_refuse(self):
        self.ensure_one()
        if self.state not in ('submitted', 'manager_approved'):
            raise UserError(_('Only pending requests can be refused.'))
        if self.state == 'submitted':
            self._check_manager_approver()
        else:
            self._check_hr_approver()
        return {
            'name': _('Refuse Remote Work Request'),
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_model': 'hr.remote.work.refuse.wizard',
            'view_mode': 'form',
            'context': {
                'default_request_id': self.id,
            },
        }

    def action_process_refusal(self, reason):
        self.ensure_one()
        if not reason or not reason.strip():
            raise UserError(_('A refusal reason is required.'))
        self.write({
            'state': 'refused',
            'refuse_reason': reason.strip(),
        })
        return True

    @api.model
    def _get_approved_for_employee_date(self, employee, target_date):
        if not employee or not target_date:
            return self.browse()
        if not employee.company_id.remote_work_requests_enabled:
            return self.browse()
        return self.sudo().search([
            ('employee_id', '=', employee.id),
            ('request_date', '=', target_date),
            ('state', '=', 'approved'),
        ], limit=1)
