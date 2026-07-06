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
        domain="['&', ('allow_timesheets', '=', True), '&', ('is_template', '=', False), '|', ('company_id', '=', False), ('company_id', '=', employee_company_id)]",
        tracking=True,
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

    @api.depends('employee_id', 'employee_id.company_id')
    def _compute_employee_company_id(self):
        for request in self:
            request.employee_company_id = request.employee_id.company_id.id if request.employee_id.company_id else False

    @api.depends('employee_id', 'employee_id.company_id')
    def _compute_currency_id(self):
        for request in self:
            company = request.employee_id.company_id.sudo() if request.employee_id else False
            request.currency_id = company.currency_id if company else False

    @api.depends('employee_company_id', 'department_id.company_id')
    def _compute_company_id(self):
        for request in self:
            request.company_id = (
                request.employee_company_id
                or request.department_id.company_id
            )

    def _sudo_company(self):
        """Company used for overtime settings; sudo avoids res.company ACL issues."""
        self.ensure_one()
        if self.employee_id and self.employee_id.company_id:
            return self.employee_id.company_id.sudo()
        return self.env.company.sudo()

    @api.model
    def _employee_company_env(self):
        """Restrict multi-company context to the employee company for self-service users."""
        employee = self.env.user.employee_id
        if (
            employee
            and employee.company_id
            and not self.env.user.has_group('hr_overtime_management.group_overtime_hr_officer')
        ):
            return self.with_context(allowed_company_ids=employee.company_id.ids)
        return self

    @api.model
    def _overtime_action_context(self):
        employee = self.env.user.employee_id
        ctx = {'search_default_my_requests': 1}
        if employee:
            ctx['default_employee_id'] = employee.id
        if employee and employee.company_id:
            ctx['allowed_company_ids'] = employee.company_id.ids
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
        extra = {
            'search_default_my_approvals': 1,
            'search_default_pending': 1,
        }
        employee = self.env.user.employee_id
        if employee.company_id:
            extra['allowed_company_ids'] = employee.company_id.ids
        return self._merge_action_context(action, extra)

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
            active_line = request.approval_line_ids.filtered(lambda l: l.state == 'to_approve')[:1]
            request.current_approver_id = active_line.approver_id

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
        field_name = {
            'regular': 'overtime_default_type_id',
            'weekend': 'overtime_weekend_type_id',
            'holiday': 'overtime_holiday_type_id',
            'day_off': 'overtime_holiday_type_id',
        }.get(category)
        if field_name and company[field_name]:
            return company[field_name]
        OvertimeType = self.env['hr.overtime.type'].sudo()
        ot_type = OvertimeType.search([
            ('company_id', '=', company.id),
            ('category', '=', 'day_off' if category == 'holiday' else category),
            ('active', '=', True),
        ], limit=1)
        if ot_type:
            return ot_type
        return OvertimeType.search([
            ('company_id', '=', False),
            ('category', '=', 'day_off' if category == 'holiday' else category),
            ('active', '=', True),
        ], limit=1)

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
        types = {
            'regular': self._get_overtime_type_for_category(company, 'regular'),
            'weekend': self._get_overtime_type_for_category(company, 'weekend'),
            'holiday': self._get_overtime_type_for_category(company, 'day_off'),
        }
        if not types['regular']:
            types['regular'] = self.env['hr.overtime.type'].sudo().search([
                ('active', '=', True),
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ], limit=1)
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
        types_by_category = self._get_company_overtime_types()
        fallback = types_by_category['regular']
        if not self.start_datetime or not self.end_datetime or not fallback:
            return fallback
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
            multiplier = candidate.rate_multiplier if candidate else 0.0
            if multiplier > best_multiplier:
                best_multiplier = multiplier
                best_type = candidate
        return best_type

    def _sync_attachment_company(self):
        for request in self:
            company = request.employee_id.company_id
            if not company:
                continue
            attachments = request.attachment_ids.sudo()
            wrong_company = attachments.filtered(
                lambda att: att.company_id and att.company_id != company
            )
            no_company = attachments.filtered(lambda att: not att.company_id)
            (wrong_company | no_company).write({'company_id': company.id})

    def _raise_if_cross_company_project(self, project, employee):
        if not project or not employee or not employee.company_id:
            return
        project_company = project.sudo().company_id
        if project_company and project_company.id != employee.company_id.id:
            raise UserError(_(
                'Project "%(project)s" belongs to %(other_company)s. '
                'Please select a project from your company (%(your_company)s).',
                project=project.sudo().display_name,
                other_company=project_company.display_name,
                your_company=employee.company_id.sudo().display_name,
            ))

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        if self.project_id:
            try:
                self._raise_if_cross_company_project(self.project_id, self.employee_id)
            except UserError:
                self.project_id = False
                self.task_id = False

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.employee_id:
            try:
                self._raise_if_cross_company_project(self.project_id, self.employee_id)
            except UserError as error:
                self.project_id = False
                self.task_id = False
                return {'warning': {'title': _('Invalid project'), 'message': error.args[0]}}
        if self.project_id and self.task_id and self.task_id.project_id != self.project_id:
            self.task_id = False

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
            if request.project_id:
                project_company = request.project_id.sudo().company_id
                if project_company and project_company.id != emp_company.id:
                    raise ValidationError(_(
                        'Project "%(project)s" does not belong to %(company)s.',
                        project=request.project_id.sudo().display_name,
                        company=emp_company.sudo().display_name,
                    ))
            if request.task_id and request.task_id.project_id != request.project_id:
                raise ValidationError(_('The task must belong to the selected project.'))
            if (
                request.overtime_type_id
                and request.overtime_type_id.company_id
                and request.overtime_type_id.company_id.id != emp_company.id
            ):
                raise ValidationError(_(
                    'Overtime type "%(otype)s" is not available for %(company)s.',
                    otype=request.overtime_type_id.display_name,
                    company=emp_company.sudo().display_name,
                ))

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
        note = _('Overtime request %(ref)s requires your approval.', ref=self.name)
        self.activity_schedule(
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
            self.activity_ids.filtered(
                lambda a: a.activity_type_id == activity_type
            ).unlink()

    def _on_approval_complete(self):
        for request in self:
            if request._sudo_company().overtime_generate_analytic_line and not request.analytic_line_id:
                request._create_analytic_line()

    def _on_approval_refused(self, line, reason):
        self.message_post(
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
            if emp and emp.company_id:
                vals['employee_company_id'] = emp.company_id.id
                vals['company_id'] = emp.company_id.id
            if vals.get('project_id') and emp:
                self._raise_if_cross_company_project(
                    self.env['project.project'].browse(vals['project_id']),
                    emp,
                )
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
        try:
            records = super(HrOvertimeRequest, self._employee_company_env()).create(vals_list)
        except AccessError as error:
            if 'res.company' in str(error):
                raise UserError(_(
                    'You cannot save this overtime request because it references another company. '
                    'Please choose a project from your own company only.'
                )) from error
            raise
        records._check_employee_company_consistency()
        records._sync_attachment_company()
        return records

    def write(self, vals):
        vals.pop('company_id', None)
        vals.pop('employee_company_id', None)
        is_hr_officer = self.env.user.has_group('hr_overtime_management.group_overtime_hr_officer')
        if not is_hr_officer:
            vals.pop('overtime_type_id', None)
        if vals.get('project_id'):
            for request in self:
                employee = self.env['hr.employee'].browse(
                    vals.get('employee_id') or request.employee_id.id
                )
                self._raise_if_cross_company_project(
                    self.env['project.project'].browse(vals['project_id']),
                    employee,
                )
        try:
            result = super(HrOvertimeRequest, self._employee_company_env()).write(vals)
        except AccessError as error:
            if 'res.company' in str(error):
                raise UserError(_(
                    'You cannot save this overtime request because it references another company. '
                    'Please choose a project from your own company only.'
                )) from error
            raise
        self._check_employee_company_consistency()
        if 'attachment_ids' in vals:
            self._sync_attachment_company()
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
            request.approval_line_ids.unlink()
            request._create_approval_lines_from_chain(chain)
            request.state = 'submitted'
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
            request.approval_line_ids.unlink()
            request.state = 'cancel'
        return True

    def action_reset_to_draft(self):
        for request in self:
            if request.state not in ('cancel', 'refused'):
                raise UserError(_('Only cancelled or refused requests can be reset to draft.'))
            request.approval_line_ids.unlink()
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
        self.analytic_line_id = analytic_line

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
