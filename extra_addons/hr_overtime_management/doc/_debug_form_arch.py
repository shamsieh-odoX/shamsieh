import re
from pathlib import Path
from lxml import etree

text = Path(__file__).resolve().parent.parent.joinpath(
    'views', 'hr_overtime_request_views.xml'
).read_text(encoding='utf-8')
record_pattern = re.compile(
    r'<record\s+id="([^"]+)"\s+model="ir\.ui\.view">(.*?)</record>',
    re.DOTALL,
)
start_marker = '<field name="arch" type="xml">'
for xmlid, body in record_pattern.findall(text):
    if xmlid != 'hr_overtime_request_view_form':
        continue
    start = body.index(start_marker) + len(start_marker)
    end = body.rindex('</field>')
    arch = body[start:end].strip()
    print('Length:', len(arch))
    print('Lines:', arch.count('\n') + 1)
    print('Last line:', arch.splitlines()[-1])
    try:
        etree.fromstring('<data>' + arch + '</data>')
        print('XML OK')
    except etree.XMLSyntaxError as exc:
        print('XML ERR:', exc)
        for i, line in enumerate(arch.splitlines()[64:80], start=65):
            print(f'{i}: {line}')
