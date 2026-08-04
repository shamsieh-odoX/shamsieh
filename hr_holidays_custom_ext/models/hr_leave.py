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

    def action_approve(self, check_state=True):
        pre_states = {leave.id: leave.state for leave in self}
        result = super().action_approve(check_state=check_state)
        current_employee = self.env.user.employee_id
        for leave in self:
            if pre_states[leave.id] == 'confirm' and leave.state == 'validate1':
                leave._create_approval_trail(
                    'first_approval',
                    approver=current_employee,
                    trail_state='approved',
                )
        return result

    def _action_validate(self, check_state=True):
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
            return super().action_refuse()
        self.ensure_one()
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
