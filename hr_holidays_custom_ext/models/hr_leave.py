# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    approval_trail_ids = fields.One2many(
        'hr.leave.approval.trail',
        'leave_id',
        string='Approval Trail',
        copy=False,
    )
    approval_trail_count = fields.Integer(compute='_compute_approval_trail_count')
    refuse_reason = fields.Text(string='Refusal Reason', copy=False, readonly=True)

    @api.depends('approval_trail_ids')
    def _compute_approval_trail_count(self):
        for leave in self:
            leave.approval_trail_count = len(leave.approval_trail_ids)

    def _is_leave_requesting_user(self):
        """True when the current user is the employee who requested this leave."""
        self.ensure_one()
        user = self.env.user
        if self.user_id and self.user_id == user:
            return True
        if self.employee_id and self.employee_id.user_id == user:
            return True
        if self.employee_id and self.employee_id in user.employee_ids:
            return True
        return False

    def _assert_not_self_approval(self, action_label):
        for leave in self:
            if leave._is_leave_requesting_user():
                raise UserError(_(
                    'You cannot %(action)s your own time off request. '
                    'Only your manager / general manager can approve or refuse it.',
                    action=action_label,
                ))

    def _trail_sequence(self, stage):
        order = {
            'submitted': 10,
            'first_approval': 20,
            'second_approval': 30,
            'refused': 40,
            'cancelled': 50,
        }
        return order.get(stage, 99)

    def _has_trail_stage(self, stage):
        self.ensure_one()
        return bool(self.approval_trail_ids.filtered(lambda line: line.stage == stage))

    def _create_approval_trail(self, stage, approver=None, trail_state=None, comment=None):
        self.ensure_one()
        if self._has_trail_stage(stage):
            return self.env['hr.leave.approval.trail']
        if trail_state is None:
            trail_state = stage if stage in ('submitted', 'refused', 'cancelled') else 'approved'
        return self.env['hr.leave.approval.trail'].sudo().create({
            'leave_id': self.id,
            'sequence': self._trail_sequence(stage),
            'stage': stage,
            'approver_id': approver.id if approver else False,
            'state': trail_state,
            'decision_date': fields.Datetime.now(),
            'comment': comment,
        })

    def _log_submitted_trail(self):
        for leave in self:
            if leave._has_trail_stage('submitted'):
                continue
            if leave.state in ('confirm', 'validate', 'validate1'):
                leave._create_approval_trail(
                    'submitted',
                    approver=leave.employee_id,
                    trail_state='submitted',
                )

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._log_submitted_trail()
        return leaves

    def _is_leave_manager(self):
        self.ensure_one()
        return bool(
            self.employee_id.leave_manager_id
            and self.employee_id.leave_manager_id == self.env.user
        )

    def _is_time_off_officer(self):
        return self.env.user.has_group('hr_holidays.group_hr_holidays_user')

    def _get_next_states_by_state(self):
        """Employees may only cancel; two-step leaves follow manager then officer/GM."""
        state_result = super()._get_next_states_by_state()
        if self._is_leave_requesting_user():
            for source in list(state_result):
                state_result[source] -= {'validate', 'validate1', 'refuse', 'confirm'}
            state_result['validate1'].add('cancel')
            state_result['validate'].add('cancel')
            state_result['refuse'].add('cancel')
            return state_result

        # Strict two-step: Approver = first only; Officer/GM = second only.
        # Prevents Time Off Admins who are also the manager from skipping GM approval.
        if self.validation_type == 'both' and not self.env.is_superuser():
            is_manager = self._is_leave_manager()
            is_officer = self._is_time_off_officer()
            for source in list(state_result):
                state_result[source] -= {'validate', 'validate1', 'refuse'}
            if is_manager:
                state_result['confirm'].update({'validate1', 'refuse'})
            if is_officer and not is_manager:
                state_result['validate1'].update({'validate', 'refuse'})
                state_result['validate'].add('refuse')
                state_result['refuse'].add('validate')
        return state_result

    def _check_approval_update(self, state, raise_if_not_possible=True):
        if state in ('validate', 'validate1', 'refuse') and not self.env.is_superuser():
            for holiday in self:
                if holiday._is_leave_requesting_user():
                    if raise_if_not_possible:
                        raise UserError(_(
                            'You cannot approve or refuse your own time off request. '
                            'Wait for your manager / general manager.'
                        ))
                    return False
                if holiday.validation_type == 'both':
                    is_manager = holiday._is_leave_manager()
                    is_officer = holiday._is_time_off_officer()
                    if state == 'validate1' and not is_manager:
                        if raise_if_not_possible:
                            raise UserError(_(
                                'Only the employee\'s Time Off Approver (manager) '
                                'can give the first approval.'
                            ))
                        return False
                    if state == 'validate' and holiday.state == 'confirm':
                        if raise_if_not_possible:
                            raise UserError(_(
                                'This time off type needs two approvals. '
                                'The manager must approve first, then the General Manager / Time Off Officer.'
                            ))
                        return False
                    if state == 'validate' and holiday.state == 'validate1' and is_manager:
                        if raise_if_not_possible:
                            raise UserError(_(
                                'You already did the first approval. '
                                'The General Manager / Time Off Officer must do the second approval.'
                            ))
                        return False
                    if state == 'validate' and holiday.state == 'validate1' and not is_officer:
                        if raise_if_not_possible:
                            raise UserError(_(
                                'Only a Time Off Officer / General Manager can give the second approval.'
                            ))
                        return False
        return super()._check_approval_update(state, raise_if_not_possible=raise_if_not_possible)

    def action_approve(self, check_state=True):
        self._assert_not_self_approval(_('approve'))
        # Force first-step-only when the Time Off Approver also has officer rights.
        both_confirm = self.filtered(
            lambda leave: leave.validation_type == 'both'
            and leave.state == 'confirm'
            and leave._is_leave_manager()
        )
        other = self - both_confirm
        pre_states = {leave.id: leave.state for leave in self}
        if both_confirm:
            both_confirm.write({
                'state': 'validate1',
                'first_approver_id': self.env.user.employee_id.id,
            })
            for leave in both_confirm:
                leave._create_approval_trail(
                    'first_approval',
                    approver=self.env.user.employee_id,
                    trail_state='approved',
                )
            if not self.env.context.get('leave_fast_create'):
                both_confirm.activity_update()
        result = True
        if other:
            result = super(HrLeave, other).action_approve(check_state=check_state)
            current_employee = self.env.user.employee_id
            for leave in other:
                if pre_states[leave.id] == 'confirm' and leave.state == 'validate1':
                    leave._create_approval_trail(
                        'first_approval',
                        approver=current_employee,
                        trail_state='approved',
                    )
        return result

    def _action_validate(self, check_state=True):
        self._assert_not_self_approval(_('validate'))
        pre_states = {leave.id: leave.state for leave in self}
        result = super()._action_validate(check_state=check_state)
        current_employee = self.env.user.employee_id
        for leave in self:
            if leave.state != 'validate':
                continue
            if leave.validation_type == 'both' and pre_states[leave.id] == 'validate1':
                leave._create_approval_trail(
                    'second_approval',
                    approver=current_employee,
                    trail_state='approved',
                )
            elif not leave._has_trail_stage('first_approval'):
                leave._create_approval_trail(
                    'first_approval',
                    approver=current_employee,
                    trail_state='approved',
                )
        return result

    def action_refuse(self):
        if self.env.context.get('leave_skip_refuse_wizard'):
            self._assert_not_self_approval(_('refuse'))
            return super().action_refuse()
        self.ensure_one()
        self._assert_not_self_approval(_('refuse'))
        if any(holiday.state not in ['confirm', 'validate', 'validate1'] for holiday in self):
            raise UserError(_('Time off request must be confirmed or validated in order to refuse it.'))
        if len(self) > 1:
            raise UserError(_('Please refuse one time off request at a time.'))
        return {
            'name': _('Refuse Time Off'),
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_model': 'hr.leave.refuse.wizard',
            'view_mode': 'form',
            'context': {
                'default_leave_id': self.id,
            },
        }

    def action_process_refusal(self, reason):
        self.ensure_one()
        self._assert_not_self_approval(_('refuse'))
        if not reason or not reason.strip():
            raise UserError(_('A refusal reason is required.'))
        reason = reason.strip()
        self.write({'refuse_reason': reason})
        current_employee = self.env.user.employee_id
        result = super(HrLeave, self.with_context(leave_skip_refuse_wizard=True)).action_refuse()
        self._create_approval_trail(
            'refused',
            approver=current_employee,
            trail_state='refused',
            comment=reason,
        )
        return result

    def _force_cancel(self, reason=None, msg_subtype='mail.mt_comment', notify_responsibles=True):
        current_employee = self.env.user.employee_id
        super()._force_cancel(
            reason=reason,
            msg_subtype=msg_subtype,
            notify_responsibles=notify_responsibles,
        )
        for leave in self:
            leave._create_approval_trail(
                'cancelled',
                approver=current_employee,
                trail_state='cancelled',
                comment=reason,
            )

    def action_print_approval_report(self):
        return self.env.ref(
            'hr_holidays_custom_ext.action_report_hr_leave_approval'
        ).report_action(self)
