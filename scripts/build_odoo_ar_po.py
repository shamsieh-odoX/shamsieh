#!/usr/bin/env python3
"""Generate Odoo-compliant Arabic ar.po files (with model/code occurrences)."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from generate_ar_po import EXTRA_BY_MODULE, TRANSLATIONS, should_skip, translate

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    'hr_attendance_custom_ext',
    'hr_holidays_custom_ext',
    'hr_overtime_management',
    'hr_overtime_payroll',
    'project_custom_ext',
]
SKIP_DIRS = {'doc', 'tests', '.venv', '__pycache__', 'migrations', 'i18n'}

PO_HEADER = '''# Translation of Odoo Server.
# Professional Arabic (ar) translations — Odoo-compliant format.
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Server 19.0\\n"
"Report-Msgid-Bugs-To: \\n"
"POT-Creation-Date: {date}\\n"
"PO-Revision-Date: {date}\\n"
"Last-Translator: Shamsieh\\n"
"Language-Team: Arabic\\n"
"Language: ar\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);\\n"
'''

MODEL_REF = {
    'ir.ui.menu': 'name',
    'ir.actions.act_window': 'name',
    'ir.actions.report': 'name',
    'ir.actions.client': 'name',
    'ir.actions.server': 'name',
    'res.groups': 'name',
    'mail.activity.type': 'name',
    'hr.overtime.type': 'name',
    'hr.leave.type': 'name',
    'project.task.template': 'name',
    'project.task.template.line': 'name',
}

RECORD_TEXT_FIELDS = {
    'project.task.template': ('name', 'description'),
}


@dataclass
class Occurrence:
    ref: str
    comment: str = ''

    def po_lines(self) -> list[str]:
        lines = []
        if self.comment:
            lines.append(f'#. {self.comment}')
        lines.append(f'#: {self.ref}')
        return lines


@dataclass
class Entry:
    msgid: str
    occurrences: list[Occurrence] = field(default_factory=list)

    def add(self, occ: Occurrence) -> None:
        if occ.ref not in {o.ref for o in self.occurrences}:
            self.occurrences.append(occ)


def model_to_xmlid(model_name: str) -> str:
    return model_name.replace('.', '_')


def field_xmlid(module: str, model_name: str, field_name: str) -> str:
    return f'model:ir.model.fields,field_description:{module}.field_{model_to_xmlid(model_name)}__{field_name}'


def model_xmlid(module: str, model_name: str, kind: str) -> str:
    return f'model:ir.model,{kind}:{module}.model_{model_to_xmlid(model_name)}'


def selection_xmlid(module: str, model_name: str, field_name: str, value: str) -> str:
    return (
        f'model:ir.model.fields.selection,name:'
        f'{module}.selection__{model_to_xmlid(model_name)}__{field_name}__{value}'
    )


def code_ref(module: str, rel_path: str, lineno: int = 0, js: bool = False) -> Occurrence:
    posix = rel_path.replace('\\', '/')
    if not posix.startswith('addons/'):
        posix = f'addons/{module}/{posix}'
    comment = 'odoo-javascript' if js else 'odoo-python'
    return Occurrence(f'code:{posix}:{lineno}', comment)


def view_terms_ref(module: str, view_xmlid: str) -> str:
    return f'model_terms:ir.ui.view,arch_db:{module}.{view_xmlid}'


def record_ref(model: str, module: str, xmlid: str) -> str:
    prop = MODEL_REF.get(model, 'name')
    return f'model:{model},{prop}:{module}.{xmlid}'


def po_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace('"', '\\"')


def extract_python(module: str, path: Path, get) -> None:
    text = path.read_text(encoding='utf-8', errors='replace')
    rel = str(path.relative_to(ROOT / 'extra_addons' / module))
    models = _detect_models(text)
    if not models:
        return
    for model_name in models:
        desc_m = re.search(r"_description\s*=\s*['\"]([^'\"]+)['\"]", text)
        if desc_m:
            get(desc_m.group(1)).add(Occurrence(model_xmlid(module, model_name, 'name')))
        for field_name, block in _parse_field_blocks(text):
            for sm in re.finditer(r"string\s*=\s*['\"]([^'\"]+)['\"]", block):
                get(sm.group(1)).add(Occurrence(field_xmlid(module, model_name, field_name)))
            for sm in re.finditer(r"help\s*=\s*['\"]([^'\"]+)['\"]", block):
                get(sm.group(1)).add(Occurrence(field_xmlid(module, model_name, field_name)))
            sel_m = re.search(r"selection\s*=\s*\[(.*?)\]\s*,?", block, re.DOTALL)
            if not sel_m:
                sel_m = re.search(r"selection\s*=\s*\[(.*?)\]\s*\)", block, re.DOTALL)
            if sel_m:
                for sm in re.finditer(
                    r"\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
                    sel_m.group(1),
                    re.DOTALL,
                ):
                    value, label = sm.group(1), sm.group(2)
                    get(label).add(Occurrence(selection_xmlid(module, model_name, field_name, value)))
    for m in re.finditer(r"_\(\s*['\"]((?:\\.|[^'\"])+?)['\"]", text):
        get(m.group(1)).add(code_ref(module, rel, js=False))
    for m in re.finditer(
        r"(?:UserError|ValidationError|AccessError)\(_\(\s*['\"]((?:\\.|[^'\"])+?)['\"]",
        text,
    ):
        get(m.group(1)).add(code_ref(module, rel, js=False))


def _detect_models(text: str) -> list[str]:
    name_m = re.search(r"^\s*_name\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    inherit_m = re.search(r"^\s*_inherit\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if name_m:
        return [name_m.group(1)]
    if inherit_m:
        return [inherit_m.group(1)]
    return []


def _parse_field_blocks(text: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for m in re.finditer(r'(\w+)\s*=\s*fields\.\w+\(', text):
        field_name = m.group(1)
        start = m.end() - 1
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    results.append((field_name, text[m.start():i + 1]))
                    break
    return results


def extract_js(module: str, path: Path, get) -> None:
    text = path.read_text(encoding='utf-8', errors='replace')
    rel = str(path.relative_to(ROOT / 'extra_addons' / module))
    for m in re.finditer(r"_t\(\s*['\"]((?:\\.|[^'\"])+?)['\"]", text):
        msgid = m.group(1)
        get(msgid).add(code_ref(module, rel, js=True))
    for m in re.finditer(r"_t\(\s*\n\s*['\"]((?:\\.|[^'\"])+?)['\"]", text):
        msgid = m.group(1)
        get(msgid).add(code_ref(module, rel, js=True))


def extract_xml(module: str, path: Path, get) -> None:
    text = path.read_text(encoding='utf-8', errors='replace')
    current_record_id = None
    current_model = None
    in_field_name = False

    for m in re.finditer(
        r'<record[^>]+id=["\']([^"\']+)["\'][^>]+model=["\']([^"\']+)["\']',
        text,
    ):
        current_record_id = m.group(1)
        current_model = m.group(2)

    for m in re.finditer(r'<menuitem[^>]+id=["\']([^"\']+)["\'][^>]*name=["\']([^"\']+)["\']', text):
        xmlid, name = m.group(1), m.group(2)
        get(name).add(Occurrence(record_ref('ir.ui.menu', module, xmlid)))

    for m in re.finditer(r'<menuitem[^>]+name=["\']([^"\']+)["\'][^>]*id=["\']([^"\']+)["\']', text):
        name, xmlid = m.group(1), m.group(2)
        get(name).add(Occurrence(record_ref('ir.ui.menu', module, xmlid)))

    for record_m in re.finditer(
        r'<record\s+id=["\']([^"\']+)["\']\s+model=["\']([^"\']+)["\'][^>]*>(.*?)</record>',
        text,
        re.DOTALL,
    ):
        rec_id, rec_model, body = record_m.group(1), record_m.group(2), record_m.group(3)
        if rec_model in RECORD_TEXT_FIELDS:
            for field_name in RECORD_TEXT_FIELDS[rec_model]:
                name_m = re.search(
                    rf'<field\s+name=["\']{field_name}["\'][^>]*>([^<]+)</field>',
                    body,
                )
                if name_m:
                    prop = 'name' if field_name == 'name' else field_name
                    get(name_m.group(1).strip()).add(Occurrence(
                        f'model:{rec_model},{prop}:{module}.{rec_id}'
                    ))
        elif rec_model in MODEL_REF:
            name_m = re.search(r'<field\s+name=["\']name["\'][^>]*>([^<]+)</field>', body)
            if name_m:
                get(name_m.group(1).strip()).add(Occurrence(record_ref(rec_model, module, rec_id)))
            name_m = re.search(r'<field\s+name=["\']name["\'][^>]*value=["\']([^"\']+)["\']', body)
            if name_m:
                get(name_m.group(1)).add(Occurrence(record_ref(rec_model, module, rec_id)))
        if rec_model == 'ir.ui.view':
            view_id = rec_id
            for sm in re.finditer(r'\bstring=["\']([^"\']+)["\']', body):
                val = sm.group(1)
                if '%(' not in val and 'eval(' not in val:
                    get(val).add(Occurrence(view_terms_ref(module, view_id)))
            for sm in re.finditer(r"\bstring=['\"]([^'\"]+)['\"]", body):
                val = sm.group(1)
                if '%(' not in val:
                    get(val).add(Occurrence(view_terms_ref(module, view_id)))
            for sm in re.finditer(r'placeholder=["\']([^"\']+)["\']', body):
                get(sm.group(1)).add(Occurrence(view_terms_ref(module, view_id)))
            for sm in re.finditer(r'title=["\']([^"\']+)["\']', body):
                get(sm.group(1)).add(Occurrence(view_terms_ref(module, view_id)))
            for sm in re.finditer(r'<(?:strong|p|em|li|span)[^>]*>([^<]{3,})</', body):
                val = sm.group(1).strip()
                if val and not val.startswith('<'):
                    get(val).add(Occurrence(view_terms_ref(module, view_id)))

    for pattern in (
        r'string="([^"]+)"',
        r"string='([^']+)'",
        r'placeholder="([^"]+)"',
        r"placeholder='([^']+)'",
        r'title="([^"]+)"',
    ):
        for m in re.finditer(pattern, text):
            val = m.group(1).strip()
            if val and '%(' not in val and 'eval(' not in val and val not in {
                'dialogTitle', 'pinPlaceholder', 'instructions', 'cancelLabel',
                'verifyingLabel', 'captureLabel', 'checkingLabel', 'submitLabel',
            }:
                get(val).add(code_ref(module, str(path.relative_to(ROOT / 'extra_addons' / module)), js='static' in str(path)))


def collect_entries(module: str) -> dict[str, Entry]:
    mod_root = ROOT / 'extra_addons' / module
    entries: dict[str, Entry] = {}

    def get_entry(msgid: str) -> Entry:
        if msgid not in entries:
            entries[msgid] = Entry(msgid=msgid)
        return entries[msgid]

    for fp in mod_root.rglob('*'):
        if not fp.is_file() or any(p in SKIP_DIRS for p in fp.parts):
            continue
        if fp.suffix == '.py':
            extract_python(module, fp, get_entry)
        elif fp.suffix == '.js':
            extract_js(module, fp, get_entry)
        elif fp.suffix == '.xml':
            extract_xml(module, fp, get_entry)
    return entries


def write_po(module: str, entries: dict[str, Entry]) -> tuple[Path, int, int]:
    date = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M+0000')
    lines = [PO_HEADER.format(date=date)]
    translated = 0
    skipped = 0
    for msgid in sorted(entries):
        if should_skip(msgid) or not msgid.strip():
            continue
        entry = entries[msgid]
        if not entry.occurrences:
            skipped += 1
            continue
        msgstr = translate(msgid, module)
        if msgstr == msgid and not msgid.startswith('Demo'):
            skipped += 1
        else:
            translated += 1
        lines.append(f'\n#. module: {module}')
        for occ in sorted(entry.occurrences, key=lambda o: o.ref):
            lines.extend(occ.po_lines())
        lines.append(f'msgid "{po_escape(msgid)}"')
        lines.append(f'msgstr "{po_escape(msgstr)}"')
    out = ROOT / 'extra_addons' / module / 'i18n' / 'ar.po'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return out, translated, skipped


def main():
    for module in MODULES:
        entries = collect_entries(module)
        out, translated, skipped = write_po(module, entries)
        print(f'{module}: wrote {out} ({len(entries)} strings, {translated} translated, {skipped} skipped/no-occ)')


if __name__ == '__main__':
    main()
