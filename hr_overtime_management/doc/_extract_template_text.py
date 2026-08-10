import re
import zipfile
from pathlib import Path

path = Path(r"c:\Users\ASUS\Downloads\ملف قالب الشركة (2).docx")
with zipfile.ZipFile(path) as z:
    for fname in ["word/header1.xml", "word/footer1.xml", "word/document.xml"]:
        xml = z.read(fname).decode("utf-8", errors="replace")
        texts = re.findall(r"<w:t[^>]*>([^<]+)</w:t>", xml)
        out = Path(__file__).parent / f"_template_{fname.replace('/','_')}.txt"
        out.write_text("\n".join(t for t in texts if t.strip()), encoding="utf-8")
        print(fname, "->", out.name, "lines:", len(texts))
