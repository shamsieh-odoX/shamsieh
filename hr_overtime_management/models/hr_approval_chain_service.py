# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class HrApprovalChainService(models.AbstractModel):
    """Standalone, reusable approval-chain resolution engine."""

    _name = 'hr.approval.chain.service'
    _description = 'Approval Chain Resolution Service'

    @api.model
    def resolve_chain(self, employee, chain_builder=None, hr_group_xmlid=None):
        """Return an ordered list of (role, approver_user) tuples.

        :param employee: hr.employee record
        :param chain_builder: callable(employee) -> list of (role, user) tuples.
            When omitted, the standard manager → upper manager → HR chain is used.
        :param hr_group_xmlid: XML id of the HR officer group for the final stage.
        """
        employee = employee.sudo()
        if chain_builder:
            chain = chain_builder(employee)
        else:
            chain = self.build_manager_hr_chain(employee, hr_group_xmlid=hr_group_xmlid)
        return self._sanitize_chain(chain)

    @api.model
    def build_manager_hr_chain(self, employee, hr_group_xmlid=None):
        """Standard chain mirroring hr_holidays manager / upper manager / HR pattern."""
        chain = []
        dept_manager = employee.parent_id or employee.department_id.manager_id
        if dept_manager:
            dept_user = dept_manager.user_id
            if dept_user:
                chain.append(('dept_manager', dept_user))
            upper_manager = dept_manager.parent_id
            if upper_manager and upper_manager != dept_manager:
                upper_user = upper_manager.user_id
                if upper_user:
                    chain.append(('upper_manager', upper_user))
        hr_officer = self.get_hr_responsible(employee, hr_group_xmlid=hr_group_xmlid)
        if hr_officer:
            chain.append(('hr', hr_officer))
        return chain

    @api.model
    def get_hr_responsible(self, employee, hr_group_xmlid=None):
        """Return a representative HR user; any member of the HR group may act."""
        xmlid = hr_group_xmlid or 'hr_overtime_management.group_overtime_hr_officer'
        hr_group = self.env.ref(xmlid, raise_if_not_found=False)
        employee_company_id = employee.sudo().company_id.id
        if hr_group:
            hr_users = hr_group.sudo().all_user_ids
            if hr_users:
                for user in hr_users:
                    # Compare ids via sudo so submitters are not forced to read
                    # every company on HR users (Odoo "company rule employee").
                    user_company_ids = user.sudo().company_ids.ids
                    if not employee_company_id or employee_company_id in user_company_ids:
                        return user
                return hr_users[0]
        fallback_group = self.env.ref('hr.group_hr_user', raise_if_not_found=False)
        if fallback_group and fallback_group.sudo().all_user_ids:
            return fallback_group.sudo().all_user_ids[0]
        return self.env.ref('base.user_admin', raise_if_not_found=False)

    @api.model
    def _sanitize_chain(self, chain):
        """Drop empty entries and deduplicate consecutive identical approvers.

        The HR stage is never removed, even when the HR officer is the same
        person as a manager — the workflow still requires a distinct HR step.
        """
        result = []
        previous_user = self.env['res.users']
        for role, user in chain:
            if not user:
                continue
            if role == 'hr':
                result.append((role, user))
                previous_user = user
                continue
            if user == previous_user:
                continue
            result.append((role, user))
            previous_user = user
        return result
