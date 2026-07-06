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
MODULE_VERSION = "19.0.1.4.0"

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
        f"Version: {MODULE_VERSION}\n"
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
    if TEMPLATE.exists():
        shutil.copy2(TEMPLATE, OUTPUT_DOCX)
        doc = Document(str(OUTPUT_DOCX))
        body = doc.element.body
        for child in list(body):
            if child.tag.endswith("p"):
                body.remove(child)
    else:
        doc = Document()

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

    # --- 2. Custom vs Standard Odoo ---
    add_heading(doc, "2. What Was Customized vs What Already Existed in Odoo", 1)
    add_body(
        doc,
        "This section separates deliverables built for your organization from standard Odoo "
        "features that were reused without re-implementing them."
    )
    add_heading(doc, "2.1 Already Existed in Odoo (Reused)", 2)
    add_table(
        doc,
        ["Odoo Standard", "How We Use It"],
        [
            ["hr.employee + parent_id chain", "Manager / upper-manager resolution (same idea as Time Off)"],
            ["hr.version (contract wage)", "Hourly cost from employee wage and work schedule"],
            ["project.project / project.task", "Project & task on each overtime request"],
            ["account.analytic.line (hr_timesheet)", "Optional timesheet line on final approval"],
            ["resource.calendar.leaves", "Public holidays / calendar days off for auto type detection"],
            ["mail.thread / mail.activity", "Chatter, notifications, approval activities"],
            ["res.company multi-company", "Company branches, record rules, allowed companies"],
            ["hr_payroll (optional)", "Payslip input via hr_overtime_payroll glue module only"],
            ["Security groups (res.groups)", "Standard privilege / group pattern"],
        ],
    )
    add_heading(doc, "2.2 Custom-Built for This Project", 2)
    add_table(
        doc,
        ["Custom Component", "Purpose"],
        [
            ["hr.overtime.request", "Main overtime request with workflow states"],
            ["hr.overtime.type", "Per-branch rate categories: Regular, Weekend, Day Off"],
            ["hr.overtime.approval.line", "Audit trail for each approval step"],
            ["hr.approval.chain.service", "Reusable approval-chain resolver (manager → HR)"],
            ["hr.approval.chain.mixin", "Reusable submit / approve / refuse workflow"],
            ["Auto overtime type by date", "Picks Regular / Weekend / Day Off from datetime + calendar"],
            ["Per-company type provisioning", "Each company branch gets its own 3 types + multipliers"],
            ["Middle-East weekend (Fri/Sat)", "Configurable weekend weekdays per company"],
            ["Multi-company employee access", "Employees only see projects / companies they belong to"],
            ["overtime_error_handler.js", "Friendly snackbar for company / access errors"],
            ["QWeb PDF report", "Printable overtime approval document"],
            ["Refuse wizard", "Mandatory reason when refusing a request"],
        ],
    )
    add_heading(doc, "2.3 Customizations Applied During Delivery", 2)
    customizations = [
        "Datetime pickers (start_datetime / end_datetime) instead of separate date + float times.",
        "Overtime Type is auto-computed — employees do not manually select the category.",
        "Three category enums on hr.overtime.type: regular, weekend, day_off.",
        "Each company branch has its own overtime types with independent rate multipliers.",
        "New companies auto-receive Regular / Weekend / Day Off types on creation.",
        "Total cost = hours × hourly wage × rate_multiplier (multiplier editable per branch).",
        "Top-level Overtime app menu (My Requests, My Approvals, All Requests, Configuration).",
        "Server actions for My Requests / My Approvals with correct multi-company context.",
    ]
    for item in customizations:
        add_bullet(doc, item)

    # --- 3. Business Need ---
    add_heading(doc, "3. Business Need & Objectives", 1)
    add_body(doc, "The following business requirements drove this development:")
    objectives = [
        "Employees submit overtime with project/task allocation and supporting documents.",
        "Approval follows the existing organizational hierarchy (manager chain + mandatory HR).",
        "Overtime pay rates per branch (Regular / Weekend / Day Off) are configurable without code.",
        "Approved overtime can generate account.analytic.line (timesheet) entries automatically.",
        "Overtime cost is derived from contract wage, not a parallel payroll engine.",
        "A reusable approval-chain component supports future request types (expenses, permissions, etc.).",
        "Security: employees see own requests; managers see pending approvals; HR sees all.",
    ]
    for o in objectives:
        add_bullet(doc, o)

    # --- 4. Modules ---
    add_heading(doc, "4. Delivered Modules", 1)
    add_table(
        doc,
        ["Module", "Type", "Purpose", "Dependencies"],
        [
            ["hr_overtime_management", "Core (required)", "Requests, approval workflow, reporting, settings", "hr, hr_timesheet, project, mail, resource"],
            ["hr_overtime_payroll", "Optional glue", "Push approved overtime to payslip inputs", "hr_overtime_management, hr_payroll"],
        ],
    )

    # --- 5. Architecture ---
    add_heading(doc, "5. System Architecture", 1)
    add_heading(doc, "5.1 Reusable Approval Engine", 2)
    add_table(
        doc,
        ["Component", "Model", "Role"],
        [
            ["Chain Service", "hr.approval.chain.service", "Resolves manager → upper manager → HR chain from employee.parent_id"],
            ["Chain Mixin", "hr.approval.chain.mixin", "Generic submit / approve / refuse workflow with mail activities"],
            ["Overtime Request", "hr.overtime.request", "Concrete implementation using the mixin"],
        ],
    )
    add_heading(doc, "5.2 Approval Chain Logic", 2)
    add_body(doc, "Mirrors Odoo hr_holidays manager resolution pattern:")
    add_bullet(doc, "Step 1: employee.parent_id (or department manager if no parent) → dept_manager")
    add_bullet(doc, "Step 2: parent of dept manager (if different person) → upper_manager")
    add_bullet(doc, "Step 3: HR officer from group_overtime_hr_officer → hr (always mandatory final stage)")
    add_body(doc, "Two scenarios:")
    add_bullet(doc, "2 stages: Solo manager → dept_manager → HR")
    add_bullet(doc, "3 stages: dept_manager → upper_manager → HR")

    add_heading(doc, "5.3 Workflow States", 2)
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

    add_heading(doc, "5.4 Automatic Overtime Type Selection", 2)
    add_body(doc, "Overtime type is computed from the request period and the employee company branch:")
    add_table(
        doc,
        ["Category (enum)", "When Applied", "Default Multiplier"],
        [
            ["regular", "Normal working days (Sun–Thu by default)", "1.5×"],
            ["weekend", "Configured weekend weekdays (default Fri=4, Sat=5)", "2.0×"],
            ["day_off", "Public holiday on employee working calendar", "2.5×"],
        ],
    )
    add_body(
        doc,
        "If the period spans multiple categories, the highest multiplier wins. "
        "Each company branch maintains its own hr.overtime.type records — San Francisco and Chicago "
        "can use different multipliers."
    )

    # --- 6. Data Models ---
    add_heading(doc, "6. Database Models & Tables", 1)
    add_body(
        doc,
        "PostgreSQL tables created or extended by hr_overtime_management. "
        "Standard Odoo tables (hr_employee, project_project, etc.) are not duplicated."
    )

    add_heading(doc, "6.1 hr.overtime.type → table hr_overtime_type", 2)
    add_table(
        doc,
        ["Column", "Type", "Description"],
        [
            ["id", "Integer", "Primary key"],
            ["name", "Varchar", "Display name (translatable)"],
            ["code", "Varchar", "Technical code: regular, weekend, holiday"],
            ["category", "Varchar", "Enum: regular | weekend | day_off"],
            ["rate_multiplier", "Float", "Pay multiplier — editable per branch (e.g. 1.5, 2.0, 2.5)"],
            ["sequence", "Integer", "Display order in lists"],
            ["company_id", "Integer FK → res_company", "Company branch (NULL = shared template)"],
            ["active", "Boolean", "Archive inactive types"],
            ["create_uid / write_uid", "Integer", "Audit — Odoo standard"],
            ["create_date / write_date", "Timestamp", "Audit — Odoo standard"],
        ],
    )

    add_heading(doc, "6.2 hr.overtime.request → table hr_overtime_request", 2)
    add_table(
        doc,
        ["Column", "Type", "Description"],
        [
            ["id", "Integer", "Primary key"],
            ["name", "Varchar", "Sequence OT/YYYY/MM/00001"],
            ["employee_id", "Integer FK → hr_employee", "Employee who worked overtime"],
            ["department_id", "Integer FK", "Stored related from employee"],
            ["manager_id", "Integer FK", "Direct manager (parent_id)"],
            ["employee_company_id", "Integer", "Employee company id (computed, stored)"],
            ["start_datetime", "Timestamp", "Overtime start"],
            ["end_datetime", "Timestamp", "Overtime end"],
            ["date", "Date", "Computed from start_datetime"],
            ["overtime_hours", "Float", "Computed duration in hours"],
            ["overtime_type_id", "Integer FK → hr_overtime_type", "Auto-computed from date/category"],
            ["project_id", "Integer FK → project_project", "Timesheet-enabled project"],
            ["task_id", "Integer FK → project_task", "Task within project"],
            ["description", "Text", "Reason / details"],
            ["state", "Varchar", "draft | submitted | manager_approved | upper_manager_approved | hr_approved | refused | cancel"],
            ["current_approver_id", "Integer FK → res_users", "User who must act now"],
            ["hourly_cost", "Numeric", "Computed from hr.version wage"],
            ["total_cost", "Numeric", "hours × hourly_cost × rate_multiplier"],
            ["analytic_line_id", "Integer FK", "Timesheet line after HR approval"],
            ["company_id", "Integer FK → res_company", "Employee company branch"],
            ["currency_id", "Integer FK", "Company currency"],
        ],
    )
    add_body(doc, "Many2many hr_overtime_request_ir_attachment_rel links supporting documents (ir_attachment).")

    add_heading(doc, "6.3 hr.overtime.approval.line → table hr_overtime_approval_line", 2)
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

    add_heading(doc, "6.4 hr.approval.chain.service (Abstract — no table)", 2)
    add_body(doc, "AbstractModel — logic only. Resolves (role, approver_user) tuples for any employee.")

    add_heading(doc, "6.5 hr.approval.chain.mixin (Abstract — no table)", 2)
    add_body(doc, "AbstractModel — generic submit, approve, refuse, activity scheduling.")

    add_heading(doc, "6.6 res.company extensions (columns added to res_company)", 2)
    add_table(
        doc,
        ["Column", "Type", "Default", "Description"],
        [
            ["overtime_generate_analytic_line", "Boolean", "True", "Auto-create timesheet on HR approval"],
            ["overtime_default_type_id", "Integer FK", "Regular type", "Regular working day multiplier"],
            ["overtime_weekend_type_id", "Integer FK", "Weekend type", "Weekend day multiplier"],
            ["overtime_holiday_type_id", "Integer FK", "Day Off type", "Public holiday multiplier"],
            ["overtime_weekend_weekdays", "Varchar", "4,5", "Weekend weekday numbers (Mon=0)"],
            ["overtime_daily_hours_cap", "Float", "4.0", "Warning threshold for long requests"],
            ["overtime_hours_per_month", "Float", "173.33", "Wage ÷ hours fallback for hourly cost"],
        ],
    )

    add_heading(doc, "6.7 Entity Relationship Summary", 2)
    add_body(doc, "hr_employee → hr_overtime_request → hr_overtime_approval_line")
    add_body(doc, "hr_overtime_request → hr_overtime_type (by category + company branch)")
    add_body(doc, "hr_overtime_request → project_project / project_task → account_analytic_line (optional)")
    add_body(doc, "res_company → 3× hr_overtime_type (regular, weekend, day_off) per branch")

    # --- 7. Cost Calculation ---
    add_heading(doc, "7. Cost Calculation", 1)
    add_body(doc, "Formula: total_cost = overtime_hours × hourly_cost × overtime_type.rate_multiplier")
    add_heading(doc, "7.1 Hourly Cost (Odoo 19)", 2)
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

    # --- 8. Security ---
    add_heading(doc, "8. Security Groups & Access", 1)
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

    # --- 9. UI & Menus ---
    add_heading(doc, "9. User Interface", 1)
    add_table(
        doc,
        ["Menu", "Purpose"],
        [
            ["Overtime → My Requests", "Employee self-service list/form"],
            ["Overtime → My Approvals", "Kanban for pending approvers"],
            ["Overtime → All Requests", "HR officers — full list"],
            ["Overtime → Configuration → Overtime Types", "Per-branch Regular / Weekend / Day Off multipliers"],
            ["Settings → Employees → Overtime", "Company branch settings + type links"],
        ],
    )
    add_body(doc, "Views delivered: List, Form (statusbar + approval tab + chatter), Kanban, Search filters, Pivot, Graph, QWeb PDF report.")

    # --- 10. Integrations ---
    add_heading(doc, "10. Integrations", 1)
    add_heading(doc, "10.1 Timesheets (account.analytic.line)", 2)
    add_body(
        doc,
        "When overtime_generate_analytic_line is enabled (default), final HR approval creates a "
        "timesheet line with project, task, employee, date, and overtime_hours as unit_amount."
    )
    add_heading(doc, "10.2 Payroll (optional — hr_overtime_payroll)", 2)
    add_body(
        doc,
        "If hr_payroll is installed and overtime_link_to_payroll is enabled, HR approval creates/updates "
        "an hr.payslip.input line (type Overtime) on the employee's open payslip."
    )

    # --- 11. Issues Fixed ---
    add_heading(doc, "11. Issues Encountered & Resolutions", 1)
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
            ["Missing overtime_type_id on save", "Computed field not set before INSERT", "Pre-resolve type in create(); category enums"],
            ["overtime_weekend_weekdays column missing", "Module not upgraded", "SQL migration + module upgrade"],
            ["Menu server action TypeError", "action context is a string not dict", "literal_eval before merge"],
            ["Multi-company project access", "Session company ≠ employee company", "allowed_company_ids + record rules"],
        ],
    )

    # --- 12. Configuration ---
    add_heading(doc, "12. Configuration Checklist (Multi-Company)", 1)
    checklist = [
        "Install hr_overtime_management on database odoo19.",
        "For each company branch: verify 3 overtime types exist (auto-created on company create).",
        "Set rate multipliers per branch under Overtime → Configuration → Overtime Types.",
        "Configure weekend weekdays per branch in Settings → HR → Overtime (default 4,5 = Fri/Sat).",
        "Assign users to Officer: Overtime HR Approval for each branch that needs HR approval.",
        "Ensure employees have wage on hr.version and projects allow timesheets.",
        "Optional: install hr_overtime_payroll for payslip integration.",
    ]
    for i, item in enumerate(checklist, 1):
        add_bullet(doc, f"{i}. {item}")

    # --- 13. User Guide ---
    add_heading(doc, "13. End-User Guide", 1)
    add_heading(doc, "13.1 Employee — Submit Overtime", 2)
    steps_emp = [
        "Go to Overtime → My Requests → New.",
        "Set start/end date & time, project, task, description (type is auto-set from date).",
        "Attach documents if needed → Save → Submit.",
        "Overtime Type and Total Cost update automatically (Regular / Weekend / Day Off).",
    ]
    for s in steps_emp:
        add_bullet(doc, s)

    add_heading(doc, "13.2 Manager — Approve", 2)
    for s in [
        "Go to Overtime → My Approvals.",
        "Open pending request → Approve or Refuse (reason required).",
        "If you are also HR, you may need to approve twice (manager step then HR step).",
    ]:
        add_bullet(doc, s)

    add_heading(doc, "13.3 HR — Configure Branch Rates", 2)
    for s in [
        "Switch to the company branch (company selector in top bar).",
        "Open Overtime → Configuration → Overtime Types — grouped by company.",
        "Edit Regular / Weekend / Day Off records and change Rate Multiplier per branch.",
        "Or use Settings → HR → Overtime to link types and set weekend weekdays.",
    ]:
        add_bullet(doc, s)

    add_heading(doc, "13.4 HR — Final Approval", 2)
    for s in [
        "Any user in Officer: Overtime HR Approval can perform final approval.",
        "On approval: state → Approved; timesheet line created if enabled; payroll input if enabled.",
    ]:
        add_bullet(doc, s)

    # --- 14. Technical ---
    add_heading(doc, "14. Technical File Structure", 1)
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
        "hooks.py — post_init: provision overtime types for all company branches",
        "tests/test_hr_overtime.py — automated tests",
        "doc/generate_full_documentation.py — this PDF/DOCX generator",
    ]
    for f in files:
        add_bullet(doc, f)

    add_heading(doc, "15. Upgrade & Maintenance", 1)
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
        Paragraph(f"Full Technical Documentation — Odoo 19 v{MODULE_VERSION}", ParagraphStyle("S", fontSize=14, textColor=accent, alignment=1)),
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
