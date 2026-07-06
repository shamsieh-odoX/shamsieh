# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, time, timedelta
from ast import literal_eval

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HrOvertimeRequest(models.Model):
    _name = 'hr.overtime.request'
    _description = 'Overtime Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'hr.approval.chain.mixin']
    _order = 'start_datetime desc, id desc'

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
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )
    manager_id = fields.Many2one(
        'hr.employee',
        related='employee_id.parent_id',
        store=True,
        readonly=True,
    )
    employee_company_id = fields.Integer(
        string='Employee Company',
        compute='_compute_employee_company_id',
        store=True,
        readonly=True,
    )
    start_datetime = fields.Datetime(
        string='Start Date & Time',
        required=True,
        tracking=True,
        default=lambda self: fields.Datetime.now(),
    )
    end_datetime = fields.Datetime(
        string='End Date & Time',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        compute='_compute_date',
        store=True,
        readonly=True,
        index=True,
        help='Calendar date derived from the start datetime (used for filters and reports).',
    )
    overtime_hours = fields.Float(
        string='Overtime Hours',
        compute='_compute_overtime_hours',
        store=True,
        readonly=True,
    )
    overtime_type_id = fields.Many2one(
        'hr.overtime.type',
        string='Overtime Type',
        compute='_compute_overtime_type_id',
        store=True,
        readonly=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', employee_company_id)]",
        help='Automatically set from the date: regular working day, weekend, or day off.',
    )

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        domain="['&', ('allow_timesheets', '=', True), ('is_template', '=', False), "
               "'|', ('company_id', '=', False), ('company_id', '=', employee_company_id)]",
        tracking=True,
        help='Timesheet projects for your company (or shared across companies).',
    )
    task_id = fields.Many2one(
        'project.task',
        string='Task',
        required=True,
        domain="[('project_id', '=', project_id), ('allow_timesheets', '=', True)]",
        tracking=True,
    )
    description = fields.Text(required=True, tracking=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
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
    approval_line_ids = fields.One2many(
        'hr.overtime.approval.line',
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
        index=True,
    )
    hourly_cost = fields.Monetary(
        string='Hourly Cost',
        compute='_compute_hourly_cost',
        store=True,
        currency_field='currency_id',
    )
    total_cost = fields.Monetary(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_company_id',
        store=True,
        readonly=True,
        index=True,
    )
    company_label = fields.Char(
        string='Company',
        compute='_compute_company_label',
        readonly=True,
    )

    @api.depends('employee_company_id')
    def _compute_company_label(self):
        for request in self:
            if request.employee_company_id:
                company = request.env['res.company'].browse(request.employee_company_id).sudo()
                request.company_label = company.display_name
            else:
                request.company_label = ''

    def _user_can_access_overtime_records(self):
        """True when the user may open this overtime request (owner or active approver)."""
        user = self.env.user
        if user.has_group('hr_overtime_management.group_overtime_hr_officer'):
            return True
        for request in self:
            if request.employee_id.user_id == user:
                continue
            if request.current_approver_id == user:
                continue
            active_lines = request.sudo().approval_line_ids.filtered(
                lambda l: l.approver_id == user and l.state == 'to_approve'
            )
            if active_lines:
                continue
            return False
        return True

    @api.readonly
    def web_read(self, specification):
        if self.env.user.has_group('hr_overtime_management.group_overtime_hr_officer'):
            return super().web_read(specification)
        if not self._user_can_access_overtime_records():
            return super().web_read(specification)
        return super(
            HrOvertimeRequest,
            self.sudo().with_context(check_company=False),
        ).web_read(specification)

    @api.depends('employee_id', 'employee_id.company_id')
    def _compute_employee_company_id(self):
        for request in self:
            company = request.employee_id.company_id.sudo() if request.employee_id else False
            request.employee_company_id = company.id if company else False

    @api.depends('employee_id', 'employee_id.company_id')
    def _compute_currency_id(self):
        for request in self:
            company = request.employee_id.company_id.sudo() if request.employee_id else False
            request.currency_id = company.currency_id if company else False

    @api.depends('employee_company_id')
    def _compute_company_id(self):
        for request in self:
            request.company_id = request.employee_company_id or False

    def _sudo_company(self):
        """Scoped sudo for company settings reads (avoids res.company record-rule errors)."""
        self.ensure_one()
        if self.employee_id and self.employee_id.company_id:
            return self.employee_id.company_id.sudo()
        return self.env.company.sudo()

    @api.model
    def _overtime_crud_env(self):
        """Skip M2O company consistency checks; project may belong to another branch."""
        return self.with_context(check_company=False, mail_create_nosubscribe=True)

    def _check_employee_owns_requests(self):
        user = self.env.user
        if user.has_group('hr_overtime_management.group_overtime_hr_officer'):
            return
        for request in self:
            if request.employee_id.user_id == user:
                continue
            if request.current_approver_id == user:
                continue
            raise AccessError(_('You can only modify your own overtime requests.'))

    def _validate_employee_company_access(self, employee):
        """Employee company must be in the user's allowed companies."""
        if not employee or not employee.company_id:
            return
        emp_company = employee.company_id.sudo()
        if emp_company.id not in self.env.user.company_ids.ids:
            raise UserError(_(
                'Your employee record is linked to %(company)s, but that company is not in your '
                'allowed companies. Ask an administrator to add it under Settings → Users → '
                '%(user)s → Allowed Companies.',
                company=emp_company.display_name,
                user=self.env.user.name,
            ))

    def _validate_project_company_access(self, project):
        """Project branch must be in the user's allowed companies (or shared)."""
        if not project or not project.company_id:
            return
        project_company = project.company_id.sudo()
        if project_company.id not in self.env.user.company_ids.ids:
            raise UserError(_(
                'The project "%(project)s" belongs to %(company)s, which is not in your allowed '
                'companies. Ask an administrator to add that company under Settings → Users → '
                '%(user)s → Allowed Companies.',
                project=project.display_name,
                company=project_company.display_name,
                user=self.env.user.name,
            ))

    @api.model
    def _overtime_request_env(self):
        return self._overtime_crud_env()

    @api.model
    def _employee_company_env(self):
        return self._overtime_request_env()

    @api.model
    def _overtime_action_context(self):
        employee = self.env.user.employee_id
        ctx = {
            'search_default_my_requests': 1,
            'allowed_company_ids': self.env.user.company_ids.ids,
        }
        if employee and employee.company_id:
            ctx['default_company_id'] = employee.company_id.id
        if employee:
            ctx['default_employee_id'] = employee.id
        return ctx

    @api.model
    def _merge_action_context(self, action, extra_context=None):
        """Merge action context (stored as a string) with runtime context."""
        action_context = literal_eval(action.get('context') or '{}')
        merged = {
            **self.env.context,
            **action_context,
            **(extra_context or {}),
        }
        action['context'] = merged
        return action

    @api.model
    def action_open_my_requests(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'hr_overtime_management.action_hr_overtime_request_window',
        )
        return self._merge_action_context(action, self._overtime_action_context())

    @api.model
    def action_open_my_approvals(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'hr_overtime_management.action_hr_overtime_my_approvals_window',
        )
        uid = self.env.user.id
        action['domain'] = [
            ('state', 'in', ('submitted', 'manager_approved', 'upper_manager_approved')),
            '|',
            ('current_approver_id', '=', uid),
            '&', ('approval_line_ids.approver_id', '=', uid), ('approval_line_ids.state', '=', 'to_approve'),
        ]
        return self._merge_action_context(action, {
            'search_default_pending': 1,
            'allowed_company_ids': self.env.user.company_ids.ids,
        })

    @api.model
    def default_get(self, fields_list):
        values = super(HrOvertimeRequest, self._employee_company_env()).default_get(fields_list)
        employee = self.env.user.employee_id
        if employee:
            values['employee_id'] = employee.id
        values.pop('company_id', None)
        return values

    analytic_line_id = fields.Many2one(
        'account.analytic.line',
        string='Timesheet Line',
        copy=False,
        readonly=True,
    )
    daily_hours_warning = fields.Char(compute='_compute_daily_hours_warning')
    can_submit_request = fields.Boolean(compute='_compute_request_permissions')
    can_approve_request = fields.Boolean(compute='_compute_request_permissions')
    can_refuse_request = fields.Boolean(compute='_compute_request_permissions')
    can_cancel_request = fields.Boolean(compute='_compute_request_permissions')
    can_reset_request = fields.Boolean(compute='_compute_request_permissions')
    can_edit_employee_id = fields.Boolean(compute='_compute_request_permissions')

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------

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
        is_hr_officer = user.has_group('hr_overtime_management.group_overtime_hr_officer')
        for request in self:
            is_owner = request.employee_id.user_id == user
            active_line = request._get_active_approval_line()
            can_approve = bool(active_line) and request._can_user_approve_line(active_line)
            request.can_submit_request = is_owner and request.state == 'draft'
            request.can_approve_request = can_approve
            request.can_refuse_request = can_approve
            request.can_cancel_request = is_owner and request.state in ('draft', 'submitted')
            request.can_reset_request = is_owner and request.state in ('cancel', 'refused')
            request.can_edit_employee_id = is_hr_officer and request.state == 'draft'

    @api.depends('approval_line_ids')
    def _compute_approval_line_count(self):
        for request in self:
            request.approval_line_count = len(request.approval_line_ids)

    @api.depends('approval_line_ids.state', 'approval_line_ids.approver_id')
    def _compute_current_approver_id(self):
        for request in self:
            active_line = request.sudo().approval_line_ids.filtered(
                lambda l: l.state == 'to_approve'
            )[:1]
            request.current_approver_id = active_line.approver_id

    @api.model
    def _recompute_current_approvers(self):
        """Refresh stored approver after rule/compute fixes (module upgrade)."""
        self._apply_approver_record_rule()
        requests = self.search([('state', 'not in', ('draft', 'cancel', 'refused', 'hr_approved'))])
        if requests:
            requests._compute_current_approver_id()
        self._refresh_stale_approval_assignments()

    @api.model
    def _apply_approver_record_rule(self):
        """Force-update manager rule (original XML is noupdate)."""
        rule = self.env.ref(
            'hr_overtime_management.hr_overtime_request_rule_manager',
            raise_if_not_found=False,
        )
        domain = (
            "['|', ('current_approver_id', '=', user.id), "
            "'&', ('approval_line_ids.approver_id', '=', user.id), "
            "('approval_line_ids.state', '=', 'to_approve')]"
        )
        if rule and rule.domain_force != domain:
            rule.sudo().write({'domain_force': domain})

    @api.model
    def _refresh_stale_approval_assignments(self):
        """Re-point active manager lines when the employee's manager changed."""
        ApprovalLine = self.env['hr.overtime.approval.line'].sudo()
        for request in self.search([
            ('state', 'in', ('submitted', 'manager_approved', 'upper_manager_approved')),
        ]):
            employee = request.employee_id
            if not employee:
                continue
            active_line = ApprovalLine.search([
                ('request_id', '=', request.id),
                ('state', '=', 'to_approve'),
            ], limit=1)
            if not active_line:
                continue
            expected_user = False
            if active_line.role == 'dept_manager':
                manager = employee.parent_id or employee.department_id.manager_id
                expected_user = manager.user_id if manager else False
            elif active_line.role == 'upper_manager' and employee.parent_id:
                upper = employee.parent_id.parent_id
                expected_user = upper.user_id if upper else False
            if expected_user and active_line.approver_id != expected_user:
                active_line.write({'approver_id': expected_user.id})
                request._compute_current_approver_id()

    @api.depends('start_datetime', 'end_datetime', 'employee_id', 'employee_company_id')
    def _compute_overtime_type_id(self):
        for request in self:
            request.overtime_type_id = request._resolve_overtime_type_for_period()

    @api.depends('start_datetime')
    def _compute_date(self):
        for request in self:
            request.date = fields.Date.to_date(request.start_datetime) if request.start_datetime else False

    @api.depends('start_datetime', 'end_datetime')
    def _compute_overtime_hours(self):
        for request in self:
            if not request.start_datetime or not request.end_datetime:
                request.overtime_hours = 0.0
                continue
            delta = request.end_datetime - request.start_datetime
            request.overtime_hours = max(delta.total_seconds() / 3600.0, 0.0)

    @api.depends(
        'employee_id',
        'employee_id.version_id.wage',
        'employee_id.version_id.resource_calendar_id',
        'employee_company_id',
    )
    def _compute_hourly_cost(self):
        for request in self:
            request.hourly_cost = request._get_hourly_cost_value()

    @api.depends('overtime_hours', 'hourly_cost', 'overtime_type_id.rate_multiplier')
    def _compute_total_cost(self):
        for request in self:
            multiplier = request.overtime_type_id.rate_multiplier if request.overtime_type_id else 1.0
            request.total_cost = request.overtime_hours * request.hourly_cost * multiplier

    @api.depends('overtime_hours', 'employee_company_id')
    def _compute_daily_hours_warning(self):
        for request in self:
            cap = request._sudo_company().overtime_daily_hours_cap
            if cap and request.overtime_hours > cap:
                request.daily_hours_warning = _(
                    'Warning: overtime hours (%.2f) exceed the daily cap (%.2f).',
                    request.overtime_hours,
                    cap,
                )
            else:
                request.daily_hours_warning = False

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('start_datetime', 'end_datetime')
    def _check_datetime_range(self):
        for request in self:
            if request.start_datetime and request.end_datetime:
                if request.end_datetime <= request.start_datetime:
                    raise ValidationError(_('End date & time must be after start date & time.'))

    @api.constrains('start_datetime', 'end_datetime', 'overtime_type_id')
    def _check_overtime_type_configured(self):
        for request in self:
            if request.start_datetime and request.end_datetime and not request.overtime_type_id:
                raise ValidationError(_(
                    'No overtime type could be determined for this date. '
                    'Ask HR to configure overtime types under Overtime → Configuration → Overtime Types.'
                ))

    @api.onchange('start_datetime')
    def _onchange_start_datetime(self):
        if self.start_datetime and not self.end_datetime:
            self.end_datetime = self.start_datetime

    @api.onchange('start_datetime', 'end_datetime', 'employee_id')
    def _onchange_datetimes_overtime_type(self):
        if self.start_datetime and self.end_datetime:
            self.overtime_type_id = self._resolve_overtime_type_for_period()

    def _get_weekend_weekdays(self, company):
        raw = (company.overtime_weekend_weekdays or '4,5').strip()
        try:
            return {int(part.strip()) for part in raw.split(',') if part.strip() != ''}
        except ValueError:
            return {4, 5}

    def _get_overtime_type_for_category(self, company, category):
        company = company.sudo()
        category_key = 'day_off' if category == 'holiday' else category
        field_name = {
            'regular': 'overtime_default_type_id',
            'weekend': 'overtime_weekend_type_id',
            'holiday': 'overtime_holiday_type_id',
            'day_off': 'overtime_holiday_type_id',
        }.get(category)
        if field_name and company[field_name] and company[field_name].active:
            return company[field_name]

        OvertimeType = self.env['hr.overtime.type'].sudo()
        code_by_category = {
            'regular': 'regular',
            'weekend': 'weekend',
            'day_off': 'holiday',
            'holiday': 'holiday',
        }
        search_domains = [
            [('company_id', '=', company.id), ('category', '=', category_key), ('active', '=', True)],
            [('company_id', '=', company.id), ('category', '=', category_key)],
            [('company_id', '=', company.id), ('code', '=', code_by_category[category_key])],
            [('company_id', '=', False), ('category', '=', category_key), ('active', '=', True)],
            [('company_id', '=', False), ('category', '=', category_key)],
            [('company_id', '=', False), ('code', '=', code_by_category[category_key])],
        ]
        for domain in search_domains:
            ot_type = OvertimeType.search(domain, order='active desc, id asc', limit=1)
            if ot_type:
                if not ot_type.active:
                    ot_type.write({'active': True})
                return ot_type

        company._ensure_overtime_types()
        if field_name and company[field_name]:
            return company[field_name]
        return OvertimeType.search([
            ('company_id', '=', company.id),
            ('category', '=', category_key),
        ], order='active desc, id asc', limit=1)

    def _get_overtime_type_by_code(self, code, company):
        category_map = {
            'regular': 'regular',
            'weekend': 'weekend',
            'holiday': 'day_off',
            'day_off': 'day_off',
        }
        category = category_map.get(code, code)
        return self._get_overtime_type_for_category(company, category)

    def _get_company_overtime_types(self):
        self.ensure_one()
        company = self._sudo_company()
        if company:
            company._ensure_overtime_types()
        types = {
            'regular': self._get_overtime_type_for_category(company, 'regular'),
            'weekend': self._get_overtime_type_for_category(company, 'weekend'),
            'holiday': self._get_overtime_type_for_category(company, 'day_off'),
        }
        if not types['regular']:
            types['regular'] = self.env['hr.overtime.type'].sudo().search([
                ('active', '=', True),
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ], order='id asc', limit=1)
        return types

    @api.model
    def _resolve_overtime_type_from_vals(self, vals):
        draft = self.new({
            'employee_id': vals.get('employee_id') or self.env.user.employee_id.id,
            'start_datetime': vals.get('start_datetime'),
            'end_datetime': vals.get('end_datetime'),
        })
        if vals.get('employee_company_id'):
            draft.employee_company_id = vals['employee_company_id']
        return draft._resolve_overtime_type_for_period()

    def _iter_dates_in_period(self, start_dt, end_dt):
        if not start_dt or not end_dt:
            return []
        start_date = fields.Date.to_date(start_dt)
        end_date = fields.Date.to_date(end_dt)
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def _is_public_holiday_date(self, day, employee, company):
        calendar = employee.resource_calendar_id or company.resource_calendar_id
        if not calendar:
            return False
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max)
        return bool(self.env['resource.calendar.leaves'].sudo().search([
            ('calendar_id', '=', calendar.id),
            ('resource_id', '=', False),
            ('date_from', '<=', day_end),
            ('date_to', '>=', day_start),
        ], limit=1))

    def _resolve_overtime_type_for_period(self):
        self.ensure_one()
        company = self._sudo_company()
        if not company:
            return self.env['hr.overtime.type']
        types_by_category = self._get_company_overtime_types()
        fallback = types_by_category['regular'] or types_by_category['weekend'] or types_by_category['holiday']
        if not self.start_datetime or not self.end_datetime:
            return fallback
        if not fallback:
            return self.env['hr.overtime.type']
        weekend_days = self._get_weekend_weekdays(company)
        employee = self.employee_id
        best_type = fallback
        best_multiplier = fallback.rate_multiplier if fallback else 0.0
        for day in self._iter_dates_in_period(self.start_datetime, self.end_datetime):
            if employee and self._is_public_holiday_date(day, employee, company):
                candidate = types_by_category['holiday'] or fallback
            elif day.weekday() in weekend_days:
                candidate = types_by_category['weekend'] or fallback
            else:
                candidate = types_by_category['regular'] or fallback
            if not candidate:
                continue
            multiplier = candidate.rate_multiplier
            if multiplier > best_multiplier:
                best_multiplier = multiplier
                best_type = candidate
        return best_type

    def _sync_attachment_company(self):
        """Shared attachments avoid multi-company access errors on save."""
        for request in self.sudo():
            if request.attachment_ids:
                request.attachment_ids.sudo().write({'company_id': False})

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if not self.employee_id:
            return

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.task_id and self.task_id.project_id != self.project_id:
            self.task_id = False
        if self.project_id:
            self._validate_project_company_access(self.project_id)

    @api.constrains('employee_id', 'company_id', 'project_id', 'task_id', 'overtime_type_id')
    def _check_employee_company_consistency(self):
        for request in self:
            if not request.employee_id or not request.employee_id.company_id:
                continue
            emp_company = request.employee_id.company_id
            if request.company_id and request.company_id.id != emp_company.id:
                raise ValidationError(_(
                    'The company must match the employee\'s company (%(company)s).',
                    company=emp_company.sudo().display_name,
                ))
            if request.task_id and request.task_id.project_id != request.project_id:
                raise ValidationError(_('The task must belong to the selected project.'))

    # -------------------------------------------------------------------------
    # Approval mixin hooks
    # -------------------------------------------------------------------------

    def _approval_line_model(self):
        return 'hr.overtime.approval.line'

    def _approval_line_inverse_field(self):
        return 'request_id'

    def _get_hourly_cost_value(self):
        """Derive hourly cost from the employee contract (hr.version) wage."""
        self.ensure_one()
        employee = self.employee_id.sudo()
        version = employee.version_id
        if not version:
            return 0.0
        hourly = version._get_normalized_wage()
        if hourly:
            return hourly
        wage = version.wage or getattr(version, 'contract_wage', 0.0)
        if not wage:
            return 0.0
        hours_per_month = self._sudo_company().overtime_hours_per_month or 173.33
        return wage / hours_per_month

    def _schedule_approval_activity(self, line):
        self.ensure_one()
        activity_type = self.env.ref(
            'hr_overtime_management.mail_activity_overtime_approval',
            raise_if_not_found=False,
        )
        if not activity_type:
            return
        request = self.sudo()
        note = _('Overtime request %(ref)s requires your approval.', ref=request.name)
        request.activity_schedule(
            activity_type_id=activity_type.id,
            user_id=line.approver_id.id,
            note=note,
        )

    def _clear_approval_activities(self):
        activity_type = self.env.ref(
            'hr_overtime_management.mail_activity_overtime_approval',
            raise_if_not_found=False,
        )
        if activity_type:
            self.sudo().activity_ids.filtered(
                lambda a: a.activity_type_id == activity_type
            ).unlink()

    def _on_approval_complete(self):
        for request in self:
            if request._sudo_company().overtime_generate_analytic_line and not request.analytic_line_id:
                request._create_analytic_line()

    def _on_approval_refused(self, line, reason):
        self.sudo().message_post(
            body=_('Request refused by %(user)s: %(reason)s', user=self.env.user.name, reason=reason),
            subtype_xmlid='mail.mt_comment',
        )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        employee = self.env.user.employee_id
        is_hr_officer = self.env.user.has_group('hr_overtime_management.group_overtime_hr_officer')
        for vals in vals_list:
            vals.pop('company_id', None)
            vals.pop('employee_company_id', None)
            if not is_hr_officer:
                vals.pop('overtime_type_id', None)
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.overtime.request') or _('New')
            if employee and not is_hr_officer:
                vals['employee_id'] = employee.id
            emp = self.env['hr.employee'].browse(vals.get('employee_id'))
            if emp:
                self._validate_employee_company_access(emp)
            if emp and emp.company_id:
                vals['employee_company_id'] = emp.company_id.id
                vals['company_id'] = emp.company_id.id
            if vals.get('project_id'):
                project = self.env['project.project'].browse(vals['project_id'])
                self._validate_project_company_access(project)
            start_dt = vals.get('start_datetime')
            end_dt = vals.get('end_datetime')
            if start_dt and not vals.get('date'):
                vals['date'] = fields.Date.to_date(start_dt)
            if start_dt and end_dt and not vals.get('overtime_hours'):
                delta = fields.Datetime.to_datetime(end_dt) - fields.Datetime.to_datetime(start_dt)
                vals['overtime_hours'] = max(delta.total_seconds() / 3600.0, 0.0)
            if not vals.get('overtime_type_id'):
                ot_type = self._resolve_overtime_type_from_vals(vals)
                if ot_type:
                    vals['overtime_type_id'] = ot_type.id
        records = super(HrOvertimeRequest, self._overtime_crud_env()).create(vals_list)
        records.sudo()._sync_attachment_company()
        return records

    def write(self, vals):
        vals.pop('company_id', None)
        vals.pop('employee_company_id', None)
        is_hr_officer = self.env.user.has_group('hr_overtime_management.group_overtime_hr_officer')
        if not is_hr_officer and not self.env.su:
            vals.pop('overtime_type_id', None)
            self._check_employee_owns_requests()
        elif not is_hr_officer:
            vals.pop('overtime_type_id', None)
        if vals.get('project_id'):
            project = self.env['project.project'].browse(vals['project_id'])
            self._validate_project_company_access(project)
        if not is_hr_officer and any(key in vals for key in ('start_datetime', 'end_datetime', 'employee_id')):
            if len(self) == 1:
                request = self
                merged = {
                    'employee_id': vals.get('employee_id', request.employee_id.id),
                    'start_datetime': vals.get('start_datetime', request.start_datetime),
                    'end_datetime': vals.get('end_datetime', request.end_datetime),
                }
                emp = self.env['hr.employee'].browse(merged['employee_id'])
                if emp:
                    self._validate_employee_company_access(emp)
                if emp.company_id:
                    merged['employee_company_id'] = emp.company_id.id
                ot_type = self._resolve_overtime_type_from_vals(merged)
                if ot_type:
                    vals['overtime_type_id'] = ot_type.id
        result = super(HrOvertimeRequest, self._overtime_crud_env()).write(vals)
        if 'attachment_ids' in vals:
            self.sudo()._sync_attachment_company()
        return result

    # -------------------------------------------------------------------------
    # Workflow actions
    # -------------------------------------------------------------------------

    def action_submit(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('Only draft requests can be submitted.'))
            if not request.employee_id:
                raise UserError(_('An employee must be set before submitting.'))
            request._validate_employee_company_access(request.employee_id)
            request._validate_project_company_access(request.project_id)
            chain = request._resolve_approval_chain(
                request.employee_id,
                chain_builder=request._build_overtime_approval_chain,
            )
            if not chain:
                raise UserError(_('No approval chain could be resolved for this employee.'))
            if chain[-1][0] != 'hr':
                raise UserError(_(
                    'No HR officer is configured for overtime approval. '
                    'Ask an administrator to assign at least one user to the '
                    '"Officer: Overtime HR Approval" group (Settings → Users).'
                ))
            request._unlink_approval_lines()
            request._create_approval_lines_from_chain(chain)
            request.sudo().write({'state': 'submitted'})
            first_line = request._get_active_approval_line()
            if first_line:
                request._schedule_approval_activity(first_line)
            request.message_post(body=_('Overtime request submitted for approval.'))
        return True

    def action_cancel(self):
        for request in self:
            if request.state in ('hr_approved', 'refused'):
                raise UserError(_('Approved or refused requests cannot be cancelled.'))
            request._clear_approval_activities()
            request._unlink_approval_lines()
            request.state = 'cancel'
        return True

    def action_reset_to_draft(self):
        for request in self:
            if request.state not in ('cancel', 'refused'):
                raise UserError(_('Only cancelled or refused requests can be reset to draft.'))
            request._unlink_approval_lines()
            request.state = 'draft'
        return True

    def action_approve(self):
        return self.action_approve_current()

    def action_refuse(self):
        return self.action_open_refuse_wizard()

    def _create_analytic_line(self):
        self.ensure_one()
        line_vals = {
            'name': self.description or self.name,
            'date': self.date,
            'unit_amount': self.overtime_hours,
            'employee_id': self.employee_id.id,
            'project_id': self.project_id.id,
            'task_id': self.task_id.id,
            'company_id': self.company_id.id,
        }
        analytic_line = self.env['account.analytic.line'].sudo().create(line_vals)
        self.sudo().analytic_line_id = analytic_line

    def action_view_approval_lines(self):
        self.ensure_one()
        return {
            'name': _('Approval History'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.overtime.approval.line',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'context': {'default_request_id': self.id},
        }

    def action_print_report(self):
        return self.env.ref('hr_overtime_management.action_report_hr_overtime_request').report_action(self)
