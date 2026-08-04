# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class HrApprovalChainMixin(models.AbstractModel):
    """Mixin providing generic multi-stage approval workflow helpers."""

    _name = 'hr.approval.chain.mixin'
    _description = 'Approval Chain Mixin'

    # -------------------------------------------------------------------------
    # Chain resolution (delegates to reusable service)
    # -------------------------------------------------------------------------

    def _get_approval_chain_service(self):
        return self.env['hr.approval.chain.service']

    def _resolve_approval_chain(self, employee, chain_builder=None, hr_group_xmlid=None):
        return self._get_approval_chain_service().resolve_chain(
            employee,
            chain_builder=chain_builder,
            hr_group_xmlid=hr_group_xmlid,
        )

    def _build_overtime_approval_chain(self, employee):
        """Overtime-specific chain spec; reuses the standard manager → HR resolver."""
        return self._get_approval_chain_service().build_manager_hr_chain(
            employee,
            hr_group_xmlid='hr_overtime_management.group_overtime_hr_officer',
        )

    # -------------------------------------------------------------------------
    # Approval line helpers (override _approval_* hooks in concrete models)
    # -------------------------------------------------------------------------

    def _approval_line_model(self):
        raise NotImplementedError

    def _approval_line_inverse_field(self):
        raise NotImplementedError

    def _approval_hr_group_xmlid(self):
        return 'hr_overtime_management.group_overtime_hr_officer'

    def _approval_state_after_role(self, role):
        return {
            'dept_manager': 'manager_approved',
            'upper_manager': 'upper_manager_approved',
            'hr': 'hr_approved',
        }.get(role)

    def _approval_submitted_state(self):
        return 'submitted'

    def _approval_refused_state(self):
        return 'refused'

    def _approval_final_state(self):
        return 'hr_approved'

    def _can_user_approve_line(self, line):
        self.ensure_one()
        user = self.env.user
        if line.role == 'hr':
            return user.has_group(self._approval_hr_group_xmlid())
        return line.approver_id == user

    def _approval_line_env(self):
        """Sudo env for workflow-managed lines; ACL stays on the request actions."""
        return self.env[self._approval_line_model()].sudo()

    def _create_approval_lines_from_chain(self, chain):
        self.ensure_one()
        ApprovalLine = self._approval_line_env()
        inverse_field = self._approval_line_inverse_field()
        lines_vals = []
        for seq, (role, approver) in enumerate(chain, start=1):
            state = 'to_approve' if seq == 1 else 'pending'
            lines_vals.append({
                inverse_field: self.id,
                'sequence': seq * 10,
                'role': role,
                'approver_id': approver.id,
                'state': state,
            })
        return ApprovalLine.create(lines_vals)

    def _unlink_approval_lines(self):
        self.ensure_one()
        self._approval_line_env().search([
            (self._approval_line_inverse_field(), '=', self.id),
        ]).unlink()

    def _get_active_approval_line(self):
        self.ensure_one()
        return self.sudo().approval_line_ids.filtered(lambda l: l.state == 'to_approve')[:1]

    def _activate_next_approval_line(self, current_line):
        self.ensure_one()
        next_line = self.sudo().approval_line_ids.filtered(
            lambda l: l.sequence > current_line.sequence and l.state == 'pending'
        ).sorted('sequence')[:1]
        if next_line:
            next_line.sudo().write({'state': 'to_approve'})
            self._schedule_approval_activity(next_line)
        return next_line

    def _schedule_approval_activity(self, line):
        """Override in concrete model to schedule mail activities."""
        return

    def _clear_approval_activities(self):
        """Override in concrete model to remove pending activities."""
        return

    def _on_approval_complete(self):
        """Hook called when the final approval stage is approved."""
        return

    def _on_approval_refused(self, line, reason):
        """Hook called when any stage is refused."""
        return

    def action_approve_current(self):
        for record in self:
            line = record._get_active_approval_line()
            if not line:
                raise UserError(_('No pending approval step found.'))
            if not record._can_user_approve_line(line):
                raise AccessError(_('You are not allowed to approve this request.'))
            record._process_approval(line)
        return True

    def _process_approval(self, line):
        self.ensure_one()
        line.sudo().write({
            'state': 'approved',
            'decision_date': fields.Datetime.now(),
        })
        new_state = self._approval_state_after_role(line.role)
        request_vals = {}
        if new_state:
            request_vals['state'] = new_state
        self._clear_approval_activities()
        if line.role == 'hr':
            request_vals['state'] = self._approval_final_state()
            if request_vals:
                self.sudo().write(request_vals)
            self._on_approval_complete()
        else:
            if request_vals:
                self.sudo().write(request_vals)
            next_line = self._activate_next_approval_line(line)
            if not next_line:
                has_hr_line = any(l.role == 'hr' for l in self.sudo().approval_line_ids)
                if not has_hr_line:
                    raise UserError(_(
                        'Approval chain is incomplete: no HR stage found. '
                        'Cancel this request, ensure an HR officer is assigned to the '
                        '"Officer: Overtime HR Approval" group, then re-submit.'
                    ))

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
            'res_model': 'hr.overtime.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_overtime_request_id': self.id,
                'default_approval_line_id': line.id,
            },
        }

    def action_process_refusal(self, line, reason):
        self.ensure_one()
        if not self._can_user_approve_line(line):
            raise AccessError(_('You are not allowed to refuse this request.'))
        line.sudo().write({
            'state': 'refused',
            'decision_date': fields.Datetime.now(),
            'comment': reason,
        })
        self.sudo().write({'state': self._approval_refused_state()})
        self._clear_approval_activities()
        self._on_approval_refused(line, reason)
