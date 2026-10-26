# -*- coding: utf-8 -*-

import base64
import calendar
import io
import zipfile
from datetime import timedelta
from pathlib import Path
from xml.sax.saxutils import escape

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


LETTERHEAD_PATH = Path(__file__).resolve().parents[1] / 'data' / 'shamsieh_letterhead.docx'
DOCX_COLUMN_WIDTHS = (700, 3100, 1100, 1200, 1300, 1200, 1100, 1100)


def _docx_run(text, bold=False, size=18, color=None):
    color_xml = '<w:color w:val="%s"/>' % color if color else ''
    bold_xml = '<w:b/><w:bCs/>' if bold else ''
    return (
        '<w:r><w:rPr>'
        '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
        '%s%s'
        '<w:sz w:val="%s"/><w:szCs w:val="%s"/>'
        '<w:rtl/>'
        '</w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
    ) % (bold_xml, color_xml, size, size, escape(text or ''))


def _docx_paragraph(text, bold=False, size=18, color=None, align='center', before=60, after=60):
    return (
        '<w:p><w:pPr><w:bidi/><w:jc w:val="%s"/>'
        '<w:spacing w:before="%s" w:after="%s"/></w:pPr>%s</w:p>'
    ) % (align, before, after, _docx_run(text, bold=bold, size=size, color=color))


def _docx_cell(text, width, header=False, align='center'):
    fill = '4F2D56' if header else 'FFFFFF'
    borders = (
        '<w:tcBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '</w:tcBorders>'
    )
    return (
        '<w:tc><w:tcPr>'
        '<w:tcW w:w="%s" w:type="dxa"/>'
        '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>'
        '%s<w:vAlign w:val="center"/>'
        '</w:tcPr>%s</w:tc>'
    ) % (
        width,
        fill,
        borders,
        _docx_paragraph(
            text,
            bold=header,
            size=14 if header else 16,
            color='FFFFFF' if header else '1A1A1A',
            align=align,
            before=40,
            after=40,
        ),
    )


def _docx_row(values, header=False):
    cells = []
    for index, (value, width) in enumerate(zip(values, DOCX_COLUMN_WIDTHS)):
        align = 'right' if index == 1 and not header else 'center'
        cells.append(_docx_cell(value, width, header=header, align=align))
    return '<w:tr>%s</w:tr>' % ''.join(cells)


def _summary_row_values(row):
    return [
        str(row['employee_number']),
        row['employee_name'] or '',
        str(row['attendance_days']),
        '%.1f' % row['total_hours'],
        '%.2f' % row['average_hours'],
        row['average_check_in'] or '',
        str(row['days_without_punch']),
        str(row['error_record_count']),
    ]


def render_attendance_summary_docx(title, subtitle, headers, rows, template_path=None):
    """Fill the approved Shamsieh letterhead with the monthly attendance table."""
    path = Path(template_path or LETTERHEAD_PATH)
    if not path.is_file():
        raise UserError(_('The company letterhead template is missing.'))

    grid = ''.join('<w:gridCol w:w="%s"/>' % width for width in DOCX_COLUMN_WIDTHS)
    table = (
        '<w:tbl><w:tblPr><w:bidiVisual/>'
        '<w:tblW w:w="10800" w:type="dxa"/>'
        '<w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
        '</w:tblPr><w:tblGrid>%s</w:tblGrid>%s%s</w:tbl>'
    ) % (
        grid,
        _docx_row(headers, header=True),
        ''.join(_docx_row(_summary_row_values(row)) for row in rows),
    )
    body = (
        _docx_paragraph(title, bold=True, size=28, align='center', before=200, after=80)
        + _docx_paragraph(subtitle, size=16, color='555555', align='right', before=40, after=160)
        + table
        + _docx_paragraph('', size=16)
    )

    source = zipfile.ZipFile(path)
    try:
        document = source.read('word/document.xml').decode('utf-8')
        start = document.find('<w:body>')
        sect = document.find('<w:sectPr')
        if start < 0 or sect < 0:
            raise UserError(_('The company letterhead template could not be read.'))
        document = document[:start + len('<w:body>')] + body + document[sect:]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                payload = document.encode('utf-8') if info.filename == 'word/document.xml' else source.read(info.filename)
                target.writestr(info, payload)
    finally:
        source.close()
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

    def _month_year(self, day):
        return '%s %s' % (AR_MONTHS[day.month - 1], day.year)

    def _report_title(self):
        self.ensure_one()
        return 'ملخص الدوام | %s | %s' % (
            self._month_year(self.date_from),
            self.company_id.name or '',
        )

    def _report_subtitle(self):
        self.ensure_one()
        period = 'من %s إلى %s %s' % (
            self.date_from.day,
            self.date_to.day,
            self._month_year(self.date_to),
        )
        return '%s · سجلات الحضور في Odoo · «أيام بلا بصمة» = أيام أنشأ لها النظام سجلاً فارغاً.' % period

    def _headers(self):
        return [
            '#',
            'الموظف',
            'أيام الحضور',
            'مجموع الساعات',
            'متوسط الساعات باليوم',
            'متوسط وقت الحضور',
            'أيام بلا بصمة',
            'سجلات بها خطأ',
        ]

    def _sheet_name(self):
        return 'ملخص الدوام'

    def _filename(self):
        self.ensure_one()
        return 'Shamsieh-Attendance-Summary-%s.xlsx' % self.date_from.strftime('%b-%Y')

    def _docx_filename(self):
        self.ensure_one()
        return 'Shamsieh-Attendance-Summary-%s.docx' % self.date_from.strftime('%b-%Y')

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
            rtl=True,
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

    def action_download_docx(self):
        self.ensure_one()
        self._check_dates()
        content = render_attendance_summary_docx(
            title=self._report_title(),
            subtitle=self._report_subtitle(),
            headers=self._headers(),
            rows=self._collect_rows(),
        )
        attachment = self.env['ir.attachment'].create({
            'name': self._docx_filename(),
            'type': 'binary',
            'datas': base64.b64encode(content),
            'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
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
    employee_id = fields.Many2one('hr.employee', string='الموظف', readonly=True)
    attendance_days = fields.Integer(string='أيام الحضور', readonly=True)
    total_hours = fields.Float(string='مجموع الساعات', digits=(16, 1), readonly=True)
    average_hours = fields.Float(string='متوسط الساعات باليوم', digits=(16, 2), readonly=True)
    average_check_in = fields.Char(string='متوسط وقت الحضور', readonly=True)
    days_without_punch = fields.Integer(
        string='أيام بلا بصمة',
        readonly=True,
        help='أيام أنشأ لها النظام سجلاً فارغاً (بدون تسجيل حضور).',
    )
    error_record_count = fields.Integer(
        string='سجلات بها خطأ',
        readonly=True,
        help='سجلات جهاز البصمة بحالة خطأ خلال هذه الفترة.',
    )
