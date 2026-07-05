#!/usr/bin/env python3
"""Generate HR Overtime Management module documentation PDF."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT = Path(__file__).resolve().parent / "HR_Overtime_Management_Documentation.pdf"


def build_pdf():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=16,
        textColor=colors.HexColor("#714B67"),
    )
    h1 = ParagraphStyle(
        "DocH1",
        parent=styles["Heading1"],
        fontSize=16,
        spaceBefore=18,
        spaceAfter=10,
        textColor=colors.HexColor("#714B67"),
    )
    h2 = ParagraphStyle(
        "DocH2",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#017E84"),
    )
    body = ParagraphStyle(
        "DocBody",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        spaceAfter=8,
    )
    bullet = ParagraphStyle(
        "DocBullet",
        parent=body,
        leftIndent=14,
        bulletIndent=0,
        spaceAfter=4,
    )

    story = []

    def add_title(text):
        story.append(Paragraph(text, title))

    def add_h1(text):
        story.append(Paragraph(text, h1))

    def add_h2(text):
        story.append(Paragraph(text, h2))

    def add_p(text):
        story.append(Paragraph(text, body))

    def add_bullet(text):
        story.append(Paragraph(f"• {text}", bullet))

    def add_table(headers, rows, col_widths=None):
        data = [headers] + rows
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#714B67")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(table)
        story.append(Spacer(1, 10))

    # Cover
    add_title("HR Overtime Management")
    add_p(
        "<b>Odoo 19 Custom Module — Technical &amp; Functional Documentation</b><br/>"
        "Modules: <b>hr_overtime_management</b> (core) + <b>hr_overtime_payroll</b> (optional glue)<br/>"
        "Version: 19.0.1.0.1<br/>"
        "Generated: July 2026"
    )
    story.append(Spacer(1, 20))

    add_h1("1. Overview")
    add_p(
        "This solution lets employees submit overtime requests linked to projects and tasks. "
        "Each request follows a multi-level approval chain (department manager → optional upper manager → HR), "
        "mirroring the pattern used by Odoo's <i>hr_holidays</i> module. "
        "On final HR approval, the system can optionally create a timesheet line "
        "(<i>account.analytic.line</i>) and, if the payroll glue module is installed, "
        "push the overtime cost to a payslip input."
    )
    add_p(
        "<b>Design principles:</b> Reusable approval engine (not overtime-specific), "
        "configurable pay-rate multipliers (never hardcoded), no parallel time-tracking table, "
        "and payroll integration isolated in a separate optional module."
    )

    add_h1("2. Module Structure")
    add_table(
        ["Module", "Purpose", "Depends on"],
        [
            ["hr_overtime_management", "Core overtime requests, approval workflow, reporting", "hr, hr_timesheet, project, mail, resource"],
            ["hr_overtime_payroll", "Contract-based hourly cost + payslip input on approval", "hr_overtime_management, hr_payroll"],
        ],
        [4.5 * cm, 7.5 * cm, 4 * cm],
    )

    add_h1("3. Bug Fix Applied (Submit Error)")
    add_p(
        "<b>Error:</b> <i>AttributeError: 'res.groups' object has no attribute 'users'</i> "
        "when clicking Submit on an overtime request."
    )
    add_p(
        "<b>Cause:</b> In Odoo 19, the field on <i>res.groups</i> is named <b>user_ids</b> "
        "(explicit members) and <b>all_user_ids</b> (including implied groups). "
        "The code incorrectly referenced <i>.users</i>, which does not exist."
    )
    add_p(
        "<b>Fix:</b> In <i>hr.approval.chain.service.get_hr_responsible()</i>, "
        "changed <i>hr_group.users</i> → <i>hr_group.all_user_ids</i> so HR officers "
        "from the overtime HR group (and its implied groups) are resolved correctly."
    )

    add_h1("4. Date &amp; Time Change")
    add_p(
        "Previously, overtime used a separate <b>date</b> field plus <b>start_time</b> / <b>end_time</b> "
        "as float fields with a time widget. These have been replaced with proper datetime pickers:"
    )
    add_table(
        ["Old field", "New field", "Type", "Description"],
        [
            ["date + start_time", "start_datetime", "Datetime", "Start date & time picker (required)"],
            ["date + end_time", "end_datetime", "Datetime", "End date & time picker (required)"],
            ["date (manual)", "date", "Date (computed, stored)", "Auto-derived from start_datetime for filters/reports"],
            ["—", "overtime_hours", "Float (computed)", "Hours = (end_datetime − start_datetime) in hours"],
        ],
        [3.5 * cm, 3.5 * cm, 3 * cm, 6 * cm],
    )
    add_p(
        "Overnight overtime is handled naturally: if end is on the next calendar day, "
        "the datetime difference still computes correctly (e.g. 22:00 → 02:00 next day = 4 hours)."
    )

    add_h1("5. Database Models &amp; Columns")

    add_h2("5.1 hr.overtime.type — Overtime Type (Configuration)")
    add_table(
        ["Column", "Type", "Description"],
        [
            ["name", "Char", "Display name, e.g. Regular Overtime, Weekend, Public Holiday"],
            ["code", "Char", "Unique code per company (regular, weekend, holiday)"],
            ["rate_multiplier", "Float", "Pay multiplier: Regular 1.5×, Weekend 2.0×, Holiday 2.5× (editable in Settings)"],
            ["sequence", "Integer", "Display order in lists"],
            ["company_id", "Many2one → res.company", "Company scope (optional)"],
            ["active", "Boolean", "Archive inactive types"],
        ],
        [3.5 * cm, 3.5 * cm, 9 * cm],
    )

    add_h2("5.2 hr.overtime.request — Main Overtime Request")
    add_table(
        ["Column", "Type", "Description"],
        [
            ["name", "Char", "Auto sequence: OT/YYYY/MM/00001"],
            ["employee_id", "Many2one → hr.employee", "Employee who worked overtime (required)"],
            ["department_id", "Many2one → hr.department", "Related from employee, stored"],
            ["manager_id", "Many2one → hr.employee", "Direct manager (employee.parent_id), stored"],
            ["start_datetime", "Datetime", "When overtime started (datetime picker)"],
            ["end_datetime", "Datetime", "When overtime ended (datetime picker)"],
            ["date", "Date", "Computed from start_datetime; used in search filters and pivot"],
            ["overtime_hours", "Float", "Computed duration in hours"],
            ["overtime_type_id", "Many2one → hr.overtime.type", "Rate category (Regular/Weekend/Holiday)"],
            ["project_id", "Many2one → project.project", "Project for timesheet allocation"],
            ["task_id", "Many2one → project.task", "Task within the project"],
            ["description", "Text", "Reason / details for the overtime"],
            ["attachment_ids", "Many2many → ir.attachment", "Supporting documents"],
            ["state", "Selection", "draft → submitted → manager_approved → upper_manager_approved → hr_approved | refused | cancel"],
            ["approval_line_ids", "One2many → hr.overtime.approval.line", "Full approval audit trail"],
            ["current_approver_id", "Many2one → res.users", "Who must act now (for record rules & My Approvals)"],
            ["hourly_cost", "Monetary", "Base hourly rate (0 in core; computed from contract in payroll module)"],
            ["total_cost", "Monetary", "overtime_hours × hourly_cost × rate_multiplier"],
            ["currency_id", "Many2one → res.currency", "Company currency"],
            ["company_id", "Many2one → res.company", "Company"],
            ["analytic_line_id", "Many2one → account.analytic.line", "Timesheet line created on final approval (if enabled)"],
            ["daily_hours_warning", "Char", "Warning if hours exceed company daily cap"],
        ],
        [3.5 * cm, 4 * cm, 8.5 * cm],
    )

    add_h2("5.3 hr.overtime.approval.line — Approval Trail")
    add_table(
        ["Column", "Type", "Description"],
        [
            ["request_id", "Many2one → hr.overtime.request", "Parent request"],
            ["sequence", "Integer", "Order in the chain (10, 20, 30…)"],
            ["role", "Selection", "dept_manager | upper_manager | hr"],
            ["approver_id", "Many2one → res.users", "Assigned approver (HR: any officer in group may act)"],
            ["state", "Selection", "pending → to_approve → approved | refused"],
            ["decision_date", "Datetime", "When the decision was made"],
            ["comment", "Text", "Refusal reason or notes"],
        ],
        [3.5 * cm, 4 * cm, 8.5 * cm],
    )

    add_h2("5.4 Reusable Engine — hr.approval.chain.service (Abstract)")
    add_p("Not stored in DB. Provides chain resolution for any future request type (expenses, permissions, etc.):")
    add_bullet("resolve_chain(employee, chain_builder, hr_group_xmlid) — generic entry point")
    add_bullet("build_manager_hr_chain(employee) — standard dept manager → upper manager → HR")
    add_bullet("get_hr_responsible(employee) — picks HR user from group_overtime_hr_officer")
    add_bullet("_sanitize_chain(chain) — removes duplicates and empty entries")

    add_h2("5.5 hr.approval.chain.mixin (Abstract)")
    add_p("Mixed into hr.overtime.request. Provides workflow methods:")
    add_bullet("action_submit → resolve chain, create approval lines, schedule activity")
    add_bullet("action_approve_current → validate approver, advance state, trigger next activity")
    add_bullet("action_process_refusal → stop chain, set state=refused")
    add_bullet("_on_approval_complete() hook → create analytic line / payslip input")

    add_h2("5.6 res.company Extensions")
    add_table(
        ["Column", "Type", "Description"],
        [
            ["overtime_generate_analytic_line", "Boolean", "Auto-create timesheet on HR approval (default: True)"],
            ["overtime_default_type_id", "Many2one", "Default overtime type for new requests"],
            ["overtime_daily_hours_cap", "Float", "Warning threshold (default: 4 hours)"],
        ],
        [5 * cm, 3 * cm, 8 * cm],
    )

    add_h2("5.7 hr.employee Extensions")
    add_table(
        ["Column", "Type", "Description"],
        [
            ["overtime_request_count", "Integer", "Count of approved overtime requests"],
            ["overtime_hours_ytd", "Float", "Approved overtime hours year-to-date"],
            ["overtime_cost_ytd", "Monetary", "Approved overtime cost year-to-date"],
        ],
        [5 * cm, 3 * cm, 8 * cm],
    )

    story.append(PageBreak())

    add_h1("6. Approval Workflow")
    add_p("<b>Chain resolution</b> (same pattern as hr_holidays):")
    add_bullet("Step 1: employee.parent_id (or department manager if no parent)")
    add_bullet("Step 2: parent of dept manager, if different person")
    add_bullet("Step 3: HR officer (always mandatory final stage)")
    add_p("<b>Two scenarios:</b>")
    add_bullet("<b>2 stages:</b> Dept manager only (no one above) → dept_manager → HR")
    add_bullet("<b>3 stages:</b> Dept manager + upper manager → dept_manager → upper_manager → HR")
    add_p(
        "<b>States after each approval:</b> submitted → manager_approved → "
        "(upper_manager_approved if 3-stage) → hr_approved. "
        "Refusal at any stage immediately sets state=refused."
    )

    add_h1("7. Security Groups &amp; Record Rules")
    add_table(
        ["Group", "Access"],
        [
            ["group_overtime_user", "Create/read own requests; write only while draft"],
            ["group_overtime_hr_officer", "Read all; write at HR-pending stage; final approval"],
            ["group_overtime_admin", "Configure types, settings; full access"],
            ["Managers (no separate group)", "Read/write requests where current_approver_id = current user"],
        ],
        [5 * cm, 11 * cm],
    )

    add_h1("8. Cost Calculation")
    add_p("<b>Formula:</b> total_cost = overtime_hours × hourly_cost × overtime_type.rate_multiplier")
    add_p("<b>Core module:</b> hourly_cost = 0 (no payroll dependency)")
    add_p("<b>hr_overtime_payroll:</b> hourly_cost = contract.wage ÷ company.overtime_hours_per_month (default 173.33)")

    add_h1("9. Configuration (Settings → Employees → Overtime)")
    add_bullet("Generate timesheet on approval")
    add_bullet("Default overtime type")
    add_bullet("Daily hours warning cap")
    add_bullet("Link to payroll (installs hr_overtime_payroll module)")

    add_h1("10. Menus &amp; Views")
    add_bullet("Overtime → My Requests — employee self-service")
    add_bullet("Overtime → My Approvals — kanban for pending approvers")
    add_bullet("Overtime → All Requests — HR officers see everything")
    add_bullet("Overtime → Configuration → Overtime Types — admin only")
    add_bullet("Views: list, form (statusbar + approval tab + chatter), kanban, pivot, graph, PDF report")

    add_h1("11. Upgrade Instructions")
    add_p("After pulling these changes, upgrade the module:")
    add_bullet("Apps → HR Overtime Management → Upgrade")
    add_bullet("Or CLI: python odoo-bin -c debian/odoo.conf -d YOUR_DB -u hr_overtime_management --stop-after-init")
    add_p(
        "Existing records with old float time fields are migrated automatically "
        "via migrations/19.0.1.0.1/post-migrate.py."
    )

    add_h1("12. Assign HR Officers")
    add_p(
        "For Submit to work, at least one user must belong to the "
        "<b>Officer: Overtime HR Approval</b> group (Settings → Users → HR Overtime HR Officer). "
        "Without this, the approval chain cannot resolve the final HR stage."
    )

    doc.build(story)
    print(f"PDF written to: {OUTPUT}")


if __name__ == "__main__":
    build_pdf()
