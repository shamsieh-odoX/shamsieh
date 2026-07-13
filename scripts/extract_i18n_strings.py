#!/usr/bin/env python3
"""Extract translatable strings from custom Odoo modules."""
import json
import re
from pathlib import Path

MODULES = [
    'extra_addons/hr_attendance_custom_ext',
    'extra_addons/hr_holidays_custom_ext',
    'extra_addons/hr_overtime_management',
    'extra_addons/hr_overtime_payroll',
    'extra_addons/project_custom_ext',
]
SKIP = {'doc', 'tests', '.venv', '__pycache__', 'migrations', 'i18n'}


def should_skip(path: Path) -> bool:
    return any(part in SKIP for part in path.parts)


def extract_from_file(fp: Path) -> set[str]:
    found: set[str] = set()
    text = fp.read_text(encoding='utf-8', errors='replace')
    if fp.suffix == '.py':
        for pattern in (
            r"_\(\s*['\"]((?:\\.|[^'\"])+?)['\"]",
            r"string=['\"]([^'\"]+)['\"]",
            r"help=['\"]([^'\"]+)['\"]",
            r"ValidationError\(_\(\s*['\"]((?:\\.|[^'\"])+?)['\"]",
            r"UserError\(_\(\s*['\"]((?:\\.|[^'\"])+?)['\"]",
        ):
            for match in re.finditer(pattern, text):
                found.add(match.group(1))
    elif fp.suffix == '.xml':
        for pattern in (
            r'string="([^"]+)"',
            r"string='([^']+)'",
            r'<field name="name">([^<]+)</field>',
            r'placeholder="([^"]+)"',
            r"placeholder='([^']+)'",
            r'title="([^"]+)"',
        ):
            for match in re.finditer(pattern, text):
                value = match.group(1).strip()
                if value and '%(' not in value and 'eval(' not in value:
                    found.add(value)
        # Skip OWL binding identifiers mistakenly matched as placeholders
        found -= {
            'dialogTitle', 'pinPlaceholder', 'instructions', 'cancelLabel',
            'verifyingLabel', 'captureLabel', 'checkingLabel', 'submitLabel',
        }
    elif fp.suffix == '.js':
        for match in re.finditer(r"_t\(['\"]((?:\\.|[^'\"])+?)['\"]", text):
            found.add(match.group(1))
    return found


def main():
    root = Path(__file__).resolve().parents[1]
    for mod_path in MODULES:
        mod_root = root / mod_path
        mod_name = mod_root.name
        strings: set[str] = set()
        for fp in mod_root.rglob('*'):
            if not fp.is_file() or should_skip(fp):
                continue
            if fp.suffix not in {'.py', '.xml', '.js'}:
                continue
            strings |= extract_from_file(fp)
        out = mod_root / 'i18n' / '_extracted_strings.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(sorted(strings), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        print(f'{mod_name}: {len(strings)} strings')


if __name__ == '__main__':
    main()
