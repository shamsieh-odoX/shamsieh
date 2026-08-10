"""Extract branding/style hints from company Word template."""
import re
import zipfile
from pathlib import Path

path = Path(r"c:\Users\ASUS\Downloads\ملف قالب الشركة (2).docx")
with zipfile.ZipFile(path) as z:
    names = z.namelist()
    print("Archive files (sample):", [n for n in names if any(x in n for x in ("styles", "theme", "header", "footer", "document"))])
    doc = z.read("word/document.xml").decode("utf-8", errors="replace")
    styles_xml = z.read("word/styles.xml").decode("utf-8", errors="replace")
    theme = ""
    if "word/theme/theme1.xml" in names:
        theme = z.read("word/theme/theme1.xml").decode("utf-8", errors="replace")

colors = re.findall(r'srgbClr val="([A-F0-9a-f]{6})"', theme)
fonts = re.findall(r'typeface="([^"]+)"', theme)
texts = re.findall(r"<w:t[^>]*>([^<]+)</w:t>", doc)
style_names = re.findall(r'w:styleId="([^"]+)"', styles_xml)

print("\nTHEME COLORS:", colors)
print("\nTHEME FONTS:", fonts[:10])
print("\nSTYLE IDS:", style_names[:20])
print("\nDOCUMENT TEXT (first 40 fragments):")
for t in texts[:40]:
    if t.strip():
        print(" -", t.strip())
