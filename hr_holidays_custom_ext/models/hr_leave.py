# Part of Odoo. See LICENSE file for full copyright and licensing details.

from calendar import monthrange
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


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
    can_second_approve = fields.Boolean(
        compute='_compute_can_second_approve',
        export_string_translation=False,
    )
    approval_flow = fields.Selection(
        [
            ('manager_hr', 'Manager then HR'),
            ('hr_gm', 'HR then General Manager'),
        ],
        string='Approval Flow',
        compute='_compute_org_approval_display',
        help='Resolved from the employee org chart for two-step leave types.',
    )
    first_approver_display_id = fields.Many2one(
        'hr.employee',
        string='First Approval',
        compute='_compute_org_approval_display',
        help='Who did (or should do) the first approval for this employee.',
    )
    second_approver_display_id = fields.Many2one(
        'hr.employee',
        string='Second Approval',
        compute='_compute_org_approval_display',
        help='Who did (or should do) the second approval for this employee.',
    )
    departure_reason = fields.Text(
        string='Departure Reason',
        copy=False,
        help='Special reason for the Article 11 hourly departure.',
    )
    is_hourly_departure_type = fields.Boolean(
        related='holiday_status_id.is_hourly_departure',
        string='Is Hourly Departure Type',
        readonly=True,
    )
    hourly_departure_hours_applied = fields.Boolean(
        string='Hourly Departure Hours Applied',
        copy=False,
        default=False,
        help='Technical: validated departure hours were added to the accumulator.',
    )
    is_hourly_departure_conversion = fields.Boolean(
        string='Hourly Departure Conversion Leave',
        copy=False,
        default=False,
        help='Technical: annual leave day auto-created from accumulated departures.',
    )

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
        for leave in leaves.filtered(lambda l: l.validation_type == 'both'):
            # Validates GM is configured when the employee has no middle manager.
            leave._resolve_org_approval_users()
        return leaves

    def _is_leave_manager(self):
        """Legacy Time Off Approver (leave_manager_id) — used for single-step manager types."""
        self.ensure_one()
        return bool(
            self.employee_id.leave_manager_id
            and self.employee_id.leave_manager_id == self.env.user
        )

    def _is_time_off_officer(self):
        user = self.env.user
        return (
            user.has_group('hr_holidays.group_hr_holidays_user')
            or user.has_group('hr_holidays.group_hr_holidays_manager')
        )

    def _routing_company(self):
        self.ensure_one()
        return self.company_id or self.employee_id.company_id or self.env.company

    def _get_hr_employee(self):
        """Company-configured Time Off HR (e.g. Ozlam) — always the HR role in the chain."""
        self.ensure_one()
        return self._routing_company().time_off_hr_id

    def _get_gm_employee(self):
        """Company-configured Time Off General Manager (e.g. Basem)."""
        self.ensure_one()
        return self._routing_company().time_off_gm_id

    def _get_middle_manager_employee(self):
        """Org-chart middle manager for step 1 (e.g. Abdullah for IT staff).

        Not a middle manager when:
        - no ``parent_id`` / no linked user
        - parent is the configured GM
        - parent is the top of the org (parent has no ``parent_id``), e.g. Abrar → Basem
        Those cases use HR → GM instead.
        """
        self.ensure_one()
        manager = self.employee_id.parent_id
        if not manager or not manager.user_id or not manager.user_id.active:
            return self.env['hr.employee']
        gm = self._get_gm_employee()
        if gm and manager == gm:
            return self.env['hr.employee']
        # Top of org chart (CEO/GM with no manager above) is not a "middle" manager.
        if not manager.parent_id:
            return self.env['hr.employee']
        return manager

    def _user_for_employee(self, employee):
        """Return the linked active user for an employee, or empty users."""
        if employee and employee.user_id and employee.user_id.active:
            return employee.user_id
        return self.env['res.users']

    def _exclude_requester_users(self, users):
        self.ensure_one()
        requester = self.employee_id.user_id
        if requester:
            return users - requester
        return users

    def _resolve_org_approval_users(self):
        """Compute step-1 / step-2 from org chart + company HR/GM settings.

        * Has middle manager (e.g. MohammadNoor → Abdullah):
          step 1 = that manager, step 2 = configured HR (Ozlam) — always.
        * No middle manager (e.g. Abrar / Abdullah → Basem at top):
          step 1 = configured HR (Ozlam), step 2 = configured GM (Basem).

        :return: dict with keys flow, step1_users, step2_users, step1_employee, step2_employee
        :raises UserError: when required HR/GM is missing or has no user
        """
        self.ensure_one()
        manager = self._get_middle_manager_employee()
        hr = self._get_hr_employee()
        gm = self._get_gm_employee()
        Employee = self.env['hr.employee']
        company = self._routing_company()

        hr_user = self._user_for_employee(hr)
        if not hr_user:
            raise UserError(_(
                'Configure Time Off HR Approver for company %(company)s '
                '(Settings → Time Off HR Approver, e.g. Ozlam). '
                'The employee must be linked to a user.',
                company=company.display_name,
            ))

        if manager:
            flow = 'manager_hr'
            step1_users = self._exclude_requester_users(manager.user_id)
            step2_users = self._exclude_requester_users(hr_user) - step1_users
            step1_employee = manager if step1_users else Employee
            step2_employee = hr if step2_users else Employee
        else:
            flow = 'hr_gm'
            gm_user = self._user_for_employee(gm)
            if not gm_user:
                raise UserError(_(
                    'Employee %(employee)s has no middle manager, and no Time Off '
                    'General Manager is configured for company %(company)s. '
                    'Set Time Off General Manager (e.g. Basem) under Settings.',
                    employee=self.employee_id.display_name,
                    company=company.display_name,
                ))
            step1_users = self._exclude_requester_users(hr_user)
            step2_users = self._exclude_requester_users(gm_user)
            if self.first_approver_id and self.first_approver_id.user_id:
                alt = step2_users - self.first_approver_id.user_id
                if alt:
                    step2_users = alt
            step1_employee = hr if step1_users else Employee
            step2_employee = gm if step2_users else Employee

        if self.first_approver_id and self.first_approver_id.user_id and flow == 'manager_hr':
            alt = step2_users - self.first_approver_id.user_id
            if alt:
                step2_users = alt
            # Display stays the configured HR even if rights were adjusted.
            if hr_user and hr_user in step2_users:
                step2_employee = hr

        if not step1_users:
            raise UserError(_(
                'No eligible first approver found for %(employee)s. '
                'Check the org chart (Manager) and Time Off HR Approver.',
                employee=self.employee_id.display_name,
            ))
        if not step2_users:
            raise UserError(_(
                'No eligible second approver found for %(employee)s. '
                'Configure Time Off HR Approver and Time Off General Manager '
                '(and ensure they are not the same as the requester).',
                employee=self.employee_id.display_name,
            ))
        return {
            'flow': flow,
            'step1_users': step1_users,
            'step2_users': step2_users,
            'step1_employee': step1_employee,
            'step2_employee': step2_employee,
        }
    def _is_step1_approver(self):
        """Current user may do first approval for this leave (org-chart step 1)."""
        self.ensure_one()
        if self._is_leave_requesting_user():
            return False
        try:
            routing = self._resolve_org_approval_users()
        except UserError:
            return False
        return self.env.user in routing['step1_users']

    def _is_second_approver_for_leave(self):
        """Current user may do second approval (HR or GM depending on flow)."""
        self.ensure_one()
        if self._is_leave_requesting_user():
            return False
        if self._is_first_approver_user():
            return False
        try:
            routing = self._resolve_org_approval_users()
        except UserError:
            return False
        return self.env.user in routing['step2_users']

    def _is_first_approver_user(self):
        self.ensure_one()
        employee = self.env.user.employee_id
        return bool(employee and self.first_approver_id and self.first_approver_id == employee)

    @api.depends(
        'second_approver_id',
        'first_approver_id',
        'employee_id',
        'employee_id.parent_id',
        'employee_id.parent_id.user_id',
        'company_id',
        'company_id.time_off_hr_id',
        'company_id.time_off_gm_id',
        'employee_id.parent_id.parent_id',
        'holiday_status_id',
        'holiday_status_id.leave_validation_type',
        'validation_type',
        'state',
    )
    def _compute_org_approval_display(self):
        for leave in self:
            leave.approval_flow = False
            leave.first_approver_display_id = False
            leave.second_approver_display_id = False
            if leave.validation_type != 'both' or not leave.employee_id:
                continue
            try:
                routing = leave._resolve_org_approval_users()
            except UserError:
                continue
            leave.approval_flow = routing['flow']
            leave.first_approver_display_id = (
                leave.first_approver_id or routing['step1_employee']
            )
            leave.second_approver_display_id = (
                leave.second_approver_id or routing['step2_employee']
            )

    @api.depends('state', 'employee_id', 'department_id', 'first_approver_id', 'holiday_status_id')
    @api.depends_context('uid')
    def _compute_can_second_approve(self):
        for holiday in self:
            holiday.can_second_approve = bool(
                holiday.validation_type == 'both'
                and holiday.state == 'validate1'
                and holiday._is_second_approver_for_leave()
            )

    @api.depends(
        'state', 'employee_id', 'department_id', 'first_approver_id',
        'employee_id.parent_id', 'company_id.time_off_gm_id',
    )
    @api.depends_context('uid')
    def _compute_can_approve(self):
        super()._compute_can_approve()
        for holiday in self:
            if holiday._is_leave_requesting_user():
                holiday.can_approve = False
                continue
            if holiday.validation_type == 'both':
                if holiday.state == 'confirm':
                    holiday.can_approve = holiday._is_step1_approver()
                else:
                    holiday.can_approve = False

    @api.depends(
        'state', 'employee_id', 'department_id', 'first_approver_id',
        'holiday_status_id', 'employee_id.parent_id', 'company_id.time_off_gm_id',
    )
    @api.depends_context('uid')
    def _compute_can_validate(self):
        super()._compute_can_validate()
        for holiday in self:
            if holiday._is_leave_requesting_user():
                holiday.can_validate = False
                continue
            if holiday.validation_type != 'both':
                continue
            if holiday.state == 'validate1':
                holiday.can_validate = holiday._is_second_approver_for_leave()
            elif holiday.state == 'confirm':
                holiday.can_validate = False

    @api.depends(
        'state', 'employee_id', 'department_id', 'first_approver_id',
        'holiday_status_id', 'employee_id.parent_id', 'company_id.time_off_gm_id',
    )
    @api.depends_context('uid')
    def _compute_can_refuse(self):
        super()._compute_can_refuse()
        for holiday in self:
            if holiday._is_leave_requesting_user():
                holiday.can_refuse = False
                continue
            if holiday.validation_type != 'both':
                continue
            if holiday.state == 'confirm':
                holiday.can_refuse = holiday._is_step1_approver()
            elif holiday.state == 'validate1':
                holiday.can_refuse = holiday._is_second_approver_for_leave()
            else:
                holiday.can_refuse = False

    def _get_responsible_for_approval(self):
        """Point activities at the org-chart current-step approver(s)."""
        self.ensure_one()
        if self.validation_type == 'both' and self.state in ('confirm', 'validate1'):
            try:
                routing = self._resolve_org_approval_users()
            except UserError:
                return super()._get_responsible_for_approval()
            if self.state == 'confirm':
                return routing['step1_users']
            return routing['step2_users']
        return super()._get_responsible_for_approval()

    def _get_next_states_by_state(self):
        """Employees may only cancel; two-step leaves follow org-chart step roles."""
        state_result = super()._get_next_states_by_state()
        if self._is_leave_requesting_user():
            for source in list(state_result):
                state_result[source] -= {'validate', 'validate1', 'refuse', 'confirm'}
            state_result['validate1'].add('cancel')
            state_result['validate'].add('cancel')
            state_result['refuse'].add('cancel')
            return state_result

        if self.validation_type == 'both' and not self.env.is_superuser():
            is_step1 = self._is_step1_approver()
            is_second = self._is_second_approver_for_leave()
            for source in list(state_result):
                state_result[source] -= {'validate', 'validate1', 'refuse'}
            if is_step1:
                state_result['confirm'].update({'validate1', 'refuse'})
            if is_second:
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
                            'Wait for your manager / HR / general manager.'
                        ))
                    return False
                if holiday.validation_type == 'both':
                    is_step1 = holiday._is_step1_approver()
                    is_second = holiday._is_second_approver_for_leave()
                    if state == 'validate1' and not is_step1:
                        if raise_if_not_possible:
                            raise UserError(_(
                                'Only the employee\'s org-chart first approver '
                                '(manager, or HR if they have no middle manager) '
                                'can give the first approval.'
                            ))
                        return False
                    if state == 'validate' and holiday.state == 'confirm':
                        if raise_if_not_possible:
                            raise UserError(_(
                                'This time off type needs two approvals. '
                                'Complete the first approval before the second.'
                            ))
                        return False
                    if state == 'validate' and holiday.state == 'validate1' and holiday._is_first_approver_user():
                        if raise_if_not_possible:
                            raise UserError(_(
                                'You already did the first approval. '
                                'The second approver (HR or General Manager) must continue.'
                            ))
                        return False
                    if state == 'validate' and holiday.state == 'validate1' and not is_second:
                        if raise_if_not_possible:
                            raise UserError(_(
                                'Only the current second approver (HR or General Manager) '
                                'can give the second approval.'
                            ))
                        return False
                    if state == 'refuse' and holiday.state == 'confirm' and not is_step1:
                        if raise_if_not_possible:
                            raise UserError(_(
                                'Only the current first approver can refuse this request.'
                            ))
                        return False
                    if state == 'refuse' and holiday.state == 'validate1' and not is_second:
                        if raise_if_not_possible:
                            raise UserError(_(
                                'Only the current second approver can refuse this request.'
                            ))
                        return False
        return super()._check_approval_update(state, raise_if_not_possible=raise_if_not_possible)

    # -------------------------------------------------------------------------
    # Article 11 — Hourly Departures
    # -------------------------------------------------------------------------

    def _is_hourly_departure(self):
        self.ensure_one()
        if self.holiday_status_id.is_hourly_departure:
            return True
        company = self.employee_company_id or self.company_id or self.env.company
        departure_type = company._get_hourly_departure_type()
        return bool(departure_type and self.holiday_status_id == departure_type)

    def _hourly_departure_consuming_states(self):
        return ('confirm', 'validate1', 'validate')

    def _get_work_day_hours(self, employee):
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        if calendar and float_compare(calendar.hours_per_day or 0.0, 0.0, precision_digits=2) > 0:
            return calendar.hours_per_day
        if employee and hasattr(employee, '_get_hours_per_day'):
            hours = employee._get_hours_per_day(fields.Date.context_today(self))
            if float_compare(hours or 0.0, 0.0, precision_digits=2) > 0:
                return hours
        return 8.0

    def _get_departure_caps(self):
        self.ensure_one()
        company = self.employee_company_id or self.company_id or self.env.company
        return (
            company.hourly_departure_max_hours_day or 3.0,
            company.hourly_departure_max_hours_month or 6.0,
        )

    def _get_hourly_departure_domain(self, employee, leave_type, date_from=None, date_to=None):
        domain = [
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', 'in', list(self._hourly_departure_consuming_states())),
        ]
        if date_from:
            domain.append(('request_date_from', '>=', date_from))
        if date_to:
            domain.append(('request_date_from', '<=', date_to))
        return domain

    def _sum_hourly_departure_hours(self, employee, leave_type, date_from=None, date_to=None, exclude_ids=None):
        domain = self._get_hourly_departure_domain(employee, leave_type, date_from, date_to)
        if exclude_ids:
            domain.append(('id', 'not in', list(exclude_ids)))
        leaves = self.sudo().search(domain)
        return sum(leaves.mapped('number_of_hours'))

    @api.constrains(
        'employee_id',
        'holiday_status_id',
        'request_date_from',
        'request_date_to',
        'request_hour_from',
        'request_hour_to',
        'number_of_hours',
        'state',
        'departure_reason',
    )
    def _check_hourly_departure_policy(self):
        for leave in self:
            if leave.env.context.get('skip_hourly_departure_check'):
                continue
            if leave.is_hourly_departure_conversion:
                continue
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if not leave._is_hourly_departure():
                continue
            if leave.state not in self._hourly_departure_consuming_states() and leave.state != 'draft':
                continue

            if not leave.departure_reason or not leave.departure_reason.strip():
                raise ValidationError(_(
                    'A departure reason is required for hourly departures (Article 11).'
                ))

            if not leave.request_date_from:
                continue

            day_cap, month_cap = leave._get_departure_caps()
            hours = leave.number_of_hours or 0.0
            if float_compare(hours, 0.0, precision_digits=2) <= 0:
                continue

            if float_compare(hours, day_cap, precision_digits=2) > 0:
                raise ValidationError(_(
                    'Hourly departure cannot exceed %(cap)s hours in a single day '
                    '(requested: %(hours).2f).',
                    cap=day_cap,
                    hours=hours,
                ))

            day = leave.request_date_from
            day_total = leave._sum_hourly_departure_hours(
                leave.employee_id,
                leave.holiday_status_id,
                date_from=day,
                date_to=day,
                exclude_ids=leave.ids,
            ) + hours
            if float_compare(day_total, day_cap, precision_digits=2) > 0:
                raise ValidationError(_(
                    'Hourly departure for %(employee)s on %(day)s would total %(total).2f hours, '
                    'exceeding the daily limit of %(cap)s hours.',
                    employee=leave.employee_id.name,
                    day=day,
                    total=day_total,
                    cap=day_cap,
                ))

            month_start = date(day.year, day.month, 1)
            month_end = date(day.year, day.month, monthrange(day.year, day.month)[1])
            month_total = leave._sum_hourly_departure_hours(
                leave.employee_id,
                leave.holiday_status_id,
                date_from=month_start,
                date_to=month_end,
                exclude_ids=leave.ids,
            ) + hours
            if float_compare(month_total, month_cap, precision_digits=2) > 0:
                raise ValidationError(_(
                    'Hourly departure for %(employee)s in %(month)02d/%(year)s would total '
                    '%(total).2f hours, exceeding the monthly limit of %(cap)s hours.',
                    employee=leave.employee_id.name,
                    month=day.month,
                    year=day.year,
                    total=month_total,
                    cap=month_cap,
                ))

    def _find_conversion_leave_dates(self, employee, start_day, annual_type):
        """Pick a working day without conflicting annual leave for the conversion leave."""
        self.ensure_one()
        day = start_day
        for _ in range(60):
            overlap = self.sudo().search_count([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', annual_type.id),
                ('state', 'not in', ('refuse', 'cancel')),
                ('request_date_from', '<=', day),
                ('request_date_to', '>=', day),
            ])
            if not overlap:
                return day, day
            day += timedelta(days=1)
        raise UserError(_(
            'Could not find an available day to deduct annual leave for %(employee)s '
            'after accumulating one work day of hourly departures.',
            employee=employee.name,
        ))

    def _auto_validate_leave(self, leave):
        leave = leave.sudo()
        if leave.state in ('confirm', 'validate1'):
            leave._action_validate(check_state=False)
        if leave.state != 'validate':
            raise UserError(_(
                'Could not auto-validate annual leave conversion for %(employee)s.',
                employee=leave.employee_id.name,
            ))
        return leave

    def _create_annual_leave_conversion(self, work_day_hours):
        self.ensure_one()
        annual_type = (
            self.employee_id.company_id._get_annual_leave_type()
            if self.employee_id.company_id
            else self.env.company._get_annual_leave_type()
        )
        if not annual_type:
            raise UserError(_(
                'Configure an annual leave type before converting hourly departures.'
            ))

        day_from, day_to = self._find_conversion_leave_dates(
            self.employee_id,
            self.request_date_from or fields.Date.context_today(self),
            annual_type,
        )
        Leave = self.env['hr.leave'].sudo().with_context(
            skip_hourly_departure_check=True,
            skip_hourly_departure_accumulation=True,
            tracking_disable=True,
            mail_activity_automation_skip=True,
            leave_fast_create=True,
        )
        annual_leave = Leave.create({
            'name': _('Hourly departure conversion (Article 11)'),
            'employee_id': self.employee_id.id,
            'holiday_status_id': annual_type.id,
            'request_date_from': day_from,
            'request_date_to': day_to,
            'number_of_days': 1.0,
            'is_hourly_departure_conversion': True,
        })
        annual_leave = self._auto_validate_leave(annual_leave)
        self.env['hr.hourly.departure.conversion'].sudo().create({
            'employee_id': self.employee_id.id,
            'annual_leave_id': annual_leave.id,
            'trigger_leave_id': self.id,
            'hours_converted': work_day_hours,
            'state': 'done',
        })
        return annual_leave

    def _apply_hourly_departure_accumulation(self):
        Balance = self.env['hr.hourly.departure.balance']
        for leave in self:
            if leave.env.context.get('skip_hourly_departure_accumulation'):
                continue
            if leave.state != 'validate' or not leave._is_hourly_departure():
                continue
            if leave.hourly_departure_hours_applied:
                continue
            hours = leave.number_of_hours or 0.0
            if float_compare(hours, 0.0, precision_digits=2) <= 0:
                continue

            balance = Balance._get_or_create_for_employee(leave.employee_id)
            work_day_hours = leave._get_work_day_hours(leave.employee_id)
            balance.accumulated_hours += hours
            leave.hourly_departure_hours_applied = True

            while float_compare(balance.accumulated_hours, work_day_hours, precision_digits=2) >= 0:
                leave._create_annual_leave_conversion(work_day_hours)
                balance.accumulated_hours -= work_day_hours

    def _reverse_hourly_departure_accumulation(self):
        Balance = self.env['hr.hourly.departure.balance']
        Conversion = self.env['hr.hourly.departure.conversion'].sudo()
        for leave in self:
            if not leave.hourly_departure_hours_applied:
                continue
            if not leave._is_hourly_departure():
                continue

            hours = leave.number_of_hours or 0.0
            balance = Balance._get_or_create_for_employee(leave.employee_id)
            work_day_hours = leave._get_work_day_hours(leave.employee_id)
            balance.accumulated_hours -= hours

            while float_compare(balance.accumulated_hours, 0.0, precision_digits=2) < 0:
                conversion = Conversion.search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('state', '=', 'done'),
                ], order='id desc', limit=1)
                if not conversion:
                    raise UserError(_(
                        'Cannot reverse hourly departure for %(employee)s: '
                        'accumulated hours would become negative and no conversion remains to undo.',
                        employee=leave.employee_id.name,
                    ))
                annual_leave = conversion.annual_leave_id
                if annual_leave.state not in ('validate', 'validate1', 'confirm'):
                    raise UserError(_(
                        'Cannot cancel this hourly departure because the linked annual leave '
                        'conversion (%(leave)s) can no longer be reversed.',
                        leave=annual_leave.display_name,
                    ))
                annual_leave.with_context(
                    skip_hourly_departure_check=True,
                    leave_skip_refuse_wizard=True,
                )._force_cancel(
                    reason=_('Reversed hourly departure conversion (Article 11)'),
                )
                conversion.state = 'reversed'
                balance.accumulated_hours += conversion.hours_converted or work_day_hours

            leave.hourly_departure_hours_applied = False

    def action_approve(self, check_state=True):
        self._assert_not_self_approval(_('approve'))
        # Force first-step-only when the org-chart step-1 approver also has officer rights.
        both_confirm = self.filtered(
            lambda leave: leave.validation_type == 'both'
            and leave.state == 'confirm'
            and leave._is_step1_approver()
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
            # Second approver at validate1: always validate even if UI flags are stale.
            to_second = other.filtered(
                lambda leave: leave.validation_type == 'both'
                and leave.state == 'validate1'
                and leave._is_second_approver_for_leave()
            )
            remaining = other - to_second
            if to_second:
                to_second._action_validate(check_state=False)
                if not self.env.context.get('leave_fast_create'):
                    to_second.activity_update()
            if remaining:
                result = super(HrLeave, remaining).action_approve(check_state=check_state)
            current_employee = self.env.user.employee_id
            for leave in remaining:
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
        # Second approvers must be able to validate even when can_validate was False
        # on a stale form cache / restricted view.
        if check_state:
            blocked = self.filtered(
                lambda leave: not leave.can_validate
                and not (
                    leave.validation_type == 'both'
                    and leave.state == 'validate1'
                    and leave._is_second_approver_for_leave()
                )
            )
            if blocked:
                raise UserError(_('You cannot validate this leave.'))
            result = super(HrLeave, self)._action_validate(check_state=False)
        else:
            result = super()._action_validate(check_state=False)
        current_employee = self.env.user.employee_id
        for leave in self:
            if leave.state != 'validate':
                continue
            if leave.validation_type == 'both' and pre_states[leave.id] == 'validate1':
                if current_employee and not leave.second_approver_id:
                    leave.second_approver_id = current_employee.id
                leave._create_approval_trail(
                    'second_approval',
                    approver=current_employee or leave.second_approver_id,
                    trail_state='approved',
                )
            elif not leave._has_trail_stage('first_approval'):
                leave._create_approval_trail(
                    'first_approval',
                    approver=current_employee,
                    trail_state='approved',
                )
        self._apply_hourly_departure_accumulation()
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
        if self.hourly_departure_hours_applied and self._is_hourly_departure():
            self._reverse_hourly_departure_accumulation()
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
        departures = self.filtered(
            lambda leave: leave.hourly_departure_hours_applied and leave._is_hourly_departure()
        )
        departures._reverse_hourly_departure_accumulation()
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
