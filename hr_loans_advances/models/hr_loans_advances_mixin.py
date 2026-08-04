# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class HrLoansAdvancesApprovalMixin(models.AbstractModel):
    """Shared manager → HR approval workflow for advances and loans."""

    _name = 'hr.loans.advances.approval.mixin'
    _description = 'Loans and Advances Approval Mixin'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'hr.approval.chain.mixin']

    employee_id = fields.Many2one(
        'hr.employee',
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
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    current_approver_id = fields.Many2one(
        'res.users',
        string='Current Approver',
        compute='_compute_current_approver_id',
        store=True,
    )
    approval_line_count = fields.Integer(compute='_compute_approval_line_count')
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
        is_hr_officer = user.has_group('hr_loans_advances.group_loans_advances_hr_officer')
        for record in self:
            is_owner = record.employee_id.user_id == user
            active_line = record._get_active_approval_line()
            can_approve = bool(active_line) and record._can_user_approve_line(active_line)
            record.can_submit_request = (is_owner or is_hr_officer) and record.state == 'draft'
            record.can_approve_request = can_approve
            record.can_refuse_request = can_approve
            record.can_cancel_request = (
                (is_owner or is_hr_officer)
                and record.state in ('draft', 'submitted', 'manager_approved')
            )
            record.can_reset_request = (
                (is_owner or is_hr_officer) and record.state in ('cancel', 'refused')
            )

    def _approval_hr_group_xmlid(self):
        return 'hr.group_hr_user'

    def _build_manager_hr_approval_chain(self, employee):
        """Two-step chain: department manager then HR (no upper manager)."""
        service = self._get_approval_chain_service()
        employee = employee.sudo()
        chain = []
        dept_manager = employee.parent_id or employee.department_id.manager_id
        if dept_manager and dept_manager.user_id:
            chain.append(('dept_manager', dept_manager.user_id))
        hr_user = service.get_hr_responsible(
            employee,
            hr_group_xmlid=self._approval_hr_group_xmlid(),
        )
        if hr_user:
            chain.append(('hr', hr_user))
        return service._sanitize_chain(chain)

    def _schedule_approval_activity(self, line):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        request = self.sudo()
        request.activity_schedule(
            activity_type_id=activity_type.id,
            user_id=line.approver_id.id,
            summary=_('Approval required'),
            note=_('%(reference)s requires your approval.', reference=request.display_name),
        )

    def _clear_approval_activities(self):
        self.sudo().activity_ids.unlink()

    def _on_approval_refused(self, line, reason):
        self.sudo().message_post(
            body=_('Request refused by %(user)s: %(reason)s', user=self.env.user.name, reason=reason),
            subtype_xmlid='mail.mt_comment',
        )

    def _submit_for_approval(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft requests can be submitted.'))
        if not self.employee_id:
            raise UserError(_('An employee must be set before submitting.'))
        chain = self._resolve_approval_chain(
            self.employee_id,
            chain_builder=self._build_manager_hr_approval_chain,
            hr_group_xmlid=self._approval_hr_group_xmlid(),
        )
        if not chain:
            raise UserError(_('No approval chain could be resolved for this employee.'))
        if chain[-1][0] != 'hr':
            raise UserError(_(
                'No HR officer is configured for final approval. '
                'Assign at least one user to the HR Officer group.'
            ))
        self._unlink_approval_lines()
        self._create_approval_lines_from_chain(chain)
        self.sudo().write({'state': 'submitted'})
        first_line = self._get_active_approval_line()
        if first_line:
            self._schedule_approval_activity(first_line)
        self.sudo().message_post(body=_('Request submitted for approval.'))

    def action_cancel(self):
        for record in self:
            if record.state in ('hr_approved', 'repaid', 'done'):
                raise UserError(_('Approved or completed requests cannot be cancelled.'))
            record._clear_approval_activities()
            record._unlink_approval_lines()
            record.state = 'cancel'
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state not in ('cancel', 'refused'):
                raise UserError(_('Only cancelled or refused requests can be reset to draft.'))
            record._unlink_approval_lines()
            record.state = 'draft'
        return True

    def action_approve(self):
        return self.action_approve_current()

    def action_refuse(self):
        return self.action_open_refuse_wizard()

    def _protected_write_fields(self):
        return set()

    def write(self, vals):
        protected = self._protected_write_fields()
        if not self.env.su and protected.intersection(vals):
            for record in self:
                if record.state != 'draft' and not self.env.user.has_group(
                    'hr_loans_advances.group_loans_advances_hr_officer'
                ):
                    raise AccessError(_('Only draft requests can be edited.'))
        return super().write(vals)
