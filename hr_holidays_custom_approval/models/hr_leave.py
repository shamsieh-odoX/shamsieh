# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""Org-chart based two-step Time Off approval.

Flow (leave types with validation other than ``no_validation`` use ``both`` states):

* Employee **has** a usable manager (``parent_id`` with ``user_id``):
  Step 1 (``confirm``) → manager · Step 2 (``validate1``) → HR officer → ``validate``
* Employee **has no** usable manager:
  Step 1 (``confirm``) → HR officer · Step 2 (``validate1``) → company GM → ``validate``

**Manager change while pending:** step roles and ``current_approver_user_ids`` are
recomputed from the live org chart / company GM for open requests (``confirm`` /
``validate1``). Historical ``first_approver_id`` / ``second_approver_id`` stay as set
on each decision.

**Self-approval:** if the requester would be the only approver for a step, that step
is skipped / escalated to the next role. If no valid approver remains, ``UserError``.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    approval_flow = fields.Selection(
        [
            ('manager_hr', 'Manager then HR'),
            ('hr_gm', 'HR then General Manager'),
        ],
        string='Approval Flow',
        compute='_compute_approval_routing',
        store=True,
        help='Resolved from the employee org chart at compute time.',
    )
    approval_step = fields.Selection(
        [
            ('none', 'None'),
            ('step1', 'First Approval'),
            ('step2', 'Second Approval'),
            ('done', 'Approved'),
            ('refused', 'Refused'),
            ('cancelled', 'Cancelled'),
        ],
        string='Approval Step',
        compute='_compute_approval_routing',
        store=True,
    )
    step1_user_ids = fields.Many2many(
        'res.users',
        'hr_leave_custom_step1_user_rel',
        'leave_id',
        'user_id',
        string='Step 1 Approvers',
        compute='_compute_approval_routing',
        store=True,
    )
    step2_user_ids = fields.Many2many(
        'res.users',
        'hr_leave_custom_step2_user_rel',
        'leave_id',
        'user_id',
        string='Step 2 Approvers',
        compute='_compute_approval_routing',
        store=True,
    )
    current_approver_user_ids = fields.Many2many(
        'res.users',
        'hr_leave_custom_current_approver_rel',
        'leave_id',
        'user_id',
        string='Current Approvers',
        compute='_compute_approval_routing',
        store=True,
    )
    current_approver_display = fields.Char(
        string='Current Approver(s)',
        compute='_compute_current_approver_display',
    )

    # -------------------------------------------------------------------------
    # Routing helpers
    # -------------------------------------------------------------------------

    def _custom_approval_enabled(self):
        """Whether this leave uses the org-chart custom two-step flow."""
        self.ensure_one()
        return self.validation_type and self.validation_type != 'no_validation'

    def _get_org_manager_user(self):
        """Return the direct manager user from ``parent_id``, or empty users.

        Managers without a linked ``user_id`` are treated as missing (escalate).
        """
        self.ensure_one()
        manager = self.employee_id.parent_id
        if manager and manager.user_id and manager.user_id.active:
            return manager.user_id
        return self.env['res.users']

    def _get_hr_officer_users(self):
        """Active Time Off Officers/Managers in the leave company."""
        self.ensure_one()
        group = self.env.ref('hr_holidays.group_hr_holidays_user', raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        company = self.company_id or self.employee_id.company_id or self.env.company
        return group.user_ids.filtered(
            lambda u: u.active and not u.share and company in u.company_ids
        )

    def _get_gm_user(self):
        """GM user from company setting (must have a linked user)."""
        self.ensure_one()
        company = self.company_id or self.employee_id.company_id or self.env.company
        gm_employee = company.time_off_gm_id
        if gm_employee and gm_employee.user_id and gm_employee.user_id.active:
            return gm_employee.user_id
        return self.env['res.users']

    def _exclude_requester(self, users):
        """Remove the leave requester from an approver set (no self-approval)."""
        self.ensure_one()
        requester = self.employee_id.user_id
        if requester:
            return users - requester
        return users

    def _resolve_approval_users(self):
        """Compute flow + step1/step2 user sets for one leave.

        :return: dict with keys approval_flow, step1_user_ids, step2_user_ids
        :rtype: dict
        :raises UserError: when HR→GM flow is required but GM is not configured,
            or when a step has no eligible approver after self-approval exclusion
        """
        self.ensure_one()
        manager_user = self._get_org_manager_user()
        hr_users = self._get_hr_officer_users()
        gm_user = self._get_gm_user()

        if manager_user:
            flow = 'manager_hr'
            step1 = self._exclude_requester(manager_user)
            step2 = self._exclude_requester(hr_users)
            # If manager is the requester (self), escalate step1 to HR.
            if not step1:
                step1 = self._exclude_requester(hr_users)
                if gm_user:
                    flow = 'hr_gm'
                    step2 = self._exclude_requester(gm_user)
                else:
                    step2 = self._exclude_requester(hr_users)
        else:
            flow = 'hr_gm'
            step1 = self._exclude_requester(hr_users)
            if not gm_user:
                raise UserError(_(
                    'Employee %(employee)s has no manager, and no Time Off General '
                    'Manager is configured for company %(company)s. '
                    'Set it under Settings → Time Off → Time Off General Manager.',
                    employee=self.employee_id.display_name,
                    company=(self.company_id or self.env.company).display_name,
                ))
            step2 = self._exclude_requester(gm_user)
            # Requester is GM: escalate step2 to HR officers (excluding requester).
            if not step2:
                step2 = self._exclude_requester(hr_users)

        # Same person cannot do both steps when an alternative exists.
        first_user = self.first_approver_id.user_id if self.first_approver_id else self.env['res.users']
        if first_user:
            step2_alt = step2 - first_user
            if step2_alt:
                step2 = step2_alt

        if not step1:
            raise UserError(_(
                'No eligible first approver found for %(employee)s. '
                'Check the org chart, Time Off Officer assignments, and self-approval rules.',
                employee=self.employee_id.display_name,
            ))
        if not step2:
            raise UserError(_(
                'No eligible second approver found for %(employee)s. '
                'Configure HR officers and/or the Time Off General Manager.',
                employee=self.employee_id.display_name,
            ))
        return {
            'approval_flow': flow,
            'step1_user_ids': step1,
            'step2_user_ids': step2,
        }

    @api.depends(
        'employee_id',
        'employee_id.parent_id',
        'employee_id.parent_id.user_id',
        'employee_id.user_id',
        'employee_id.company_id',
        'employee_id.company_id.time_off_gm_id',
        'employee_id.company_id.time_off_gm_id.user_id',
        'company_id',
        'company_id.time_off_gm_id',
        'company_id.time_off_gm_id.user_id',
        'holiday_status_id',
        'holiday_status_id.leave_validation_type',
        'state',
    )
    def _compute_approval_routing(self):
        """Store flow, step labels, and current approver users for pending leaves.

        Does not raise: missing GM / approvers are validated on ``create`` and
        on approval actions via ``_resolve_approval_users``.
        """
        for leave in self:
            if not leave.employee_id or not leave._custom_approval_enabled():
                leave.approval_flow = False
                leave.approval_step = 'none'
                leave.step1_user_ids = False
                leave.step2_user_ids = False
                leave.current_approver_user_ids = False
                continue
            try:
                routing = leave._resolve_approval_users()
            except UserError:
                leave.approval_flow = False
                leave.approval_step = 'none'
                leave.step1_user_ids = False
                leave.step2_user_ids = False
                leave.current_approver_user_ids = False
                continue

            leave.approval_flow = routing['approval_flow']
            leave.step1_user_ids = routing['step1_user_ids']
            leave.step2_user_ids = routing['step2_user_ids']

            if leave.state == 'confirm':
                leave.approval_step = 'step1'
                leave.current_approver_user_ids = routing['step1_user_ids']
            elif leave.state == 'validate1':
                leave.approval_step = 'step2'
                leave.current_approver_user_ids = routing['step2_user_ids']
            elif leave.state == 'validate':
                leave.approval_step = 'done'
                leave.current_approver_user_ids = False
            elif leave.state == 'refuse':
                leave.approval_step = 'refused'
                leave.current_approver_user_ids = False
            elif leave.state == 'cancel':
                leave.approval_step = 'cancelled'
                leave.current_approver_user_ids = False
            else:
                leave.approval_step = 'none'
                leave.current_approver_user_ids = False

    @api.depends('current_approver_user_ids')
    def _compute_current_approver_display(self):
        for leave in self:
            leave.current_approver_display = ', '.join(
                leave.current_approver_user_ids.mapped('name')
            ) if leave.current_approver_user_ids else False

    def _is_current_custom_approver(self):
        """True when the current user is in ``current_approver_user_ids``."""
        self.ensure_one()
        return self.env.user in self.current_approver_user_ids

    def _assert_custom_approver(self, action_label):
        """Raise if the user is not the current-step approver (or superuser)."""
        if self.env.is_superuser():
            return
        for leave in self:
            if not leave._custom_approval_enabled():
                continue
            if leave.state not in ('confirm', 'validate1'):
                continue
            if not leave._is_current_custom_approver():
                raise AccessError(_(
                    'You are not allowed to %(action)s this time off request. '
                    'Current approver(s): %(approvers)s.',
                    action=action_label,
                    approvers=leave.current_approver_display or _('(none)'),
                ))

    # -------------------------------------------------------------------------
    # Create / write guards
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Validate routing exists when creating a leave that needs approval."""
        leaves = super().create(vals_list)
        for leave in leaves.filtered(lambda l: l._custom_approval_enabled()):
            # Forces UserError if GM missing / no approvers.
            leave._resolve_approval_users()
        leaves.filtered(lambda l: l._custom_approval_enabled())._compute_approval_routing()
        return leaves

    # -------------------------------------------------------------------------
    # Button visibility (override core computes)
    # -------------------------------------------------------------------------

    @api.depends(
        'state', 'employee_id', 'department_id',
        'current_approver_user_ids', 'approval_flow', 'validation_type',
    )
    @api.depends_context('uid')
    def _compute_can_approve(self):
        """First-step Approve: only current step-1 approvers for custom flow."""
        super()._compute_can_approve()
        for holiday in self:
            if not holiday._custom_approval_enabled():
                continue
            if holiday.state != 'confirm':
                holiday.can_approve = False
                continue
            holiday.can_approve = holiday._is_current_custom_approver()

    @api.depends(
        'state', 'employee_id', 'department_id',
        'current_approver_user_ids', 'approval_flow', 'validation_type',
    )
    @api.depends_context('uid')
    def _compute_can_validate(self):
        """Second-step Validate: only current step-2 approvers for custom flow."""
        super()._compute_can_validate()
        for holiday in self:
            if not holiday._custom_approval_enabled():
                continue
            if holiday.state != 'validate1':
                # Block officers from single-shot validate at confirm.
                holiday.can_validate = False
                continue
            holiday.can_validate = holiday._is_current_custom_approver()

    @api.depends(
        'state', 'employee_id', 'department_id',
        'current_approver_user_ids', 'approval_flow', 'validation_type',
    )
    @api.depends_context('uid')
    def _compute_can_refuse(self):
        """Refuse allowed for the current-step approver only."""
        super()._compute_can_refuse()
        for holiday in self:
            if not holiday._custom_approval_enabled():
                continue
            if holiday.state not in ('confirm', 'validate1'):
                holiday.can_refuse = False
                continue
            holiday.can_refuse = holiday._is_current_custom_approver()

    def _get_next_states_by_state(self):
        """Restrict transitions to the org-chart current approver.

        Core officers could otherwise skip steps via ``_check_approval_update``.
        """
        state_result = super()._get_next_states_by_state()
        if not self._custom_approval_enabled() or self.env.is_superuser():
            return state_result
        if not self._is_current_custom_approver():
            # Strip approval transitions for non-current users (keep cancel for own leave).
            for source in list(state_result):
                state_result[source] -= {'validate', 'validate1', 'refuse', 'confirm'}
            return state_result

        # Current approver: only the transition matching this step.
        cleaned = {k: set() for k in state_result}
        if self.state == 'confirm':
            cleaned['confirm'] = {'validate1', 'refuse'}
        elif self.state == 'validate1':
            cleaned['validate1'] = {'validate', 'refuse'}
        # Preserve cancel options from core for the requester.
        user_employees = self.env.user.employee_ids
        if self.employee_id in user_employees:
            for src in ('validate1', 'validate', 'refuse'):
                if 'cancel' in state_result.get(src, set()):
                    cleaned[src].add('cancel')
        return cleaned

    def _check_approval_update(self, state, raise_if_not_possible=True):
        """Enforce custom current-approver rules after core checks."""
        result = super()._check_approval_update(state, raise_if_not_possible=raise_if_not_possible)
        if not result:
            return result
        if self.env.is_superuser() or state == 'cancel':
            return result
        for holiday in self:
            if not holiday._custom_approval_enabled():
                continue
            if state in ('validate1', 'validate', 'refuse') and holiday.state in ('confirm', 'validate1'):
                if not holiday._is_current_custom_approver():
                    if raise_if_not_possible:
                        raise AccessError(_(
                            'Only the current approver can move this request to "%(state)s". '
                            'Current approver(s): %(approvers)s.',
                            state=state,
                            approvers=holiday.current_approver_display or _('(none)'),
                        ))
                    return False
            # Prevent skipping: validate from confirm is never allowed in custom flow.
            if state == 'validate' and holiday.state == 'confirm':
                if raise_if_not_possible:
                    raise UserError(_(
                        'This time off requires two approval steps. '
                        'Approve first, then the second approver can validate.'
                    ))
                return False
        return True

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_approve(self, check_state=True):
        """Approve step 1 (→ validate1) or step 2 (→ validate) for current approver."""
        custom = self.filtered(lambda l: l._custom_approval_enabled())
        other = self - custom
        if custom:
            custom._assert_custom_approver(_('approve'))
            # Refresh routing (manager may have changed).
            custom._compute_approval_routing()
            custom._assert_custom_approver(_('approve'))
            leave_to_approve = custom.filtered(lambda l: l.state == 'confirm')
            leave_to_validate = custom.filtered(lambda l: l.state == 'validate1')
            current_employee = self.env.user.employee_id
            if leave_to_approve:
                leave_to_approve.write({
                    'state': 'validate1',
                    'first_approver_id': current_employee.id,
                })
            if leave_to_validate:
                leave_to_validate._action_validate(check_state=False)
            if not self.env.context.get('leave_fast_create'):
                custom.activity_update()
                for leave in leave_to_approve:
                    leave.message_post(body=_(
                        'First approval given by %(user)s. Waiting for: %(next)s.',
                        user=self.env.user.display_name,
                        next=leave.current_approver_display or _('second approver'),
                    ))
        result = True
        if other:
            result = super(HrLeave, other).action_approve(check_state=check_state)
        return result

    def _action_validate(self, check_state=True):
        """Validate (final step); assert current approver on custom leaves."""
        custom = self.filtered(lambda l: l._custom_approval_enabled())
        if custom:
            if check_state:
                custom._assert_custom_approver(_('validate'))
            # Recompute then assert again after possible org change.
            custom._compute_approval_routing()
            custom._assert_custom_approver(_('validate'))
            # Only validate from validate1 in custom flow.
            bad = custom.filtered(lambda l: l.state != 'validate1')
            if bad and check_state:
                raise UserError(_(
                    'Custom approval leaves must be in Second Approval before validation.'
                ))
        result = super()._action_validate(check_state=check_state)
        for leave in custom.filtered(lambda l: l.state == 'validate'):
            leave.message_post(body=_(
                'Time off fully approved by %(user)s.',
                user=self.env.user.display_name,
            ))
            if leave.employee_id.user_id:
                leave.message_post(
                    body=_(
                        'Your %(leave_type)s from %(date_from)s has been approved.',
                        leave_type=leave.holiday_status_id.display_name,
                        date_from=leave.request_date_from,
                    ),
                    partner_ids=leave.employee_id.user_id.partner_id.ids,
                )
        return result

    def action_refuse(self):
        """Refuse at the current step; notify the employee."""
        custom = self.filtered(lambda l: l._custom_approval_enabled())
        if custom:
            custom._assert_custom_approver(_('refuse'))
            custom._compute_approval_routing()
            custom._assert_custom_approver(_('refuse'))
        result = super().action_refuse()
        for leave in custom.filtered(lambda l: l.state == 'refuse'):
            body = _(
                'Time off refused by %(user)s.',
                user=self.env.user.display_name,
            )
            leave.message_post(body=body)
            if leave.employee_id.user_id:
                leave.message_post(
                    body=_(
                        'Your %(leave_type)s from %(date_from)s has been refused.',
                        leave_type=leave.holiday_status_id.display_name,
                        date_from=leave.request_date_from,
                    ),
                    partner_ids=leave.employee_id.user_id.partner_id.ids,
                )
        return result

    def _get_responsible_for_approval(self):
        """Point activities at the current custom approver user(s)."""
        self.ensure_one()
        if self._custom_approval_enabled() and self.state in ('confirm', 'validate1'):
            # Ensure routing is up to date before scheduling activities.
            if not self.current_approver_user_ids:
                self._compute_approval_routing()
            return self.current_approver_user_ids
        return super()._get_responsible_for_approval()
