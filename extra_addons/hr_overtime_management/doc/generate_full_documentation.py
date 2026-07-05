# -*- coding: utf-8 -*-
"""Generate full HR Overtime Management documentation using company Word template style."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

TEMPLATE = Path(r"c:\Users\ASUS\Downloads\ملف قالب الشركة (2).docx")
OUTPUT_DOCX = Path(__file__).resolve().parent / "HR_Overtime_Management_Full_Documentation.docx"
OUTPUT_PDF = Path(__file__).resolve().parent / "HR_Overtime_Management_Full_Documentation.pdf"

# Company template theme colors
COLOR_PRIMARY = RGBColor(0x0E, 0x28, 0x41)   # dark navy
COLOR_ACCENT = RGBColor(0x15, 0x60, 0x82)    # teal
COLOR_ACCENT2 = RGBColor(0xE9, 0x71, 0x32)   # orange
COLOR_TEXT = RGBColor(0x33, 0x33, 0x33)


def set_paragraph_shading(paragraph, fill_hex: str):
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill_hex)
    shd.set(qn("w:val"), "clear")
    p_pr.append(shd)


def add_cover(doc: Document):
    for _ in range(4):
        doc.add_paragraph()
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("HR Overtime Management System")
    run.bold = True
    run.font.size = Pt(28)
    run.font.color.rgb = COLOR_PRIMARY

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run("Technical & Functional Documentation — Odoo 19")
    r.font.size = Pt(16)
    r.font.color.rgb = COLOR_ACCENT

    doc.add_paragraph()
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = meta.add_run(
        f"Modules: hr_overtime_management + hr_overtime_payroll (optional)\n"
        f"Version: 19.0.1.0.3\n"
        f"Document date: {date.today().strftime('%B %d, %Y')}\n"
        f"Database: odoo19"
    )
    r.font.size = Pt(11)
    r.font.color.rgb = COLOR_TEXT
    doc.add_page_break()


def add_heading(doc: Document, text: str, level: int = 1):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    if level == 1:
        run.font.size = Pt(18)
        run.font.color.rgb = COLOR_PRIMARY
        set_paragraph_shading(p, "E8E8E8")
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(8)
    elif level == 2:
        run.font.size = Pt(14)
        run.font.color.rgb = COLOR_ACCENT
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
    else:
        run.font.size = Pt(12)
        run.font.color.rgb = COLOR_ACCENT2
        p.paragraph_format.space_before = Pt(6)
    return p


def add_body(doc: Document, text: str):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(6)
    for run in p.runs:
        run.font.size = Pt(11)
        run.font.color.rgb = COLOR_TEXT
    return p


def add_bullet(doc: Document, text: str):
    p = doc.add_paragraph()
    run = p.add_run(f"• {text}")
    run.font.size = Pt(11)
    run.font.color.rgb = COLOR_TEXT
    p.paragraph_format.left_indent = Cm(0.75)
    p.paragraph_format.space_after = Pt(3)
    return p


def add_table(doc: Document, headers: list[str], rows: list[list[str]]):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        for p in hdr_cells[i].paragraphs:
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(10)
            set_paragraph_shading(p, "0E2841")
    for r_idx, row in enumerate(rows):
        cells = table.rows[r_idx + 1].cells
        for c_idx, val in enumerate(row):
            cells[c_idx].text = str(val)
            for p in cells[c_idx].paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
    doc.add_paragraph()
    return table


def build_document() -> Document:
    shutil.copy2(TEMPLATE, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    # Clear placeholder paragraphs from template
    body = doc.element.body
    for child in list(body):
        if child.tag.endswith("p"):
            body.remove(child)

    add_cover(doc)

    # --- 1. Executive Summary ---
    add_heading(doc, "1. Executive Summary", 1)
    add_body(
        doc,
        "This document describes the custom Odoo 19 overtime management solution delivered for "
        "your organization. The system allows employees to submit overtime requests linked to "
        "projects and tasks, routes them through a multi-level approval chain (department manager "
        "→ optional upper manager → HR), calculates overtime cost from the employee contract wage, "
        "optionally creates timesheet lines on final approval, and optionally pushes costs to payroll."
    )
    add_body(
        doc,
        "The implementation follows Odoo best practices: reusable approval engine (mirroring "
        "hr_holidays patterns), configurable pay-rate multipliers, no duplicate time-tracking tables, "
        "and optional payroll integration in a separate glue module."
    )

    # --- 2. Business Need ---
    add_heading(doc, "2. Business Need & Objectives", 1)
    add_body(doc, "The following business requirements drove this development:")
    objectives = [
        "Employees submit overtime with project/task allocation and supporting documents.",
        "Approval follows the existing organizational hierarchy (manager chain + mandatory HR).",
        "Overtime pay rates (Regular 1.5×, Weekend 2.0×, Holiday 2.5×) are configurable without code changes.",
        "Approved overtime can generate account.analytic.line (timesheet) entries automatically.",
        "Overtime cost is derived from contract wage, not a parallel payroll engine.",
        "A reusable approval-chain component supports future request types (expenses, permissions, etc.).",
        "Security: employees see own requests; managers see pending approvals; HR sees all.",
    ]
    for o in objectives:
        add_bullet(doc, o)

    # --- 3. Modules ---
    add_heading(doc, "3. Delivered Modules", 1)
    add_table(
        doc,
        ["Module", "Type", "Purpose", "Dependencies"],
        [
            ["hr_overtime_management", "Core (required)", "Requests, approval workflow, reporting, settings", "hr, hr_timesheet, project, mail, resource"],
            ["hr_overtime_payroll", "Optional glue", "Push approved overtime to payslip inputs", "hr_overtime_management, hr_payroll"],
        ],
    )

    # --- 4. Architecture ---
    add_heading(doc, "4. System Architecture", 1)
    add_heading(doc, "4.1 Reusable Approval Engine", 2)
    add_table(
        doc,
        ["Component", "Model", "Role"],
        [
            ["Chain Service", "hr.approval.chain.service", "Resolves manager → upper manager → HR chain from employee.parent_id"],
            ["Chain Mixin", "hr.approval.chain.mixin", "Generic submit / approve / refuse workflow with mail activities"],
            ["Overtime Request", "hr.overtime.request", "Concrete implementation using the mixin"],
        ],
    )
    add_heading(doc, "4.2 Approval Chain Logic", 2)
    add_body(doc, "Mirrors Odoo hr_holidays manager resolution pattern:")
    add_bullet(doc, "Step 1: employee.parent_id (or department manager if no parent) → dept_manager")
    add_bullet(doc, "Step 2: parent of dept manager (if different person) → upper_manager")
    add_bullet(doc, "Step 3: HR officer from group_overtime_hr_officer → hr (always mandatory final stage)")
    add_body(doc, "Two scenarios:")
    add_bullet(doc, "2 stages: Solo manager → dept_manager → HR")
    add_bullet(doc, "3 stages: dept_manager → upper_manager → HR")

    add_heading(doc, "4.3 Workflow States", 2)
    add_table(
        doc,
        ["State", "Meaning"],
        [
            ["draft", "Employee is editing; not yet submitted"],
            ["submitted", "Waiting on first approver (dept manager)"],
            ["manager_approved", "Dept manager approved; waiting upper manager or HR"],
            ["upper_manager_approved", "Upper manager approved; waiting HR"],
            ["hr_approved", "Fully approved — triggers timesheet / payroll hooks"],
            ["refused", "Rejected at any stage (reason required)"],
            ["cancel", "Cancelled by employee before completion"],
        ],
    )

    # --- 5. Data Models ---
    add_heading(doc, "5. Database Models & Columns", 1)

    add_heading(doc, "5.1 hr.overtime.type (Configuration)", 2)
    add_table(
        doc,
        ["Column", "Type", "Description"],
        [
            ["name", "Char", "Display name: Regular Overtime, Weekend, Public Holiday"],
            ["code", "Char", "Unique code per company: regular, weekend, holiday"],
            ["rate_multiplier", "Float", "Pay multiplier — seeded 1.5 / 2.0 / 2.5, editable in Settings"],
            ["sequence", "Integer", "Display order"],
            ["company_id", "Many2one", "Company scope"],
            ["active", "Boolean", "Archive inactive types"],
        ],
    )

    add_heading(doc, "5.2 hr.overtime.request (Main Record)", 2)
    add_table(
        doc,
        ["Column", "Type", "Description"],
        [
            ["name", "Char", "Auto sequence OT/YYYY/MM/00001"],
            ["employee_id", "Many2one", "Employee who worked overtime"],
            ["department_id", "Many2one", "Related from employee, stored"],
            ["manager_id", "Many2one", "Direct manager (parent_id), stored"],
            ["start_datetime", "Datetime", "Overtime start (date & time picker)"],
            ["end_datetime", "Datetime", "Overtime end (date & time picker)"],
            ["date", "Date", "Computed from start_datetime for filters/reports"],
            ["overtime_hours", "Float", "Computed: (end − start) in hours"],
            ["overtime_type_id", "Many2one", "Rate category with multiplier"],
            ["project_id", "Many2one", "Project (timesheet-enabled)"],
            ["task_id", "Many2one", "Task within project"],
            ["description", "Text", "Reason / details"],
            ["attachment_ids", "Many2many", "Supporting documents"],
            ["state", "Selection", "Workflow status (see section 4.3)"],
            ["approval_line_ids", "One2many", "Full approval audit trail"],
            ["current_approver_id", "Many2one", "User who must act now (record rules)"],
            ["hourly_cost", "Monetary", "From contract wage via hr.version"],
            ["total_cost", "Monetary", "hours × hourly_cost × rate_multiplier"],
            ["analytic_line_id", "Many2one", "Timesheet line created on HR approval"],
            ["company_id", "Many2one", "Company"],
            ["currency_id", "Many2one", "Company currency"],
        ],
    )

    add_heading(doc, "5.3 hr.overtime.approval.line (Audit Trail)", 2)
    add_table(
        doc,
        ["Column", "Type", "Description"],
        [
            ["request_id", "Many2one", "Parent overtime request"],
            ["sequence", "Integer", "Order in chain (10, 20, 30…)"],
            ["role", "Selection", "dept_manager | upper_manager | hr"],
            ["approver_id", "Many2one", "Assigned approver user"],
            ["state", "Selection", "pending | to_approve | approved | refused"],
            ["decision_date", "Datetime", "When decision was made"],
            ["comment", "Text", "Refusal reason or notes"],
        ],
    )

    add_heading(doc, "5.4 res.company Extensions", 2)
    add_table(
        doc,
        ["Column", "Type", "Default", "Description"],
        [
            ["overtime_generate_analytic_line", "Boolean", "True", "Auto-create timesheet on HR approval"],
            ["overtime_default_type_id", "Many2one", "Regular", "Default overtime type for new requests"],
            ["overtime_daily_hours_cap", "Float", "4.0", "Warning if single request exceeds hours"],
            ["overtime_hours_per_month", "Float", "173.33", "Fallback divisor: wage ÷ hours for hourly cost"],
        ],
    )

    # --- 6. Cost Calculation ---
    add_heading(doc, "6. Cost Calculation", 1)
    add_body(doc, "Formula: total_cost = overtime_hours × hourly_cost × overtime_type.rate_multiplier")
    add_heading(doc, "6.1 Hourly Cost (Odoo 19)", 2)
    add_body(
        doc,
        "In Odoo 19, contract data lives on hr.version (linked via employee.current_version_id). "
        "Hourly cost is calculated as:"
    )
    add_bullet(doc, "Primary: wage × 12 ÷ 52 ÷ hours_per_week (from employee work schedule)")
    add_bullet(doc, "Fallback: wage ÷ overtime_hours_per_month (company setting, default 173.33)")
    add_body(
        doc,
        "Example — Administrator, wage $7,540/month, 38 h/week, 2 h Regular OT (1.5×): "
        "Hourly ≈ $45.81 → Total ≈ $137.43"
    )

    # --- 7. Security ---
    add_heading(doc, "7. Security Groups & Access", 1)
    add_table(
        doc,
        ["Group", "Users", "Access"],
        [
            ["group_overtime_user", "All employees", "Create/read own requests; edit only in draft"],
            ["Managers (record rule)", "current_approver_id = me", "Approve/refuse pending requests"],
            ["group_overtime_hr_officer", "HR team", "Read all; final HR approval"],
            ["group_overtime_admin", "Administrators", "Configure types, settings, full access"],
        ],
    )

    # --- 8. UI & Menus ---
    add_heading(doc, "8. User Interface", 1)
    add_table(
        doc,
        ["Menu", "Purpose"],
        [
            ["Overtime → My Requests", "Employee self-service list/form"],
            ["Overtime → My Approvals", "Kanban for pending approvers"],
            ["Overtime → All Requests", "HR officers — full list"],
            ["Overtime → Configuration → Overtime Types", "Admin — rate multipliers"],
            ["Settings → Employees → Overtime", "Company configuration"],
        ],
    )
    add_body(doc, "Views delivered: List, Form (statusbar + approval tab + chatter), Kanban, Search filters, Pivot, Graph, QWeb PDF report.")

    # --- 9. Integrations ---
    add_heading(doc, "9. Integrations", 1)
    add_heading(doc, "9.1 Timesheets (account.analytic.line)", 2)
    add_body(
        doc,
        "When overtime_generate_analytic_line is enabled (default), final HR approval creates a "
        "timesheet line with project, task, employee, date, and overtime_hours as unit_amount."
    )
    add_heading(doc, "9.2 Payroll (optional — hr_overtime_payroll)", 2)
    add_body(
        doc,
        "If hr_payroll is installed and overtime_link_to_payroll is enabled, HR approval creates/updates "
        "an hr.payslip.input line (type Overtime) on the employee's open payslip."
    )

    # --- 10. Issues Fixed ---
    add_heading(doc, "10. Issues Encountered & Resolutions", 1)
    add_table(
        doc,
        ["Issue", "Cause", "Resolution"],
        [
            ["Submit crash: res.groups has no attribute users", "Odoo 19 uses all_user_ids not users", "Fixed get_hr_responsible() to use all_user_ids"],
            ["column start_datetime does not exist", "Code updated but module not upgraded on odoo19", "SQL migration + module upgrade"],
            ["OwlError: start_time field undefined", "Stale ir.ui.view records in database", "Updated stored view XML in odoo19"],
            ["Approval chain incomplete: no HR stage", "Sanitizer removed HR when same user as manager", "HR stage always preserved in chain"],
            ["Hourly/Total cost $0.00", "Core returned 0; Odoo 19 uses hr.version not hr.contract", "Read wage from employee.version_id"],
            ["column overtime_hours_per_month missing", "New field without DB upgrade", "Added column + reset module state"],
            ["PDF: wkhtmltopdf not found", "Binary not installed on Windows", "Installed wkhtmltopdf 0.12.6 via winget"],
        ],
    )

    # --- 11. Configuration ---
    add_heading(doc, "11. Configuration Checklist", 1)
    checklist = [
        "Install hr_overtime_management on database odoo19.",
        "Assign users to security groups (especially Officer: Overtime HR Approval).",
        "Verify overtime types and multipliers under Overtime → Configuration.",
        "Set company settings: default type, daily cap, hours/month divisor, timesheet toggle.",
        "Ensure employees have contract wage and work schedule on hr.version.",
        "Optional: install hr_overtime_payroll for payslip integration.",
        "Optional: add C:\\Program Files\\wkhtmltopdf\\bin to PATH for PDF reports.",
    ]
    for i, item in enumerate(checklist, 1):
        add_bullet(doc, f"{i}. {item}")

    # --- 12. User Guide ---
    add_heading(doc, "12. End-User Guide", 1)
    add_heading(doc, "12.1 Employee — Submit Overtime", 2)
    steps_emp = [
        "Go to Overtime → My Requests → New.",
        "Select employee, start/end date & time, overtime type, project, task, description.",
        "Attach documents if needed → Save → Submit.",
        "Track status in form statusbar and Approval History tab.",
    ]
    for s in steps_emp:
        add_bullet(doc, s)

    add_heading(doc, "12.2 Manager — Approve", 2)
    for s in [
        "Go to Overtime → My Approvals.",
        "Open pending request → Approve or Refuse (reason required).",
        "If you are also HR, you may need to approve twice (manager step then HR step).",
    ]:
        add_bullet(doc, s)

    add_heading(doc, "12.3 HR — Final Approval", 2)
    for s in [
        "Any user in Officer: Overtime HR Approval can perform final approval.",
        "On approval: state → Approved; timesheet line created if enabled; payroll input if enabled.",
    ]:
        add_bullet(doc, s)

    # --- 13. Technical ---
    add_heading(doc, "13. Technical File Structure", 1)
    add_body(doc, "extra_addons/hr_overtime_management/")
    files = [
        "models/hr_approval_chain_service.py — reusable chain resolver",
        "models/hr_approval_mixin.py — generic workflow mixin",
        "models/hr_overtime_request.py — main request + state machine",
        "models/hr_overtime_approval_line.py — approval trail",
        "models/hr_overtime_type.py — configurable rate types",
        "security/security.xml — groups + record rules",
        "views/ — list, form, kanban, search, pivot, graph",
        "report/hr_overtime_report.xml — QWeb PDF",
        "wizard/hr_overtime_refuse_wizard.py — refusal reason dialog",
        "tests/test_hr_overtime.py — automated tests",
        "migrations/ — database upgrade scripts",
    ]
    for f in files:
        add_bullet(doc, f)

    add_heading(doc, "14. Upgrade & Maintenance", 1)
    add_body(doc, "After any code change, upgrade the module:")
    add_body(doc, "python odoo-bin -c debian/odoo.conf -d odoo19 -u hr_overtime_management --stop-after-init")
    add_body(doc, "Or: Apps → HR Overtime Management → Upgrade")
    add_body(doc, "Always use database odoo19 (not odoo) for this installation.")

    # Footer note
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("— End of Document —")
    r.font.color.rgb = COLOR_ACCENT
    r.italic = True

    return doc


def convert_to_pdf(docx_path: Path, pdf_path: Path) -> bool:
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        return pdf_path.exists()
    except Exception as e:
        print(f"docx2pdf failed: {e}")
    try:
        import subprocess
        soffice = r"C:\Program Files\LibreOffice\program\soffice.exe"
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(docx_path.parent), str(docx_path)],
            check=True,
            timeout=120,
        )
        return pdf_path.exists()
    except Exception as e:
        print(f"LibreOffice failed: {e}")
    return False


def build_pdf_fallback():
    """ReportLab PDF with company template colors if Word conversion unavailable."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    primary = colors.HexColor("#0E2841")
    accent = colors.HexColor("#156082")
    accent2 = colors.HexColor("#E97132")
    light = colors.HexColor("#E8E8E8")

    doc = SimpleDocTemplate(str(OUTPUT_PDF), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, textColor=primary, spaceAfter=10, spaceBefore=14)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, textColor=accent, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=6)
    story = [
        Paragraph("HR Overtime Management System", ParagraphStyle("T", fontSize=22, textColor=primary, alignment=1, spaceAfter=20)),
        Paragraph("Full Technical Documentation — Odoo 19 v19.0.1.0.3", ParagraphStyle("S", fontSize=14, textColor=accent, alignment=1)),
        Spacer(1, 30),
        Paragraph(f"Generated: {date.today()}", body),
        PageBreak(),
        Paragraph("See accompanying DOCX file for complete formatted documentation.", body),
        Paragraph("PDF auto-conversion requires Microsoft Word (docx2pdf) or LibreOffice.", body),
    ]
    doc.build(story)


def main():
    print("Building DOCX from company template...")
    doc = build_document()
    doc.save(str(OUTPUT_DOCX))
    print(f"DOCX saved: {OUTPUT_DOCX}")

    print("Converting to PDF...")
    if convert_to_pdf(OUTPUT_DOCX, OUTPUT_PDF):
        print(f"PDF saved: {OUTPUT_PDF}")
    else:
        print("Word/LibreOffice conversion unavailable — building styled PDF fallback...")
        build_pdf_fallback()
        print(f"PDF saved (fallback): {OUTPUT_PDF}")
        print("For best results matching the Word template, open the DOCX in Word and Save As PDF.")


if __name__ == "__main__":
    main()
