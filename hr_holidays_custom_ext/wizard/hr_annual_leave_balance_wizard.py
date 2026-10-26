# -*- coding: utf-8 -*-

import base64
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LETTERHEAD_PATH = (
    Path(__file__).resolve().parents[2]
    / 'hr_attendance_custom_ext' / 'data' / 'shamsieh_letterhead.docx'
)
DOCX_COLUMN_WIDTHS = (500, 2800, 1200, 1300, 1100, 1400, 1200, 1300)

BALANCE_NOTES = (
    'طريقة الاحتساب:',
    '• عدد الأيام = تاريخ اليوم − تاريخ الالتحاق.',
    '• الأيام المستحقة = 14 × (عدد الأيام ÷ 365) لأول 5 سنوات، ثم 21 × (الأيام الزائدة عن 5 سنوات ÷ 365)، مقربة لمنزلة عشرية واحدة. الأساس: المادة 61 من قانون العمل الأردني رقم 8 لسنة 1996 وتعديلاته، والمادة 18 من النظام الداخلي المصدق.',
    '• الرصيد المتبقي = الأيام المستحقة − الأيام المأخوذة. الأيام المأخوذة هي الإجازات السنوية المعتمدة في أودو.',
    '• لا يحتسب الجدول سقوط الإجازة المؤجلة: رصيد أي سنة يجوز تأجيله بالاتفاق للسنة التالية فقط ويسقط إن لم يُطلب استعماله فيها (المادة 18/د).',
    '• العطل الرسمية والأعياد الدينية والعطل الأسبوعية لا تُخصم من الإجازة السنوية (المادة 18/ج).',
    '• هذا احتساب إداري إرشادي وليس استشارة قانونية.',
)


def compute_annual_leave_balance(joining, as_of, taken, days_before=14, days_after=21):
    """Pro-rata annual leave from the joining date, matching the company sheet.

    First five years earn ``days_before`` per 365 days. Service after that earns
    ``days_after`` per 365 days. Accrued days are rounded to one decimal.
    """
    if not joining or not as_of or as_of < joining:
        return None
    service_days = (as_of - joining).days
    service_years = round(service_days / 365, 2)
    first_period_days = 5 * 365
    if service_days <= first_period_days:
        accrued = round(days_before * service_days / 365, 1)
    else:
        accrued = round(
            days_before * first_period_days / 365
            + days_after * (service_days - first_period_days) / 365,
            1,
        )
    taken = round(float(taken or 0.0), 1)
    return {
        'service_days': service_days,
        'service_years': service_years,
        'accrued_days': accrued,
        'taken_days': taken,
        'remaining_days': round(accrued - taken, 1),
    }


def _xlsx_formats(workbook):
    border = {'border': 1, 'border_color': '#BBBBBB', 'font_name': 'Arial', 'font_size': 11, 'align': 'center'}
    return {
        'title': workbook.add_format({'font_name': 'Arial', 'font_size': 14, 'bold': True}),
        'note': workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'bold': True, 'italic': True, 'font_color': '#555555',
        }),
        'header': workbook.add_format({
            **border, 'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#4F2D56',
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
        }),
        'center': workbook.add_format(border),
        'name': workbook.add_format({**border, 'align': 'right'}),
        'date': workbook.add_format({**border, 'num_format': 'dd/mm/yyyy'}),
        'years': workbook.add_format({**border, 'num_format': '0.00'}),
        'days': workbook.add_format({**border, 'num_format': '0.0'}),
        'total': workbook.add_format({**border, 'bold': True, 'bg_color': '#F4F0F5'}),
        'total_days': workbook.add_format({**border, 'bold': True, 'bg_color': '#F4F0F5', 'num_format': '0.0'}),
    }


def render_annual_leave_balance_xlsx(title, as_of, days_before, days_after, headers, rows, notes):
    import xlsxwriter

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    sheet = workbook.add_worksheet('رصيد الإجازات')
    sheet.right_to_left()
    sheet.freeze_panes(5, 0)
    widths = (5, 40, 16, 18, 16, 18, 16, 16)
    for index, width in enumerate(widths):
        sheet.set_column(index, index, width)
    fmt = _xlsx_formats(workbook)
    sheet.set_row(0, 22)
    sheet.set_row(4, 32)
    sheet.write(0, 0, title, fmt['title'])
    sheet.write(1, 0, 'تاريخ اليوم:', fmt['note'])
    sheet.write(1, 1, as_of.strftime('%d/%m/%Y'), fmt['note'])
    sheet.write(1, 4, 'أيام الإجازة سنوياً:', fmt['note'])
    sheet.write(1, 5, days_before, fmt['note'])
    sheet.write(2, 4, 'بعد 5 سنوات خدمة:', fmt['note'])
    sheet.write(2, 5, days_after, fmt['note'])
    for col, header in enumerate(headers):
        sheet.write(4, col, header, fmt['header'])

    accrued_total = taken_total = remaining_total = 0.0
    for index, row in enumerate(rows):
        excel_row = 5 + index
        sheet.write(excel_row, 0, index + 1, fmt['center'])
        sheet.write(excel_row, 1, row['employee_name'], fmt['name'])
        sheet.write(excel_row, 2, row['joining_date'].strftime('%d/%m/%Y'), fmt['center'])
        sheet.write(excel_row, 3, row['service_days'], fmt['center'])
        sheet.write_number(excel_row, 4, row['service_years'], fmt['years'])
        sheet.write_number(excel_row, 5, row['accrued_days'], fmt['days'])
        sheet.write_number(excel_row, 6, row['taken_days'], fmt['days'])
        sheet.write_number(excel_row, 7, row['remaining_days'], fmt['days'])
        accrued_total += row['accrued_days']
        taken_total += row['taken_days']
        remaining_total += row['remaining_days']

    total_row = 5 + len(rows)
    sheet.write(total_row, 1, 'المجموع', fmt['total'])
    sheet.write_number(total_row, 5, round(accrued_total, 1), fmt['total_days'])
    sheet.write_number(total_row, 6, round(taken_total, 1), fmt['total_days'])
    sheet.write_number(total_row, 7, round(remaining_total, 1), fmt['total_days'])
    note_row = total_row + 2
    for offset, note in enumerate(notes):
        sheet.write(note_row + offset, 0, note, fmt['note'])
    workbook.close()
    return buffer.getvalue()


def _docx_run(text, bold=False, size=18, color=None):
    color_xml = '<w:color w:val="%s"/>' % color if color else ''
    bold_xml = '<w:b/><w:bCs/>' if bold else ''
    return (
        '<w:r><w:rPr>'
        '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
        '%s%s<w:sz w:val="%s"/><w:szCs w:val="%s"/><w:rtl/>'
        '</w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
    ) % (bold_xml, color_xml, size, size, escape(text or ''))


def _docx_paragraph(text, bold=False, size=18, color=None, align='right', before=40, after=40):
    return (
        '<w:p><w:pPr><w:bidi/><w:jc w:val="%s"/>'
        '<w:spacing w:before="%s" w:after="%s"/></w:pPr>%s</w:p>'
    ) % (align, before, after, _docx_run(text, bold=bold, size=size, color=color))


def _docx_cell(text, width, header=False, align='center', total=False):
    fill = '4F2D56' if header else ('F4F0F5' if total else 'FFFFFF')
    color = 'FFFFFF' if header else '1A1A1A'
    borders = (
        '<w:tcBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="BBBBBB"/>'
        '</w:tcBorders>'
    )
    return (
        '<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/>'
        '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>%s'
        '<w:vAlign w:val="center"/></w:tcPr>%s</w:tc>'
    ) % (
        width, fill, borders,
        _docx_paragraph(text, bold=header or total, size=14 if header else 16, color=color, align=align),
    )


def _docx_row(values, header=False, total=False):
    cells = []
    for index, (value, width) in enumerate(zip(values, DOCX_COLUMN_WIDTHS)):
        align = 'right' if index == 1 and not header else 'center'
        cells.append(_docx_cell(value, width, header=header, align=align, total=total))
    return '<w:tr>%s</w:tr>' % ''.join(cells)


def render_annual_leave_balance_docx(title, subtitle, headers, rows, notes, template_path=None):
    path = Path(template_path or LETTERHEAD_PATH)
    if not path.is_file():
        raise UserError(_('The company letterhead template is missing.'))
    grid = ''.join('<w:gridCol w:w="%s"/>' % width for width in DOCX_COLUMN_WIDTHS)
    accrued = round(sum(row['accrued_days'] for row in rows), 1)
    taken = round(sum(row['taken_days'] for row in rows), 1)
    remaining = round(sum(row['remaining_days'] for row in rows), 1)
    body_rows = [_docx_row(headers, header=True)]
    for index, row in enumerate(rows):
        body_rows.append(_docx_row([
            str(index + 1),
            row['employee_name'],
            row['joining_date'].strftime('%d/%m/%Y'),
            str(row['service_days']),
            '%.2f' % row['service_years'],
            '%.1f' % row['accrued_days'],
            '%.1f' % row['taken_days'],
            '%.1f' % row['remaining_days'],
        ]))
    body_rows.append(_docx_row(['', 'المجموع', '', '', '', '%.1f' % accrued, '%.1f' % taken, '%.1f' % remaining], total=True))
    table = (
        '<w:tbl><w:tblPr><w:bidiVisual/><w:tblW w:w="10800" w:type="dxa"/>'
        '<w:jc w:val="center"/><w:tblLayout w:type="fixed"/></w:tblPr>'
        '<w:tblGrid>%s</w:tblGrid>%s</w:tbl>'
    ) % (grid, ''.join(body_rows))
    body = (
        _docx_paragraph(title, bold=True, size=28, align='center', before=200, after=60)
        + _docx_paragraph(subtitle, size=16, color='555555', before=20, after=120)
        + table
        + ''.join(_docx_paragraph(note, size=14, color='555555', before=40, after=20) for note in notes)
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


class HrAnnualLeaveBalanceWizard(models.TransientModel):
    _name = 'hr.annual.leave.balance.wizard'
    _description = 'Annual Leave Balance Report'

    as_of_date = fields.Date(
        string='تاريخ اليوم',
        required=True,
        default=fields.Date.context_today,
    )
    days_per_year = fields.Integer(string='أيام الإجازة سنوياً', required=True, default=14)
    days_after_five_years = fields.Integer(string='بعد 5 سنوات خدمة', required=True, default=21)
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        required=True,
        default=lambda self: self.env.company,
    )
    footnote = fields.Text(compute='_compute_footnote')
    line_ids = fields.One2many(
        'hr.annual.leave.balance.line',
        'wizard_id',
        string='الرصيد',
    )

    @api.depends('as_of_date', 'days_per_year', 'days_after_five_years', 'line_ids')
    def _compute_footnote(self):
        for wizard in self:
            wizard.footnote = '\n'.join(BALANCE_NOTES) if wizard.line_ids else False

    def _headers(self):
        return [
            '#',
            'اسم الموظف',
            'تاريخ الالتحاق',
            'عدد الأيام منذ الالتحاق حتى اليوم',
            'مدة الخدمة (سنة)',
            'الأيام المستحقة حتى اليوم',
            'الأيام المأخوذة',
            'الرصيد المتبقي',
        ]

    def _report_title(self):
        self.ensure_one()
        return 'رصيد الإجازات السنوية للموظفين — %s' % (self.company_id.name or '')

    def _report_subtitle(self):
        self.ensure_one()
        return 'تاريخ اليوم: %s · أيام الإجازة سنوياً: %s · بعد 5 سنوات خدمة: %s' % (
            self.as_of_date.strftime('%d/%m/%Y'),
            self.days_per_year,
            self.days_after_five_years,
        )

    def _filename(self, extension):
        self.ensure_one()
        return 'Shamsieh-Annual-Leave-Balance-%s.%s' % (
            self.as_of_date.strftime('%Y-%m-%d'),
            extension,
        )

    def _check_rates(self):
        self.ensure_one()
        if self.days_per_year < 0 or self.days_after_five_years < 0:
            raise UserError(_('Leave days cannot be negative.'))

    def _joining_date(self, employee):
        if 'version_ids' in employee._fields:
            dates = [day for day in employee.version_ids.mapped('contract_date_start') if day]
            if dates:
                return min(dates)
        for field_name in ('contract_date_start', 'first_contract_date'):
            if field_name in employee._fields and employee[field_name]:
                return employee[field_name]
        return False

    def _taken_days(self, employee, leave_type, joining, as_of):
        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
            ('request_date_from', '>=', joining),
            ('request_date_to', '<=', as_of),
        ])
        return sum(abs(leave.number_of_days or 0.0) for leave in leaves)

    def _collect_rows(self):
        self.ensure_one()
        leave_type = self.company_id._get_annual_leave_type()
        if not leave_type:
            raise UserError(_('Configure an annual leave type before running this report.'))
        employees = self.env['hr.employee'].search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ])
        rows = []
        for employee in employees:
            joining = self._joining_date(employee)
            balance = compute_annual_leave_balance(
                joining,
                self.as_of_date,
                self._taken_days(employee, leave_type, joining, self.as_of_date) if joining else 0.0,
                self.days_per_year,
                self.days_after_five_years,
            )
            if not balance:
                continue
            rows.append({
                'employee_id': employee.id,
                'employee_name': employee.name or '',
                'joining_date': joining,
                **balance,
            })
        rows.sort(key=lambda row: (row['joining_date'], row['employee_name']))
        for sequence, row in enumerate(rows, start=1):
            row['sequence'] = sequence
        return rows

    def _replace_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        fields_to_copy = {
            'sequence', 'employee_id', 'joining_date', 'service_days',
            'service_years', 'accrued_days', 'taken_days', 'remaining_days',
        }
        self.line_ids = [
            (0, 0, {key: row[key] for key in fields_to_copy})
            for row in self._collect_rows()
        ]

    def _download(self, content, filename, mimetype):
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(content),
            'mimetype': mimetype,
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def action_open_report(self):
        self.ensure_one()
        self._check_rates()
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
        self._check_rates()
        try:
            content = render_annual_leave_balance_xlsx(
                title=self._report_title(),
                as_of=self.as_of_date,
                days_before=self.days_per_year,
                days_after=self.days_after_five_years,
                headers=self._headers(),
                rows=self._collect_rows(),
                notes=BALANCE_NOTES,
            )
        except ImportError as exc:
            raise UserError(_('Excel export needs the xlsxwriter library, which is included with Odoo.')) from exc
        return self._download(
            content,
            self._filename('xlsx'),
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def action_download_docx(self):
        self.ensure_one()
        self._check_rates()
        content = render_annual_leave_balance_docx(
            title=self._report_title(),
            subtitle=self._report_subtitle(),
            headers=self._headers(),
            rows=self._collect_rows(),
            notes=BALANCE_NOTES,
        )
        return self._download(
            content,
            self._filename('docx'),
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )


class HrAnnualLeaveBalanceLine(models.TransientModel):
    _name = 'hr.annual.leave.balance.line'
    _description = 'Annual Leave Balance Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'hr.annual.leave.balance.wizard',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='#', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='اسم الموظف', readonly=True)
    joining_date = fields.Date(string='تاريخ الالتحاق', readonly=True)
    service_days = fields.Integer(string='عدد الأيام منذ الالتحاق حتى اليوم', readonly=True)
    service_years = fields.Float(string='مدة الخدمة (سنة)', digits=(16, 2), readonly=True)
    accrued_days = fields.Float(string='الأيام المستحقة حتى اليوم', digits=(16, 1), readonly=True)
    taken_days = fields.Float(string='الأيام المأخوذة', digits=(16, 1), readonly=True)
    remaining_days = fields.Float(string='الرصيد المتبقي', digits=(16, 1), readonly=True)
