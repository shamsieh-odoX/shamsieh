"""Restore hr.overtime.request views from module XML (fixes truncated arch_db)."""
import json
import re
from pathlib import Path

import psycopg2

MODULE = 'hr_overtime_management'
VIEWS_FILE = Path(__file__).resolve().parent.parent / 'views' / 'hr_overtime_request_views.xml'


def extract_view_archs(xml_text):
    """Return {xmlid: arch_string} from Odoo view XML file."""
    archs = {}
    record_pattern = re.compile(
        r'<record\s+id="([^"]+)"\s+model="ir\.ui\.view">(.*?)</record>',
        re.DOTALL,
    )
    start_marker = '<field name="arch" type="xml">'
    for xmlid, body in record_pattern.findall(xml_text):
        if start_marker not in body:
            continue
        start = body.index(start_marker) + len(start_marker)
        end = body.rindex('</field>')
        archs[xmlid] = body[start:end].strip()
    return archs


def main():
    xml_text = VIEWS_FILE.read_text(encoding='utf-8')
    archs = extract_view_archs(xml_text)
    print(f'Parsed {len(archs)} view arch(s) from {VIEWS_FILE.name}')

    conn = psycopg2.connect(
        host='127.0.0.1', port=5432, user='odoo',
        password='Shamsieh@dev2025', dbname='odoo19',
    )
    conn.autocommit = True
    cur = conn.cursor()

    for xmlid, arch in archs.items():
        cur.execute(
            "SELECT res_id FROM ir_model_data "
            "WHERE module = %s AND name = %s AND model = 'ir.ui.view'",
            (MODULE, xmlid),
        )
        row = cur.fetchone()
        if not row:
            print(f'  SKIP {xmlid}: not in database')
            continue
        view_id = row[0]
        arch_db = json.dumps({'en_US': arch})
        view_type = re.match(r'<(\w+)', arch).group(1)
        cur.execute(
            "UPDATE ir_ui_view SET arch_db = %s::jsonb, type = %s, write_date = NOW() "
            "WHERE id = %s",
            (arch_db, view_type, view_id),
        )
        # Validate XML parses
        from lxml import etree
        try:
            etree.fromstring(f'<data>{arch}</data>')
        except etree.XMLSyntaxError as exc:
            print(f'  ERROR {xmlid}: invalid XML after update: {exc}')
            continue
        print(f'  OK {xmlid} (id={view_id}, type={view_type}, {len(arch)} chars)')

    conn.close()
    print('Done. Hard-refresh browser (Ctrl+F5).')


if __name__ == '__main__':
    main()
