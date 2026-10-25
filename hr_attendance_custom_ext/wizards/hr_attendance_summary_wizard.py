# -*- coding: utf-8 -*-

import base64
import calendar
import io
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

AR_MONTHS = (
    'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
    'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر',
)
SUMMARY_MONTHS = [
    ('1', 'January'),
    ('2', 'February'),
    ('3', 'March'),
    ('4', 'April'),
    ('5', 'May'),
    ('6', 'June'),
    ('7', 'July'),
    ('8', 'August'),
    ('9', 'September'),
    ('10', 'October'),
    ('11', 'November'),
    ('12', 'December'),
]


def format_hhmm(minutes):
    rounded = int(round(minutes)) % (24 * 60)
    return '%02d:%02d' % (rounded // 60, rounded % 60)


def build_summary_row(employee_id, employee_name, check_in_minutes, total_hours, empty_days, error_count):
    """One employee row, rounded the same way as the September summary sheet."""
    days = len(check_in_minutes)
    total = round(float(total_hours or 0.0), 1)
    average = round(total / days, 2) if days else 0.0
    average_check_in = format_hhmm(sum(check_in_minutes) / days) if days else ''
    return {
        'employee_number': employee_id,
        'employee_id': employee_id,
        'employee_name': employee_name or '',
        'attendance_days': days,
        'total_hours': total,
        'average_hours': average,
        'average_check_in': average_check_in,
        'days_without_punch': empty_days,
        'error_record_count': error_count,
    }


def render_attendance_summary_xlsx(title, subtitle, headers, rows, rtl=True, sheet_name='Attendance Summary'):
    """Workbook laid out like Shamsieh-Attendance-Summary (title, note, header, rows)."""
    try:
        import xlsxwriter
    except ImportError as exc:
        raise UserError(_('Excel export needs the xlsxwriter library, which is included with Odoo.')) from exc

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    sheet = workbook.add_worksheet((sheet_name or 'Attendance Summary')[:31])
    if rtl:
        sheet.right_to_left()
    sheet.freeze_panes(4, 0)
    sheet.set_column(0, 0, 5)
    sheet.set_column(1, 1, 40)
    sheet.set_column(2, 2, 12)
    sheet.set_column(3, 3, 14)
    sheet.set_column(4, 5, 16)
    sheet.set_column(6, 7, 14)

    title_fmt = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 14,
        'bold': True,
    })
    subtitle_fmt = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 11,
        'bold': True,
        'italic': True,
        'font_color': '#555555',
        'align': 'right' if rtl else 'left',
        'valign': 'vcenter',
    })
    header_fmt = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 11,
        'bold': True,
        'font_color': '#FFFFFF',
        'bg_color': '#4F2D56',
        'align': 'center',
        'valign': 'vcenter',
        'text_wrap': True,
        'border': 1,
        'border_color': '#BBBBBB',
    })
    name_fmt = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 11,
        'align': 'right' if rtl else 'left',
        'border': 1,
        'border_color': '#BBBBBB',
    })
    center_fmt = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 11,
        'align': 'center',
        'border': 1,
        'border_color': '#BBBBBB',
    })
    hours_fmt = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 11,
        'align': 'center',
        'num_format': '0.0',
        'border': 1,
        'border_color': '#BBBBBB',
    })
    average_fmt = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 11,
        'align': 'center',
        'num_format': '0.00',
        'border': 1,
        'border_color': '#BBBBBB',
    })

    sheet.set_row(0, 22)
    sheet.set_row(1, 18)
    sheet.set_row(3, 30)
    sheet.write(0, 0, title, title_fmt)
    sheet.write(1, 0, subtitle, subtitle_fmt)
    for col, header in enumerate(headers):
        sheet.write(3, col, header, header_fmt)

    for index, row in enumerate(rows):
        excel_row = 4 + index
        sheet.write(excel_row, 0, row['employee_number'], center_fmt)
        sheet.write(excel_row, 1, row['employee_name'], name_fmt)
        sheet.write(excel_row, 2, row['attendance_days'], center_fmt)
        sheet.write_number(excel_row, 3, row['total_hours'], hours_fmt)
        sheet.write_number(excel_row, 4, row['average_hours'], average_fmt)
        sheet.write(excel_row, 5, row['average_check_in'] or '', center_fmt)
        sheet.write(excel_row, 6, row['days_without_punch'], center_fmt)
        sheet.write(excel_row, 7, row['error_record_count'], center_fmt)

    workbook.close()
    return buffer.getvalue()


class HrAttendanceSummaryWizard(models.TransientModel):
    _name = 'hr.attendance.summary.wizard'
    _description = 'Attendance Summary Report'

    summary_month = fields.Selection(
        selection=SUMMARY_MONTHS,
        string='Month',
        required=True,
        default=lambda self: str(fields.Date.today().month),
    )
    summary_year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    date_from = fields.Date(compute='_compute_month_bounds', store=True)
    date_to = fields.Date(compute='_compute_month_bounds', store=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    footnote = fields.Text(compute='_compute_footnote')
    line_ids = fields.One2many(
        'hr.attendance.summary.line',
        'wizard_id',
        string='Summary',
    )

    @api.depends('summary_year', 'summary_month')
    def _compute_month_bounds(self):
        for wizard in self:
            if not wizard.summary_year or not wizard.summary_month:
                wizard.date_from = False
                wizard.date_to = False
                continue
            month = int(wizard.summary_month)
            year = wizard.summary_year
            last_day = calendar.monthrange(year, month)[1]
            wizard.date_from = fields.Date.from_string('%04d-%02d-01' % (year, month))
            wizard.date_to = fields.Date.from_string('%04d-%02d-%02d' % (year, month, last_day))

    @api.constrains('summary_year')
    def _check_summary_year(self):
        for wizard in self:
            if wizard.summary_year < 2000 or wizard.summary_year > 2100:
                raise UserError(_('Year must be between 2000 and 2100.'))

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_footnote(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.company_id:
                wizard.footnote = wizard._report_subtitle()
            else:
                wizard.footnote = False

    def _is_arabic(self):
        return (self.env.lang or '').startswith('ar')

    def _month_year(self, day):
        if self._is_arabic():
            return '%s %s' % (AR_MONTHS[day.month - 1], day.year)
        return '%s %s' % (calendar.month_name[day.month], day.year)

    def _report_title(self):
        self.ensure_one()
        return '%s | %s | %s' % (
            _('Attendance Summary'),
            self._month_year(self.date_from),
            self.company_id.name or '',
        )

    def _report_subtitle(self):
        self.ensure_one()
        if self._is_arabic():
            period = 'من %s إلى %s %s' % (
                self.date_from.day,
                self.date_to.day,
                self._month_year(self.date_to),
            )
        else:
            period = 'From %s to %s %s' % (
                self.date_from.day,
                self.date_to.day,
                self._month_year(self.date_to),
            )
        return _(
            '%(period)s · Attendance records in Odoo · '
            '"Days without a punch" = days the system created an empty record for.',
            period=period,
        )

    def _headers(self):
        return [
            '#',
            _('Employee'),
            _('Attendance Days'),
            _('Total Hours'),
            _('Average Hours per Day'),
            _('Average Check-in Time'),
            _('Days Without a Punch'),
            _('Records with Errors'),
        ]

    def _sheet_name(self):
        self.ensure_one()
        if self._is_arabic():
            return 'ملخص الدوام'
        return _('Attendance Summary')

    def _filename(self):
        self.ensure_one()
        return 'Shamsieh-Attendance-Summary-%s.xlsx' % self.date_from.strftime('%b-%Y')

    def _check_dates(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_('Choose a month and year.'))
        if self.summary_year < 2000 or self.summary_year > 2100:
            raise UserError(_('Year must be between 2000 and 2100.'))

    def _local_check_in_minutes(self, employee, check_in):
        tzname = (
            employee.tz
            or employee.company_id.resource_calendar_id.tz
            or self.env.user.tz
            or 'Asia/Amman'
        )
        local = fields.Datetime.context_timestamp(
            self.with_context(tz=tzname),
            check_in,
        )
        return local.hour * 60 + local.minute + (local.second / 60.0)

    def _collect_rows(self):
        """Aggregate attendance the same way as the monthly summary spreadsheet.

        Attendance days and hours come from hr.attendance.
        Days without a punch are daily-status rows the cron created with no check-in
        (absent, not leave, not a public holiday).
        Records with errors are fingerprint device logs in the Error state.
        """
        self.ensure_one()
        date_from = self.date_from
        date_to = self.date_to
        company = self.company_id

        attendances = self.env['hr.attendance'].search([
            ('employee_id.company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('check_in', '!=', False),
        ], order='check_in asc')

        first_check_in = {}
        hours = {}
        for attendance in attendances:
            employee_id = attendance.employee_id.id
            key = (employee_id, attendance.date)
            current = first_check_in.get(key)
            if current is None or attendance.check_in < current:
                first_check_in[key] = attendance.check_in
            hours[employee_id] = hours.get(employee_id, 0.0) + (attendance.worked_hours or 0.0)

        attended_dates = {}
        for employee_id, day in first_check_in:
            attended_dates.setdefault(employee_id, set()).add(day)

        empty_statuses = self.env['hr.attendance.daily.status'].search([
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('check_in', '=', False),
            ('status', '=', 'absent'),
            ('is_on_approved_leave', '=', False),
            ('is_public_holiday', '=', False),
        ])
        empty_days = {}
        for status in empty_statuses:
            employee_id = status.employee_id.id
            if status.date in attended_dates.get(employee_id, ()):
                continue
            empty_days[employee_id] = empty_days.get(employee_id, 0) + 1

        window_start = fields.Datetime.to_datetime(date_from) - timedelta(days=1)
        window_end = fields.Datetime.to_datetime(date_to) + timedelta(days=2)
        error_logs = self.env['fingerprint.device.log'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'error'),
            ('employee_id', '!=', False),
            ('event_time', '>=', window_start),
            ('event_time', '<', window_end),
        ])
        error_counts = {}
        for log in error_logs:
            local_date = log._event_local_date(log.employee_id)
            if not local_date or local_date < date_from or local_date > date_to:
                continue
            error_counts[log.employee_id.id] = error_counts.get(log.employee_id.id, 0) + 1

        employee_ids = set(hours) | set(empty_days) | set(error_counts)
        employees = self.env['hr.employee'].browse(sorted(employee_ids))
        check_in_minutes = {}
        for (employee_id, _day), check_in in first_check_in.items():
            employee = employees.browse(employee_id)
            check_in_minutes.setdefault(employee_id, []).append(
                self._local_check_in_minutes(employee, check_in)
            )

        rows = []
        for employee in employees:
            rows.append(build_summary_row(
                employee.id,
                employee.name,
                check_in_minutes.get(employee.id, []),
                hours.get(employee.id, 0.0),
                empty_days.get(employee.id, 0),
                error_counts.get(employee.id, 0),
            ))
        return rows

    def _replace_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        line_fields = {
            'employee_number', 'employee_id', 'attendance_days', 'total_hours',
            'average_hours', 'average_check_in', 'days_without_punch', 'error_record_count',
        }
        self.line_ids = [
            (0, 0, {key: row[key] for key in line_fields})
            for row in self._collect_rows()
        ]

    def action_open_report(self):
        self.ensure_one()
        self._check_dates()
        self._replace_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': self._report_title(),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_refresh(self):
        return self.action_open_report()

    def action_download_xlsx(self):
        self.ensure_one()
        self._check_dates()
        rows = self._collect_rows()
        content = render_attendance_summary_xlsx(
            title=self._report_title(),
            subtitle=self._report_subtitle(),
            headers=self._headers(),
            rows=rows,
            rtl=self._is_arabic(),
            sheet_name=self._sheet_name(),
        )
        attachment = self.env['ir.attachment'].create({
            'name': self._filename(),
            'type': 'binary',
            'datas': base64.b64encode(content),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }


class HrAttendanceSummaryLine(models.TransientModel):
    _name = 'hr.attendance.summary.line'
    _description = 'Attendance Summary Line'
    _order = 'employee_number, id'

    wizard_id = fields.Many2one(
        'hr.attendance.summary.wizard',
        required=True,
        ondelete='cascade',
    )
    employee_number = fields.Integer(string='#', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    attendance_days = fields.Integer(string='Attendance Days', readonly=True)
    total_hours = fields.Float(string='Total Hours', digits=(16, 1), readonly=True)
    average_hours = fields.Float(string='Average Hours per Day', digits=(16, 2), readonly=True)
    average_check_in = fields.Char(string='Average Check-in Time', readonly=True)
    days_without_punch = fields.Integer(
        string='Days Without a Punch',
        readonly=True,
        help='Days the system created an empty attendance record for (no check-in).',
    )
    error_record_count = fields.Integer(
        string='Records with Errors',
        readonly=True,
        help='Fingerprint device logs in the Error state during this period.',
    )
